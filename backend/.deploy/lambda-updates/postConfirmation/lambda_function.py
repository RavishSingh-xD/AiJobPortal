"""
Cognito Post Confirmation trigger: creates the Users DynamoDB record and
sets verification custom attributes after signup confirmation.

Handler: lambda_function.lambda_handler (deployed zip) /
         post_confirmation.lambda_handler (repo package layout)

Only handles PostConfirmation_ConfirmSignUp. Forgot-password confirmation
is ignored so it cannot overwrite an existing Users row.
"""

import os
import logging
import datetime

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

COLLEGE_DOMAINS_TABLE = os.environ.get("COLLEGE_DOMAINS_TABLE", "CollegeDomains")
USERS_TABLE = os.environ.get("USERS_TABLE", "Users")
REGION = os.environ.get("AWS_REGION", "ap-south-1")

_dynamodb = boto3.resource("dynamodb", region_name=REGION)
_college_domains_table = _dynamodb.Table(COLLEGE_DOMAINS_TABLE)
_users_table = _dynamodb.Table(USERS_TABLE)
_cognito = boto3.client("cognito-idp", region_name=REGION)


def _extract_domain(email: str) -> str | None:
    if not email or not isinstance(email, str):
        return None
    email = email.strip().lower()
    if "@" not in email:
        return None
    domain = email.split("@")[-1]
    return domain or None


def _lookup_college(domain: str) -> dict | None:
    """Returns the CollegeDomains item if found, else None. Raises on DynamoDB error."""
    try:
        response = _college_domains_table.get_item(Key={"domain": domain})
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB GetItem failed for CollegeDomains lookup: %s", error_code)
        raise
    return response.get("Item")


def _update_cognito_attributes(
    user_pool_id: str,
    username: str,
    verification_type: str,
    verification_status: str,
    college_name: str,
) -> None:
    try:
        _cognito.admin_update_user_attributes(
            UserPoolId=user_pool_id,
            Username=username,
            UserAttributes=[
                {"Name": "custom:verification_type", "Value": verification_type},
                {"Name": "custom:verification_status", "Value": verification_status},
                {"Name": "custom:college_name", "Value": college_name},
            ],
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("AdminUpdateUserAttributes failed: %s", error_code)
        raise


def _create_users_record(
    user_id: str,
    email: str,
    name: str,
    college_name: str,
    verification_type: str,
    verification_status: str,
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    item = {
        "userId": user_id,
        "email": email,
        "name": name or "",
        "role": "student",
        "collegeName": college_name,
        "verificationType": verification_type,
        "verificationStatus": verification_status,
        "createdAt": now,
        "updatedAt": now,
    }
    try:
        # Do not clobber an existing profile if Cognito re-delivers the event.
        _users_table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(userId)",
        )
        logger.info("Created Users record for userId=%s", user_id)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "ConditionalCheckFailedException":
            logger.info("Users record already exists for userId=%s — leaving it unchanged", user_id)
            return
        logger.error("DynamoDB PutItem failed for Users record: %s", error_code)
        raise


def lambda_handler(event, context):
    """
    Cognito Post Confirmation trigger entrypoint.
    Always returns the event on success, per Cognito Lambda trigger contract.
    Raises on Users-write failure so Cognito surfaces the error.
    """
    trigger_source = event.get("triggerSource")
    if trigger_source and trigger_source != "PostConfirmation_ConfirmSignUp":
        logger.info("Ignoring non-signup confirmation triggerSource=%s", trigger_source)
        return event

    user_attrs = event.get("request", {}).get("userAttributes", {}) or {}
    email = (user_attrs.get("email") or "").strip().lower()
    user_id = user_attrs.get("sub")
    name = user_attrs.get("name", "")

    user_pool_id = event.get("userPoolId")
    username = event.get("userName")

    if not user_id or not isinstance(user_id, str):
        logger.error("Post confirmation missing Cognito sub — cannot create Users record")
        raise ValueError("Missing Cognito sub in PostConfirmation event")
    if not email:
        logger.error("Post confirmation missing email for userId=%s", user_id)
        raise ValueError("Missing email in PostConfirmation event")

    domain = _extract_domain(email)

    college_record = None
    if domain is not None:
        college_record = _lookup_college(domain)

    if college_record:
        verification_type = "college_email"
        verification_status = "verified"
        college_name = college_record.get("collegeName", "")
    else:
        verification_type = "manual"
        verification_status = "pending_review"
        college_name = ""

    logger.info(
        "Post confirmation userId=%s: verificationType=%s verificationStatus=%s",
        user_id,
        verification_type,
        verification_status,
    )

    # Users row first. Cognito attribute sync is secondary — if it fails after
    # the write, the account still exists in DynamoDB for profile/verify flows.
    _create_users_record(
        user_id, email, name, college_name, verification_type, verification_status
    )

    try:
        _update_cognito_attributes(
            user_pool_id, username, verification_type, verification_status, college_name
        )
    except ClientError:
        logger.exception(
            "Users record saved but Cognito attribute sync failed for userId=%s",
            user_id,
        )
        # Do not raise — DynamoDB is the source of truth for verificationStatus.

    return event

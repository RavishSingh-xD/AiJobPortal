

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


def _update_cognito_attributes(user_pool_id: str, username: str,
                                verification_type: str, verification_status: str,
                                college_name: str) -> None:
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


def _create_users_record(user_id: str, email: str, name: str, college_name: str,
                          verification_type: str, verification_status: str) -> None:
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
        _users_table.put_item(Item=item)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB PutItem failed for Users record: %s", error_code)
        raise


def lambda_handler(event, context):
    """
    Cognito Post Confirmation trigger entrypoint.
    Always returns the event on success, per Cognito Lambda trigger contract.
    Raises on any failure so Cognito surfaces the error rather than letting
    a user through with no Users record / no custom attributes.
    """
    user_attrs = event.get("request", {}).get("userAttributes", {})
    email = user_attrs.get("email")
    user_id = user_attrs.get("sub")
    name = user_attrs.get("name", "")

    user_pool_id = event.get("userPoolId")
    username = event.get("userName")

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
        "Post confirmation: setting verificationType=%s verificationStatus=%s",
        verification_type, verification_status
    )

    _update_cognito_attributes(
        user_pool_id, username, verification_type, verification_status, college_name
    )

    _create_users_record(
        user_id, email, name, college_name, verification_type, verification_status
    )

    return event
"""
API Gateway-triggered Lambda: admin-only endpoint for reviewing manual
verification submissions (selfie + ID card uploads) and approving or
rejecting them.

Handler: review_verification.lambda_handler

Expected request (API Gateway proxy integration, JSON body):
    {
        "userId": "<cognito sub>",
        "decision": "approved" | "rejected"
    }

Response (200):
    {
        "userId": "<cognito sub>",
        "verificationStatus": "verified" | "rejected"
    }

Scope:
    - Reads: DynamoDB GetItem on Users (to confirm the user exists and to
      look up their email, needed for the Cognito username).
    - Writes: DynamoDB UpdateItem on Users (verificationStatus, updatedAt).
    - Writes: Cognito AdminUpdateUserAttributes for approved and rejected
      decisions so the frontend login flow stays in sync with DynamoDB.
    - Does NOT touch S3 -- this Lambda only handles the decision, not the
      uploaded files themselves.
    - This endpoint is intended to sit behind an admin-only API Gateway
      route (e.g. protected by a Cognito authorizer scoped to an admin
      group) -- this Lambda itself does NOT do authorization checks on
      who is calling it. That's a gap to close before this goes anywhere
      near production; flagged here rather than silently assumed.

Required IAM permissions (reviewVerificationRole -- not yet created):
    dynamodb:GetItem on Users
    dynamodb:UpdateItem on Users
    cognito-idp:AdminUpdateUserAttributes on the User Pool ARN

Environment variables:
    USERS_TABLE     (default: "Users")
    USER_POOL_ID    (required, no default -- must be set explicitly)
    AWS_REGION      (default fallback: "ap-south-1")
"""

import os
import json
import logging
import datetime

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

USERS_TABLE = os.environ.get("USERS_TABLE", "Users")
USER_POOL_ID = os.environ.get("USER_POOL_ID")
REGION = os.environ.get("AWS_REGION", "ap-south-1")

ALLOWED_DECISIONS = {"approved": "verified", "rejected": "rejected"}

_dynamodb = boto3.resource("dynamodb", region_name=REGION)
_users_table = _dynamodb.Table(USERS_TABLE)
_cognito = boto3.client("cognito-idp", region_name=REGION)


def _cors_headers():
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "OPTIONS,POST",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
    }


def _response(status_code: int, body_dict: dict):
    return {
        "statusCode": status_code,
        "headers": _cors_headers(),
        "body": json.dumps(body_dict),
    }


def lambda_handler(event, context):
    if USER_POOL_ID is None:
        logger.error("USER_POOL_ID environment variable is not set")
        return _response(500, {"error": "Server misconfiguration"})

    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _response(400, {"error": "Request body must be valid JSON"})

    user_id = body.get("userId")
    decision = body.get("decision")

    if not user_id or not isinstance(user_id, str):
        return _response(400, {"error": "userId is required"})

    if decision not in ALLOWED_DECISIONS:
        return _response(
            400,
            {"error": f"decision must be one of: {', '.join(sorted(ALLOWED_DECISIONS))}"},
        )

    new_status = ALLOWED_DECISIONS[decision]

    # Look up the user first -- need their email to identify them in Cognito
    # (Cognito's username in this pool is the email, not the sub).
    try:
        get_response = _users_table.get_item(Key={"userId": user_id})
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB GetItem failed for Users lookup: %s", error_code)
        return _response(500, {"error": "Could not look up user"})

    user_item = get_response.get("Item")
    if user_item is None:
        return _response(404, {"error": "User not found"})

    email = user_item.get("email")

    # Keep Cognito in sync for both approval and rejection so login/route
    # guards can block rejected users until they re-verify.
    if email:
        try:
            _cognito.admin_update_user_attributes(
                UserPoolId=USER_POOL_ID,
                Username=email,
                UserAttributes=[
                    {"Name": "custom:verification_status", "Value": new_status},
                ],
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error("AdminUpdateUserAttributes failed: %s", error_code)
            return _response(500, {"error": "Could not update Cognito attributes"})

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        _users_table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET verificationStatus = :status, updatedAt = :now",
            ExpressionAttributeValues={
                ":status": new_status,
                ":now": now,
            },
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB UpdateItem failed for Users record: %s", error_code)
        return _response(500, {"error": "Could not update user record"})

    logger.info("Reviewed userId=%s decision=%s newStatus=%s", user_id, decision, new_status)

    return _response(200, {"userId": user_id, "verificationStatus": new_status})
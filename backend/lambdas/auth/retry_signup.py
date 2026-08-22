"""
API Gateway Lambda: clears UNCONFIRMED Cognito users so signup can be retried.

Handler: retry_signup.lambda_handler

POST /auth/retry-signup
Body: { "email": "student@college.edu" }

Response (200):
    { "action": "deleted" }      — unconfirmed user removed; client may SignUp again
    { "action": "confirmed" }    — verified account exists; client should log in
    { "action": "not_found" }    — no Cognito user; client may SignUp

Environment variables:
    USER_POOL_ID
    AWS_REGION (default ap-south-1)
"""

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "ap-south-1")
USER_POOL_ID = os.environ.get("USER_POOL_ID", "")

_cognito = boto3.client("cognito-idp", region_name=REGION)


def _cors_headers():
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "OPTIONS,POST",
    }


def _response(status_code: int, body: dict):
    return {
        "statusCode": status_code,
        "headers": _cors_headers(),
        "body": json.dumps(body),
    }


def _normalize_email(raw: str) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    email = raw.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        return None
    return email


def _clear_unconfirmed_user(email: str) -> str:
    if not USER_POOL_ID:
        logger.error("USER_POOL_ID is not configured")
        raise RuntimeError("signup_recovery_unavailable")

    try:
        user = _cognito.admin_get_user(UserPoolId=USER_POOL_ID, Username=email)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "Unknown")
        if code == "UserNotFoundException":
            return "not_found"
        logger.error("admin_get_user failed for %s: %s", email, code)
        raise

    status = str(user.get("UserStatus") or "").upper()
    if status == "CONFIRMED":
        return "confirmed"
    if status == "UNCONFIRMED":
        _cognito.admin_delete_user(UserPoolId=USER_POOL_ID, Username=email)
        logger.info("Deleted unconfirmed Cognito user for retry signup: %s", email)
        return "deleted"

    # FORCE_CHANGE_PASSWORD, RESET_REQUIRED, etc. — treat as existing account
    return "confirmed"


def lambda_handler(event, context):
    method = (
        (event.get("requestContext") or {}).get("http", {}).get("method")
        or event.get("httpMethod")
        or "POST"
    ).upper()

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": _cors_headers(), "body": ""}

    if method != "POST":
        return _response(405, {"error": "Method not allowed"})

    try:
        body = event.get("body") or "{}"
        payload = json.loads(body) if isinstance(body, str) else body
    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON body"})

    email = _normalize_email(payload.get("email"))
    if not email:
        return _response(400, {"error": "A valid email is required"})

    try:
        action = _clear_unconfirmed_user(email)
    except RuntimeError:
        return _response(503, {"error": "Signup recovery is not available right now"})
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("retry_signup failed for %s: %s", email, code)
        return _response(500, {"error": "Could not process signup recovery"})

    return _response(200, {"action": action})

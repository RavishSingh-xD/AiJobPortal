"""
API Gateway-triggered Lambda: generates a pre-signed S3 PUT URL for the
manual verification flow (selfie + ID card uploads).

Handler: generate_upload_url.lambda_handler

Expected request (API Gateway proxy integration, JSON body):
    {
        "fileType": "selfie" | "id_card"
    }

The authenticated user's Cognito sub is taken from the API Gateway JWT
authorizer claims (requestContext.authorizer.jwt.claims.sub). Any userId
in the request body is ignored.

Response (200):
    {
        "uploadUrl": "https://...",   -- pre-signed PUT URL, expires in 5 min
        "key": "verification/<userId>/<fileType>.jpg"
    }

Scope:
    - Only generates PUT URLs. Does not read/list/delete anything in S3.
    - Writes under the "verification/" prefix only.
    - When the user's verificationStatus is "rejected", resets status to
      pending_review in Users + Cognito so a new upload can be processed.

Required IAM permissions (generateUploadUrlRole):
    s3:PutObject on arn:aws:s3:::<VERIFICATION_BUCKET>/verification/*
    dynamodb:GetItem, dynamodb:UpdateItem on Users
    cognito-idp:AdminUpdateUserAttributes on the User Pool ARN

Environment variables:
    VERIFICATION_BUCKET   (required)
    USERS_TABLE           (default: "Users")
    USER_POOL_ID          (required for status reset on re-upload)
    AWS_REGION            (default fallback: "ap-south-1")
    URL_EXPIRY_SECONDS    (default: 300)
"""

import os
import json
import logging
import datetime

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

VERIFICATION_BUCKET = os.environ.get("VERIFICATION_BUCKET")
USERS_TABLE = os.environ.get("USERS_TABLE", "Users")
USER_POOL_ID = os.environ.get("USER_POOL_ID")
REGION = os.environ.get("AWS_REGION", "ap-south-1")
URL_EXPIRY_SECONDS = int(os.environ.get("URL_EXPIRY_SECONDS", "300"))

ALLOWED_FILE_TYPES = {"selfie", "id_card"}

_s3 = boto3.client("s3", region_name=REGION)
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


def _get_authenticated_user_id(event):
    try:
        user_id = (
            event.get("requestContext", {})
            .get("authorizer", {})
            .get("jwt", {})
            .get("claims", {})
            .get("sub")
        )
    except (AttributeError, TypeError):
        return None

    if not user_id or not isinstance(user_id, str):
        return None

    return user_id


def _reset_rejected_verification(user_id: str):
    """Allow re-upload after OCR/face rejection by moving back to pending_review."""
    try:
        get_response = _users_table.get_item(Key={"userId": user_id})
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.warning("Could not read Users record for reset userId=%s: %s", user_id, error_code)
        return

    user_item = get_response.get("Item") or {}
    if user_item.get("verificationStatus") != "rejected":
        return

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        _users_table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET verificationStatus = :status, updatedAt = :now",
            ExpressionAttributeValues={
                ":status": "pending_review",
                ":now": now,
            },
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.warning("Could not reset Users verificationStatus userId=%s: %s", user_id, error_code)
        return

    email = user_item.get("email")
    if not USER_POOL_ID or not email or not isinstance(email, str):
        logger.warning("Skipping Cognito reset for userId=%s (missing pool or email)", user_id)
        return

    try:
        _cognito.admin_update_user_attributes(
            UserPoolId=USER_POOL_ID,
            Username=email,
            UserAttributes=[{"Name": "custom:verification_status", "Value": "pending_review"}],
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.warning("Could not reset Cognito verification_status userId=%s: %s", user_id, error_code)


def lambda_handler(event, context):
    if VERIFICATION_BUCKET is None:
        logger.error("VERIFICATION_BUCKET environment variable is not set")
        return _response(500, {"error": "Server misconfiguration"})

    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _response(400, {"error": "Request body must be valid JSON"})

    file_type = body.get("fileType")

    if file_type not in ALLOWED_FILE_TYPES:
        return _response(
            400,
            {"error": f"fileType must be one of: {', '.join(sorted(ALLOWED_FILE_TYPES))}"},
        )

    user_id = _get_authenticated_user_id(event)
    if user_id is None:
        return _response(401, {"error": "Unauthorized"})

    _reset_rejected_verification(user_id)

    key = f"verification/{user_id}/{file_type}.jpg"

    try:
        upload_url = _s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": VERIFICATION_BUCKET,
                "Key": key,
                "ContentType": "image/jpeg",
            },
            ExpiresIn=URL_EXPIRY_SECONDS,
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("Failed to generate pre-signed URL: %s", error_code)
        return _response(500, {"error": "Could not generate upload URL"})

    logger.info("Generated upload URL for key=%s (expires in %ss)", key, URL_EXPIRY_SECONDS)

    return _response(200, {"uploadUrl": upload_url, "key": key})
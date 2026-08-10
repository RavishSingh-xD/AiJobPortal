"""
API Gateway-triggered Lambda: generates a pre-signed S3 PUT URL for the
manual verification flow (selfie + ID card uploads).

Handler: generate_upload_url.lambda_handler

Expected request (API Gateway proxy integration, JSON body):
    {
        "userId": "<cognito sub>",
        "fileType": "selfie" | "id_card"
    }

Response (200):
    {
        "uploadUrl": "https://...",   -- pre-signed PUT URL, expires in 5 min
        "key": "verification/<userId>/<fileType>.jpg"
    }

Scope:
    - Only generates PUT URLs. Does not read/list/delete anything in S3.
    - Only writes under the "verification/" prefix -- matches the IAM
      policy scoping (generateUploadUrlRole can only PutObject on
      verification/* in the bucket).
    - Does not touch DynamoDB or Cognito at all.

Required IAM permission (generateUploadUrlRole):
    s3:PutObject on arn:aws:s3:::<VERIFICATION_BUCKET>/verification/*

Environment variables:
    VERIFICATION_BUCKET   (required, no default -- must be set explicitly)
    AWS_REGION            (default fallback: "ap-south-1")
    URL_EXPIRY_SECONDS     (default: 300 -- 5 minutes)
"""

import os
import json
import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

VERIFICATION_BUCKET = os.environ.get("VERIFICATION_BUCKET")
REGION = os.environ.get("AWS_REGION", "ap-south-1")
URL_EXPIRY_SECONDS = int(os.environ.get("URL_EXPIRY_SECONDS", "300"))

ALLOWED_FILE_TYPES = {"selfie", "id_card"}

_s3 = boto3.client("s3", region_name=REGION)


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
    if VERIFICATION_BUCKET is None:
        logger.error("VERIFICATION_BUCKET environment variable is not set")
        return _response(500, {"error": "Server misconfiguration"})

    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _response(400, {"error": "Request body must be valid JSON"})

    user_id = body.get("userId")
    file_type = body.get("fileType")

    if not user_id or not isinstance(user_id, str):
        return _response(400, {"error": "userId is required"})

    if file_type not in ALLOWED_FILE_TYPES:
        return _response(
            400,
            {"error": f"fileType must be one of: {', '.join(sorted(ALLOWED_FILE_TYPES))}"},
        )

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
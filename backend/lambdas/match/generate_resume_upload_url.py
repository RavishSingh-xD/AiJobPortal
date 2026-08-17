"""
API Gateway-triggered Lambda: stores match profile URLs on a session and
returns a pre-signed S3 PUT URL for the resume file.

Handler: generate_resume_upload_url.lambda_handler

Expected request (API Gateway HTTP API, JWT authorizer):
    POST /match/{sessionId}/resume-upload-url
    {
        "linkedinUrl": "https://linkedin.com/in/...",
        "githubHandle": "<optional>",
        "leetcodeHandle": "<optional>"
    }

The authenticated user's Cognito sub is taken from the API Gateway JWT
authorizer claims (requestContext.authorizer.jwt.claims.sub). Any userId
in the request body is ignored.

Response (200):
    {
        "uploadUrl": "https://...",
        "resumeS3Key": "resumes/<userId>/<sessionId>/resume"
    }

Scope:
    - Reads: DynamoDB GetItem on match_sessions.
    - Writes: DynamoDB UpdateItem on match_sessions (linkedinUrl,
      optional githubHandle / leetcodeHandle).
    - Generates S3 PUT pre-signed URLs under resumes/ only.

Required IAM permissions (generateResumeUploadUrlRole -- create when deploying):
    dynamodb:GetItem, dynamodb:UpdateItem on match_sessions
    s3:PutObject on arn:aws:s3:::aijobportal-verification-470361396576/resumes/*

Environment variables:
    MATCH_SESSIONS_TABLE  (default: "match_sessions")
    VERIFICATION_BUCKET   (default: "aijobportal-verification-470361396576")
    AWS_REGION            (default fallback: "ap-south-1")
    URL_EXPIRY_SECONDS    (default: 300 -- 5 minutes)
"""

import os
import json
import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MATCH_SESSIONS_TABLE = os.environ.get("MATCH_SESSIONS_TABLE", "match_sessions")
VERIFICATION_BUCKET = os.environ.get(
    "VERIFICATION_BUCKET", "aijobportal-verification-470361396576"
)
REGION = os.environ.get("AWS_REGION", "ap-south-1")
URL_EXPIRY_SECONDS = int(os.environ.get("URL_EXPIRY_SECONDS", "300"))

FORBIDDEN_MESSAGE = "Forbidden"

_dynamodb = boto3.resource("dynamodb", region_name=REGION)
_sessions_table = _dynamodb.Table(MATCH_SESSIONS_TABLE)
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


def _is_http_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def lambda_handler(event, context):
    user_id = _get_authenticated_user_id(event)
    if user_id is None:
        return _response(401, {"error": "Unauthorized"})

    path_params = event.get("pathParameters") or {}
    session_id = path_params.get("sessionId")
    if not session_id or not isinstance(session_id, str):
        return _response(400, {"error": "sessionId is required"})

    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _response(400, {"error": "Request body must be valid JSON"})

    linkedin_url = body.get("linkedinUrl")
    if not linkedin_url or not isinstance(linkedin_url, str) or not linkedin_url.strip():
        return _response(400, {"error": "linkedinUrl is required"})

    linkedin_url = linkedin_url.strip()
    if not _is_http_url(linkedin_url):
        return _response(400, {"error": "linkedinUrl must start with http:// or https://"})

    github_handle = body.get("githubHandle")
    leetcode_handle = body.get("leetcodeHandle")
    if github_handle is not None and not isinstance(github_handle, str):
        github_handle = None
    if leetcode_handle is not None and not isinstance(leetcode_handle, str):
        leetcode_handle = None
    github_handle = github_handle.strip() if github_handle else None
    leetcode_handle = leetcode_handle.strip() if leetcode_handle else None

    try:
        get_response = _sessions_table.get_item(Key={"sessionId": session_id})
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB GetItem failed for match_sessions: %s", error_code)
        return _response(500, {"error": "Could not look up match session"})

    session_item = get_response.get("Item")
    if session_item is None:
        return _response(403, {"error": FORBIDDEN_MESSAGE})

    if session_item.get("userId") != user_id:
        return _response(403, {"error": FORBIDDEN_MESSAGE})

    set_parts = ["linkedinUrl = :linkedin"]
    expr_values = {":linkedin": linkedin_url}
    if github_handle:
        set_parts.append("githubHandle = :github")
        expr_values[":github"] = github_handle
    if leetcode_handle:
        set_parts.append("leetcodeHandle = :leetcode")
        expr_values[":leetcode"] = leetcode_handle

    try:
        _sessions_table.update_item(
            Key={"sessionId": session_id},
            UpdateExpression="SET " + ", ".join(set_parts),
            ExpressionAttributeValues=expr_values,
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB UpdateItem failed for match_sessions: %s", error_code)
        return _response(500, {"error": "Could not update match session"})

    resume_key = f"resumes/{user_id}/{session_id}/resume"

    try:
        upload_url = _s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": VERIFICATION_BUCKET,
                "Key": resume_key,
            },
            ExpiresIn=URL_EXPIRY_SECONDS,
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("Failed to generate resume pre-signed URL: %s", error_code)
        return _response(500, {"error": "Could not generate upload URL"})

    logger.info(
        "Generated resume upload URL sessionId=%s userId=%s key=%s",
        session_id,
        user_id,
        resume_key,
    )

    return _response(200, {"uploadUrl": upload_url, "resumeS3Key": resume_key})

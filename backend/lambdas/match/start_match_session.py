"""
API Gateway-triggered Lambda: starts a new AI matching session.

Handler: start_match_session.lambda_handler

Expected request (API Gateway HTTP API, JWT authorizer):
    POST /match/start
    Body is optional and ignored. userId is never taken from the client.

The authenticated user's Cognito sub is taken from the API Gateway JWT
authorizer claims (requestContext.authorizer.jwt.claims.sub).

Response (200):
    {
        "sessionId": "<uuid>"
    }

Scope:
    - Writes: DynamoDB PutItem on match_sessions (sessionId, userId,
      status=in_progress, createdAt).
    - Does NOT touch S3, Cognito, or jobs tables.

Required IAM permissions (startMatchSessionRole -- create when deploying):
    dynamodb:PutItem on match_sessions

Environment variables:
    MATCH_SESSIONS_TABLE  (default: "match_sessions")
    AWS_REGION            (default fallback: "ap-south-1")
"""

import os
import json
import uuid
import logging
import datetime

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MATCH_SESSIONS_TABLE = os.environ.get("MATCH_SESSIONS_TABLE", "match_sessions")
REGION = os.environ.get("AWS_REGION", "ap-south-1")

_dynamodb = boto3.resource("dynamodb", region_name=REGION)
_sessions_table = _dynamodb.Table(MATCH_SESSIONS_TABLE)


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


def lambda_handler(event, context):
    user_id = _get_authenticated_user_id(event)
    if user_id is None:
        return _response(401, {"error": "Unauthorized"})

    session_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        _sessions_table.put_item(
            Item={
                "sessionId": session_id,
                "userId": user_id,
                "status": "in_progress",
                "createdAt": now,
            }
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB PutItem failed for match_sessions: %s", error_code)
        return _response(500, {"error": "Could not start match session"})

    logger.info("Started match session sessionId=%s userId=%s", session_id, user_id)

    return _response(200, {"sessionId": session_id})

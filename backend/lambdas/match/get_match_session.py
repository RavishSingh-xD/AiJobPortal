"""
API Gateway-triggered Lambda: returns the caller's match session.

Handler: get_match_session.lambda_handler

Expected request (API Gateway HTTP API, JWT authorizer):
    GET /match/{sessionId}

The authenticated user's Cognito sub is taken from the API Gateway JWT
authorizer claims (requestContext.authorizer.jwt.claims.sub).

Response (200): the session fields that are present, excluding userId.

Required IAM permissions (getMatchSessionRole -- create when deploying):
    dynamodb:GetItem on match_sessions

Environment variables:
    MATCH_SESSIONS_TABLE  (default: "match_sessions")
    AWS_REGION            (default fallback: "ap-south-1")
"""

import os
import json
import logging
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MATCH_SESSIONS_TABLE = os.environ.get("MATCH_SESSIONS_TABLE", "match_sessions")
REGION = os.environ.get("AWS_REGION", "ap-south-1")

FORBIDDEN_MESSAGE = "Forbidden"

RESPONSE_FIELDS = (
    "sessionId",
    "status",
    "createdAt",
    "linkedinUrl",
    "githubHandle",
    "leetcodeHandle",
    "powScore",
    "powBreakdown",
    "errorMessage",
)

_dynamodb = boto3.resource("dynamodb", region_name=REGION)
_sessions_table = _dynamodb.Table(MATCH_SESSIONS_TABLE)


def _cors_headers():
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "OPTIONS,GET",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
    }


def _json_default(obj):
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _response(status_code: int, body_dict: dict):
    return {
        "statusCode": status_code,
        "headers": _cors_headers(),
        "body": json.dumps(body_dict, default=_json_default),
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


def _public_session(item: dict) -> dict:
    return {field: item[field] for field in RESPONSE_FIELDS if field in item}


def lambda_handler(event, context):
    user_id = _get_authenticated_user_id(event)
    if user_id is None:
        return _response(401, {"error": "Unauthorized"})

    path_params = event.get("pathParameters") or {}
    session_id = path_params.get("sessionId")
    if not session_id or not isinstance(session_id, str):
        return _response(400, {"error": "sessionId is required"})

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

    logger.info("Fetched match session sessionId=%s userId=%s", session_id, user_id)

    return _response(200, _public_session(session_item))

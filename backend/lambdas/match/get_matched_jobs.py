"""
API Gateway-triggered Lambda: returns internship and job listings the
caller qualifies for after completing a domain test, plus discovery extras:
almost-there roles and a structured skill gap report.

Handler: get_matched_jobs.lambda_handler

Expected request (API Gateway HTTP API, JWT authorizer):
    GET /match/{sessionId}/matches

Response (200):
    {
        "internships": [...],
        "jobs": [...],
        "almostThere": { "internships": [...], "jobs": [...] },
        "skillGapReport": {
            "strongSkills": [...],
            "weakSkills": [...],
            "missingSkills": [...],
            "summary": "..."
        },
        "powScore": <number>,
        "domain": "Engineering",
        "skill": "Python"
    }
"""

import json
import logging
import os
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

try:
    from lambdas.match import listing_utils as lu
except ImportError:
    import listing_utils as lu

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MATCH_SESSIONS_TABLE = os.environ.get("MATCH_SESSIONS_TABLE", "match_sessions")
REGION = os.environ.get("AWS_REGION", "ap-south-1")

FORBIDDEN_MESSAGE = "Forbidden"
STATUS_REQUIRED = "test_completed"
CONFLICT_MESSAGE = "Complete the domain test before viewing matches."

GROUP_CAP = 20
ALMOST_CAP = 10

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


def _scan_jobs(table_name: str):
    table = _dynamodb.Table(table_name)
    return table.scan(Limit=lu.SCAN_LIMIT)


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

    if session_item.get("status") != STATUS_REQUIRED:
        return _response(409, {"error": CONFLICT_MESSAGE})

    domain = session_item.get("domain")
    skill = session_item.get("skill")
    pow_score = lu.as_number(session_item.get("powScore"), default=None)
    table_name = lu.DOMAIN_TABLE_MAP.get(domain) if isinstance(domain, str) else None
    if not table_name or skill is None or pow_score is None:
        return _response(409, {"error": CONFLICT_MESSAGE})

    try:
        scan_response = _scan_jobs(table_name)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB Scan failed for table=%s: %s", table_name, error_code)
        return _response(500, {"error": "Could not load matched jobs"})

    items = scan_response.get("Items") or []
    partitioned = lu.partition_matches(
        items,
        skill,
        domain,
        pow_score,
        group_cap=GROUP_CAP,
        almost_cap=ALMOST_CAP,
    )
    skill_gap_report = lu.build_skill_gap_report(
        partitioned["matched_flat"],
        partitioned["almost_flat"],
        skill,
        domain,
    )

    logger.info(
        "Matched jobs sessionId=%s internships=%s jobs=%s almost=%s",
        session_id,
        len(partitioned["internships"]),
        len(partitioned["jobs"]),
        len(partitioned["almost_flat"]),
    )
    return _response(
        200,
        {
            "internships": partitioned["internships"],
            "jobs": partitioned["jobs"],
            "almostThere": partitioned["almostThere"],
            "skillGapReport": skill_gap_report,
            "powScore": session_item.get("powScore"),
            "domain": domain,
            "skill": skill,
        },
    )

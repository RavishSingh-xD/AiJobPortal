"""
API Gateway-triggered Lambda: returns internship and job listings the
caller qualifies for after completing a domain test.

Handler: get_matched_jobs.lambda_handler

Expected request (API Gateway HTTP API, JWT authorizer):
    GET /match/{sessionId}/matches

Response (200):
    {
        "internships": [...],
        "jobs": [...],
        "powScore": <number>,
        "domain": "Engineering",
        "skill": "Python"
    }

Listing filter:
    - Skill match copies list_jobs._skill_matches (case-insensitive
      substring against required_skills).
    - Active listings copy start_domain_test._is_open_listing
      (list_jobs.py surfaces status/display_status but does not drop
      inactive rows when listing; the only in-repo active rule is
      start_domain_test's closed/expired/inactive check).
    - min_pow_score <= session powScore (this endpoint's extra filter).

Required IAM permissions (getMatchedJobsRole -- create when deploying):
    dynamodb:GetItem on match_sessions
    dynamodb:Scan on jobs_engineering, jobs_business, jobs_healthcare,
      jobs_design

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
STATUS_REQUIRED = "test_completed"
CONFLICT_MESSAGE = "Complete the domain test before viewing matches."

# Same table names as start_domain_test.DOMAIN_TABLE_MAP / list_jobs.DOMAIN_TABLE_MAP.
DOMAIN_TABLE_MAP = {
    "Engineering": "jobs_engineering",
    "Business": "jobs_business",
    "Healthcare": "jobs_healthcare",
    "Design": "jobs_design",
}

# Canonical employment_type values from list_jobs.py's filter UI.
EMPLOYMENT_INTERNSHIP = "Internship"
EMPLOYMENT_JOB = "Job"

# Copied from start_domain_test.py -- list_jobs.py does not filter these.
CLOSED_STATUSES = {"closed", "expired", "inactive"}

# Known limitation: one bounded Scan (not full-table pagination), then cap
# each result group. Same class of simplification as harvest_status.
SCAN_LIMIT = 100
GROUP_CAP = 20

LISTING_FIELDS = (
    "canonical_id",
    "title",
    "company",
    "location",
    "apply_url",
    "min_pow_score",
    "is_fallback",
    "employment_type",
    "required_skills",
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


def _as_number(value, default=0):
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_open_listing(item: dict) -> bool:
    """Mirror start_domain_test._is_open_listing exactly."""
    status = item.get("status") or item.get("display_status") or ""
    return str(status).strip().lower() not in CLOSED_STATUSES


def _skill_matches(required_skills, skill_query: str) -> bool:
    """Mirror list_jobs._skill_matches (case-insensitive substring)."""
    if not skill_query:
        return True
    if isinstance(required_skills, str):
        required_skills = [required_skills]
    if not required_skills:
        return False
    needle = skill_query.strip().lower()
    if not needle:
        return True
    for skill in required_skills:
        if skill is None:
            continue
        if needle in str(skill).lower():
            return True
    return False


def _employment_type_key(employment_type):
    if not employment_type:
        return None
    needle = str(employment_type).strip().lower()
    if needle == EMPLOYMENT_INTERNSHIP.lower():
        return "internships"
    if needle == EMPLOYMENT_JOB.lower():
        return "jobs"
    return None


def _public_listing(item: dict) -> dict:
    listing = {}
    for field in LISTING_FIELDS:
        if field in item:
            listing[field] = item[field]
    return listing


def _scan_jobs(table_name: str):
    table = _dynamodb.Table(table_name)
    return table.scan(Limit=SCAN_LIMIT)


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
    pow_score = _as_number(session_item.get("powScore"), default=None)
    table_name = DOMAIN_TABLE_MAP.get(domain) if isinstance(domain, str) else None
    if not table_name or skill is None or pow_score is None:
        return _response(409, {"error": CONFLICT_MESSAGE})

    try:
        scan_response = _scan_jobs(table_name)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB Scan failed for table=%s: %s", table_name, error_code)
        return _response(500, {"error": "Could not load matched jobs"})

    internships = []
    jobs = []
    for item in scan_response.get("Items") or []:
        if not isinstance(item, dict):
            continue
        if not _is_open_listing(item):
            continue
        if not _skill_matches(item.get("required_skills"), skill):
            continue
        min_pow = _as_number(item.get("min_pow_score"), default=0)
        if min_pow > pow_score:
            continue
        group = _employment_type_key(item.get("employment_type"))
        if group is None:
            continue
        listing = _public_listing(item)
        if group == "internships":
            internships.append(listing)
        else:
            jobs.append(listing)

    # Default ranking for this step only: highest min_pow_score first
    # (closest still-qualifying bar). Step 4's recommendation may rank
    # differently; the project spec does not mandate order here.
    internships.sort(key=lambda row: _as_number(row.get("min_pow_score"), 0), reverse=True)
    jobs.sort(key=lambda row: _as_number(row.get("min_pow_score"), 0), reverse=True)

    internships = internships[:GROUP_CAP]
    jobs = jobs[:GROUP_CAP]

    logger.info(
        "Matched jobs sessionId=%s internships=%s jobs=%s",
        session_id,
        len(internships),
        len(jobs),
    )
    return _response(
        200,
        {
            "internships": internships,
            "jobs": jobs,
            "powScore": session_item.get("powScore"),
            "domain": domain,
            "skill": skill,
        },
    )

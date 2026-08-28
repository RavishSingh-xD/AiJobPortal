"""
compare_jobs.py -- Side-by-side comparison for up to four job listings.

Handler: compare_jobs.handler

POST /jobs/compare
{
    "domain": "Engineering",
    "canonicalIds": ["id-1", "id-2"],
    "sessionId": "<optional match session for scores>"
}
"""

import json
import logging
import os

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
MAX_COMPARE = 4

VALID_DOMAINS = {"Engineering", "Business", "Healthcare"}
_DOMAIN_BY_LOWER = {domain.lower(): domain for domain in VALID_DOMAINS}
DOMAIN_TABLE_MAP = {
    "Engineering": "jobs_engineering",
    "Business": "jobs_business",
    "Healthcare": "jobs_healthcare",
}

_dynamodb = boto3.resource("dynamodb", region_name=REGION)
_sessions_table = _dynamodb.Table(MATCH_SESSIONS_TABLE)


def _get_user_id(event: dict) -> str:
    try:
        sub = event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
    except (KeyError, TypeError):
        raise ValueError("Missing or invalid JWT claims in request context")
    if not sub or not isinstance(sub, str):
        raise ValueError("Missing or invalid JWT claims in request context")
    return sub


def _response(status_code: int, body) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
        },
        "body": json.dumps(body, default=str),
    }


def _normalize_domain(value):
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    return _DOMAIN_BY_LOWER.get(stripped.lower(), stripped)


def _load_session_scores(user_id: str, session_id: str):
    try:
        response = _sessions_table.get_item(Key={"sessionId": session_id})
    except ClientError:
        return None

    item = response.get("Item")
    if not item or item.get("userId") != user_id:
        return None

    pow_score = lu.as_number(item.get("powScore"), default=None)
    score_percent = lu.as_number(item.get("scorePercent"), default=None)
    skill = item.get("skill")
    domain = item.get("domain")
    if pow_score is None or score_percent is None or not skill or not domain:
        return None

    return {
        "powScore": pow_score,
        "scorePercent": score_percent,
        "skill": skill,
        "domain": domain,
    }


def _find_listings(domain: str, canonical_ids: list[str]) -> dict[str, dict]:
    table_name = DOMAIN_TABLE_MAP.get(domain)
    if not table_name:
        return {}

    wanted = set(canonical_ids)
    found = {}
    table = _dynamodb.Table(table_name)
    start_key = None
    try:
        for _ in range(lu.MAX_SCAN_PAGES):
            scan_kwargs = {"Limit": lu.SCAN_PAGE_SIZE}
            if start_key:
                scan_kwargs["ExclusiveStartKey"] = start_key
            response = table.scan(**scan_kwargs)
            for item in response.get("Items") or []:
                if not isinstance(item, dict):
                    continue
                canonical_id = item.get("canonical_id")
                if canonical_id in wanted:
                    found[canonical_id] = item
            if len(found) >= len(wanted):
                break
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
    except ClientError as e:
        logger.error("Scan failed for compare domain=%s: %s", domain, e)
        return {}

    return found


def _pow_bar(pow_score: float, min_pow: float) -> dict:
    return {
        "yourPowScore": pow_score,
        "requiredPowScore": min_pow,
        "meetsRequirement": min_pow <= pow_score,
        "gap": max(0.0, round(min_pow - pow_score, 2)),
    }


def handler(event, context):
    try:
        user_id = _get_user_id(event)
    except ValueError as e:
        return _response(401, {"error": str(e)})

    http_method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
    )
    if http_method != "POST":
        return _response(405, {"error": f"Unsupported method: {http_method}"})

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON body"})

    domain = _normalize_domain(body.get("domain"))
    canonical_ids = body.get("canonicalIds")
    session_id = body.get("sessionId")

    if domain not in VALID_DOMAINS:
        return _response(400, {"error": f"domain must be one of {sorted(VALID_DOMAINS)}"})
    if not isinstance(canonical_ids, list) or not canonical_ids:
        return _response(400, {"error": "canonicalIds must be a non-empty array"})
    if len(canonical_ids) > MAX_COMPARE:
        return _response(400, {"error": f"Compare up to {MAX_COMPARE} roles at once"})

    cleaned_ids = []
    for canonical_id in canonical_ids:
        if isinstance(canonical_id, str) and canonical_id.strip():
            cleaned_ids.append(canonical_id.strip())
    if not cleaned_ids:
        return _response(400, {"error": "canonicalIds must contain valid ids"})

    session_ctx = None
    if session_id and isinstance(session_id, str):
        session_ctx = _load_session_scores(user_id, session_id)

    found = _find_listings(domain, cleaned_ids)
    jobs = []
    for canonical_id in cleaned_ids:
        item = found.get(canonical_id)
        if not item:
            continue
        listing = lu.public_listing(item)
        listing["domain"] = domain
        listing["companySize"] = item.get("company_size") or item.get("companySize") or ""
        min_pow = lu.as_number(listing.get("min_pow_score"), default=0)
        if session_ctx:
            overlap = lu.skill_overlap(
                listing.get("required_skills"),
                session_ctx["skill"],
                session_ctx["domain"],
            )
            listing["skillOverlap"] = round(overlap, 4)
            listing["powBar"] = _pow_bar(session_ctx["powScore"], min_pow)
            listing["qualifies"] = lu.qualifies_for_match(
                item,
                session_ctx["skill"],
                session_ctx["powScore"],
            )
        jobs.append(listing)

    if not jobs:
        return _response(404, {"error": "No matching listings found for compare"})

    return _response(
        200,
        {
            "domain": domain,
            "jobs": jobs,
            "sessionContext": session_ctx,
        },
    )

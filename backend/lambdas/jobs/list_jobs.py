"""
API Gateway-triggered Lambda: lists internship jobs from Blackhole-written
domain tables (jobs_engineering, jobs_business, jobs_healthcare).

Handler: list_jobs.lambda_handler

Expected request (HTTP API GET):
    GET /jobs?domain=Engineering
    GET /jobs?domain=Engineering&skill=Python
    GET /jobs?domain=Healthcare&skill=Cardiology&limit=20
    GET /jobs?domain=Business&nextToken=<base64>
    GET /jobs?domain=Engineering&employmentType=Internship

Response (200):
    {
        "jobs": [...],
        "count": <int>,
        "nextToken": <string|null>
    }

Domain-to-table mapping is controlled in code -- clients may never pass a
raw DynamoDB table name.

employmentType filter matches exactly what the underlying data actually
contains: "Job" or "Internship" (case-insensitive). Unrecognized values
are treated as "no matches" rather than an error, since this mirrors how
the skill filter already behaves for a query with no hits.

Scope:
    - Read-only: DynamoDB Scan on the selected domain table.
    - Does NOT write, update, or delete any records.
    - Does NOT touch Cognito, S3, or verification flows.

Required IAM permissions (listJobsRole):
    dynamodb:Scan on jobs_engineering, jobs_business, jobs_healthcare

Environment variables:
    AWS_REGION  (default fallback: "ap-south-1")
"""

import os
import json
import base64
import logging
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "ap-south-1")

DEFAULT_LIMIT = 20
MAX_LIMIT = 50

DOMAIN_TABLE_MAP = {
    "engineering": "jobs_engineering",
    "business": "jobs_business",
    "healthcare": "jobs_healthcare",
}

JOB_FIELDS = (
    "canonical_id",
    "title",
    "company",
    "location",
    "source",
    "apply_url",
    "required_skills",
    "employment_type",
    "status",
    "display_status",
    "domain",
    "min_pow_score",
    "is_fallback",
)

_dynamodb = boto3.resource("dynamodb", region_name=REGION)


def domain_to_table_name(domain: str):
    """Map a canonical domain label to its DynamoDB table. Returns None if unsupported."""
    if not domain or not isinstance(domain, str):
        return None
    normalized = domain.strip().lower()
    return DOMAIN_TABLE_MAP.get(normalized)


def _cors_headers():
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
    }


def _response(status_code: int, body_dict: dict):
    return {
        "statusCode": status_code,
        "headers": _cors_headers(),
        "body": json.dumps(body_dict, default=_json_default),
    }


def _json_default(obj):
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _get_http_method(event) -> str:
    http = (event.get("requestContext") or {}).get("http") or {}
    method = http.get("method") or event.get("httpMethod") or "GET"
    return str(method).upper()


def _get_query_params(event) -> dict:
    return event.get("queryStringParameters") or {}


def _parse_limit(raw_limit):
    if raw_limit is None or raw_limit == "":
        return DEFAULT_LIMIT

    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return None

    if limit < 1 or limit > MAX_LIMIT:
        return None

    return limit


def _encode_next_token(last_evaluated_key):
    if not last_evaluated_key:
        return None
    payload = json.dumps(last_evaluated_key, default=_json_default).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def _decode_next_token(token: str):
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8"))
        decoded = json.loads(raw.decode("utf-8"))
    except Exception:
        return None

    if not isinstance(decoded, dict) or not decoded:
        return None

    return decoded


def _skill_matches(required_skills, skill_query: str) -> bool:
    if not skill_query:
        return True
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


def _employment_type_matches(employment_type, employment_type_query: str) -> bool:
    """
    Case-insensitive exact match against employment_type (e.g. "Job",
    "Internship"). No employmentType query param means no filtering.
    A missing/None employment_type on the item never matches a real query.
    """
    if not employment_type_query:
        return True

    needle = employment_type_query.strip().lower()
    if not needle:
        return True

    if not employment_type:
        return False

    return str(employment_type).strip().lower() == needle


def _normalize_job(item: dict) -> dict:
    job = {}
    for field in JOB_FIELDS:
        if field in item:
            value = item[field]
            if isinstance(value, Decimal):
                value = int(value) if value % 1 == 0 else float(value)
            job[field] = value
    return job


def _scan_jobs(table_name: str, limit: int, exclusive_start_key=None):
    table = _dynamodb.Table(table_name)
    scan_kwargs = {"Limit": limit}
    if exclusive_start_key:
        scan_kwargs["ExclusiveStartKey"] = exclusive_start_key
    return table.scan(**scan_kwargs)


def lambda_handler(event, context):
    method = _get_http_method(event)
    if method != "GET":
        return _response(405, {"error": "Method not allowed"})

    params = _get_query_params(event)
    domain = params.get("domain")
    skill = params.get("skill")
    employment_type_query = params.get("employmentType")
    raw_limit = params.get("limit")
    next_token = params.get("nextToken")

    if not domain or not isinstance(domain, str) or not domain.strip():
        return _response(400, {"error": "domain is required"})

    table_name = domain_to_table_name(domain)
    if table_name is None:
        return _response(
            400,
            {
                "error": (
                    "Unsupported domain. Must be one of: "
                    + ", ".join(sorted(d.title() for d in DOMAIN_TABLE_MAP))
                )
            },
        )

    limit = _parse_limit(raw_limit)
    if limit is None:
        return _response(
            400,
            {"error": f"limit must be an integer between 1 and {MAX_LIMIT}"},
        )

    exclusive_start_key = None
    if next_token:
        exclusive_start_key = _decode_next_token(next_token)
        if exclusive_start_key is None:
            return _response(400, {"error": "Invalid nextToken"})

    try:
        scan_response = _scan_jobs(table_name, limit, exclusive_start_key)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB Scan failed for table=%s: %s", table_name, error_code)
        return _response(500, {"error": "Could not list jobs"})
    except Exception:
        logger.exception("Unexpected error listing jobs from table=%s", table_name)
        return _response(500, {"error": "Could not list jobs"})

    items = scan_response.get("Items") or []
    jobs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if skill and not _skill_matches(item.get("required_skills"), skill):
            continue
        if employment_type_query and not _employment_type_matches(
            item.get("employment_type"), employment_type_query
        ):
            continue
        jobs.append(_normalize_job(item))

    response_body = {
        "jobs": jobs,
        "count": len(jobs),
        "nextToken": _encode_next_token(scan_response.get("LastEvaluatedKey")),
    }

    logger.info(
        "Listed jobs domain=%s table=%s employmentType=%s count=%s hasMore=%s",
        domain.strip(),
        table_name,
        employment_type_query,
        len(jobs),
        response_body["nextToken"] is not None,
    )

    return _response(200, response_body)
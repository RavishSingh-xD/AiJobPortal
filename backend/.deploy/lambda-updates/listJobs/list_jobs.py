"""
API Gateway-triggered Lambda: lists internship jobs from Blackhole-written
domain tables (jobs_engineering, jobs_business, jobs_healthcare), and
triggers an on-demand harvest via SSM when a domain has no data yet.

Handler: list_jobs.lambda_handler

Expected request (HTTP API GET):
    GET /jobs?domain=Engineering
    GET /jobs?domain=Engineering&skill=Python
    GET /jobs?domain=Healthcare&skill=Cardiology&limit=20
    GET /jobs?domain=Business&nextToken=<base64>
    GET /jobs?domain=Engineering&employmentType=Internship

Response (200) -- normal case, table has data:
    {
        "jobs": [...],
        "count": <int>,
        "nextToken": <string|null>
    }

Response (202) -- on-demand harvest just triggered, no data available yet:
    {
        "status": "harvesting",
        "domain": "Engineering",
        "message": "..."
    }

On-demand harvest trigger logic:
    - Only fires when the domain's table doesn't exist yet, OR exists but
      is genuinely empty on a raw (unfiltered) scan. A skill/employmentType
      filter simply not matching anything in an already-populated table
      does NOT trigger a harvest -- that's a normal empty search result,
      not "we have zero data for this domain."
    - Checks harvest_status first to avoid firing duplicate harvests if
      multiple requests hit the same missing domain around the same time.
    - If a previous trigger's startedAt is older than STALE_THRESHOLD_SECONDS
      without completing, treats it as stale and allows re-triggering
      (protects against a crashed/stuck harvest blocking future searches).
    - Uses ssm.send_command against the harvester EC2 instance -- the same
      command shape proven to work manually during setup.

Domain-to-table mapping is controlled in code -- clients may never pass a
raw DynamoDB table name.

Scope:
    - Read-only on jobs_* tables: DynamoDB Scan only.
    - Filters out closed/expired/inactive listings (same CLOSED_STATUSES /
      _is_open_listing rule as get_matched_jobs / start_domain_test).
    - Read/write on harvest_status: GetItem, PutItem.
    - ssm:SendCommand on the harvester instance, when triggering.
    - Does NOT touch Cognito, S3, or verification flows.

Required IAM permissions (listJobsRole):
    dynamodb:Scan on jobs_engineering, jobs_business, jobs_healthcare
    dynamodb:GetItem, dynamodb:PutItem on harvest_status
    ssm:SendCommand on the harvester instance ARN and the
      AWS-RunShellScript document ARN

Environment variables:
    AWS_REGION               (default fallback: "ap-south-1")
    HARVEST_STATUS_TABLE     (default: "harvest_status")
    HARVESTER_INSTANCE_ID    (required to actually trigger harvests --
                              if unset, the Lambda just returns empty
                              results instead of triggering, so this can
                              be deployed before the instance exists)
    STALE_THRESHOLD_SECONDS  (default: "300" -- 5 minutes)
"""

import os
import json
import base64
import logging
import datetime
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "ap-south-1")
HARVEST_STATUS_TABLE = os.environ.get("HARVEST_STATUS_TABLE", "harvest_status")
HARVESTER_INSTANCE_ID = os.environ.get("HARVESTER_INSTANCE_ID")
STALE_THRESHOLD_SECONDS = int(os.environ.get("STALE_THRESHOLD_SECONDS", "300"))

DEFAULT_LIMIT = 20
MAX_LIMIT = 50

DOMAIN_TABLE_MAP = {
    "engineering": "jobs_engineering",
    "business": "jobs_business",
    "healthcare": "jobs_healthcare",
}

# harvester.py requires SOME skill value to run -- if none is given, it
# falls back to an interactive input() prompt, which crashes immediately
# under SSM's non-interactive send_command (no stdin available). These
# defaults let a domain-only search still trigger a real harvest.
DEFAULT_SKILL_BY_DOMAIN = {
    "engineering": "Software",
    "business": "Management",
    "healthcare": "Medicine",
}

# Same exclusion set as get_matched_jobs.CLOSED_STATUSES /
# start_domain_test.CLOSED_STATUSES. "Active" means status (or, if
# status is empty, display_status) is not one of these values -- not a
# strict status == "active" equality check.
CLOSED_STATUSES = {"closed", "expired", "inactive"}

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
_harvest_status_table = _dynamodb.Table(HARVEST_STATUS_TABLE)
_ssm = boto3.client("ssm", region_name=REGION)


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


def _is_open_listing(item: dict) -> bool:
    """Mirror get_matched_jobs._is_open_listing / start_domain_test exactly."""
    status = item.get("status") or item.get("display_status") or ""
    return str(status).strip().lower() not in CLOSED_STATUSES


def _employment_type_matches(employment_type, employment_type_query: str) -> bool:
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


def _raw_scan_is_empty(table_name: str) -> bool:
    """
    Does an unfiltered, tiny scan just to check if the table has ANY data
    at all. Separate from the real paginated scan used for the actual
    response -- this is purely a "is this domain harvested yet" check.
    """
    table = _dynamodb.Table(table_name)
    response = table.scan(Limit=1)
    return len(response.get("Items") or []) == 0


def _get_harvest_status(domain_key: str):
    try:
        response = _harvest_status_table.get_item(Key={"domain": domain_key})
    except ClientError as e:
        logger.error("Failed to read harvest_status for domain=%s: %s", domain_key, e)
        return None
    return response.get("Item")


def _is_stale(status_item) -> bool:
    started_at = status_item.get("startedAt")
    if not started_at:
        return True
    try:
        started = datetime.datetime.fromisoformat(started_at)
    except ValueError:
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    age_seconds = (now - started).total_seconds()
    return age_seconds > STALE_THRESHOLD_SECONDS


def _trigger_harvest(domain_display: str, domain_key: str, skill: str):
    """
    Fires an on-demand harvest via SSM, unless one is already genuinely
    in progress for this domain. Returns True if a harvest was triggered
    (or already running), False if triggering itself failed.
    """
    existing = _get_harvest_status(domain_key)
    if existing and existing.get("status") == "in_progress" and not _is_stale(existing):
        logger.info("Harvest already in progress for domain=%s, not re-triggering", domain_key)
        return True

    if not HARVESTER_INSTANCE_ID:
        logger.warning("HARVESTER_INSTANCE_ID not set -- cannot trigger harvest for domain=%s", domain_key)
        return False

    effective_skill = skill or DEFAULT_SKILL_BY_DOMAIN.get(domain_key)
    skill_arg = f' -s "{effective_skill}"' if effective_skill else ""
    command = (
        f"cd /home/ubuntu/blackhole && "
        f'sudo -u ubuntu ./venv/bin/python harvester.py -d "{domain_display}"{skill_arg} --exclude-fallbacks'
    )

    try:
        ssm_response = _ssm.send_command(
            InstanceIds=[HARVESTER_INSTANCE_ID],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": [command]},
            TimeoutSeconds=300,
        )
        command_id = ssm_response["Command"]["CommandId"]
    except ClientError as e:
        logger.error("Failed to send SSM command for domain=%s: %s", domain_key, e)
        return False

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        _harvest_status_table.put_item(
            Item={
                "domain": domain_key,
                "status": "in_progress",
                "startedAt": now,
                "ssmCommandId": command_id,
            }
        )
    except ClientError as e:
        logger.error("Failed to record harvest_status for domain=%s: %s", domain_key, e)
        # The harvest itself was still triggered successfully -- don't
        # fail the request just because the status record write failed.

    logger.info("Triggered on-demand harvest for domain=%s commandId=%s", domain_key, command_id)
    return True


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
        return _response(400, {"error": f"limit must be an integer between 1 and {MAX_LIMIT}"})

    exclusive_start_key = None
    if next_token:
        exclusive_start_key = _decode_next_token(next_token)
        if exclusive_start_key is None:
            return _response(400, {"error": "Invalid nextToken"})

    domain_key = domain.strip().lower()
    domain_display = domain.strip().title()

    # Check if this domain has any data at all -- table missing or empty
    # both mean "never harvested" from the caller's perspective.
    table_is_empty_or_missing = False
    try:
        table_is_empty_or_missing = _raw_scan_is_empty(table_name)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "ResourceNotFoundException":
            table_is_empty_or_missing = True
        else:
            logger.error("DynamoDB check failed for table=%s: %s", table_name, error_code)
            return _response(500, {"error": "Could not list jobs"})

    if table_is_empty_or_missing:
        logger.info("Domain=%s table missing/empty -- attempting trigger", domain_key)
        try:
            triggered = _trigger_harvest(domain_display, domain_key, skill)
        except Exception:
            logger.exception("Unexpected exception inside _trigger_harvest for domain=%s", domain_key)
            triggered = False
        logger.info("_trigger_harvest returned triggered=%s for domain=%s", triggered, domain_key)
        if triggered:
            return _response(
                202,
                {
                    "status": "harvesting",
                    "domain": domain_display,
                    "message": "We're finding fresh listings for this domain -- check back shortly.",
                },
            )
        # Triggering itself failed (e.g. no instance configured) -- fall
        # through to a normal empty response rather than erroring, so the
        # API still behaves sensibly even without the harvester wired up.

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
        if not _is_open_listing(item):
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
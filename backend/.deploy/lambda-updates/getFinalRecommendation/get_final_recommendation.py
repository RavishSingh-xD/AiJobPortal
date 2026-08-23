"""
API Gateway-triggered Lambda: final AI recommendation for a completed
match session (Pillar 3 Step 4).

Handler: get_final_recommendation.lambda_handler

Expected request (API Gateway HTTP API, JWT authorizer):
    POST /match/{sessionId}/recommendation

Prerequisites on match_sessions (from Steps 1-3):
    status=test_completed, powScore, scorePercent, domain, skill

Step 3 (get_matched_jobs) does NOT persist matched listings -- this
Lambda re-runs the same active/skill/pow/employment_type filters, then:
  1. Deterministically ranks listings (LLM never touches scores/order)
  2. One batched Groq call for per-job "whyThisFits" + readinessSummary
     (or summary-only when zero matches)
  3. Persists rankedJobs, readinessSummary, explanationsAvailable,
     recommendationCompletedAt, status=recommendation_complete

Groq setup mirrors start_domain_test.py exactly (SSM param, model,
User-Agent, urllib, fence-strip).

Required IAM permissions (getFinalRecommendationRole -- create when deploying):
    dynamodb:GetItem, dynamodb:UpdateItem on match_sessions
    dynamodb:Scan on jobs_engineering, jobs_business, jobs_healthcare
    ssm:GetParameter on /aijobportal/groq-api-key
    kms:Decrypt on the key encrypting that SecureString

Environment variables:
    MATCH_SESSIONS_TABLE  (default: "match_sessions")
    AWS_REGION            (default fallback: "ap-south-1")
    GROQ_API_KEY_PARAM    (default: "/aijobportal/groq-api-key")
    GROQ_MODEL            (default: "openai/gpt-oss-120b")
    GROQ_API_URL          (default: Groq OpenAI-compatible chat completions)
"""

import os
import json
import logging
import datetime
from decimal import Decimal
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

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
GROQ_API_KEY_PARAM = os.environ.get("GROQ_API_KEY_PARAM", "/aijobportal/groq-api-key")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_API_URL = os.environ.get(
    "GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions"
)

FORBIDDEN_MESSAGE = "Forbidden"
# Step 3 leaves status at test_completed; Step 4 advances it.
STATUS_REQUIRED = "test_completed"
STATUS_COMPLETE = "recommendation_complete"
CONFLICT_MESSAGE = "Complete the domain test before requesting a recommendation."

# Tunable ranking weights (must sum to 1.0). PoW and domain-test scores are
# session-level constants; skill overlap is what differentiates jobs.
WEIGHT_POW = 0.35
WEIGHT_DOMAIN_TEST = 0.40
WEIGHT_SKILL_OVERLAP = 0.25

POW_SCORE_MAX = 50.0
DOMAIN_TEST_MAX = 100.0

DOMAIN_TABLE_MAP = {
    "Engineering": "jobs_engineering",
    "Business": "jobs_business",
    "Healthcare": "jobs_healthcare",
}

EMPLOYMENT_INTERNSHIP = "Internship"
EMPLOYMENT_JOB = "Job"
CLOSED_STATUSES = {"closed", "expired", "inactive"}
MAX_SCAN_PAGES = 25
SCAN_PAGE_SIZE = 100
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
)

_dynamodb = boto3.resource("dynamodb", region_name=REGION)
_sessions_table = _dynamodb.Table(MATCH_SESSIONS_TABLE)
_ssm = boto3.client("ssm", region_name=REGION)

_groq_api_key = None


def _cors_headers():
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "OPTIONS,POST",
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
    """Delegate to shared match listing helpers."""
    return lu.is_open_listing(item)


def _skill_matches(item: dict, skill_query: str, needles=None) -> bool:
    """Mirror list_jobs / get_matched_jobs (expanded subdomain needles)."""
    return lu.job_matches_skill(item, skill_query, needles)


def _employment_type_key(employment_type):
    return lu.employment_type_key(employment_type)


def _normalize_required_skills(required_skills):
    return lu.normalize_required_skills(required_skills)


def _public_listing(item: dict) -> dict:
    listing = lu.public_listing(item)
    # Recommendation payload keeps the historical field set (no harvest_skill/source).
    public = {
        field: listing[field] for field in LISTING_FIELDS if field in listing
    }
    public["required_skills"] = listing.get("required_skills", [])
    return public


def _scan_jobs(table_name: str):
    table = _dynamodb.Table(table_name)
    items = []
    start_key = None
    for _ in range(MAX_SCAN_PAGES):
        scan_kwargs = {"Limit": SCAN_PAGE_SIZE}
        if start_key:
            scan_kwargs["ExclusiveStartKey"] = start_key
        response = table.scan(**scan_kwargs)
        items.extend(response.get("Items") or [])
        start_key = response.get("LastEvaluatedKey")
        if not start_key:
            break
    return {"Items": items}


def _collect_matched_listings(domain: str, skill: str, pow_score: float):
    """Re-run Step 3 filters (get_matched_jobs does not persist matches)."""
    table_name = DOMAIN_TABLE_MAP.get(domain)
    if not table_name:
        return []

    scan_response = _scan_jobs(table_name)
    needles = lu.expand_skill_needles(domain, skill)
    matched = []
    for item in scan_response.get("Items") or []:
        if not isinstance(item, dict):
            continue
        if not lu.qualifies_for_match(item, skill, pow_score, needles):
            continue
        matched.append(_public_listing(item))
    return matched[: GROUP_CAP * 2]


def _skill_overlap(required_skills, skill: str, domain: str) -> float:
    """Fraction of job skill tags that match the session skill or domain."""
    return lu.skill_overlap(required_skills, skill, domain)


def _rank_jobs(listings, pow_score: float, score_percent: float, skill: str, domain: str):
    """
    Deterministic ranking. LLM must never call this or alter its output.

    matchScore = WEIGHT_POW * (pow/50)
               + WEIGHT_DOMAIN_TEST * (scorePercent/100)
               + WEIGHT_SKILL_OVERLAP * overlap
    Tie-break: higher matchScore first, then canonical_id ascending.
    """
    ranked = []
    pow_norm = max(0.0, min(1.0, float(pow_score) / POW_SCORE_MAX))
    test_norm = max(0.0, min(1.0, float(score_percent) / DOMAIN_TEST_MAX))

    for listing in listings:
        overlap = _skill_overlap(listing.get("required_skills"), skill, domain)
        match_score = (
            WEIGHT_POW * pow_norm
            + WEIGHT_DOMAIN_TEST * test_norm
            + WEIGHT_SKILL_OVERLAP * overlap
        )
        match_score = round(match_score, 6)
        entry = {
            **{k: v for k, v in listing.items()},
            "skillOverlap": round(overlap, 4),
            "matchScore": match_score,
            "whyThisFits": "",
        }
        ranked.append(entry)

    ranked.sort(
        key=lambda row: (-row["matchScore"], str(row.get("canonical_id") or ""))
    )
    return ranked


def _get_groq_api_key():
    global _groq_api_key
    if _groq_api_key:
        return _groq_api_key

    response = _ssm.get_parameter(Name=GROQ_API_KEY_PARAM, WithDecryption=True)
    _groq_api_key = response["Parameter"]["Value"]
    return _groq_api_key


def _call_groq(messages):
    """Same pattern as start_domain_test._call_groq (User-Agent required)."""
    api_key = _get_groq_api_key()
    payload = json.dumps(
        {
            "model": GROQ_MODEL,
            "temperature": 0,
            "messages": messages,
        }
    ).encode("utf-8")
    request = Request(
        GROQ_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "AiJobPortal-MatchPipeline/1.0",
        },
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


def _strip_json_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.endswith("```"):
            stripped = stripped[: -len("```")]
        stripped = stripped.strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    return stripped


def _parse_recommendation_payload(raw_content: str):
    data = json.loads(_strip_json_fences(raw_content))
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    summary = data.get("readinessSummary")
    if not isinstance(summary, str):
        summary = ""
    explanations = data.get("explanations") or {}
    if not isinstance(explanations, dict):
        explanations = {}
    cleaned = {}
    for key, value in explanations.items():
        if isinstance(value, str) and value.strip():
            cleaned[str(key)] = value.strip()
    return cleaned, summary.strip()


def _generate_narratives(ranked_jobs, domain, skill, pow_score, score_percent):
    """
    One batched Groq call. Returns (explanations_by_id, readiness_summary).
    Raises on parse/API failure so the caller can fall back.
    """
    if ranked_jobs:
        jobs_payload = [
            {
                "canonical_id": job.get("canonical_id"),
                "title": job.get("title"),
                "company": job.get("company"),
                "employment_type": job.get("employment_type"),
                "required_skills": job.get("required_skills"),
                "min_pow_score": job.get("min_pow_score"),
                "matchScore": job.get("matchScore"),
                "skillOverlap": job.get("skillOverlap"),
            }
            for job in ranked_jobs
        ]
        system = (
            "You are a career coach for student internships. Respond with ONLY "
            "a valid JSON object of the exact shape "
            '{"explanations": {"<canonical_id>": "<short why-this-fits text>"}, '
            '"readinessSummary": "<short constructive narrative of strengths and '
            'gaps>"}. Nothing else. No markdown code fences.'
        )
        user = (
            f"Domain: {domain}\n"
            f"Tested skill: {skill}\n"
            f"PoW score: {pow_score}/50\n"
            f"Domain test scorePercent: {score_percent}\n"
            f"Ranked jobs (already ordered — do not re-rank):\n"
            f"{json.dumps(jobs_payload, default=str)}\n"
            "Write one short explanation per canonical_id and one readinessSummary."
        )
    else:
        system = (
            "You are a career coach for student internships. Respond with ONLY "
            "a valid JSON object of the exact shape "
            '{"explanations": {}, "readinessSummary": "<short constructive '
            'narrative explaining no current listings matched and which skills '
            'would help>"}. Nothing else. No markdown code fences.'
        )
        user = (
            f"Domain: {domain}\n"
            f"Tested skill: {skill}\n"
            f"PoW score: {pow_score}/50\n"
            f"Domain test scorePercent: {score_percent}\n"
            "No active job listings currently match this skill/domain. "
            "Explain that constructively and suggest skills that would help."
        )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    content = _call_groq(messages)
    try:
        return _parse_recommendation_payload(content)
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("Groq recommendation payload invalid; retrying once")
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": user
                + "\nRespond with ONLY the JSON object, no other text.",
            },
        ]
        content = _call_groq(messages)
        return _parse_recommendation_payload(content)


def _attach_explanations(ranked_jobs, explanations_by_id):
    for job in ranked_jobs:
        cid = str(job.get("canonical_id") or "")
        job["whyThisFits"] = explanations_by_id.get(cid, "")
    return ranked_jobs


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
    score_percent = _as_number(session_item.get("scorePercent"), default=None)
    if (
        not isinstance(domain, str)
        or skill is None
        or pow_score is None
        or score_percent is None
    ):
        return _response(409, {"error": CONFLICT_MESSAGE})

    try:
        matched = _collect_matched_listings(domain, skill, pow_score)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("Jobs scan failed for recommendation: %s", error_code)
        return _response(500, {"error": "Could not load matched jobs for recommendation"})

    ranked = _rank_jobs(matched, pow_score, score_percent, skill, domain)

    explanations_available = False
    readiness_summary = ""
    try:
        explanations_by_id, readiness_summary = _generate_narratives(
            ranked, domain, skill, pow_score, score_percent
        )
        ranked = _attach_explanations(ranked, explanations_by_id)
        explanations_available = True
    except (json.JSONDecodeError, TypeError, ValueError, KeyError, HTTPError, URLError):
        logger.exception("Groq narrative generation failed sessionId=%s", session_id)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("SSM/Groq dependency failed: %s", error_code)
    except Exception:
        logger.exception("Unexpected Groq failure sessionId=%s", session_id)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    # DynamoDB-friendly decimals for nested scores
    persist_jobs = []
    for job in ranked:
        row = dict(job)
        row["matchScore"] = Decimal(str(row["matchScore"]))
        row["skillOverlap"] = Decimal(str(row["skillOverlap"]))
        if "min_pow_score" in row and not isinstance(row["min_pow_score"], Decimal):
            row["min_pow_score"] = Decimal(str(_as_number(row["min_pow_score"], 0)))
        persist_jobs.append(row)

    try:
        _sessions_table.update_item(
            Key={"sessionId": session_id},
            UpdateExpression=(
                "SET rankedJobs = :ranked, readinessSummary = :summary, "
                "explanationsAvailable = :explained, "
                "recommendationCompletedAt = :completed, #status = :status"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":ranked": persist_jobs,
                ":summary": readiness_summary,
                ":explained": explanations_available,
                ":completed": now,
                ":status": STATUS_COMPLETE,
            },
            ConditionExpression="attribute_exists(sessionId)",
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB UpdateItem failed for match_sessions: %s", error_code)
        return _response(500, {"error": "Could not save recommendation"})

    logger.info(
        "Recommendation complete sessionId=%s ranked=%s explanations=%s",
        session_id,
        len(ranked),
        explanations_available,
    )
    return _response(
        200,
        {
            "rankedJobs": ranked,
            "readinessSummary": readiness_summary,
            "explanationsAvailable": explanations_available,
            "powScore": session_item.get("powScore"),
            "scorePercent": session_item.get("scorePercent"),
            "domain": domain,
            "skill": skill,
            "status": STATUS_COMPLETE,
        },
    )

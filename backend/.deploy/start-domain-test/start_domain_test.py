"""
API Gateway-triggered Lambda: starts a 15-question domain test for a
match session that already has a PoW score.

Handler: start_domain_test.lambda_handler

Expected request (API Gateway HTTP API, JWT authorizer):
    POST /match/{sessionId}/test/start
    {
        "domain": "Engineering",
        "skill": "Python"
    }

domain must be exactly one of Engineering, Business, Healthcare, Design.
The test always includes a mix of easy, medium, and hard questions (5 each).

Response (200): the first question, sanitized (no correctIndex, no
difficulty), plus totalQuestions and currentQuestionIndex.

Required IAM permissions (startDomainTestRole -- create when deploying):
    dynamodb:GetItem, dynamodb:UpdateItem on match_sessions
    dynamodb:Scan on jobs_engineering, jobs_business, jobs_healthcare,
      jobs_design
    ssm:GetParameter on /aijobportal/groq-api-key
    kms:Decrypt on the key encrypting that SecureString parameter

Environment variables:
    MATCH_SESSIONS_TABLE  (default: "match_sessions")
    AWS_REGION            (default fallback: "ap-south-1")
    GROQ_API_KEY_PARAM    (default: "/aijobportal/groq-api-key")
    GROQ_MODEL            (default: "openai/gpt-oss-120b")
    GROQ_API_URL          (default: Groq OpenAI-compatible chat completions)
"""

import os
import json
import random
import logging
import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import boto3
from botocore.exceptions import ClientError

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
QUESTION_COUNT = 15
JOBS_SAMPLE_LIMIT = 20
STATUS_REQUIRED = "awaiting_test"
CONFLICT_MESSAGE = "Domain test already started or PoW score not yet available."

VALID_DOMAINS = ("Engineering", "Business", "Healthcare", "Design")
QUESTION_DIFFICULTIES = ("easy", "medium", "hard")
DIFFICULTY_MODE_MIXED = "mixed"

DOMAIN_TABLE_MAP = {
    "Engineering": "jobs_engineering",
    "Business": "jobs_business",
    "Healthcare": "jobs_healthcare",
    "Design": "jobs_design",
}

TIME_LIMIT_EASY = 15
TIME_LIMIT_MEDIUM = 25
TIME_LIMIT_HARD = 30

CLOSED_STATUSES = {"closed", "expired", "inactive"}

SYSTEM_PROMPT = (
    "You are an exam writer for an internship matching platform. "
    "Respond with ONLY a valid JSON array of exactly 15 objects, each of "
    'the exact shape {"questionText": "<string>", "options": '
    '["<a>", "<b>", "<c>", "<d>"], "correctIndex": <integer 0-3>}. '
    "Nothing else. No markdown code fences, no commentary."
)
RETRY_JSON_INSTRUCTION = (
    "Respond with ONLY a JSON array of exactly 15 objects, no other text "
    "and no markdown. Each object must have questionText (string), "
    "options (array of exactly 4 strings), and correctIndex (integer 0-3)."
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


def _get_groq_api_key():
    global _groq_api_key
    if _groq_api_key:
        return _groq_api_key

    response = _ssm.get_parameter(Name=GROQ_API_KEY_PARAM, WithDecryption=True)
    _groq_api_key = response["Parameter"]["Value"]
    return _groq_api_key


def _call_groq(messages):
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


def _time_limit_seconds(difficulty: str) -> int:
    if difficulty == "easy":
        return TIME_LIMIT_EASY
    if difficulty == "medium":
        return TIME_LIMIT_MEDIUM
    if difficulty == "hard":
        return TIME_LIMIT_HARD
    raise ValueError(f"unsupported difficulty: {difficulty}")


def _is_open_listing(item: dict) -> bool:
    status = item.get("status") or item.get("display_status") or ""
    return str(status).strip().lower() not in CLOSED_STATUSES


def _sample_in_demand_skills(domain: str) -> str:
    table_name = DOMAIN_TABLE_MAP[domain]
    table = _dynamodb.Table(table_name)
    response = table.scan(Limit=JOBS_SAMPLE_LIMIT)
    items = response.get("Items") or []
    skills = []
    seen = set()
    for item in items:
        if not isinstance(item, dict) or not _is_open_listing(item):
            continue
        required = item.get("required_skills") or []
        if isinstance(required, str):
            required = [required]
        if not isinstance(required, list):
            continue
        for skill in required:
            label = str(skill).strip()
            key = label.lower()
            if not label or key in seen:
                continue
            seen.add(key)
            skills.append(label)
    return ", ".join(skills[:30])


def _build_user_prompt(domain, skill, in_demand_skills, extra=None):
    lines = [
        f"Domain: {domain}",
        f"Target skill: {skill}",
        "Difficulty mix: include a balanced mix of easy, medium, and hard questions.",
        f"Generate exactly {QUESTION_COUNT} multiple-choice questions "
        "specific to this domain and skill.",
        "Each question must have exactly 4 options and one correct answer "
        "indicated by correctIndex (0-3).",
    ]
    if in_demand_skills:
        lines.append(
            "Weight topics toward skills currently appearing in open job "
            f"listings: {in_demand_skills}"
        )
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def _coerce_correct_index(value):
    if isinstance(value, bool):
        raise ValueError("correctIndex must be an integer 0-3")
    if isinstance(value, int):
        index = value
    elif isinstance(value, float) and value == int(value):
        index = int(value)
    else:
        raise ValueError("correctIndex must be an integer 0-3")
    if index < 0 or index > 3:
        raise ValueError("correctIndex must be an integer 0-3")
    return index


def _parse_questions_payload(raw_content: str):
    data = json.loads(_strip_json_fences(raw_content))
    if not isinstance(data, list) or len(data) != QUESTION_COUNT:
        raise ValueError("expected a JSON array of exactly 15 questions")

    parsed = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("each question must be an object")
        text = item.get("questionText")
        options = item.get("options")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("questionText must be a non-empty string")
        if not isinstance(options, list) or len(options) != 4:
            raise ValueError("options must be an array of exactly 4 strings")
        if not all(isinstance(option, str) and option.strip() for option in options):
            raise ValueError("options must be an array of exactly 4 strings")
        parsed.append(
            {
                "questionText": text.strip(),
                "options": [option.strip() for option in options],
                "correctIndex": _coerce_correct_index(item.get("correctIndex")),
            }
        )
    return parsed


def _generate_questions(domain, skill, in_demand_skills):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _build_user_prompt(domain, skill, in_demand_skills),
        },
    ]
    content = _call_groq(messages)
    try:
        return _parse_questions_payload(content)
    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
        logger.warning("Groq question payload was invalid; retrying once")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_user_prompt(
                    domain, skill, in_demand_skills, extra=RETRY_JSON_INSTRUCTION
                ),
            },
        ]
        content = _call_groq(messages)
        return _parse_questions_payload(content)


def _build_mixed_difficulties(count=QUESTION_COUNT):
    """Return a shuffled list with equal counts of easy, medium, and hard."""
    per_level = count // len(QUESTION_DIFFICULTIES)
    remainder = count % len(QUESTION_DIFFICULTIES)
    difficulties = []
    for index, level in enumerate(QUESTION_DIFFICULTIES):
        extra = 1 if index < remainder else 0
        difficulties.extend([level] * (per_level + extra))
    random.shuffle(difficulties)
    return difficulties


def _attach_metadata(questions):
    difficulties = _build_mixed_difficulties(len(questions))
    decorated = []
    for index, question in enumerate(questions, start=1):
        difficulty = difficulties[index - 1]
        decorated.append(
            {
                "questionId": f"q{index}",
                "questionText": question["questionText"],
                "options": question["options"],
                "correctIndex": question["correctIndex"],
                "difficulty": difficulty,
                "timeLimitSeconds": _time_limit_seconds(difficulty),
            }
        )
    return decorated


def _sanitize_question(question: dict) -> dict:
    return {
        "questionId": question["questionId"],
        "questionText": question["questionText"],
        "options": question["options"],
        "timeLimitSeconds": question["timeLimitSeconds"],
    }


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

    domain = body.get("domain")
    if domain not in VALID_DOMAINS:
        return _response(
            400,
            {
                "error": (
                    "domain must be one of: " + ", ".join(VALID_DOMAINS)
                )
            },
        )

    skill = body.get("skill")
    if not skill or not isinstance(skill, str) or not skill.strip():
        return _response(400, {"error": "skill is required"})
    skill = skill.strip()

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

    in_demand_skills = ""
    try:
        in_demand_skills = _sample_in_demand_skills(domain)
        if not in_demand_skills:
            logger.warning("No open-listing skills found for domain=%s", domain)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.warning("Jobs table scan failed for domain=%s: %s", domain, error_code)
    except Exception:
        logger.exception("Unexpected error sampling jobs for domain=%s", domain)

    try:
        raw_questions = _generate_questions(domain, skill, in_demand_skills)
    except (json.JSONDecodeError, TypeError, ValueError, KeyError, HTTPError, URLError):
        logger.exception("Question generation failed sessionId=%s", session_id)
        return _response(500, {"error": "Could not generate domain test questions"})
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("SSM GetParameter failed: %s", error_code)
        return _response(500, {"error": "Could not generate domain test questions"})

    questions = _attach_metadata(raw_questions)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        _sessions_table.update_item(
            Key={"sessionId": session_id},
            UpdateExpression=(
                "SET #domain = :domain, skill = :skill, difficulty = :difficulty, "
                "questions = :questions, currentQuestionIndex = :index, "
                "questionServedAt = :served, #status = :status"
            ),
            ExpressionAttributeNames={"#domain": "domain", "#status": "status"},
            ExpressionAttributeValues={
                ":domain": domain,
                ":skill": skill,
                ":difficulty": DIFFICULTY_MODE_MIXED,
                ":questions": questions,
                ":index": 0,
                ":served": now,
                ":status": "test_in_progress",
            },
            ConditionExpression="attribute_exists(sessionId)",
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB UpdateItem failed for match_sessions: %s", error_code)
        return _response(500, {"error": "Could not start domain test"})

    first = _sanitize_question(questions[0])
    logger.info(
        "Started domain test sessionId=%s userId=%s domain=%s difficulty=%s",
        session_id,
        user_id,
        domain,
        DIFFICULTY_MODE_MIXED,
    )
    return _response(
        200,
        {
            **first,
            "totalQuestions": QUESTION_COUNT,
            "currentQuestionIndex": 0,
        },
    )

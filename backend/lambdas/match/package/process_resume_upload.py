"""
S3-triggered Lambda: extracts resume text, scores it via Groq, and updates
the match_sessions item.

Handler: process_resume_upload.lambda_handler
S3 trigger: ObjectCreated events on the verification bucket, prefix
"resumes/" only (additive -- does not replace the verification/ trigger).

Expected object key:
    resumes/{userId}/{sessionId}/resume

On success the session is updated to:
    status=awaiting_test, powScore, powBreakdown

On handled failures the session is updated to:
    status=failed, errorMessage=<reason>

This is not an API Gateway handler; it does not return CORS HTTP responses.

Required IAM permissions (processResumeUploadRole -- create when deploying):
    s3:GetObject on arn:aws:s3:::aijobportal-verification-470361396576/resumes/*
    dynamodb:GetItem, dynamodb:UpdateItem on match_sessions
    ssm:GetParameter on arn:aws:ssm:ap-south-1:470361396576:parameter/aijobportal/groq-api-key

Environment variables:
    MATCH_SESSIONS_TABLE     (default: "match_sessions")
    AWS_REGION               (default fallback: "ap-south-1")
    GROQ_API_KEY_PARAM       (default: "/aijobportal/groq-api-key")
    GROQ_MODEL               (default: "openai/gpt-oss-120b")
    GROQ_API_URL             (default: Groq OpenAI-compatible chat completions)
"""

import io
import os
import json
import logging
from urllib.parse import unquote_plus
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
MIN_RESUME_TEXT_LENGTH = 50
POW_SCORE_MIN = 0
POW_SCORE_MAX = 50

ERROR_UNREADABLE = "Unsupported or unreadable resume file"
ERROR_EMPTY_TEXT = "Could not read resume text"
ERROR_AI_SCORING = "AI scoring failed"
ERROR_UNEXPECTED = "Unexpected error during resume processing"

SYSTEM_PROMPT = (
    "You are a resume evaluator. Respond with ONLY a valid JSON object of the "
    'exact shape {"powScore": <integer 0-50>, "breakdown": "<short plain-text '
    "explanation>\"}, nothing else, no markdown code fences."
)
RETRY_JSON_INSTRUCTION = (
    "Respond with ONLY the JSON object, no other text. "
    'Exact shape: {"powScore": <integer 0-50>, "breakdown": "<short plain-text explanation>"}'
)

_dynamodb = boto3.resource("dynamodb", region_name=REGION)
_sessions_table = _dynamodb.Table(MATCH_SESSIONS_TABLE)
_s3 = boto3.client("s3", region_name=REGION)
_ssm = boto3.client("ssm", region_name=REGION)

_groq_api_key = None


def _parse_resume_key(key: str):
    """Return (userId, sessionId) for resumes/{userId}/{sessionId}/resume, else None."""
    if not key or not isinstance(key, str):
        return None
    parts = key.split("/")
    if len(parts) != 4:
        return None
    prefix, user_id, session_id, filename = parts
    if prefix != "resumes" or filename != "resume":
        return None
    if not user_id or not session_id:
        return None
    return user_id, session_id


def _detect_file_type(content_type: str, data: bytes):
    """Return 'pdf', 'docx', or None. Prefer ContentType; fall back to magic bytes."""
    normalized = (content_type or "").split(";")[0].strip().lower()
    if normalized == "application/pdf":
        return "pdf"
    if normalized in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/docx",
    ):
        return "docx"

    ambiguous = normalized in ("", "application/octet-stream", "binary/octet-stream")
    if not ambiguous:
        # Explicit but unrecognized type -- still try magic bytes before giving up.
        pass

    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"PK"):
        return "docx"
    return None


def _extract_pdf_text(data: bytes) -> str:
    import pdfplumber

    pages = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()


def _extract_docx_text(data: bytes) -> str:
    from docx import Document

    document = Document(io.BytesIO(data))
    return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()


def _extract_resume_text(file_type: str, data: bytes) -> str:
    if file_type == "pdf":
        return _extract_pdf_text(data)
    if file_type == "docx":
        return _extract_docx_text(data)
    raise ValueError("unsupported file type")


def _get_groq_api_key():
    global _groq_api_key
    if _groq_api_key:
        return _groq_api_key

    response = _ssm.get_parameter(Name=GROQ_API_KEY_PARAM, WithDecryption=True)
    _groq_api_key = response["Parameter"]["Value"]
    return _groq_api_key


def _build_user_prompt(resume_text, linkedin_url, github_handle, leetcode_handle, extra=None):
    lines = [
        f"Resume text:\n{resume_text}",
        f"LinkedIn URL: {linkedin_url}",
    ]
    if github_handle:
        lines.append(f"GitHub handle: {github_handle}")
    if leetcode_handle:
        lines.append(f"LeetCode handle: {leetcode_handle}")
    if extra:
        lines.append(extra)
    return "\n\n".join(lines)


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
    with urlopen(request, timeout=30) as response:
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


def _parse_score_payload(raw_content: str):
    return json.loads(_strip_json_fences(raw_content))


def _clamp_pow_score(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("powScore is not numeric")
    score = int(round(value))
    if score < POW_SCORE_MIN or score > POW_SCORE_MAX:
        logger.warning("Clamping powScore=%s into range %s-%s", score, POW_SCORE_MIN, POW_SCORE_MAX)
        score = max(POW_SCORE_MIN, min(POW_SCORE_MAX, score))
    return score


def _score_resume(resume_text, linkedin_url, github_handle, leetcode_handle):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _build_user_prompt(
                resume_text, linkedin_url, github_handle, leetcode_handle
            ),
        },
    ]
    content = _call_groq(messages)
    try:
        payload = _parse_score_payload(content)
    except (json.JSONDecodeError, TypeError, KeyError, ValueError):
        logger.warning("Groq response was not valid JSON; retrying once")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_user_prompt(
                    resume_text,
                    linkedin_url,
                    github_handle,
                    leetcode_handle,
                    extra=RETRY_JSON_INSTRUCTION,
                ),
            },
        ]
        content = _call_groq(messages)
        payload = _parse_score_payload(content)

    pow_score = _clamp_pow_score(payload.get("powScore"))
    breakdown = payload.get("breakdown")
    if breakdown is None:
        breakdown = ""
    if not isinstance(breakdown, str):
        breakdown = str(breakdown)
    return pow_score, breakdown


def _mark_failed(session_id: str, error_message: str):
    _sessions_table.update_item(
        Key={"sessionId": session_id},
        UpdateExpression="SET #status = :status, errorMessage = :error",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": "failed",
            ":error": error_message,
        },
        ConditionExpression="attribute_exists(sessionId)",
    )


def _mark_awaiting_test(session_id: str, pow_score: int, breakdown: str):
    _sessions_table.update_item(
        Key={"sessionId": session_id},
        UpdateExpression=(
            "SET #status = :status, powScore = :score, powBreakdown = :breakdown "
            "REMOVE errorMessage"
        ),
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": "awaiting_test",
            ":score": pow_score,
            ":breakdown": breakdown,
        },
        ConditionExpression="attribute_exists(sessionId)",
    )


def _process_record(record):
    bucket = record["s3"]["bucket"]["name"]
    key = unquote_plus(record["s3"]["object"]["key"])
    parsed = _parse_resume_key(key)
    if parsed is None:
        logger.error("Malformed resume S3 key, ignoring: %s", key)
        return {"key": key, "status": "ignored"}

    user_id, session_id = parsed
    may_update_session = False

    try:
        try:
            get_response = _sessions_table.get_item(Key={"sessionId": session_id})
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error("DynamoDB GetItem failed for match_sessions: %s", error_code)
            try:
                _mark_failed(session_id, "Could not look up match session")
            except ClientError as mark_error:
                mark_code = mark_error.response.get("Error", {}).get("Code", "Unknown")
                logger.error(
                    "Failed to mark session failed sessionId=%s: %s",
                    session_id,
                    mark_code,
                )
            return {"key": key, "status": "failed", "reason": "lookup"}

        session_item = get_response.get("Item")
        if session_item is None:
            logger.error(
                "No match_sessions item for sessionId=%s key=%s; stopping without write",
                session_id,
                key,
            )
            return {"key": key, "status": "ignored"}

        if session_item.get("userId") != user_id:
            logger.error(
                "S3 key userId does not match session owner sessionId=%s; stopping without write",
                session_id,
            )
            return {"key": key, "status": "ignored"}

        may_update_session = True
        linkedin_url = session_item.get("linkedinUrl") or ""
        github_handle = session_item.get("githubHandle")
        leetcode_handle = session_item.get("leetcodeHandle")

        try:
            obj = _s3.get_object(Bucket=bucket, Key=key)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error("S3 GetObject failed key=%s: %s", key, error_code)
            raise

        data = obj["Body"].read()
        content_type = obj.get("ContentType") or ""
        file_type = _detect_file_type(content_type, data)

        try:
            if file_type is None:
                raise ValueError("unrecognized resume format")
            resume_text = _extract_resume_text(file_type, data)
        except Exception:
            logger.exception("Resume extraction failed key=%s", key)
            _mark_failed(session_id, ERROR_UNREADABLE)
            return {"key": key, "status": "failed", "reason": "unreadable"}

        if not resume_text or len(resume_text) < MIN_RESUME_TEXT_LENGTH:
            _mark_failed(session_id, ERROR_EMPTY_TEXT)
            return {"key": key, "status": "failed", "reason": "empty_text"}

        try:
            pow_score, breakdown = _score_resume(
                resume_text, linkedin_url, github_handle, leetcode_handle
            )
        except (json.JSONDecodeError, TypeError, KeyError, ValueError, HTTPError, URLError):
            logger.exception("AI scoring failed sessionId=%s", session_id)
            _mark_failed(session_id, ERROR_AI_SCORING)
            return {"key": key, "status": "failed", "reason": "ai_scoring"}
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error("SSM GetParameter failed: %s", error_code)
            _mark_failed(session_id, ERROR_AI_SCORING)
            return {"key": key, "status": "failed", "reason": "ai_scoring"}

        _mark_awaiting_test(session_id, pow_score, breakdown)
        logger.info(
            "Resume scored sessionId=%s userId=%s powScore=%s",
            session_id,
            user_id,
            pow_score,
        )
        return {"key": key, "status": "awaiting_test", "powScore": pow_score}

    except Exception:
        logger.exception("Unexpected error processing resume key=%s", key)
        if may_update_session:
            try:
                _mark_failed(session_id, ERROR_UNEXPECTED)
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                logger.error(
                    "Failed to mark session failed sessionId=%s: %s",
                    session_id,
                    error_code,
                )
        return {"key": key, "status": "failed", "reason": "unexpected"}


def lambda_handler(event, context):
    results = []
    for record in event.get("Records", []):
        try:
            results.append(_process_record(record))
        except Exception:
            # Record-level parse failures (missing s3 keys, etc.)
            logger.exception("Failed to process S3 record")
            results.append({"status": "failed", "reason": "unexpected"})
    return {"status": "processed", "results": results}

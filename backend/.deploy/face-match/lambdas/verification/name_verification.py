"""
ID card name verification: PaddleOCR text + Groq name comparison.

Compares the user's registered name (Cognito / Users table) against the name
read from their uploaded ID card image.
"""

import json
import logging
import os
import re
from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import boto3

from lambdas.verification.paddle_ocr import download_and_ocr_s3

logger = logging.getLogger(__name__)

REGION = os.environ.get("AWS_REGION", "ap-south-1")
GROQ_API_KEY_PARAM = os.environ.get("GROQ_API_KEY_PARAM", "/aijobportal/groq-api-key")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_API_URL = os.environ.get(
    "GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions"
)
NAME_MATCH_MIN_CONFIDENCE = float(os.environ.get("NAME_MATCH_MIN_CONFIDENCE", "70"))
NAME_VERIFICATION_ENABLED = os.environ.get("NAME_VERIFICATION_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)

_ssm = boto3.client("ssm", region_name=REGION)
_groq_api_key: Optional[str] = None


def _get_groq_api_key() -> Optional[str]:
    global _groq_api_key
    if _groq_api_key:
        return _groq_api_key
    try:
        response = _ssm.get_parameter(Name=GROQ_API_KEY_PARAM, WithDecryption=True)
        _groq_api_key = response["Parameter"]["Value"]
        return _groq_api_key
    except Exception as exc:
        logger.error("Failed to load Groq API key from SSM: %s", exc)
        return None


def _normalize_name_tokens(name: str) -> set:
    if not name:
        return set()
    cleaned = re.sub(r"[^a-zA-Z\s]", " ", name.lower())
    return {t for t in cleaned.split() if len(t) > 1}


def _heuristic_name_match(registered_name: str, ocr_text: str) -> Tuple[bool, str, float]:
    """Token overlap fallback when Groq is unavailable."""
    reg_tokens = _normalize_name_tokens(registered_name)
    ocr_tokens = _normalize_name_tokens(ocr_text)
    if not reg_tokens:
        return False, "registered_name_missing", 0.0
    if not ocr_tokens:
        return False, "ocr_empty", 0.0

    overlap = reg_tokens & ocr_tokens
    ratio = len(overlap) / len(reg_tokens)
    matched = ratio >= 0.5 and len(overlap) >= 1
    confidence = round(ratio * 100, 1)
    reason = "heuristic_match" if matched else "heuristic_mismatch"
    return matched, reason, confidence


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


def _call_groq(messages: list) -> Optional[str]:
    api_key = _get_groq_api_key()
    if not api_key:
        return None
    payload = json.dumps(
        {
            "model": GROQ_MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": messages,
        }
    ).encode("utf-8")
    request = Request(
        GROQ_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "AiJobPortal-IdVerification/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        return content if isinstance(content, str) else None
    except (HTTPError, URLError, KeyError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("Groq name comparison failed: %s", exc)
        return None


def _groq_compare_names(registered_name: str, ocr_text: str) -> Optional[Dict[str, Any]]:
    prompt = (
        "You verify whether a person's registered name matches the name on their ID card.\n"
        f"Registered name: {registered_name}\n"
        f"OCR text from ID card:\n{ocr_text}\n\n"
        "Rules:\n"
        "- Allow minor OCR errors, missing middle names, and word order differences.\n"
        "- Reject if the registered name clearly does not appear on the ID.\n"
        "- Extract the best full name you see on the ID as nameOnCard.\n"
        "Return ONLY JSON: "
        '{"match": boolean, "nameOnCard": string, "confidence": number 0-100, "reason": string}'
    )
    raw = _call_groq(
        [
            {
                "role": "system",
                "content": "You compare names on ID documents. Respond with JSON only.",
            },
            {"role": "user", "content": prompt},
        ]
    )
    if not raw:
        return None
    try:
        parsed = json.loads(_strip_json_fences(raw))
        if not isinstance(parsed, dict):
            return None
        return parsed
    except json.JSONDecodeError:
        logger.warning("Groq returned unparseable JSON for name comparison")
        return None


def _rekognition_ocr_s3(rekognition_client, bucket: str, key: str) -> str:
    """Fallback OCR via Rekognition DetectText (no Paddle dependency)."""
    if rekognition_client is None:
        return ""
    try:
        response = rekognition_client.detect_text(
            Image={"S3Object": {"Bucket": bucket, "Name": key}}
        )
        lines = [
            item["DetectedText"]
            for item in response.get("TextDetections", [])
            if item.get("Type") == "LINE" and item.get("DetectedText")
        ]
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("Rekognition DetectText failed for %s/%s: %s", bucket, key, exc)
        return ""


def verify_id_name(
    s3_client,
    bucket: str,
    id_card_key: str,
    registered_name: str,
    rekognition_client=None,
) -> Dict[str, Any]:
    """
    OCR the ID card and compare names.

    Returns dict with keys: match (bool), reason (str), nameOnCard (str),
    confidence (float), ocrText (truncated preview), method (groq|heuristic|skipped).
    """
    if not NAME_VERIFICATION_ENABLED:
        return {
            "match": True,
            "reason": "name_verification_disabled",
            "nameOnCard": "",
            "confidence": 100.0,
            "ocrText": "",
            "method": "skipped",
        }

    if not registered_name or not str(registered_name).strip():
        return {
            "match": False,
            "reason": "registered_name_missing",
            "nameOnCard": "",
            "confidence": 0.0,
            "ocrText": "",
            "method": "skipped",
        }

    ocr_text = download_and_ocr_s3(s3_client, bucket, id_card_key)
    if not ocr_text.strip():
        ocr_text = _rekognition_ocr_s3(rekognition_client, bucket, id_card_key)
    ocr_preview = (ocr_text[:500] + "…") if len(ocr_text) > 500 else ocr_text

    groq_result = _groq_compare_names(registered_name.strip(), ocr_text)
    if groq_result is not None:
        try:
            confidence = float(groq_result.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        match = bool(groq_result.get("match")) and confidence >= NAME_MATCH_MIN_CONFIDENCE
        name_on_card = str(groq_result.get("nameOnCard") or "").strip()
        reason = str(groq_result.get("reason") or ("name_match" if match else "name_mismatch"))
        if groq_result.get("match") and not match:
            reason = "name_below_confidence_threshold"
        return {
            "match": match,
            "reason": reason,
            "nameOnCard": name_on_card,
            "confidence": confidence,
            "ocrText": ocr_preview,
            "method": "groq",
        }

    matched, reason, confidence = _heuristic_name_match(registered_name, ocr_text)
    return {
        "match": matched,
        "reason": reason,
        "nameOnCard": "",
        "confidence": confidence,
        "ocrText": ocr_preview,
        "method": "heuristic",
    }

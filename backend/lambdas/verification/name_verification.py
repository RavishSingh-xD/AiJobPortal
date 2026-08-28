"""
ID card name verification: OCR text + deterministic name matching.

Decision rule is binary and rule-based (not a confidence/probability gate):
every significant token of the registered name must appear in the OCR text
(or in the extracted card name), after OCR-noise normalization.

Groq is used only as an optional name extractor from OCR text. Its
"confidence" score never decides accept/reject.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple
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
NAME_VERIFICATION_ENABLED = os.environ.get("NAME_VERIFICATION_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
# Ignore very short tokens (initials like "A" still allowed when len==1? we keep
# single-letter tokens only if the registered name itself uses them).
MIN_TOKEN_LEN = 2

# Common OCR confusions → canonical latin letters.
_OCR_CONFUSABLES = str.maketrans(
    {
        "0": "o",
        "1": "l",
        "5": "s",
        "8": "b",
        "@": "a",
        "$": "s",
        "|": "l",
        "!": "i",
    }
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


def normalize_name_text(value: str) -> str:
    """Lowercase, strip accents/punctuation, fix common OCR letter swaps."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().translate(_OCR_CONFUSABLES)
    text = re.sub(r"[^a-z\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def name_tokens(value: str, *, min_len: int = MIN_TOKEN_LEN) -> List[str]:
    normalized = normalize_name_text(value)
    if not normalized:
        return []
    tokens = [t for t in normalized.split(" ") if t]
    # Keep short tokens only when the whole name is short (e.g. "Li Bo").
    if any(len(t) >= min_len for t in tokens):
        return [t for t in tokens if len(t) >= min_len]
    return tokens


def _token_present(token: str, haystack_tokens: Set[str], haystack_text: str) -> bool:
    if token in haystack_tokens:
        return True
    # Contiguous substring for OCR glued/split noise (e.g. "priyeshbarhate").
    if len(token) >= MIN_TOKEN_LEN and token in haystack_text.replace(" ", ""):
        return True
    # Allow 1-char OCR typo inside a long token via exact neighbor match.
    if len(token) >= 4:
        for hay in haystack_tokens:
            if abs(len(hay) - len(token)) > 1:
                continue
            # Hamming-ish: at most one substitution, same length; or one insert/delete.
            if _edit_distance_at_most_one(token, hay):
                return True
    return False


def _edit_distance_at_most_one(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diffs = sum(1 for x, y in zip(a, b) if x != y)
        return diffs == 1
    # Ensure a is shorter.
    if len(a) > len(b):
        a, b = b, a
    i = j = 0
    skipped = False
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        if skipped:
            return False
        skipped = True
        j += 1
    return True


def deterministic_name_match(registered_name: str, *sources: str) -> Tuple[bool, str, float]:
    """
    Accept only when every registered name token is found in the combined
    OCR / extracted-name sources. Confidence is informational only (0 or 100).
    """
    reg_tokens = name_tokens(registered_name)
    if not reg_tokens:
        return False, "registered_name_missing", 0.0

    combined = "\n".join(s for s in sources if s and str(s).strip())
    haystack_text = normalize_name_text(combined)
    if not haystack_text:
        return False, "ocr_empty", 0.0

    haystack_tokens = set(name_tokens(haystack_text, min_len=1))
    compact = haystack_text.replace(" ", "")

    # Exact full-name equality or contiguous phrase.
    reg_norm = normalize_name_text(registered_name)
    if reg_norm and (reg_norm == haystack_text or reg_norm in haystack_text):
        return True, "exact_name_match", 100.0
    if reg_norm.replace(" ", "") and reg_norm.replace(" ", "") in compact:
        return True, "exact_name_match_compact", 100.0

    missing = [
        token
        for token in reg_tokens
        if not _token_present(token, haystack_tokens, haystack_text)
    ]
    if missing:
        return False, f"missing_tokens:{','.join(missing)}", 0.0

    return True, "all_tokens_present", 100.0


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
        logger.warning("Groq name extraction failed: %s", exc)
        return None


def _groq_extract_name_on_card(registered_name: str, ocr_text: str) -> Optional[str]:
    """Ask Groq only to extract the ID card name — never to decide match."""
    prompt = (
        "Extract the person's full name printed on this ID card from the OCR text.\n"
        f"Registered name (context only, do not invent): {registered_name}\n"
        f"OCR text:\n{ocr_text}\n\n"
        "Return ONLY JSON: {\"nameOnCard\": string}\n"
        "If no person name is visible, return {\"nameOnCard\": \"\"}."
    )
    raw = _call_groq(
        [
            {
                "role": "system",
                "content": "You extract names from ID OCR text. Respond with JSON only.",
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
        name = str(parsed.get("nameOnCard") or "").strip()
        return name or None
    except json.JSONDecodeError:
        logger.warning("Groq returned unparseable JSON for name extraction")
        return None


def _rekognition_ocr_s3(rekognition_client, bucket: str, key: str) -> str:
    """OCR via Rekognition DetectText (LINE + high-confidence WORDs)."""
    if rekognition_client is None:
        return ""
    try:
        response = rekognition_client.detect_text(
            Image={"S3Object": {"Bucket": bucket, "Name": key}}
        )
    except Exception as exc:
        logger.warning("Rekognition DetectText failed for %s/%s: %s", bucket, key, exc)
        return ""

    lines: List[str] = []
    words: List[str] = []
    for item in response.get("TextDetections", []) or []:
        text = (item.get("DetectedText") or "").strip()
        if not text:
            continue
        confidence = float(item.get("Confidence") or 0)
        kind = item.get("Type")
        # Keep only high-confidence detections to reduce OCR garbage.
        if kind == "LINE" and confidence >= 80:
            lines.append(text)
        elif kind == "WORD" and confidence >= 85:
            words.append(text)

    if lines:
        return "\n".join(lines)
    return " ".join(words)


def _merge_ocr_texts(*parts: str) -> str:
    seen = set()
    ordered: List[str] = []
    for part in parts:
        for line in str(part or "").splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            key = normalize_name_text(cleaned)
            if not key or key in seen:
                continue
            seen.add(key)
            ordered.append(cleaned)
    return "\n".join(ordered)


def verify_id_name(
    s3_client,
    bucket: str,
    id_card_key: str,
    registered_name: str,
    rekognition_client=None,
) -> Dict[str, Any]:
    """
    OCR the ID card and compare names with deterministic rules.

    Returns dict with keys: match (bool), reason (str), nameOnCard (str),
    confidence (float 0 or 100), ocrText (truncated preview), method (str).
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

    paddle_text = download_and_ocr_s3(s3_client, bucket, id_card_key)
    rekognition_text = _rekognition_ocr_s3(rekognition_client, bucket, id_card_key)
    ocr_text = _merge_ocr_texts(paddle_text, rekognition_text)
    ocr_preview = (ocr_text[:500] + "…") if len(ocr_text) > 500 else ocr_text

    name_on_card = _groq_extract_name_on_card(registered_name.strip(), ocr_text) or ""
    method = "deterministic+groq_extract" if name_on_card else "deterministic"

    matched, reason, confidence = deterministic_name_match(
        registered_name.strip(),
        ocr_text,
        name_on_card,
    )

    return {
        "match": matched,
        "reason": reason,
        "nameOnCard": name_on_card,
        "confidence": confidence,
        "ocrText": ocr_preview,
        "method": method,
    }


# Back-compat alias used by older tests / callers.
def _heuristic_name_match(registered_name: str, ocr_text: str) -> Tuple[bool, str, float]:
    return deterministic_name_match(registered_name, ocr_text)


def _normalize_name_tokens(name: str) -> set:
    return set(name_tokens(name))

"""
Heuristic + AI checks that extracted document text is a resume/CV, not
an invoice, marksheet, ID scan, or other unrelated document.
"""

import json
import re
from typing import Callable, Optional, Tuple

CLASSIFY_SYSTEM_PROMPT = (
    "You classify uploaded documents for a job-matching platform. "
    "Determine whether the text is a candidate RESUME/CV listing education, "
    "skills, work experience, internships, or projects — versus another "
    "document type (invoice, receipt, bill, marksheet, admit card, ID card, "
    "certificate only, bank statement, cover letter with no experience details, "
    "article, or random letter). "
    "A cover letter alone without resume-style career details is NOT a resume. "
    "Respond ONLY with valid JSON, no markdown: "
    '{"isResume": true|false, "documentType": "resume|invoice|marksheet|id_card|certificate|letter|other", "reason": "one short sentence"}'
)

STRONG_NON_RESUME_PHRASES = (
    "tax invoice",
    "invoice number",
    "invoice no",
    "bill to",
    "amount due",
    "amount payable",
    "bank statement",
    "purchase order",
    "payment receipt",
    "marksheet",
    "mark sheet",
    "admit card",
    "hall ticket",
    "electricity bill",
    "power bill",
    "proforma invoice",
    "gstin",
    "identity card",
    "aadhaar",
    "passport no",
)

RESUME_SIGNAL_PHRASES = (
    "experience",
    "education",
    "skills",
    "project",
    "employment",
    "internship",
    "qualification",
    "objective",
    "summary",
    "resume",
    "curriculum vitae",
    "work history",
    "professional summary",
    "technical skills",
    "certification",
)

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_PATTERN = re.compile(r"(?:\+?\d[\d\s\-().]{7,}\d)")


def _strip_json_fences(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    return stripped


def _heuristic_check(text: str) -> Tuple[Optional[bool], str]:
    lower = (text or "").lower()
    if not lower.strip():
        return False, "Document has no readable text."

    strong_non_hits = sum(1 for phrase in STRONG_NON_RESUME_PHRASES if phrase in lower)
    if strong_non_hits >= 2:
        return False, "Document looks like an invoice, bill, or certificate — not a resume."
    if strong_non_hits == 1 and "invoice" in lower and "experience" not in lower:
        return False, "Document appears to be an invoice or payment record."

    resume_hits = sum(1 for phrase in RESUME_SIGNAL_PHRASES if phrase in lower)
    has_contact = bool(EMAIL_PATTERN.search(lower) or PHONE_PATTERN.search(lower))

    if resume_hits >= 2 and has_contact:
        return True, "Resume structure detected."
    if resume_hits >= 3:
        return True, "Resume keywords detected."

    return None, "borderline"


def _classify_with_groq(
    resume_text: str, call_groq: Callable[[list], str]
) -> Tuple[bool, str]:
    snippet = resume_text[:8000]
    messages = [
        {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
        {"role": "user", "content": f"Document text:\n{snippet}"},
    ]
    raw = call_groq(messages)
    payload = json.loads(_strip_json_fences(raw))
    is_resume = payload.get("isResume")
    if not isinstance(is_resume, bool):
        raise ValueError("Classifier returned invalid isResume value")
    reason = payload.get("reason") or payload.get("documentType") or ""
    if not isinstance(reason, str):
        reason = str(reason)
    if is_resume:
        return True, reason
    return False, reason or "Document is not a resume."


def verify_is_resume(
    resume_text: str,
    call_groq: Optional[Callable[[list], str]] = None,
) -> Tuple[bool, str]:
    """
    Returns (True, reason) if the text is a resume, else (False, reason).
  When heuristics are inconclusive, uses Groq via call_groq (required).
    """
    verdict, reason = _heuristic_check(resume_text)
    if verdict is True:
        return True, reason
    if verdict is False:
        return False, reason
    if call_groq is None:
        return False, "Could not verify that this document is a resume."
    return _classify_with_groq(resume_text, call_groq)

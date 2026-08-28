"""
PaddleOCR wrapper for ID card text extraction.

Used only inside the face-match Lambda container image (see Dockerfile).
Import is optional at runtime — if PaddleOCR is not installed, callers get
empty OCR text and Rekognition OCR / name heuristics may still run.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Drop low-confidence OCR fragments so garbage characters do not dilute matching.
MIN_LINE_CONFIDENCE = float(__import__("os").environ.get("OCR_MIN_LINE_CONFIDENCE", "0.80"))

_ocr_engine = None
_init_failed = False


def _get_ocr_engine():
    global _ocr_engine, _init_failed
    if _init_failed:
        return None
    if _ocr_engine is not None:
        return _ocr_engine
    try:
        from paddleocr import PaddleOCR

        _ocr_engine = PaddleOCR(
            use_angle_cls=True,
            lang="en",
            show_log=False,
            use_gpu=False,
        )
        logger.info("PaddleOCR engine initialized")
        return _ocr_engine
    except Exception as exc:
        _init_failed = True
        logger.error("PaddleOCR init failed: %s", exc)
        return None


def _parse_ocr_line(line) -> Optional[Tuple[str, float]]:
    """Paddle line shape: [box, (text, confidence)]."""
    if not line or len(line) < 2:
        return None
    payload = line[1]
    text = ""
    confidence = 0.0
    if isinstance(payload, (list, tuple)) and payload:
        text = str(payload[0] or "").strip()
        if len(payload) > 1:
            try:
                confidence = float(payload[1])
            except (TypeError, ValueError):
                confidence = 0.0
    elif isinstance(payload, str):
        text = payload.strip()
        confidence = 1.0
    if not text:
        return None
    return text, confidence


def extract_text_from_image_bytes(image_bytes: bytes) -> str:
    """Run OCR on raw image bytes; returns high-confidence lines only."""
    engine = _get_ocr_engine()
    if engine is None:
        return ""

    try:
        from PIL import Image, ImageOps, ImageFilter

        image = Image.open(BytesIO(image_bytes))
        # Mild preprocessing: upright grayscale + contrast helps ID cards.
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        gray = ImageOps.grayscale(image)
        gray = ImageOps.autocontrast(gray)
        gray = gray.filter(ImageFilter.SHARPEN)
        rgb = gray.convert("RGB")
        result = engine.ocr(rgb, cls=True)
    except Exception as exc:
        logger.error("PaddleOCR processing failed: %s", exc)
        return ""

    lines: List[str] = []
    if not result:
        return ""

    for page in result:
        if not page:
            continue
        for line in page:
            parsed = _parse_ocr_line(line)
            if not parsed:
                continue
            text, confidence = parsed
            if confidence < MIN_LINE_CONFIDENCE:
                continue
            lines.append(text)

    return "\n".join(lines)


def download_and_ocr_s3(s3_client, bucket: str, key: str) -> str:
    """Fetch an S3 object and return OCR text."""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
    except Exception as exc:
        logger.error("S3 GetObject failed for %s/%s: %s", bucket, key, exc)
        return ""
    return extract_text_from_image_bytes(body)

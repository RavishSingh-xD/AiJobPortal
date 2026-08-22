"""
PaddleOCR wrapper for ID card text extraction.

Used only inside the face-match Lambda container image (see Dockerfile).
Import is optional at runtime — if PaddleOCR is not installed, callers get
empty OCR text and Groq/name heuristics may still run on whatever text exists.
"""

import logging
from io import BytesIO
from typing import List, Optional

logger = logging.getLogger(__name__)

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


def extract_text_from_image_bytes(image_bytes: bytes) -> str:
    """Run OCR on raw image bytes; returns concatenated lines."""
    engine = _get_ocr_engine()
    if engine is None:
        return ""

    try:
        from PIL import Image

        image = Image.open(BytesIO(image_bytes))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        result = engine.ocr(image, cls=True)
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
            if not line or len(line) < 2:
                continue
            text = line[1][0]
            if isinstance(text, str) and text.strip():
                lines.append(text.strip())

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

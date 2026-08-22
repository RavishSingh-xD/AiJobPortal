"""
Tests for name_verification.py (OCR + Groq name matching).
"""

from unittest.mock import patch

from lambdas.verification import name_verification as nv


def _name_match_result():
    return {
        "match": True,
        "reason": "name_match",
        "nameOnCard": "Jane Doe",
        "confidence": 92.0,
        "ocrText": "Jane Doe\nCollege ID",
        "method": "groq",
    }


@patch.object(nv, "download_and_ocr_s3", return_value="Jane Doe Student ID")
@patch.object(nv, "_groq_compare_names")
def test_groq_match_above_threshold(mock_groq, mock_ocr):
    mock_groq.return_value = {
        "match": True,
        "nameOnCard": "Jane Doe",
        "confidence": 95,
        "reason": "names align",
    }
    result = nv.verify_id_name(None, "bucket", "key", "Jane Doe")
    assert result["match"] is True
    assert result["method"] == "groq"
    assert result["nameOnCard"] == "Jane Doe"


@patch.object(nv, "download_and_ocr_s3", return_value="Someone Else")
@patch.object(nv, "_groq_compare_names")
def test_groq_mismatch_rejects(mock_groq, mock_ocr):
    mock_groq.return_value = {
        "match": False,
        "nameOnCard": "Someone Else",
        "confidence": 90,
        "reason": "different person",
    }
    result = nv.verify_id_name(None, "bucket", "key", "Jane Doe")
    assert result["match"] is False
    assert result["method"] == "groq"


@patch.object(nv, "download_and_ocr_s3", return_value="Jane Doe ID Card")
@patch.object(nv, "_groq_compare_names", return_value=None)
def test_heuristic_fallback_when_groq_fails(mock_groq, mock_ocr):
    result = nv.verify_id_name(None, "bucket", "key", "Jane Doe")
    assert result["method"] == "heuristic"
    assert result["match"] is True


@patch.object(nv, "NAME_VERIFICATION_ENABLED", False)
def test_disabled_skips_check():
    result = nv.verify_id_name(None, "bucket", "key", "Jane Doe")
    assert result["match"] is True
    assert result["method"] == "skipped"


def test_heuristic_mismatch():
    matched, reason, conf = nv._heuristic_name_match("Alice Smith", "Bob Jones card")
    assert matched is False
    assert reason == "heuristic_mismatch"

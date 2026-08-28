"""
Tests for name_verification.py (deterministic OCR name matching).
"""

from unittest.mock import patch

from lambdas.verification import name_verification as nv


@patch.object(nv, "download_and_ocr_s3", return_value="JANE DOE\nStudent ID\nRoll 123")
@patch.object(nv, "_groq_extract_name_on_card", return_value="Jane Doe")
@patch.object(nv, "_rekognition_ocr_s3", return_value="")
def test_deterministic_match_with_extracted_name(mock_rek, mock_groq, mock_ocr):
    result = nv.verify_id_name(None, "bucket", "key", "Jane Doe")
    assert result["match"] is True
    assert result["confidence"] == 100.0
    assert result["nameOnCard"] == "Jane Doe"
    assert "deterministic" in result["method"]


@patch.object(nv, "download_and_ocr_s3", return_value="SOMEONE ELSE\nID CARD")
@patch.object(nv, "_groq_extract_name_on_card", return_value="Someone Else")
@patch.object(nv, "_rekognition_ocr_s3", return_value="")
def test_mismatch_rejects(mock_rek, mock_groq, mock_ocr):
    result = nv.verify_id_name(None, "bucket", "key", "Jane Doe")
    assert result["match"] is False
    assert result["confidence"] == 0.0


@patch.object(nv, "download_and_ocr_s3", return_value="PRIYESH BARHATE COLLEGE ID")
@patch.object(nv, "_groq_extract_name_on_card", return_value=None)
@patch.object(nv, "_rekognition_ocr_s3", return_value="")
def test_all_tokens_in_ocr_without_groq(mock_rek, mock_groq, mock_ocr):
    result = nv.verify_id_name(None, "bucket", "key", "Priyesh Barhate")
    assert result["match"] is True
    assert result["method"] == "deterministic"
    assert result["confidence"] == 100.0


@patch.object(nv, "download_and_ocr_s3", return_value="BARHATE PRIYESH PRAVIN")
@patch.object(nv, "_groq_extract_name_on_card", return_value=None)
@patch.object(nv, "_rekognition_ocr_s3", return_value="")
def test_token_order_does_not_matter(mock_rek, mock_groq, mock_ocr):
    result = nv.verify_id_name(None, "bucket", "key", "Priyesh Barhate")
    assert result["match"] is True


@patch.object(nv, "download_and_ocr_s3", return_value="JANE ONLY")
@patch.object(nv, "_groq_extract_name_on_card", return_value=None)
@patch.object(nv, "_rekognition_ocr_s3", return_value="")
def test_partial_token_overlap_rejects(mock_rek, mock_groq, mock_ocr):
    """Old 50%-overlap heuristic would pass; deterministic rule must reject."""
    result = nv.verify_id_name(None, "bucket", "key", "Jane Doe")
    assert result["match"] is False
    assert "missing_tokens" in result["reason"]


@patch.object(nv, "NAME_VERIFICATION_ENABLED", False)
def test_disabled_skips_check():
    result = nv.verify_id_name(None, "bucket", "key", "Jane Doe")
    assert result["match"] is True
    assert result["method"] == "skipped"


def test_heuristic_alias_rejects_mismatch():
    matched, reason, conf = nv._heuristic_name_match("Alice Smith", "Bob Jones card")
    assert matched is False
    assert conf == 0.0


def test_ocr_confusable_normalization():
    # 0/O style noise in OCR should still match.
    matched, reason, conf = nv.deterministic_name_match("jose", "J0SE ID CARD")
    assert matched is True
    assert conf == 100.0

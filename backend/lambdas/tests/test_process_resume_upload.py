"""
Local unit tests for process_resume_upload.py.
No real AWS or Groq calls -- S3, DynamoDB, SSM, and HTTP are mocked.

Run with (from the backend/ directory):
    PYTHONPATH=. pytest lambdas/tests/test_process_resume_upload.py -v
"""

import json
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

from lambdas.match import process_resume_upload as pru

USER_A = "USER_A"
USER_B = "USER_B"
SESSION_ID = "session-123"
RESUME_KEY = f"resumes/{USER_A}/{SESSION_ID}/resume"


def make_s3_event(key=RESUME_KEY, bucket="aijobportal-verification-470361396576"):
    return {
        "Records": [
            {"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}
        ]
    }


def mock_s3_object(data: bytes, content_type="application/pdf"):
    body = MagicMock()
    body.read.return_value = data
    return {"Body": body, "ContentType": content_type}


def client_error(code="AccessDeniedException", operation="GetItem"):
    return ClientError({"Error": {"Code": code, "Message": "denied"}}, operation)


@patch.object(pru, "_ssm")
@patch.object(pru, "_sessions_table")
@patch.object(pru, "_s3")
def test_malformed_key_logs_and_does_not_touch_dynamodb(mock_s3, mock_table, mock_ssm):
    result = pru.lambda_handler(make_s3_event(key="resumes/only-two/parts"), None)

    assert result["results"][0]["status"] == "ignored"
    mock_table.get_item.assert_not_called()
    mock_table.update_item.assert_not_called()
    mock_s3.get_object.assert_not_called()


@patch.object(pru, "_ssm")
@patch.object(pru, "_sessions_table")
@patch.object(pru, "_s3")
def test_getitem_client_error_marks_lookup_failed(mock_s3, mock_table, mock_ssm):
    mock_table.get_item.side_effect = client_error("AccessDeniedException", "GetItem")
    result = pru.lambda_handler(make_s3_event(), None)

    assert result["results"][0]["status"] == "failed"
    values = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":status"] == "failed"
    assert values[":error"] == "Could not look up match session"
    mock_s3.get_object.assert_not_called()


@patch.object(pru, "_ssm")
@patch.object(pru, "_sessions_table")
@patch.object(pru, "_s3")
def test_missing_session_does_not_write(mock_s3, mock_table, mock_ssm):
    mock_table.get_item.return_value = {}
    result = pru.lambda_handler(make_s3_event(), None)

    assert result["results"][0]["status"] == "ignored"
    mock_s3.get_object.assert_not_called()
    mock_table.update_item.assert_not_called()


@patch.object(pru, "_ssm")
@patch.object(pru, "_sessions_table")
@patch.object(pru, "_s3")
def test_user_mismatch_does_not_write(mock_s3, mock_table, mock_ssm):
    mock_table.get_item.return_value = {
        "Item": {"sessionId": SESSION_ID, "userId": USER_B, "linkedinUrl": "https://linkedin.com/in/x"}
    }
    result = pru.lambda_handler(make_s3_event(), None)

    assert result["results"][0]["status"] == "ignored"
    mock_s3.get_object.assert_not_called()
    mock_table.update_item.assert_not_called()


@patch.object(pru, "_extract_resume_text")
@patch.object(pru, "_ssm")
@patch.object(pru, "_sessions_table")
@patch.object(pru, "_s3")
def test_unrecognized_file_marks_unreadable(mock_s3, mock_table, mock_ssm, mock_extract):
    mock_table.get_item.return_value = {
        "Item": {"sessionId": SESSION_ID, "userId": USER_A, "linkedinUrl": "https://linkedin.com/in/x"}
    }
    mock_s3.get_object.return_value = mock_s3_object(b"not-a-resume", content_type="text/plain")

    result = pru.lambda_handler(make_s3_event(), None)

    assert result["results"][0]["status"] == "failed"
    mock_extract.assert_not_called()
    values = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":status"] == "failed"
    assert values[":error"] == "Unsupported or unreadable resume file"


@patch.object(pru, "_extract_resume_text", side_effect=RuntimeError("parse boom"))
@patch.object(pru, "_ssm")
@patch.object(pru, "_sessions_table")
@patch.object(pru, "_s3")
def test_extraction_exception_marks_unreadable(mock_s3, mock_table, mock_ssm, mock_extract):
    mock_table.get_item.return_value = {
        "Item": {"sessionId": SESSION_ID, "userId": USER_A, "linkedinUrl": "https://linkedin.com/in/x"}
    }
    mock_s3.get_object.return_value = mock_s3_object(b"%PDF-1.4 fake")

    result = pru.lambda_handler(make_s3_event(), None)

    assert result["results"][0]["status"] == "failed"
    values = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":error"] == "Unsupported or unreadable resume file"


@patch.object(pru, "_extract_resume_text", return_value="too short")
@patch.object(pru, "_ssm")
@patch.object(pru, "_sessions_table")
@patch.object(pru, "_s3")
def test_short_text_marks_could_not_read(mock_s3, mock_table, mock_ssm, mock_extract):
    mock_table.get_item.return_value = {
        "Item": {"sessionId": SESSION_ID, "userId": USER_A, "linkedinUrl": "https://linkedin.com/in/x"}
    }
    mock_s3.get_object.return_value = mock_s3_object(b"%PDF-1.4 fake")

    result = pru.lambda_handler(make_s3_event(), None)

    assert result["results"][0]["status"] == "failed"
    values = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":error"] == "Could not read resume text"


def _owned_session():
    return {
        "Item": {
            "sessionId": SESSION_ID,
            "userId": USER_A,
            "linkedinUrl": "https://linkedin.com/in/jane",
            "githubHandle": "jane",
            "leetcodeHandle": "jane-lc",
        }
    }


LONG_TEXT = "Experienced software intern. " * 5  # well over 50 chars


@patch.object(pru, "_users_table")
@patch.object(pru, "_call_groq")
@patch.object(pru, "_extract_resume_text", return_value=LONG_TEXT)
@patch.object(pru, "_ssm")
@patch.object(pru, "_sessions_table")
@patch.object(pru, "_s3")
def test_success_updates_awaiting_test(
    mock_s3, mock_table, mock_ssm, mock_extract, mock_groq, mock_users_table
):
    mock_table.get_item.return_value = _owned_session()
    mock_users_table.get_item.return_value = {}
    mock_s3.get_object.return_value = mock_s3_object(b"%PDF-1.4 fake")
    mock_groq.return_value = json.dumps({"powScore": 42, "breakdown": "Strong internships."})

    result = pru.lambda_handler(make_s3_event(), None)

    assert result["results"][0]["status"] == "awaiting_test"
    assert result["results"][0]["powScore"] == 42
    values = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":status"] == "awaiting_test"
    assert values[":score"] == 42
    assert values[":breakdown"] == "Strong internships."
    user_content = mock_groq.call_args.args[0][1]["content"]
    assert "https://linkedin.com/in/jane" in user_content
    assert "jane" in user_content
    assert "jane-lc" in user_content
    assert LONG_TEXT in user_content


@patch.object(pru, "_users_table")
@patch.object(pru, "_call_groq")
@patch.object(pru, "_extract_resume_text", return_value=LONG_TEXT)
@patch.object(pru, "_ssm")
@patch.object(pru, "_sessions_table")
@patch.object(pru, "_s3")
def test_groq_retries_once_on_invalid_json(
    mock_s3, mock_table, mock_ssm, mock_extract, mock_groq, mock_users_table
):
    mock_table.get_item.return_value = _owned_session()
    mock_users_table.get_item.return_value = {}
    mock_s3.get_object.return_value = mock_s3_object(b"%PDF-1.4 fake")
    mock_groq.side_effect = [
        "not json",
        json.dumps({"powScore": 10, "breakdown": "ok"}),
    ]

    result = pru.lambda_handler(make_s3_event(), None)

    assert result["results"][0]["status"] == "awaiting_test"
    assert mock_groq.call_count == 2
    retry_content = mock_groq.call_args_list[1].args[0][1]["content"]
    assert "ONLY the JSON object" in retry_content


@patch.object(pru, "_users_table")
@patch.object(pru, "_call_groq", return_value="still not json")
@patch.object(pru, "_extract_resume_text", return_value=LONG_TEXT)
@patch.object(pru, "_ssm")
@patch.object(pru, "_sessions_table")
@patch.object(pru, "_s3")
def test_groq_parse_failure_marks_ai_scoring_failed(
    mock_s3, mock_table, mock_ssm, mock_extract, mock_groq, mock_users_table
):
    mock_table.get_item.return_value = _owned_session()
    mock_users_table.get_item.return_value = {}
    mock_s3.get_object.return_value = mock_s3_object(b"%PDF-1.4 fake")

    result = pru.lambda_handler(make_s3_event(), None)

    assert result["results"][0]["status"] == "failed"
    values = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":error"] == "AI scoring failed"
    assert mock_groq.call_count == 2


@patch.object(pru, "_users_table")
@patch.object(pru, "_call_groq")
@patch.object(pru, "_extract_resume_text", return_value=LONG_TEXT)
@patch.object(pru, "_ssm")
@patch.object(pru, "_sessions_table")
@patch.object(pru, "_s3")
def test_pow_score_is_clamped(
    mock_s3, mock_table, mock_ssm, mock_extract, mock_groq, mock_users_table
):
    mock_table.get_item.return_value = _owned_session()
    mock_users_table.get_item.return_value = {}
    mock_s3.get_object.return_value = mock_s3_object(b"%PDF-1.4 fake")
    mock_groq.return_value = json.dumps({"powScore": 99, "breakdown": "too high"})

    result = pru.lambda_handler(make_s3_event(), None)

    assert result["results"][0]["powScore"] == 50
    values = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":score"] == 50


@patch.object(pru, "_s3")
@patch.object(pru, "_ssm")
@patch.object(pru, "_sessions_table")
def test_unexpected_error_after_ownership_check_marks_session_failed(
    mock_table, mock_ssm, mock_s3
):
    mock_table.get_item.return_value = _owned_session()
    mock_s3.get_object.side_effect = RuntimeError("boom")

    result = pru.lambda_handler(make_s3_event(), None)

    assert result["results"][0]["status"] == "failed"
    values = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":error"] == "Unexpected error during resume processing"


@patch.object(pru, "_users_table")
@patch.object(pru, "_ssm")
@patch.object(pru, "_sessions_table")
@patch.object(pru, "_s3")
def test_magic_bytes_detect_pdf_when_content_type_ambiguous(
    mock_s3, mock_table, mock_ssm, mock_users_table
):
    mock_table.get_item.return_value = _owned_session()
    mock_users_table.get_item.return_value = {}
    mock_s3.get_object.return_value = mock_s3_object(
        b"%PDF-1.4 rest", content_type="application/octet-stream"
    )
    with patch.object(pru, "_extract_resume_text", return_value=LONG_TEXT) as extract, patch.object(
        pru, "_call_groq", return_value=json.dumps({"powScore": 1, "breakdown": "x"})
    ):
        pru.lambda_handler(make_s3_event(), None)
        extract.assert_called_once()
        assert extract.call_args.args[0] == "pdf"


def test_detect_docx_from_pk_magic():
    assert pru._detect_file_type("", b"PK\x03\x04rest") == "docx"


def test_detect_pdf_from_content_type():
    assert pru._detect_file_type("application/pdf", b"ignored") == "pdf"


@patch.object(pru, "_ssm")
def test_groq_api_key_is_cached(mock_ssm):
    pru._groq_api_key = None
    mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "secret-key"}}

    assert pru._get_groq_api_key() == "secret-key"
    assert pru._get_groq_api_key() == "secret-key"
    mock_ssm.get_parameter.assert_called_once_with(
        Name="/aijobportal/groq-api-key", WithDecryption=True
    )
    pru._groq_api_key = None


def test_normalize_linkedin_url_variants_match():
    urls = [
        "https://www.linkedin.com/in/jane/",
        "https://linkedin.com/in/jane",
        "HTTPS://LinkedIn.com/in/jane/",
    ]
    normalized = [pru._normalize_linkedin_url(u) for u in urls]
    assert normalized[0] == normalized[1] == normalized[2]


def test_compute_pow_fingerprint_same_inputs_same_hash():
    resume = b"%PDF-1.4 same resume bytes"
    fp1 = pru._compute_pow_fingerprint(
        "https://www.linkedin.com/in/jane/", "Jane", "Jane-LC", resume
    )
    fp2 = pru._compute_pow_fingerprint(
        "https://linkedin.com/in/jane", "jane", "jane-lc", resume
    )
    assert fp1 == fp2


@patch.object(pru, "_users_table")
@patch.object(pru, "_call_groq")
@patch.object(pru, "_extract_resume_text", return_value=LONG_TEXT)
@patch.object(pru, "_ssm")
@patch.object(pru, "_sessions_table")
@patch.object(pru, "_s3")
def test_cached_pow_score_skips_groq(
    mock_s3, mock_table, mock_ssm, mock_extract, mock_groq, mock_users_table
):
    resume_bytes = b"%PDF-1.4 fake cached resume"
    fingerprint = pru._compute_pow_fingerprint(
        "https://linkedin.com/in/jane", "jane", "jane-lc", resume_bytes
    )
    mock_table.get_item.return_value = _owned_session()
    mock_users_table.get_item.return_value = {
        "Item": {
            "userId": USER_A,
            "powScoreFingerprint": fingerprint,
            "powScore": 37,
            "powBreakdown": "Cached breakdown.",
        }
    }
    mock_s3.get_object.return_value = mock_s3_object(resume_bytes)

    result = pru.lambda_handler(make_s3_event(), None)

    assert result["results"][0]["status"] == "awaiting_test"
    assert result["results"][0]["powScore"] == 37
    assert result["results"][0]["cached"] is True
    mock_groq.assert_not_called()
    mock_users_table.update_item.assert_not_called()
    values = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":score"] == 37
    assert values[":breakdown"] == "Cached breakdown."
    assert values[":fingerprint"] == fingerprint


@patch.object(pru, "_users_table")
@patch.object(pru, "_call_groq")
@patch.object(pru, "_extract_resume_text", return_value=LONG_TEXT)
@patch.object(pru, "_ssm")
@patch.object(pru, "_sessions_table")
@patch.object(pru, "_s3")
def test_new_pow_score_is_stored_on_users_table(
    mock_s3, mock_table, mock_ssm, mock_extract, mock_groq, mock_users_table
):
    resume_bytes = b"%PDF-1.4 new score resume"
    mock_table.get_item.return_value = _owned_session()
    mock_users_table.get_item.return_value = {}
    mock_s3.get_object.return_value = mock_s3_object(resume_bytes)
    mock_groq.return_value = json.dumps({"powScore": 25, "breakdown": "Fresh score."})

    result = pru.lambda_handler(make_s3_event(), None)

    assert result["results"][0]["cached"] is False
    mock_groq.assert_called_once()
    cache_kwargs = mock_users_table.update_item.call_args.kwargs
    cache_values = cache_kwargs["ExpressionAttributeValues"]
    assert cache_values[":score"] == 25
    assert cache_values[":breakdown"] == "Fresh score."
    expected_fp = pru._compute_pow_fingerprint(
        "https://linkedin.com/in/jane", "jane", "jane-lc", resume_bytes
    )
    assert cache_values[":fingerprint"] == expected_fp

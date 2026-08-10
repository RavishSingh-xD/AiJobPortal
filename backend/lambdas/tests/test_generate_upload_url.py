"""
Local unit tests for generate_upload_url.py.
No real AWS calls -- the S3 client's generate_presigned_url is mocked.

Run with (from the backend/ directory):
    python3 -m pytest lambdas/tests/test_generate_upload_url.py -v
"""

import json
from unittest.mock import patch
from lambdas.verification import generate_upload_url


def make_event(body_dict):
    return {"body": json.dumps(body_dict)}


@patch.object(generate_upload_url, "_s3")
@patch.object(generate_upload_url, "VERIFICATION_BUCKET", "test-bucket")
def test_valid_selfie_request_returns_url(mock_s3):
    mock_s3.generate_presigned_url.return_value = "https://example.com/presigned-url"

    event = make_event({"userId": "user-123", "fileType": "selfie"})
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["uploadUrl"] == "https://example.com/presigned-url"
    assert body["key"] == "verification/user-123/selfie.jpg"


@patch.object(generate_upload_url, "_s3")
@patch.object(generate_upload_url, "VERIFICATION_BUCKET", "test-bucket")
def test_valid_id_card_request_returns_url(mock_s3):
    mock_s3.generate_presigned_url.return_value = "https://example.com/presigned-url"

    event = make_event({"userId": "user-123", "fileType": "id_card"})
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["key"] == "verification/user-123/id_card.jpg"


@patch.object(generate_upload_url, "VERIFICATION_BUCKET", "test-bucket")
def test_invalid_file_type_rejected():
    event = make_event({"userId": "user-123", "fileType": "passport_photo"})
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 400
    assert "fileType" in json.loads(result["body"])["error"]


@patch.object(generate_upload_url, "VERIFICATION_BUCKET", "test-bucket")
def test_missing_user_id_rejected():
    event = make_event({"fileType": "selfie"})
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 400
    assert "userId" in json.loads(result["body"])["error"]


@patch.object(generate_upload_url, "VERIFICATION_BUCKET", "test-bucket")
def test_malformed_json_body_rejected():
    event = {"body": "not valid json{{{"}
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 400


@patch.object(generate_upload_url, "VERIFICATION_BUCKET", None)
def test_missing_bucket_env_var_returns_500():
    event = make_event({"userId": "user-123", "fileType": "selfie"})
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 500


@patch.object(generate_upload_url, "_s3")
@patch.object(generate_upload_url, "VERIFICATION_BUCKET", "test-bucket")
def test_s3_error_returns_500(mock_s3):
    from botocore.exceptions import ClientError

    mock_s3.generate_presigned_url.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "boom"}},
        "GeneratePresignedUrl"
    )

    event = make_event({"userId": "user-123", "fileType": "selfie"})
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 500
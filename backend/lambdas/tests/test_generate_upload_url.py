"""
Local unit tests for generate_upload_url.py.
No real AWS calls -- the S3 client's generate_presigned_url is mocked.

Run with (from the backend/ directory):
    python3 -m pytest lambdas/tests/test_generate_upload_url.py -v
"""

import json
from unittest.mock import patch
from lambdas.verification import generate_upload_url

USER_A = "USER_A"
USER_B = "USER_B"


def make_event(body_dict, sub=USER_A):
    event = {"body": json.dumps(body_dict)}
    if sub is not None:
        event["requestContext"] = {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": sub,
                    }
                }
            }
        }
    return event


@patch.object(generate_upload_url, "_users_table")
@patch.object(generate_upload_url, "_s3")
@patch.object(generate_upload_url, "VERIFICATION_BUCKET", "test-bucket")
def test_valid_jwt_selfie_returns_url_for_jwt_sub(mock_s3, mock_users_table):
    mock_s3.generate_presigned_url.return_value = "https://example.com/presigned-url"
    mock_users_table.get_item.return_value = {"Item": {"verificationStatus": "verified"}}

    event = make_event({"fileType": "selfie"}, sub=USER_A)
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["uploadUrl"] == "https://example.com/presigned-url"
    assert body["key"] == "verification/USER_A/selfie.jpg"


@patch.object(generate_upload_url, "_users_table")
@patch.object(generate_upload_url, "_s3")
@patch.object(generate_upload_url, "VERIFICATION_BUCKET", "test-bucket")
def test_valid_jwt_id_card_returns_url_for_jwt_sub(mock_s3, mock_users_table):
    mock_s3.generate_presigned_url.return_value = "https://example.com/presigned-url"
    mock_users_table.get_item.return_value = {"Item": {"verificationStatus": "verified"}}

    event = make_event({"fileType": "id_card"}, sub=USER_A)
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["key"] == "verification/USER_A/id_card.jpg"


@patch.object(generate_upload_url, "_users_table")
@patch.object(generate_upload_url, "_s3")
@patch.object(generate_upload_url, "VERIFICATION_BUCKET", "test-bucket")
def test_body_user_id_is_ignored_in_favor_of_jwt_sub(mock_s3, mock_users_table):
    mock_s3.generate_presigned_url.return_value = "https://example.com/presigned-url"
    mock_users_table.get_item.return_value = {"Item": {"verificationStatus": "verified"}}

    event = make_event(
        {"userId": USER_B, "fileType": "selfie"},
        sub=USER_A,
    )
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["key"] == "verification/USER_A/selfie.jpg"
    assert USER_B not in body["key"]


@patch.object(generate_upload_url, "_s3")
@patch.object(generate_upload_url, "VERIFICATION_BUCKET", "test-bucket")
def test_missing_jwt_sub_returns_unauthorized_and_does_not_call_s3(mock_s3):
    event = make_event({"fileType": "selfie"}, sub=None)
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 401
    assert json.loads(result["body"])["error"] == "Unauthorized"
    mock_s3.generate_presigned_url.assert_not_called()


@patch.object(generate_upload_url, "VERIFICATION_BUCKET", "test-bucket")
def test_invalid_file_type_rejected():
    event = make_event({"fileType": "passport_photo"})
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 400
    assert "fileType" in json.loads(result["body"])["error"]


@patch.object(generate_upload_url, "VERIFICATION_BUCKET", "test-bucket")
def test_malformed_json_body_rejected():
    event = {"body": "not valid json{{{"}
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 400


@patch.object(generate_upload_url, "VERIFICATION_BUCKET", None)
def test_missing_bucket_env_var_returns_500():
    event = make_event({"fileType": "selfie"})
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 500


@patch.object(generate_upload_url, "_users_table")
@patch.object(generate_upload_url, "_s3")
@patch.object(generate_upload_url, "VERIFICATION_BUCKET", "test-bucket")
def test_s3_error_returns_500(mock_s3, mock_users_table):
    from botocore.exceptions import ClientError

    mock_users_table.get_item.return_value = {"Item": {"verificationStatus": "verified"}}
    mock_s3.generate_presigned_url.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "boom"}},
        "GeneratePresignedUrl"
    )

    event = make_event({"fileType": "selfie"})
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 500


@patch.object(generate_upload_url, "_cognito")
@patch.object(generate_upload_url, "_users_table")
@patch.object(generate_upload_url, "_s3")
@patch.object(generate_upload_url, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(generate_upload_url, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_rejected_user_reset_to_pending_review(mock_s3, mock_users_table, mock_cognito):
    mock_s3.generate_presigned_url.return_value = "https://example.com/presigned-url"
    mock_users_table.get_item.return_value = {
        "Item": {
            "userId": USER_A,
            "email": "student@iitb.ac.in",
            "verificationStatus": "rejected",
        }
    }

    event = make_event({"fileType": "selfie"}, sub=USER_A)
    result = generate_upload_url.lambda_handler(event, None)

    assert result["statusCode"] == 200
    mock_users_table.update_item.assert_called_once()
    update_values = mock_users_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert update_values[":status"] == "pending_review"
    mock_cognito.admin_update_user_attributes.assert_called_once()

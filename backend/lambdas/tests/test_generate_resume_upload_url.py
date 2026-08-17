"""
Local unit tests for generate_resume_upload_url.py.
No real AWS calls -- DynamoDB and S3 clients are mocked.

Run with (from the backend/ directory):
    PYTHONPATH=. pytest lambdas/tests/test_generate_resume_upload_url.py -v
"""

import json
from unittest.mock import patch
from botocore.exceptions import ClientError

from lambdas.match import generate_resume_upload_url as gru

USER_A = "USER_A"
USER_B = "USER_B"
SESSION_ID = "session-123"


def make_event(body_dict=None, sub=USER_A, session_id=SESSION_ID):
    event = {"body": json.dumps(body_dict or {})}
    if session_id is not None:
        event["pathParameters"] = {"sessionId": session_id}
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


@patch.object(gru, "_s3")
@patch.object(gru, "_sessions_table")
def test_valid_request_updates_session_and_returns_upload_url(mock_table, mock_s3):
    mock_table.get_item.return_value = {"Item": {"sessionId": SESSION_ID, "userId": USER_A}}
    mock_s3.generate_presigned_url.return_value = "https://example.com/presigned"

    event = make_event({
        "linkedinUrl": "https://linkedin.com/in/jane",
        "githubHandle": "jane",
        "leetcodeHandle": "jane-lc",
    })
    result = gru.lambda_handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["uploadUrl"] == "https://example.com/presigned"
    assert body["resumeS3Key"] == f"resumes/{USER_A}/{SESSION_ID}/resume"

    update_kwargs = mock_table.update_item.call_args.kwargs
    values = update_kwargs["ExpressionAttributeValues"]
    assert values[":linkedin"] == "https://linkedin.com/in/jane"
    assert values[":github"] == "jane"
    assert values[":leetcode"] == "jane-lc"

    mock_s3.generate_presigned_url.assert_called_once()
    s3_kwargs = mock_s3.generate_presigned_url.call_args.kwargs
    assert s3_kwargs["Params"]["Key"] == body["resumeS3Key"]
    assert s3_kwargs["ExpiresIn"] == 300


@patch.object(gru, "_s3")
@patch.object(gru, "_sessions_table")
def test_optional_handles_omitted_from_update_when_not_provided(mock_table, mock_s3):
    mock_table.get_item.return_value = {"Item": {"sessionId": SESSION_ID, "userId": USER_A}}
    mock_s3.generate_presigned_url.return_value = "https://example.com/presigned"

    event = make_event({"linkedinUrl": "https://linkedin.com/in/jane"})
    result = gru.lambda_handler(event, None)

    assert result["statusCode"] == 200
    values = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert ":github" not in values
    assert ":leetcode" not in values


@patch.object(gru, "_sessions_table")
def test_missing_jwt_returns_401_and_does_not_touch_dynamodb(mock_table):
    event = make_event({"linkedinUrl": "https://linkedin.com/in/jane"}, sub=None)
    result = gru.lambda_handler(event, None)

    assert result["statusCode"] == 401
    mock_table.get_item.assert_not_called()


def test_missing_linkedin_url_returns_400():
    result = gru.lambda_handler(make_event({}), None)
    assert result["statusCode"] == 400
    assert json.loads(result["body"])["error"] == "linkedinUrl is required"


def test_linkedin_url_must_be_http():
    result = gru.lambda_handler(
        make_event({"linkedinUrl": "linkedin.com/in/jane"}),
        None,
    )
    assert result["statusCode"] == 400
    assert "http" in json.loads(result["body"])["error"]


@patch.object(gru, "_s3")
@patch.object(gru, "_sessions_table")
def test_missing_session_returns_403_with_generic_forbidden_message(mock_table, mock_s3):
    mock_table.get_item.return_value = {}
    result = gru.lambda_handler(
        make_event({"linkedinUrl": "https://linkedin.com/in/jane"}),
        None,
    )

    assert result["statusCode"] == 403
    assert json.loads(result["body"])["error"] == "Forbidden"
    mock_table.update_item.assert_not_called()
    mock_s3.generate_presigned_url.assert_not_called()


@patch.object(gru, "_s3")
@patch.object(gru, "_sessions_table")
def test_session_owned_by_another_user_returns_403_with_same_message(mock_table, mock_s3):
    mock_table.get_item.return_value = {"Item": {"sessionId": SESSION_ID, "userId": USER_B}}
    result = gru.lambda_handler(
        make_event({"linkedinUrl": "https://linkedin.com/in/jane"}, sub=USER_A),
        None,
    )

    assert result["statusCode"] == 403
    assert json.loads(result["body"])["error"] == "Forbidden"
    mock_table.update_item.assert_not_called()
    mock_s3.generate_presigned_url.assert_not_called()


@patch.object(gru, "_s3")
@patch.object(gru, "_sessions_table")
def test_dynamodb_get_error_returns_500(mock_table, mock_s3):
    mock_table.get_item.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "GetItem",
    )
    result = gru.lambda_handler(
        make_event({"linkedinUrl": "https://linkedin.com/in/jane"}),
        None,
    )
    assert result["statusCode"] == 500
    mock_s3.generate_presigned_url.assert_not_called()

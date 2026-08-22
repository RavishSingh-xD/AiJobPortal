"""Tests for retry_signup.py"""

import json
from unittest.mock import patch

from lambdas.auth import retry_signup as rs


def _post_event(email):
    return {
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps({"email": email}),
    }


@patch.object(rs, "_cognito")
@patch.object(rs, "USER_POOL_ID", "pool-test")
def test_deletes_unconfirmed_user(mock_cognito):
    mock_cognito.admin_get_user.return_value = {"UserStatus": "UNCONFIRMED"}

    result = rs.lambda_handler(_post_event("student@college.edu"), None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["action"] == "deleted"
    mock_cognito.admin_delete_user.assert_called_once()


@patch.object(rs, "_cognito")
@patch.object(rs, "USER_POOL_ID", "pool-test")
def test_confirmed_user_not_deleted(mock_cognito):
    mock_cognito.admin_get_user.return_value = {"UserStatus": "CONFIRMED"}

    result = rs.lambda_handler(_post_event("student@college.edu"), None)

    body = json.loads(result["body"])
    assert body["action"] == "confirmed"
    mock_cognito.admin_delete_user.assert_not_called()


@patch.object(rs, "_cognito")
@patch.object(rs, "USER_POOL_ID", "pool-test")
def test_not_found_user(mock_cognito):
    from botocore.exceptions import ClientError

    mock_cognito.admin_get_user.side_effect = ClientError(
        {"Error": {"Code": "UserNotFoundException", "Message": "x"}},
        "AdminGetUser",
    )

    result = rs.lambda_handler(_post_event("new@college.edu"), None)

    body = json.loads(result["body"])
    assert body["action"] == "not_found"

"""
Local unit tests for get_match_session.py.
No real AWS calls -- DynamoDB GetItem is mocked.

Run with (from the backend/ directory):
    PYTHONPATH=. pytest lambdas/tests/test_get_match_session.py -v
"""

import json
from decimal import Decimal
from unittest.mock import patch
from botocore.exceptions import ClientError

from lambdas.match import get_match_session as gms

USER_A = "USER_A"
USER_B = "USER_B"
SESSION_ID = "session-123"


def make_event(sub=USER_A, session_id=SESSION_ID):
    event = {}
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


@patch.object(gms, "_sessions_table")
def test_owned_session_returns_fields_and_omits_userid(mock_table):
    mock_table.get_item.return_value = {
        "Item": {
            "sessionId": SESSION_ID,
            "userId": USER_A,
            "status": "awaiting_test",
            "createdAt": "2026-08-16T00:00:00+00:00",
            "linkedinUrl": "https://linkedin.com/in/jane",
            "githubHandle": "jane",
            "powScore": Decimal("42"),
            "powBreakdown": "Strong internships.",
        }
    }
    result = gms.lambda_handler(make_event(), None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["sessionId"] == SESSION_ID
    assert body["status"] == "awaiting_test"
    assert body["linkedinUrl"] == "https://linkedin.com/in/jane"
    assert body["githubHandle"] == "jane"
    assert body["powScore"] == 42
    assert body["powBreakdown"] == "Strong internships."
    assert "leetcodeHandle" not in body
    assert "errorMessage" not in body
    assert "userId" not in body
    mock_table.get_item.assert_called_once_with(Key={"sessionId": SESSION_ID})


@patch.object(gms, "_sessions_table")
def test_missing_jwt_returns_401_and_does_not_touch_dynamodb(mock_table):
    result = gms.lambda_handler(make_event(sub=None), None)
    assert result["statusCode"] == 401
    mock_table.get_item.assert_not_called()


def test_missing_session_id_returns_400():
    result = gms.lambda_handler(make_event(session_id=None), None)
    assert result["statusCode"] == 400
    assert json.loads(result["body"])["error"] == "sessionId is required"


@patch.object(gms, "_sessions_table")
def test_missing_session_returns_403_with_generic_forbidden_message(mock_table):
    mock_table.get_item.return_value = {}
    result = gms.lambda_handler(make_event(), None)

    assert result["statusCode"] == 403
    assert json.loads(result["body"])["error"] == "Forbidden"


@patch.object(gms, "_sessions_table")
def test_session_owned_by_another_user_returns_403_with_same_message(mock_table):
    mock_table.get_item.return_value = {
        "Item": {"sessionId": SESSION_ID, "userId": USER_B, "status": "in_progress"}
    }
    result = gms.lambda_handler(make_event(sub=USER_A), None)

    assert result["statusCode"] == 403
    assert json.loads(result["body"])["error"] == "Forbidden"


@patch.object(gms, "_sessions_table")
def test_dynamodb_get_error_returns_500(mock_table):
    mock_table.get_item.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "GetItem",
    )
    result = gms.lambda_handler(make_event(), None)
    assert result["statusCode"] == 500
    assert "error" in json.loads(result["body"])

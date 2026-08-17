"""
Local unit tests for start_match_session.py.
No real AWS calls -- DynamoDB PutItem is mocked.

Run with (from the backend/ directory):
    PYTHONPATH=. pytest lambdas/tests/test_start_match_session.py -v
"""

import json
from unittest.mock import patch
from botocore.exceptions import ClientError

from lambdas.match import start_match_session

USER_A = "USER_A"
USER_B = "USER_B"


def make_event(body_dict=None, sub=USER_A):
    event = {"body": json.dumps(body_dict or {})}
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


@patch.object(start_match_session, "_sessions_table")
def test_valid_jwt_creates_session_and_returns_session_id(mock_table):
    event = make_event()
    result = start_match_session.lambda_handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert "sessionId" in body
    assert isinstance(body["sessionId"], str)
    assert len(body["sessionId"]) > 0

    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args.kwargs["Item"]
    assert item["sessionId"] == body["sessionId"]
    assert item["userId"] == USER_A
    assert item["status"] == "in_progress"
    assert "createdAt" in item


@patch.object(start_match_session, "_sessions_table")
def test_body_user_id_is_ignored_in_favor_of_jwt_sub(mock_table):
    event = make_event({"userId": USER_B}, sub=USER_A)
    result = start_match_session.lambda_handler(event, None)

    assert result["statusCode"] == 200
    item = mock_table.put_item.call_args.kwargs["Item"]
    assert item["userId"] == USER_A
    assert item["userId"] != USER_B


@patch.object(start_match_session, "_sessions_table")
def test_missing_jwt_sub_returns_unauthorized_and_does_not_write(mock_table):
    event = make_event(sub=None)
    result = start_match_session.lambda_handler(event, None)

    assert result["statusCode"] == 401
    assert json.loads(result["body"])["error"] == "Unauthorized"
    mock_table.put_item.assert_not_called()


@patch.object(start_match_session, "_sessions_table")
def test_dynamodb_error_returns_500(mock_table):
    mock_table.put_item.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "PutItem",
    )

    result = start_match_session.lambda_handler(make_event(), None)

    assert result["statusCode"] == 500
    assert "Could not start match session" in json.loads(result["body"])["error"]

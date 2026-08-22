"""
Local unit tests for review_verification.py.
No real AWS calls -- DynamoDB table and cognito-idp client are mocked.

Run with (from the backend/ directory):
    python3 -m pytest lambdas/tests/test_review_verification.py -v
"""

import json
from unittest.mock import patch
from lambdas.verification import review_verification


def make_event(body_dict):
    return {"body": json.dumps(body_dict)}


@patch.object(review_verification, "_cognito")
@patch.object(review_verification, "_users_table")
@patch.object(review_verification, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_approval_updates_cognito_and_dynamodb(mock_users_table, mock_cognito):
    mock_users_table.get_item.return_value = {
        "Item": {"userId": "user-123", "email": "student@iitb.ac.in"}
    }

    event = make_event({"userId": "user-123", "decision": "approved"})
    result = review_verification.lambda_handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["verificationStatus"] == "verified"

    # Cognito was updated
    cognito_kwargs = mock_cognito.admin_update_user_attributes.call_args.kwargs
    assert cognito_kwargs["Username"] == "student@iitb.ac.in"
    attrs = {a["Name"]: a["Value"] for a in cognito_kwargs["UserAttributes"]}
    assert attrs["custom:verification_status"] == "verified"

    # DynamoDB was updated
    update_kwargs = mock_users_table.update_item.call_args.kwargs
    assert update_kwargs["ExpressionAttributeValues"][":status"] == "verified"


@patch.object(review_verification, "_cognito")
@patch.object(review_verification, "_users_table")
@patch.object(review_verification, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_rejection_updates_cognito_and_dynamodb(mock_users_table, mock_cognito):
    mock_users_table.get_item.return_value = {
        "Item": {"userId": "user-123", "email": "student@gmail.com"}
    }

    event = make_event({"userId": "user-123", "decision": "rejected"})
    result = review_verification.lambda_handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["verificationStatus"] == "rejected"

    mock_cognito.admin_update_user_attributes.assert_called_once()
    cognito_kwargs = mock_cognito.admin_update_user_attributes.call_args.kwargs
    attrs = {a["Name"]: a["Value"] for a in cognito_kwargs["UserAttributes"]}
    assert attrs["custom:verification_status"] == "rejected"

    update_kwargs = mock_users_table.update_item.call_args.kwargs
    assert update_kwargs["ExpressionAttributeValues"][":status"] == "rejected"


@patch.object(review_verification, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_invalid_decision_rejected():
    event = make_event({"userId": "user-123", "decision": "maybe"})
    result = review_verification.lambda_handler(event, None)

    assert result["statusCode"] == 400
    assert "decision" in json.loads(result["body"])["error"]


@patch.object(review_verification, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_missing_user_id_rejected():
    event = make_event({"decision": "approved"})
    result = review_verification.lambda_handler(event, None)

    assert result["statusCode"] == 400


@patch.object(review_verification, "_users_table")
@patch.object(review_verification, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_user_not_found_returns_404(mock_users_table):
    mock_users_table.get_item.return_value = {}  # no Item

    event = make_event({"userId": "nonexistent-user", "decision": "approved"})
    result = review_verification.lambda_handler(event, None)

    assert result["statusCode"] == 404


@patch.object(review_verification, "USER_POOL_ID", None)
def test_missing_user_pool_id_returns_500():
    event = make_event({"userId": "user-123", "decision": "approved"})
    result = review_verification.lambda_handler(event, None)

    assert result["statusCode"] == 500


@patch.object(review_verification, "_cognito")
@patch.object(review_verification, "_users_table")
@patch.object(review_verification, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_cognito_failure_returns_500_and_skips_dynamodb_update(mock_users_table, mock_cognito):
    from botocore.exceptions import ClientError

    mock_users_table.get_item.return_value = {
        "Item": {"userId": "user-123", "email": "student@iitb.ac.in"}
    }
    mock_cognito.admin_update_user_attributes.side_effect = ClientError(
        {"Error": {"Code": "UserNotFoundException", "Message": "boom"}},
        "AdminUpdateUserAttributes"
    )

    event = make_event({"userId": "user-123", "decision": "approved"})
    result = review_verification.lambda_handler(event, None)

    assert result["statusCode"] == 500
    mock_users_table.update_item.assert_not_called()
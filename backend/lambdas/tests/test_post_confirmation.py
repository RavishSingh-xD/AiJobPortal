"""
Local unit tests for post_confirmation.py.
No real AWS calls -- DynamoDB tables and the cognito-idp client are mocked.

Run with (from the backend/ directory):
    cd backend
    python3 -m pytest lambdas/tests/test_post_confirmation.py -v
"""

from unittest.mock import patch
from botocore.exceptions import ClientError

from lambdas.auth import post_confirmation


def make_event(
    email,
    sub="test-sub-123",
    name="Test User",
    user_pool_id="ap-south-1_TESTPOOL",
    username="testuser",
    trigger_source="PostConfirmation_ConfirmSignUp",
):
    return {
        "triggerSource": trigger_source,
        "userPoolId": user_pool_id,
        "userName": username,
        "request": {
            "userAttributes": {
                "email": email,
                "sub": sub,
                "name": name,
            }
        },
        "response": {},
    }


@patch.object(post_confirmation, "_cognito")
@patch.object(post_confirmation, "_users_table")
@patch.object(post_confirmation, "_college_domains_table")
def test_college_domain_creates_verified_record(
    mock_domains_table, mock_users_table, mock_cognito
):
    mock_domains_table.get_item.return_value = {
        "Item": {"domain": "iitb.ac.in", "collegeName": "IIT Bombay"}
    }

    event = make_event("student@iitb.ac.in")
    result = post_confirmation.lambda_handler(event, None)

    call_kwargs = mock_cognito.admin_update_user_attributes.call_args.kwargs
    attrs = {a["Name"]: a["Value"] for a in call_kwargs["UserAttributes"]}
    assert attrs["custom:verification_type"] == "college_email"
    assert attrs["custom:verification_status"] == "verified"
    assert attrs["custom:college_name"] == "IIT Bombay"

    put_kwargs = mock_users_table.put_item.call_args.kwargs
    item = put_kwargs["Item"]
    assert item["userId"] == "test-sub-123"
    assert item["verificationType"] == "college_email"
    assert item["verificationStatus"] == "verified"
    assert "idCardImageKey" not in item
    assert "selfieImageKey" not in item

    assert result == event


@patch.object(post_confirmation, "_cognito")
@patch.object(post_confirmation, "_users_table")
@patch.object(post_confirmation, "_college_domains_table")
def test_non_college_domain_creates_pending_record(
    mock_domains_table, mock_users_table, mock_cognito
):
    mock_domains_table.get_item.return_value = {}

    event = make_event("student@gmail.com")
    post_confirmation.lambda_handler(event, None)

    call_kwargs = mock_cognito.admin_update_user_attributes.call_args.kwargs
    attrs = {a["Name"]: a["Value"] for a in call_kwargs["UserAttributes"]}
    assert attrs["custom:verification_type"] == "manual"
    assert attrs["custom:verification_status"] == "pending_review"
    assert attrs["custom:college_name"] == ""

    put_kwargs = mock_users_table.put_item.call_args.kwargs
    assert put_kwargs["Item"]["verificationType"] == "manual"
    assert put_kwargs["Item"]["verificationStatus"] == "pending_review"


@patch.object(post_confirmation, "_cognito")
@patch.object(post_confirmation, "_users_table")
@patch.object(post_confirmation, "_college_domains_table")
def test_dynamodb_putitem_failure_raises(
    mock_domains_table, mock_users_table, mock_cognito
):
    mock_domains_table.get_item.return_value = {}
    mock_users_table.put_item.side_effect = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "boom"}},
        "PutItem",
    )

    event = make_event("student@gmail.com")

    try:
        post_confirmation.lambda_handler(event, None)
        assert False, "expected ClientError to propagate"
    except ClientError:
        pass

    mock_cognito.admin_update_user_attributes.assert_not_called()


@patch.object(post_confirmation, "_cognito")
@patch.object(post_confirmation, "_users_table")
@patch.object(post_confirmation, "_college_domains_table")
def test_cognito_failure_still_keeps_users_record(
    mock_domains_table, mock_users_table, mock_cognito
):
    mock_domains_table.get_item.return_value = {}
    mock_cognito.admin_update_user_attributes.side_effect = ClientError(
        {"Error": {"Code": "UserNotFoundException", "Message": "boom"}},
        "AdminUpdateUserAttributes",
    )

    event = make_event("student@gmail.com")
    result = post_confirmation.lambda_handler(event, None)

    mock_users_table.put_item.assert_called_once()
    assert result == event


@patch.object(post_confirmation, "_cognito")
@patch.object(post_confirmation, "_users_table")
@patch.object(post_confirmation, "_college_domains_table")
def test_userid_matches_cognito_sub(
    mock_domains_table, mock_users_table, mock_cognito
):
    mock_domains_table.get_item.return_value = {}

    event = make_event("someone@example.com", sub="unique-sub-abc-999")
    post_confirmation.lambda_handler(event, None)

    put_kwargs = mock_users_table.put_item.call_args.kwargs
    assert put_kwargs["Item"]["userId"] == "unique-sub-abc-999"


@patch.object(post_confirmation, "_cognito")
@patch.object(post_confirmation, "_users_table")
@patch.object(post_confirmation, "_college_domains_table")
def test_forgot_password_trigger_is_ignored(
    mock_domains_table, mock_users_table, mock_cognito
):
    event = make_event(
        "student@gmail.com",
        trigger_source="PostConfirmation_ConfirmForgotPassword",
    )
    result = post_confirmation.lambda_handler(event, None)
    assert result == event
    mock_users_table.put_item.assert_not_called()
    mock_cognito.admin_update_user_attributes.assert_not_called()

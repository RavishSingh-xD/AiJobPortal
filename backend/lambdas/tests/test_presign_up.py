
from unittest.mock import patch
from lambdas.auth import pre_signup


def make_event(email):
    """Builds a minimal Cognito Pre Sign-up event shape."""
    return {
        "request": {
            "userAttributes": {
                "email": email
            }
        },
        "response": {}
    }


@patch.object(pre_signup, "_table")
def test_approved_domain_auto_confirms(mock_table):
    mock_table.get_item.return_value = {
        "Item": {"domain": "iitb.ac.in", "collegeName": "IIT Bombay"}
    }

    event = make_event("student@iitb.ac.in")
    result = pre_signup.lambda_handler(event, None)

    assert result["response"]["autoConfirmUser"] is True
    assert result["response"]["autoVerifyEmail"] is True


@patch.object(pre_signup, "_table")
def test_unapproved_domain_does_not_auto_confirm(mock_table):
    mock_table.get_item.return_value = {}  # no "Item" key = not found

    event = make_event("student@gmail.com")
    result = pre_signup.lambda_handler(event, None)

    assert "autoConfirmUser" not in result["response"]
    assert "autoVerifyEmail" not in result["response"]


def test_missing_email_does_not_crash():
    event = {"request": {"userAttributes": {}}, "response": {}}
    result = pre_signup.lambda_handler(event, None)

    assert "autoConfirmUser" not in result["response"]
    assert result is not None


def test_malformed_email_no_at_symbol():
    event = make_event("not-an-email")
    result = pre_signup.lambda_handler(event, None)

    assert "autoConfirmUser" not in result["response"]


@patch.object(pre_signup, "_table")
def test_dynamodb_error_fails_safe(mock_table):
    from botocore.exceptions import ClientError

    mock_table.get_item.side_effect = ClientError(
        {"Error": {"Code": "InternalServerError", "Message": "boom"}},
        "GetItem"
    )

    event = make_event("student@iitb.ac.in")
    # Should NOT raise -- should fail safe and leave response untouched
    result = pre_signup.lambda_handler(event, None)

    assert "autoConfirmUser" not in result["response"]


@patch.object(pre_signup, "_table")
def test_email_domain_is_lowercased(mock_table):
    mock_table.get_item.return_value = {
        "Item": {"domain": "iitb.ac.in", "collegeName": "IIT Bombay"}
    }

    event = make_event("Student@IITB.AC.IN")
    pre_signup.lambda_handler(event, None)

    # Confirm the lookup was called with the lowercased domain
    mock_table.get_item.assert_called_once_with(Key={"domain": "iitb.ac.in"})
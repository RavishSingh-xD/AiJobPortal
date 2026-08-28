"""
Local unit tests for lambdas/profile.py.
Uses moto to mock DynamoDB (Users table).

Run with (from the backend/ directory):
    PYTHONPATH=. pytest lambdas/tests/test_profile.py -v
"""

import json
import os
import importlib
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

USER_ID = "user-sub-123"


def make_event(method="GET", body=None, sub=USER_ID, email=None, name=None):
    claims = {"sub": sub}
    if email is not None:
        claims["email"] = email
    if name is not None:
        claims["name"] = name
    event = {
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": claims
                }
            },
        }
    }
    if body is not None:
        event["body"] = json.dumps(body) if not isinstance(body, str) else body
    return event


@pytest.fixture
def profile_module():
    """Create a moto-backed Users table and reload profile against it."""
    with mock_aws():
        os.environ["USERS_TABLE_NAME"] = "Users"
        os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
        os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

        dynamodb = boto3.resource("dynamodb", region_name="ap-south-1")
        dynamodb.create_table(
            TableName="Users",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        import lambdas.profile as profile

        importlib.reload(profile)
        yield profile


# --- _valid_url ---


def test_valid_url_linkedin(profile_module):
    assert profile_module._valid_url(
        "https://linkedin.com/in/jane", profile_module.LINKEDIN_DOMAIN
    )


def test_valid_url_linkedin_www_subdomain(profile_module):
    assert profile_module._valid_url(
        "https://www.linkedin.com/in/jane", profile_module.LINKEDIN_DOMAIN
    )


def test_valid_url_rejects_substring_lookalike(profile_module):
    assert not profile_module._valid_url(
        "https://not-linkedin.com/x", profile_module.LINKEDIN_DOMAIN
    )


def test_valid_url_rejects_http(profile_module):
    assert not profile_module._valid_url(
        "http://linkedin.com/in/jane", profile_module.LINKEDIN_DOMAIN
    )


def test_valid_url_rejects_empty(profile_module):
    assert not profile_module._valid_url("", profile_module.LINKEDIN_DOMAIN)


def test_valid_url_rejects_none(profile_module):
    assert not profile_module._valid_url(None, profile_module.LINKEDIN_DOMAIN)


def test_valid_url_rejects_malformed(profile_module):
    assert not profile_module._valid_url(
        "not a url at all", profile_module.LINKEDIN_DOMAIN
    )


# --- _get_user_id ---


def test_get_user_id_returns_sub(profile_module):
    assert profile_module._get_user_id(make_event()) == USER_ID


def test_get_user_id_missing_request_context_raises(profile_module):
    with pytest.raises(ValueError, match="JWT"):
        profile_module._get_user_id({})


def test_get_user_id_missing_sub_raises(profile_module):
    event = {
        "requestContext": {
            "authorizer": {"jwt": {"claims": {}}},
        }
    }
    with pytest.raises(ValueError, match="JWT"):
        profile_module._get_user_id(event)


# --- GET handler ---


def test_get_no_existing_item_backfills_users_row(profile_module):
    result = profile_module.handler(
        make_event("GET", email="new@example.com", name="New User"),
        None,
    )
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["linkedinUrl"] == ""
    assert body["githubUrl"] == ""
    assert body["completionPct"] == 0
    assert body["verificationStatus"] == "pending_review"
    assert body["verificationType"] == "manual"
    assert body["email"] == "new@example.com"
    assert body["name"] == "New User"

    stored = profile_module.users_table.get_item(Key={"userId": USER_ID})["Item"]
    assert stored["email"] == "new@example.com"
    assert stored["role"] == "student"


def test_get_includes_verification_fields(profile_module):
    profile_module.users_table.put_item(
        Item={
            "userId": USER_ID,
            "verificationStatus": "rejected",
            "verificationType": "manual",
        }
    )
    result = profile_module.handler(make_event("GET"), None)
    body = json.loads(result["body"])
    assert body["verificationStatus"] == "rejected"
    assert body["verificationType"] == "manual"


def test_get_both_urls_completion_100(profile_module):
    profile_module.users_table.put_item(
        Item={
            "userId": USER_ID,
            "linkedinUrl": "https://linkedin.com/in/jane",
            "githubUrl": "https://github.com/jane",
        }
    )
    result = profile_module.handler(make_event("GET"), None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["completionPct"] == 100
    assert body["linkedinUrl"] == "https://linkedin.com/in/jane"
    assert body["githubUrl"] == "https://github.com/jane"


def test_get_one_url_completion_50(profile_module):
    profile_module.users_table.put_item(
        Item={
            "userId": USER_ID,
            "linkedinUrl": "https://linkedin.com/in/jane",
        }
    )
    result = profile_module.handler(make_event("GET"), None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["completionPct"] == 50
    assert body["githubUrl"] == ""


# --- PUT handler ---


def test_put_valid_urls(profile_module):
    profile_module.users_table.put_item(Item={"userId": USER_ID})
    result = profile_module.handler(
        make_event(
            "PUT",
            {
                "linkedinUrl": "https://linkedin.com/in/jane",
                "githubUrl": "https://github.com/jane",
            },
        ),
        None,
    )
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["completionPct"] == 100
    assert body["linkedinUrl"] == "https://linkedin.com/in/jane"
    assert body["githubUrl"] == "https://github.com/jane"

    stored = profile_module.users_table.get_item(Key={"userId": USER_ID})["Item"]
    assert stored["linkedinUrl"] == "https://linkedin.com/in/jane"
    assert stored["githubUrl"] == "https://github.com/jane"


def test_put_invalid_linkedin_url_rejected(profile_module):
    with patch.object(
        profile_module.users_table, "update_item", wraps=profile_module.users_table.update_item
    ) as mock_update:
        result = profile_module.handler(
            make_event("PUT", {"linkedinUrl": "https://not-linkedin.com/x"}),
            None,
        )
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "linkedinUrl" in body["errors"]
        mock_update.assert_not_called()


def test_put_invalid_github_url_rejected(profile_module):
    result = profile_module.handler(
        make_event("PUT", {"githubUrl": "https://not-github.com/jane"}),
        None,
    )
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert "githubUrl" in body["errors"]


def test_put_empty_body_rejected(profile_module):
    result = profile_module.handler(make_event("PUT", {}), None)
    assert result["statusCode"] == 400
    assert json.loads(result["body"])["error"] == "No valid fields to update"


def test_put_only_linkedin_url(profile_module):
    profile_module.users_table.put_item(
        Item={
            "userId": USER_ID,
            "githubUrl": "https://github.com/existing",
        }
    )
    result = profile_module.handler(
        make_event("PUT", {"linkedinUrl": "https://www.linkedin.com/in/jane"}),
        None,
    )
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["linkedinUrl"] == "https://www.linkedin.com/in/jane"
    assert body["githubUrl"] == "https://github.com/existing"
    assert body["completionPct"] == 100

    stored = profile_module.users_table.get_item(Key={"userId": USER_ID})["Item"]
    assert stored["linkedinUrl"] == "https://www.linkedin.com/in/jane"
    assert stored["githubUrl"] == "https://github.com/existing"


def test_put_clear_linkedin_with_empty_string(profile_module):
    profile_module.users_table.put_item(
        Item={
            "userId": USER_ID,
            "linkedinUrl": "https://linkedin.com/in/jane",
            "githubUrl": "https://github.com/jane",
        }
    )
    result = profile_module.handler(
        make_event("PUT", {"linkedinUrl": ""}),
        None,
    )
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["linkedinUrl"] == ""
    assert body["githubUrl"] == "https://github.com/jane"
    assert body["completionPct"] == 50


def test_handler_missing_jwt_returns_401(profile_module):
    result = profile_module.handler({"requestContext": {"http": {"method": "GET"}}}, None)
    assert result["statusCode"] == 401


def test_handler_unsupported_method_returns_405(profile_module):
    result = profile_module.handler(make_event("DELETE"), None)
    assert result["statusCode"] == 405


def test_put_invalid_json_body(profile_module):
    event = make_event("PUT")
    event["body"] = "{not-json"
    result = profile_module.handler(event, None)
    assert result["statusCode"] == 400
    assert "Invalid JSON" in json.loads(result["body"])["error"]


def test_valid_url_github(profile_module):
    assert profile_module._valid_url(
        "https://github.com/jane", profile_module.GITHUB_DOMAIN
    )


def test_get_user_id_empty_sub_raises(profile_module):
    event = make_event(sub="")
    with pytest.raises(ValueError, match="JWT"):
        profile_module._get_user_id(event)

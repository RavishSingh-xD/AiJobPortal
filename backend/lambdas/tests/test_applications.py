"""
Local unit tests for lambdas/applications.py.
Uses moto to mock DynamoDB (Applications table).

Run with (from the backend/ directory):
    PYTHONPATH=. pytest lambdas/tests/test_applications.py -v
"""

import json
import os
import importlib

import boto3
import pytest
from moto import mock_aws

USER_ID = "user-sub-123"
OTHER_USER = "other-user-456"


def make_event(method="GET", body=None, sub=USER_ID):
    event = {
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": sub,
                    }
                }
            },
        }
    }
    if body is not None:
        event["body"] = json.dumps(body) if not isinstance(body, str) else body
    return event


def valid_application(**overrides):
    payload = {
        "canonicalId": "job-1",
        "jobTitle": "Software Intern",
        "company": "Acme",
        "domain": "Engineering",
        "applyUrl": "https://example.com/apply/1",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def applications_module():
    with mock_aws():
        os.environ["APPLICATIONS_TABLE_NAME"] = "Applications"
        os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
        os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

        dynamodb = boto3.resource("dynamodb", region_name="ap-south-1")
        dynamodb.create_table(
            TableName="Applications",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "canonicalId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "canonicalId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        import lambdas.applications as applications

        importlib.reload(applications)
        yield applications


def test_post_valid_application(applications_module):
    result = applications_module.handler(
        make_event("POST", valid_application()),
        None,
    )
    assert result["statusCode"] == 201
    body = json.loads(result["body"])
    assert body["status"] == "applied"
    assert body["userId"] == USER_ID
    assert body["canonicalId"] == "job-1"
    assert body["appliedAt"]

    stored = applications_module.applications_table.get_item(
        Key={"userId": USER_ID, "canonicalId": "job-1"}
    )["Item"]
    assert stored["status"] == "applied"
    assert stored["appliedAt"]


def test_post_missing_canonical_id(applications_module):
    payload = valid_application()
    del payload["canonicalId"]
    result = applications_module.handler(make_event("POST", payload), None)
    assert result["statusCode"] == 400
    assert "canonicalId" in json.loads(result["body"])["errors"]


def test_post_missing_job_title(applications_module):
    payload = valid_application()
    del payload["jobTitle"]
    result = applications_module.handler(make_event("POST", payload), None)
    assert result["statusCode"] == 400
    assert "jobTitle" in json.loads(result["body"])["errors"]


def test_post_missing_company(applications_module):
    payload = valid_application()
    del payload["company"]
    result = applications_module.handler(make_event("POST", payload), None)
    assert result["statusCode"] == 400
    assert "company" in json.loads(result["body"])["errors"]


def test_post_invalid_domain(applications_module):
    result = applications_module.handler(
        make_event("POST", valid_application(domain="not-a-real-domain")),
        None,
    )
    assert result["statusCode"] == 400
    assert "domain" in json.loads(result["body"])["errors"]


def test_post_lowercase_domain_normalized(applications_module):
    result = applications_module.handler(
        make_event("POST", valid_application(domain="engineering")),
        None,
    )
    assert result["statusCode"] == 201
    body = json.loads(result["body"])
    assert body["domain"] == "Engineering"

    stored = applications_module.applications_table.get_item(
        Key={"userId": USER_ID, "canonicalId": "job-1"}
    )["Item"]
    assert stored["domain"] == "Engineering"


def test_post_missing_apply_url(applications_module):
    payload = valid_application()
    del payload["applyUrl"]
    result = applications_module.handler(make_event("POST", payload), None)
    assert result["statusCode"] == 400
    assert "applyUrl" in json.loads(result["body"])["errors"]


def test_get_no_applications(applications_module):
    result = applications_module.handler(make_event("GET"), None)
    assert result["statusCode"] == 200
    assert json.loads(result["body"])["applications"] == []


def test_get_multiple_applications_most_recent_first(applications_module):
    applications_module.applications_table.put_item(
        Item={
            "userId": USER_ID,
            "canonicalId": "old",
            "jobTitle": "Old Role",
            "company": "Acme",
            "domain": "Engineering",
            "applyUrl": "https://example.com/old",
            "appliedAt": "2026-01-01T00:00:00+00:00",
            "status": "applied",
        }
    )
    applications_module.applications_table.put_item(
        Item={
            "userId": USER_ID,
            "canonicalId": "new",
            "jobTitle": "New Role",
            "company": "Beta",
            "domain": "Business",
            "applyUrl": "https://example.com/new",
            "appliedAt": "2026-08-01T00:00:00+00:00",
            "status": "applied",
        }
    )
    result = applications_module.handler(make_event("GET"), None)
    assert result["statusCode"] == 200
    apps = json.loads(result["body"])["applications"]
    assert [a["canonicalId"] for a in apps] == ["new", "old"]


def test_handler_missing_jwt_returns_401(applications_module):
    result = applications_module.handler(
        {"requestContext": {"http": {"method": "GET"}}},
        None,
    )
    assert result["statusCode"] == 401


def test_handler_unsupported_method_returns_405(applications_module):
    result = applications_module.handler(make_event("DELETE"), None)
    assert result["statusCode"] == 405


def test_userid_always_from_jwt_not_body(applications_module):
    payload = valid_application(userId=OTHER_USER)
    result = applications_module.handler(make_event("POST", payload), None)
    assert result["statusCode"] == 201
    body = json.loads(result["body"])
    assert body["userId"] == USER_ID

    stored = applications_module.applications_table.get_item(
        Key={"userId": USER_ID, "canonicalId": "job-1"}
    ).get("Item")
    assert stored is not None
    assert stored["userId"] == USER_ID

    other = applications_module.applications_table.get_item(
        Key={"userId": OTHER_USER, "canonicalId": "job-1"}
    ).get("Item")
    assert other is None

"""
Local unit tests for lambdas/saved_jobs.py.
Uses moto to mock DynamoDB (SavedJobs table).

Run with (from the backend/ directory):
    PYTHONPATH=. pytest lambdas/tests/test_saved_jobs.py -v
"""

import json
import os
import importlib

import boto3
import pytest
from moto import mock_aws

USER_ID = "user-sub-123"
OTHER_USER = "other-user-456"


def make_event(method="GET", body=None, sub=USER_ID, query=None):
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
    if query is not None:
        event["queryStringParameters"] = query
    return event


def valid_saved_job(**overrides):
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
def saved_jobs_module():
    with mock_aws():
        os.environ["SAVED_JOBS_TABLE_NAME"] = "SavedJobs"
        os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
        os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

        dynamodb = boto3.resource("dynamodb", region_name="ap-south-1")
        dynamodb.create_table(
            TableName="SavedJobs",
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

        import lambdas.saved_jobs as saved_jobs

        importlib.reload(saved_jobs)
        yield saved_jobs


def test_post_valid_saved_job(saved_jobs_module):
    result = saved_jobs_module.handler(
        make_event("POST", valid_saved_job()),
        None,
    )
    assert result["statusCode"] == 201
    body = json.loads(result["body"])
    assert body["userId"] == USER_ID
    assert body["canonicalId"] == "job-1"
    assert body["savedAt"]

    stored = saved_jobs_module.saved_jobs_table.get_item(
        Key={"userId": USER_ID, "canonicalId": "job-1"}
    )["Item"]
    assert stored["savedAt"]


def test_post_missing_canonical_id(saved_jobs_module):
    payload = valid_saved_job()
    del payload["canonicalId"]
    result = saved_jobs_module.handler(make_event("POST", payload), None)
    assert result["statusCode"] == 400
    assert "canonicalId" in json.loads(result["body"])["errors"]


def test_post_invalid_domain(saved_jobs_module):
    result = saved_jobs_module.handler(
        make_event("POST", valid_saved_job(domain="not-a-real-domain")),
        None,
    )
    assert result["statusCode"] == 400
    assert "domain" in json.loads(result["body"])["errors"]


def test_post_lowercase_domain_normalized(saved_jobs_module):
    result = saved_jobs_module.handler(
        make_event("POST", valid_saved_job(domain="engineering")),
        None,
    )
    assert result["statusCode"] == 201
    body = json.loads(result["body"])
    assert body["domain"] == "Engineering"

    stored = saved_jobs_module.saved_jobs_table.get_item(
        Key={"userId": USER_ID, "canonicalId": "job-1"}
    )["Item"]
    assert stored["domain"] == "Engineering"


def test_get_no_saved_jobs(saved_jobs_module):
    result = saved_jobs_module.handler(make_event("GET"), None)
    assert result["statusCode"] == 200
    assert json.loads(result["body"])["savedJobs"] == []


def test_get_multiple_saved_jobs_most_recent_first(saved_jobs_module):
    saved_jobs_module.saved_jobs_table.put_item(
        Item={
            "userId": USER_ID,
            "canonicalId": "old",
            "jobTitle": "Old Role",
            "company": "Acme",
            "domain": "Engineering",
            "applyUrl": "https://example.com/old",
            "savedAt": "2026-01-01T00:00:00+00:00",
        }
    )
    saved_jobs_module.saved_jobs_table.put_item(
        Item={
            "userId": USER_ID,
            "canonicalId": "new",
            "jobTitle": "New Role",
            "company": "Beta",
            "domain": "Business",
            "applyUrl": "https://example.com/new",
            "savedAt": "2026-08-01T00:00:00+00:00",
        }
    )
    result = saved_jobs_module.handler(make_event("GET"), None)
    assert result["statusCode"] == 200
    jobs = json.loads(result["body"])["savedJobs"]
    assert [j["canonicalId"] for j in jobs] == ["new", "old"]


def test_delete_existing_saved_job(saved_jobs_module):
    saved_jobs_module.saved_jobs_table.put_item(
        Item={
            "userId": USER_ID,
            "canonicalId": "job-1",
            "jobTitle": "Software Intern",
            "company": "Acme",
            "domain": "Engineering",
            "applyUrl": "https://example.com/apply/1",
            "savedAt": "2026-08-01T00:00:00+00:00",
        }
    )
    result = saved_jobs_module.handler(
        make_event("DELETE", query={"canonicalId": "job-1"}),
        None,
    )
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["deleted"] is True
    assert body["canonicalId"] == "job-1"

    remaining = saved_jobs_module.saved_jobs_table.get_item(
        Key={"userId": USER_ID, "canonicalId": "job-1"}
    ).get("Item")
    assert remaining is None


def test_delete_missing_canonical_id(saved_jobs_module):
    result = saved_jobs_module.handler(make_event("DELETE"), None)
    assert result["statusCode"] == 400
    assert "canonicalId" in json.loads(result["body"])["error"]


def test_handler_missing_jwt_returns_401(saved_jobs_module):
    result = saved_jobs_module.handler(
        {"requestContext": {"http": {"method": "GET"}}},
        None,
    )
    assert result["statusCode"] == 401


def test_handler_unsupported_method_returns_405(saved_jobs_module):
    result = saved_jobs_module.handler(make_event("PUT"), None)
    assert result["statusCode"] == 405


def test_userid_always_from_jwt_not_body(saved_jobs_module):
    payload = valid_saved_job(userId=OTHER_USER)
    result = saved_jobs_module.handler(make_event("POST", payload), None)
    assert result["statusCode"] == 201
    body = json.loads(result["body"])
    assert body["userId"] == USER_ID

    stored = saved_jobs_module.saved_jobs_table.get_item(
        Key={"userId": USER_ID, "canonicalId": "job-1"}
    ).get("Item")
    assert stored is not None
    assert stored["userId"] == USER_ID

    other = saved_jobs_module.saved_jobs_table.get_item(
        Key={"userId": OTHER_USER, "canonicalId": "job-1"}
    ).get("Item")
    assert other is None

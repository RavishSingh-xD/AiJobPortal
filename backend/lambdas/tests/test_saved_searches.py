"""Tests for saved_searches.py."""

import json
import os
import importlib

import boto3
import pytest
from moto import mock_aws

USER_ID = "user-sub-123"


def make_event(method="GET", body=None, sub=USER_ID, query=None, path="/saved-searches"):
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": sub,
                    }
                }
            },
        },
    }
    if body is not None:
        event["body"] = json.dumps(body) if not isinstance(body, str) else body
    if query is not None:
        event["queryStringParameters"] = query
    return event


@pytest.fixture
def saved_searches_module():
    with mock_aws():
        os.environ["SAVED_SEARCHES_TABLE_NAME"] = "SavedSearches"
        os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
        os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

        dynamodb = boto3.resource("dynamodb", region_name="ap-south-1")
        dynamodb.create_table(
            TableName="SavedSearches",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "searchId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "searchId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        import lambdas.saved_searches as module

        importlib.reload(module)
        yield module


def test_create_and_list_saved_search(saved_searches_module):
    create = saved_searches_module.handler(
        make_event(
            "POST",
            {"domain": "Engineering", "skill": "Python", "label": "Python roles"},
        ),
        None,
    )
    assert create["statusCode"] == 201

    listed = saved_searches_module.handler(make_event("GET"), None)
    body = json.loads(listed["body"])
    assert len(body["savedSearches"]) == 1
    assert body["savedSearches"][0]["label"] == "Python roles"


def test_alerts_endpoint_returns_shape(saved_searches_module):
    saved_searches_module.handler(
        make_event("POST", {"domain": "Healthcare", "skill": "Nursing"}),
        None,
    )
    alerts = saved_searches_module.handler(
        make_event("GET", path="/saved-searches/alerts"),
        None,
    )
    body = json.loads(alerts["body"])
    assert "alerts" in body
    assert "alertCount" in body

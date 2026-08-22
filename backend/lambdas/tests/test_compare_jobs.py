"""Tests for compare_jobs.py."""

import json
from decimal import Decimal
from unittest.mock import patch

from lambdas.jobs import compare_jobs as cj

USER_ID = "user-sub-123"
SESSION_ID = "session-1"


def make_event(body=None, sub=USER_ID):
    return {
        "requestContext": {
            "http": {"method": "POST"},
            "authorizer": {"jwt": {"claims": {"sub": sub}}},
        },
        "body": json.dumps(body or {}),
    }


def job_item(canonical_id="job-a", min_pow=20):
    return {
        "canonical_id": canonical_id,
        "title": "Intern",
        "company": "Acme",
        "location": "Remote",
        "apply_url": "https://example.com/a",
        "min_pow_score": Decimal(str(min_pow)),
        "employment_type": "Internship",
        "required_skills": ["Python"],
        "status": "ACTIVE",
    }


@patch.object(cj, "_find_listings")
def test_compare_returns_jobs(mock_find):
    mock_find.return_value = {"job-a": job_item()}
    result = cj.handler(
        make_event({"domain": "Engineering", "canonicalIds": ["job-a"]}),
        None,
    )
    body = json.loads(result["body"])
    assert result["statusCode"] == 200
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["canonical_id"] == "job-a"


@patch.object(cj, "_load_session_scores")
@patch.object(cj, "_find_listings")
def test_compare_with_session_adds_pow_bar(mock_find, mock_session):
    mock_find.return_value = {"job-a": job_item(min_pow=30)}
    mock_session.return_value = {
        "powScore": 32,
        "scorePercent": 80,
        "skill": "Python",
        "domain": "Engineering",
    }
    result = cj.handler(
        make_event(
            {
                "domain": "Engineering",
                "canonicalIds": ["job-a"],
                "sessionId": SESSION_ID,
            }
        ),
        None,
    )
    body = json.loads(result["body"])
    assert body["jobs"][0]["powBar"]["meetsRequirement"] is True
    assert "skillOverlap" in body["jobs"][0]

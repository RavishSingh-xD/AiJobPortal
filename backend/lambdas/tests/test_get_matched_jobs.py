"""
Local unit tests for get_matched_jobs.py.
No real AWS calls -- DynamoDB GetItem and jobs Scan are mocked.

Run with (from the backend/ directory):
    PYTHONPATH=. pytest lambdas/tests/test_get_matched_jobs.py -v
"""

import json
from decimal import Decimal
from unittest.mock import patch
from botocore.exceptions import ClientError

from lambdas.match import get_matched_jobs as gmj

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


def completed_session(pow_score=Decimal("32")):
    return {
        "Item": {
            "sessionId": SESSION_ID,
            "userId": USER_A,
            "status": "test_completed",
            "domain": "Engineering",
            "skill": "Python",
            "powScore": pow_score,
        }
    }


def listing(
    canonical_id,
    employment_type="Internship",
    min_pow=10,
    skills=None,
    status="ACTIVE",
    display_status="Active",
    **overrides,
):
    item = {
        "canonical_id": canonical_id,
        "title": f"Role {canonical_id}",
        "company": "Acme",
        "location": "Remote",
        "apply_url": f"https://example.com/{canonical_id}",
        "min_pow_score": Decimal(str(min_pow)),
        "is_fallback": False,
        "employment_type": employment_type,
        "required_skills": skills or ["Python"],
        "status": status,
        "display_status": display_status,
        "internal_hash": "omit-me",
    }
    item.update(overrides)
    return item


@patch.object(gmj, "_sessions_table")
def test_missing_session_returns_403(mock_table):
    mock_table.get_item.return_value = {}
    result = gmj.lambda_handler(make_event(), None)
    assert result["statusCode"] == 403
    assert json.loads(result["body"])["error"] == "Forbidden"


@patch.object(gmj, "_sessions_table")
def test_session_owned_by_another_user_returns_403(mock_table):
    session = completed_session()
    session["Item"]["userId"] = USER_B
    mock_table.get_item.return_value = session
    result = gmj.lambda_handler(make_event(), None)
    assert result["statusCode"] == 403
    assert json.loads(result["body"])["error"] == "Forbidden"


@patch.object(gmj, "_sessions_table")
def test_session_not_completed_returns_409(mock_table):
    session = completed_session()
    session["Item"]["status"] = "test_in_progress"
    mock_table.get_item.return_value = session
    result = gmj.lambda_handler(make_event(), None)
    assert result["statusCode"] == 409
    assert "Complete the domain test" in json.loads(result["body"])["error"]


@patch.object(gmj, "_scan_jobs")
@patch.object(gmj, "_sessions_table")
def test_successful_match_filters_splits_and_sorts(mock_table, mock_scan):
    mock_table.get_item.return_value = completed_session(pow_score=Decimal("32"))
    mock_scan.return_value = {
        "Items": [
            listing("high-intern", "Internship", min_pow=30, skills=["Python"]),
            listing("low-intern", "Internship", min_pow=10, skills=["Python"]),
            listing("over-intern", "Internship", min_pow=40, skills=["Python"]),
            listing("java-intern", "Internship", min_pow=10, skills=["Java"]),
            listing("closed-intern", "Internship", min_pow=10, skills=["Python"], status="closed"),
            listing("mid-job", "Job", min_pow=25, skills=["python backend"]),
            listing("low-job", "Job", min_pow=5, skills=["Python"]),
            listing("over-job", "Job", min_pow=50, skills=["Python"]),
        ]
    }
    result = gmj.lambda_handler(make_event(), None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["domain"] == "Engineering"
    assert body["skill"] == "Python"
    assert body["powScore"] == 32

    intern_ids = [row["canonical_id"] for row in body["internships"]]
    job_ids = [row["canonical_id"] for row in body["jobs"]]
    assert intern_ids == ["high-intern", "low-intern"]
    assert job_ids == ["mid-job", "low-job"]
    assert "over-intern" not in intern_ids
    assert "java-intern" not in intern_ids
    assert "closed-intern" not in intern_ids
    assert "over-job" not in job_ids

    assert "almostThere" in body
    assert "skillGapReport" in body
    assert isinstance(body["skillGapReport"]["missingSkills"], list)

    for row in body["internships"] + body["jobs"]:
        assert "internal_hash" not in row
        assert "required_skills" in row
        assert isinstance(row["required_skills"], list)
        assert set(row.keys()) <= {
            "canonical_id",
            "title",
            "company",
            "location",
            "apply_url",
            "min_pow_score",
            "is_fallback",
            "employment_type",
            "required_skills",
            "source",
        }

    assert body["internships"][0]["required_skills"] == ["Python"]
    assert body["jobs"][0]["required_skills"] == ["python backend"]

    mock_scan.assert_called_once_with("jobs_engineering")


@patch.object(gmj, "_scan_jobs")
@patch.object(gmj, "_sessions_table")
def test_decimal_fields_serialize(mock_table, mock_scan):
    mock_table.get_item.return_value = completed_session(pow_score=Decimal("32.5"))
    mock_scan.return_value = {
        "Items": [
            listing("i1", "Internship", min_pow=Decimal("12.5"), skills=["Python"]),
        ]
    }
    result = gmj.lambda_handler(make_event(), None)
    body = json.loads(result["body"])
    assert body["powScore"] == 32.5
    assert body["internships"][0]["min_pow_score"] == 12.5
    assert isinstance(body["internships"][0]["min_pow_score"], float)


@patch.object(gmj, "_scan_jobs")
@patch.object(gmj, "_sessions_table")
def test_jobs_scan_client_error_returns_500(mock_table, mock_scan):
    mock_table.get_item.return_value = completed_session()
    mock_scan.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "Scan",
    )
    result = gmj.lambda_handler(make_event(), None)
    assert result["statusCode"] == 500
    assert "matched jobs" in json.loads(result["body"])["error"]

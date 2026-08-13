"""
Unit tests for list_jobs.py -- domain validation, skill filtering,
employmentType filtering, pagination, and error handling. No real AWS
calls -- the DynamoDB resource is mocked.

Run with (from the backend/ directory):
    PYTHONPATH=. pytest lambdas/tests/test_list_jobs.py -v
"""

import json
import base64
from unittest.mock import patch, MagicMock
from lambdas.jobs import list_jobs


def make_event(query_params=None, method="GET"):
    return {
        "requestContext": {"http": {"method": method}},
        "queryStringParameters": query_params or {},
    }


def make_job(canonical_id, employment_type="Job", required_skills=None, **overrides):
    job = {
        "canonical_id": canonical_id,
        "title": "Sample Role",
        "company": "Sample Co",
        "location": "India",
        "source": "Indeed India",
        "apply_url": "https://example.com/apply",
        "required_skills": required_skills or ["Python"],
        "employment_type": employment_type,
        "status": "ACTIVE",
        "display_status": "Active",
        "domain": "Engineering",
        "min_pow_score": 20,
        "is_fallback": False,
    }
    job.update(overrides)
    return job


# ---------- domain validation ----------

def test_missing_domain_returns_400():
    event = make_event({})
    result = list_jobs.lambda_handler(event, None)
    assert result["statusCode"] == 400
    assert "domain" in json.loads(result["body"])["error"]


def test_unsupported_domain_returns_400():
    event = make_event({"domain": "Astrology"})
    result = list_jobs.lambda_handler(event, None)
    assert result["statusCode"] == 400
    assert "Unsupported domain" in json.loads(result["body"])["error"]


def test_domain_is_case_insensitive():
    assert list_jobs.domain_to_table_name("ENGINEERING") == "jobs_engineering"
    assert list_jobs.domain_to_table_name("Healthcare") == "jobs_healthcare"
    assert list_jobs.domain_to_table_name("business") == "jobs_business"


# ---------- method validation ----------

def test_non_get_method_returns_405():
    event = make_event({"domain": "Engineering"}, method="POST")
    result = list_jobs.lambda_handler(event, None)
    assert result["statusCode"] == 405


# ---------- limit validation ----------

def test_invalid_limit_returns_400():
    event = make_event({"domain": "Engineering", "limit": "0"})
    result = list_jobs.lambda_handler(event, None)
    assert result["statusCode"] == 400

    event = make_event({"domain": "Engineering", "limit": "not-a-number"})
    result = list_jobs.lambda_handler(event, None)
    assert result["statusCode"] == 400

    event = make_event({"domain": "Engineering", "limit": "999"})
    result = list_jobs.lambda_handler(event, None)
    assert result["statusCode"] == 400


# ---------- employmentType filter (new) ----------

@patch.object(list_jobs, "_dynamodb")
def test_employment_type_filters_to_internship_only(mock_dynamodb):
    mock_table = MagicMock()
    mock_table.scan.return_value = {
        "Items": [
            make_job("1", employment_type="Job"),
            make_job("2", employment_type="Internship"),
            make_job("3", employment_type="Internship"),
        ]
    }
    mock_dynamodb.Table.return_value = mock_table

    event = make_event({"domain": "Engineering", "employmentType": "Internship"})
    result = list_jobs.lambda_handler(event, None)
    body = json.loads(result["body"])

    assert result["statusCode"] == 200
    assert body["count"] == 2
    assert all(job["employment_type"] == "Internship" for job in body["jobs"])


@patch.object(list_jobs, "_dynamodb")
def test_employment_type_filters_to_job_only(mock_dynamodb):
    mock_table = MagicMock()
    mock_table.scan.return_value = {
        "Items": [
            make_job("1", employment_type="Job"),
            make_job("2", employment_type="Internship"),
        ]
    }
    mock_dynamodb.Table.return_value = mock_table

    event = make_event({"domain": "Engineering", "employmentType": "Job"})
    result = list_jobs.lambda_handler(event, None)
    body = json.loads(result["body"])

    assert body["count"] == 1
    assert body["jobs"][0]["employment_type"] == "Job"


@patch.object(list_jobs, "_dynamodb")
def test_employment_type_is_case_insensitive(mock_dynamodb):
    mock_table = MagicMock()
    mock_table.scan.return_value = {
        "Items": [make_job("1", employment_type="Internship")]
    }
    mock_dynamodb.Table.return_value = mock_table

    event = make_event({"domain": "Engineering", "employmentType": "internship"})
    result = list_jobs.lambda_handler(event, None)
    body = json.loads(result["body"])

    assert body["count"] == 1


@patch.object(list_jobs, "_dynamodb")
def test_employment_type_absent_means_no_filtering(mock_dynamodb):
    mock_table = MagicMock()
    mock_table.scan.return_value = {
        "Items": [
            make_job("1", employment_type="Job"),
            make_job("2", employment_type="Internship"),
        ]
    }
    mock_dynamodb.Table.return_value = mock_table

    event = make_event({"domain": "Engineering"})
    result = list_jobs.lambda_handler(event, None)
    body = json.loads(result["body"])

    assert body["count"] == 2


@patch.object(list_jobs, "_dynamodb")
def test_employment_type_unrecognized_value_returns_no_matches(mock_dynamodb):
    mock_table = MagicMock()
    mock_table.scan.return_value = {
        "Items": [
            make_job("1", employment_type="Job"),
            make_job("2", employment_type="Internship"),
        ]
    }
    mock_dynamodb.Table.return_value = mock_table

    event = make_event({"domain": "Engineering", "employmentType": "Freelance"})
    result = list_jobs.lambda_handler(event, None)
    body = json.loads(result["body"])

    assert body["count"] == 0


@patch.object(list_jobs, "_dynamodb")
def test_employment_type_and_skill_combined(mock_dynamodb):
    mock_table = MagicMock()
    mock_table.scan.return_value = {
        "Items": [
            make_job("1", employment_type="Internship", required_skills=["Python"]),
            make_job("2", employment_type="Internship", required_skills=["Java"]),
            make_job("3", employment_type="Job", required_skills=["Python"]),
        ]
    }
    mock_dynamodb.Table.return_value = mock_table

    event = make_event({
        "domain": "Engineering",
        "employmentType": "Internship",
        "skill": "Python",
    })
    result = list_jobs.lambda_handler(event, None)
    body = json.loads(result["body"])

    assert body["count"] == 1
    assert body["jobs"][0]["canonical_id"] == "1"


# ---------- skill filter (existing behavior, regression) ----------

@patch.object(list_jobs, "_dynamodb")
def test_skill_filter_case_insensitive_substring(mock_dynamodb):
    mock_table = MagicMock()
    mock_table.scan.return_value = {
        "Items": [
            make_job("1", required_skills=["Python", "Django"]),
            make_job("2", required_skills=["Java"]),
        ]
    }
    mock_dynamodb.Table.return_value = mock_table

    event = make_event({"domain": "Engineering", "skill": "python"})
    result = list_jobs.lambda_handler(event, None)
    body = json.loads(result["body"])

    assert body["count"] == 1
    assert body["jobs"][0]["canonical_id"] == "1"


# ---------- pagination ----------

@patch.object(list_jobs, "_dynamodb")
def test_next_token_round_trips(mock_dynamodb):
    mock_table = MagicMock()
    mock_table.scan.return_value = {
        "Items": [make_job("1")],
        "LastEvaluatedKey": {"canonical_id": "1"},
    }
    mock_dynamodb.Table.return_value = mock_table

    event = make_event({"domain": "Engineering"})
    result = list_jobs.lambda_handler(event, None)
    body = json.loads(result["body"])

    assert body["nextToken"] is not None

    decoded = json.loads(base64.urlsafe_b64decode(body["nextToken"]))
    assert decoded == {"canonical_id": "1"}


def test_invalid_next_token_returns_400():
    event = make_event({"domain": "Engineering", "nextToken": "not-valid-base64!!"})
    result = list_jobs.lambda_handler(event, None)
    assert result["statusCode"] == 400


# ---------- error handling ----------

@patch.object(list_jobs, "_dynamodb")
def test_dynamodb_error_returns_500(mock_dynamodb):
    from botocore.exceptions import ClientError

    mock_table = MagicMock()
    mock_table.scan.side_effect = ClientError(
        {"Error": {"Code": "InternalServerError", "Message": "boom"}}, "Scan"
    )
    mock_dynamodb.Table.return_value = mock_table

    event = make_event({"domain": "Engineering"})
    result = list_jobs.lambda_handler(event, None)
    assert result["statusCode"] == 500
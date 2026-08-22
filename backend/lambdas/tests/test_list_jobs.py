"""
Unit tests for list_jobs.py -- domain validation, skill/employmentType
filtering, pagination, error handling, and on-demand harvest triggering.
No real AWS calls -- DynamoDB and SSM clients are mocked.

Run with (from the backend/ directory):
    PYTHONPATH=. pytest lambdas/tests/test_list_jobs.py -v
"""

import json
import base64
import datetime
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


# ---------- domain validation (regression) ----------

def test_missing_domain_returns_400():
    event = make_event({})
    result = list_jobs.lambda_handler(event, None)
    assert result["statusCode"] == 400


def test_unsupported_domain_returns_400():
    event = make_event({"domain": "Astrology"})
    result = list_jobs.lambda_handler(event, None)
    assert result["statusCode"] == 400


def test_non_get_method_returns_405():
    event = make_event({"domain": "Engineering"}, method="POST")
    result = list_jobs.lambda_handler(event, None)
    assert result["statusCode"] == 405


# ---------- normal path when data exists (regression) ----------

@patch.object(list_jobs, "_dynamodb")
def test_existing_data_returns_normally_no_trigger(mock_dynamodb):
    mock_table = MagicMock()
    # First call: the raw "is it empty" check (Limit=1) -- has data
    # Second call: the real paginated scan
    mock_table.scan.side_effect = [
        {"Items": [make_job("1")]},  # raw check
        {"Items": [make_job("1"), make_job("2")]},  # real scan
    ]
    mock_dynamodb.Table.return_value = mock_table

    with patch.object(list_jobs, "_trigger_harvest") as mock_trigger:
        event = make_event({"domain": "Engineering"})
        result = list_jobs.lambda_handler(event, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["count"] == 2
        mock_trigger.assert_not_called()


@patch.object(list_jobs, "_dynamodb")
def test_skill_filter_no_matches_does_not_trigger_harvest(mock_dynamodb):
    """A skill filter matching nothing in an already-populated table is a
    normal empty search result, NOT a signal to harvest more data."""
    mock_table = MagicMock()
    mock_table.scan.side_effect = [
        {"Items": [make_job("1")]},  # raw check -- has data
        {"Items": [make_job("1", required_skills=["Java"])]},  # real scan
    ]
    mock_dynamodb.Table.return_value = mock_table

    with patch.object(list_jobs, "_trigger_harvest") as mock_trigger:
        event = make_event({"domain": "Engineering", "skill": "Rust"})
        result = list_jobs.lambda_handler(event, None)

        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["count"] == 0
        mock_trigger.assert_not_called()


# ---------- on-demand harvest triggering ----------

@patch.object(list_jobs, "_dynamodb")
def test_missing_table_triggers_harvest_returns_202(mock_dynamodb):
    from botocore.exceptions import ClientError

    mock_table = MagicMock()
    mock_table.scan.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "no table"}}, "Scan"
    )
    mock_dynamodb.Table.return_value = mock_table

    with patch.object(list_jobs, "_trigger_harvest", return_value=True) as mock_trigger:
        event = make_event({"domain": "Engineering"})
        result = list_jobs.lambda_handler(event, None)

        assert result["statusCode"] == 202
        body = json.loads(result["body"])
        assert body["status"] == "harvesting"
        assert body["domain"] == "Engineering"
        mock_trigger.assert_called_once()


@patch.object(list_jobs, "_dynamodb")
def test_empty_table_triggers_harvest_returns_202(mock_dynamodb):
    mock_table = MagicMock()
    mock_table.scan.return_value = {"Items": []}  # raw check -- genuinely empty
    mock_dynamodb.Table.return_value = mock_table

    with patch.object(list_jobs, "_trigger_harvest", return_value=True) as mock_trigger:
        event = make_event({"domain": "Healthcare"})
        result = list_jobs.lambda_handler(event, None)

        assert result["statusCode"] == 202
        body = json.loads(result["body"])
        assert body["status"] == "harvesting"
        mock_trigger.assert_called_once()


@patch.object(list_jobs, "_dynamodb")
def test_trigger_failure_falls_back_to_normal_empty_response(mock_dynamodb):
    """If triggering itself fails (e.g. no instance configured), don't
    error out -- just behave like a normal empty result."""
    mock_table = MagicMock()
    mock_table.scan.side_effect = [
        {"Items": []},  # raw check -- empty
        {"Items": []},  # real scan (falls through since trigger failed)
    ]
    mock_dynamodb.Table.return_value = mock_table

    with patch.object(list_jobs, "_trigger_harvest", return_value=False):
        event = make_event({"domain": "Engineering"})
        result = list_jobs.lambda_handler(event, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["count"] == 0


# ---------- _trigger_harvest internals ----------

@patch.object(list_jobs, "_ssm")
@patch.object(list_jobs, "_harvest_status_table")
@patch.object(list_jobs, "HARVESTER_INSTANCE_ID", "i-test123")
def test_trigger_harvest_sends_ssm_command_and_records_status(mock_status_table, mock_ssm):
    mock_status_table.get_item.return_value = {}  # no existing status
    mock_ssm.send_command.return_value = {"Command": {"CommandId": "cmd-abc"}}

    result = list_jobs._trigger_harvest("Engineering", "engineering", "Python")

    assert result is True
    call_kwargs = mock_ssm.send_command.call_args.kwargs
    assert call_kwargs["InstanceIds"] == ["i-test123"]
    assert "Engineering" in call_kwargs["Parameters"]["commands"][0]
    assert "Python" in call_kwargs["Parameters"]["commands"][0]

    put_kwargs = mock_status_table.put_item.call_args.kwargs
    assert put_kwargs["Item"]["domain"] == "engineering"
    assert put_kwargs["Item"]["status"] == "in_progress"
    assert put_kwargs["Item"]["ssmCommandId"] == "cmd-abc"


@patch.object(list_jobs, "_ssm")
@patch.object(list_jobs, "_harvest_status_table")
@patch.object(list_jobs, "HARVESTER_INSTANCE_ID", "i-test123")
def test_trigger_harvest_skips_duplicate_when_already_in_progress(mock_status_table, mock_ssm):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    mock_status_table.get_item.return_value = {
        "Item": {"domain": "engineering", "status": "in_progress", "startedAt": now}
    }

    result = list_jobs._trigger_harvest("Engineering", "engineering", None)

    assert result is True
    mock_ssm.send_command.assert_not_called()


@patch.object(list_jobs, "_ssm")
@patch.object(list_jobs, "_harvest_status_table")
@patch.object(list_jobs, "HARVESTER_INSTANCE_ID", "i-test123")
@patch.object(list_jobs, "STALE_THRESHOLD_SECONDS", 300)
def test_trigger_harvest_retries_when_status_is_stale(mock_status_table, mock_ssm):
    old_time = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=600)
    ).isoformat()
    mock_status_table.get_item.return_value = {
        "Item": {"domain": "engineering", "status": "in_progress", "startedAt": old_time}
    }
    mock_ssm.send_command.return_value = {"Command": {"CommandId": "cmd-retry"}}

    result = list_jobs._trigger_harvest("Engineering", "engineering", None)

    assert result is True
    mock_ssm.send_command.assert_called_once()


def test_trigger_harvest_returns_false_when_no_instance_configured():
    with patch.object(list_jobs, "HARVESTER_INSTANCE_ID", None):
        with patch.object(list_jobs, "_harvest_status_table") as mock_status_table:
            mock_status_table.get_item.return_value = {}
            result = list_jobs._trigger_harvest("Engineering", "engineering", None)
            assert result is False


@patch.object(list_jobs, "_ssm")
@patch.object(list_jobs, "_harvest_status_table")
@patch.object(list_jobs, "HARVESTER_INSTANCE_ID", "i-test123")
def test_trigger_harvest_ssm_failure_returns_false(mock_status_table, mock_ssm):
    from botocore.exceptions import ClientError

    mock_status_table.get_item.return_value = {}
    mock_ssm.send_command.side_effect = ClientError(
        {"Error": {"Code": "InvalidInstanceId", "Message": "boom"}}, "SendCommand"
    )

    result = list_jobs._trigger_harvest("Engineering", "engineering", None)
    assert result is False


# ---------- pagination (regression) ----------

@patch.object(list_jobs, "_dynamodb")
def test_next_token_round_trips(mock_dynamodb):
    mock_table = MagicMock()
    mock_table.scan.side_effect = [
        {"Items": [make_job("1")]},  # raw check
        {"Items": [make_job("1")], "LastEvaluatedKey": {"canonical_id": "1"}},  # real scan
    ]
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


# ---------- active-listing filter (matches get_matched_jobs) ----------

@patch.object(list_jobs, "_dynamodb")
def test_get_returns_only_open_listings_from_mixed_statuses(mock_dynamodb):
    mock_table = MagicMock()
    mock_table.scan.side_effect = [
        {"Items": [make_job("seed")]},
        {
            "Items": [
                make_job("active-1", status="ACTIVE", display_status="Active"),
                make_job("closed-1", status="closed", display_status="Closed"),
                make_job("expired-1", status="expired", display_status="Expired"),
                make_job("inactive-1", status="inactive", display_status="Inactive"),
                make_job("active-2", status="open", display_status="Open"),
            ]
        },
    ]
    mock_dynamodb.Table.return_value = mock_table

    result = list_jobs.lambda_handler(make_event({"domain": "Engineering"}), None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    ids = [job["canonical_id"] for job in body["jobs"]]
    assert ids == ["active-1", "active-2"]
    assert body["count"] == 2
    for job in body["jobs"]:
        assert "display_status" in job


@patch.object(list_jobs, "_dynamodb")
def test_get_all_closed_returns_empty_list_not_error(mock_dynamodb):
    mock_table = MagicMock()
    mock_table.scan.side_effect = [
        {"Items": [make_job("seed", status="closed")]},
        {
            "Items": [
                make_job("closed-1", status="closed"),
                make_job("expired-1", status="expired"),
                make_job("inactive-1", status="inactive"),
            ]
        },
    ]
    mock_dynamodb.Table.return_value = mock_table

    with patch.object(list_jobs, "_trigger_harvest") as mock_trigger:
        result = list_jobs.lambda_handler(make_event({"domain": "Engineering"}), None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["jobs"] == []
        assert body["count"] == 0
        mock_trigger.assert_not_called()


def test_active_definition_matches_get_matched_jobs():
    from lambdas.match import listing_utils as lu

    assert list_jobs.CLOSED_STATUSES == lu.CLOSED_STATUSES

    open_item = make_job("1", status="ACTIVE", display_status="Active")
    closed_item = make_job("2", status="closed", display_status="Closed")
    expired_via_display = {"status": "", "display_status": "expired"}
    assert list_jobs._is_open_listing(open_item) is True
    assert lu.is_open_listing(open_item) is True
    assert list_jobs._is_open_listing(closed_item) is False
    assert lu.is_open_listing(closed_item) is False
    assert list_jobs._is_open_listing(expired_via_display) is False
    assert lu.is_open_listing(expired_via_display) is False

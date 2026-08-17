"""
Local unit tests for get_final_recommendation.py.
No real AWS or Groq calls -- DynamoDB, jobs Scan, and Groq are mocked.

Run with (from the backend/ directory):
    PYTHONPATH=. pytest lambdas/tests/test_get_final_recommendation.py -v
"""

import json
from decimal import Decimal
from unittest.mock import patch
from urllib.error import URLError

from lambdas.match import get_final_recommendation as gfr

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


def completed_session(
    pow_score=Decimal("32"),
    score_percent=Decimal("80"),
    skill="Python",
    domain="Engineering",
):
    return {
        "Item": {
            "sessionId": SESSION_ID,
            "userId": USER_A,
            "status": "test_completed",
            "domain": domain,
            "skill": skill,
            "powScore": pow_score,
            "scorePercent": score_percent,
        }
    }


def listing(
    canonical_id,
    employment_type="Internship",
    min_pow=10,
    skills=None,
    status="ACTIVE",
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
        "required_skills": skills if skills is not None else ["Python"],
        "status": status,
        "display_status": "Active",
    }
    item.update(overrides)
    return item


def groq_payload(explanations=None, summary="You are ready for these roles."):
    return json.dumps(
        {
            "explanations": explanations or {},
            "readinessSummary": summary,
        }
    )


# ---------------------------------------------------------------------------
# Pure ranking helpers (no AWS)
# ---------------------------------------------------------------------------


def test_rank_jobs_orders_by_skill_overlap_then_canonical_id():
    """PoW and domain test are session-level; relative order is overlap-driven."""
    listings = [
        listing("z-low", skills=["Java"]),  # 0/1 overlap
        listing("a-mid", skills=["Python", "Django"]),  # 1/2 overlap
        listing("m-mid", skills=["Python", "Java"]),  # 1/2 overlap — tie with a-mid
        listing("b-high", skills=["Python"]),  # 1/1 overlap
    ]
    ranked = gfr._rank_jobs(
        [gfr._public_listing(x) for x in listings],
        pow_score=32,
        score_percent=80,
        skill="Python",
        domain="Engineering",
    )
    ids = [row["canonical_id"] for row in ranked]
    # Highest overlap first; among equal overlap, canonical_id ascending
    assert ids == ["b-high", "a-mid", "m-mid", "z-low"]
    assert ranked[0]["matchScore"] > ranked[1]["matchScore"] > ranked[3]["matchScore"]
    assert ranked[1]["matchScore"] == ranked[2]["matchScore"]


def test_rank_jobs_tie_break_is_stable_on_canonical_id():
    listings = [
        listing("job-b", skills=["Python"]),
        listing("job-a", skills=["Python"]),
        listing("job-c", skills=["Python"]),
    ]
    ranked = gfr._rank_jobs(
        [gfr._public_listing(x) for x in listings],
        pow_score=40,
        score_percent=90,
        skill="Python",
        domain="Engineering",
    )
    assert [r["canonical_id"] for r in ranked] == ["job-a", "job-b", "job-c"]
    assert len({r["matchScore"] for r in ranked}) == 1


def test_weights_sum_to_one():
    assert abs(gfr.WEIGHT_POW + gfr.WEIGHT_DOMAIN_TEST + gfr.WEIGHT_SKILL_OVERLAP - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Auth / status guards
# ---------------------------------------------------------------------------


@patch.object(gfr, "_sessions_table")
def test_missing_session_returns_403(mock_table):
    mock_table.get_item.return_value = {}
    result = gfr.lambda_handler(make_event(), None)
    assert result["statusCode"] == 403
    assert json.loads(result["body"])["error"] == "Forbidden"


@patch.object(gfr, "_sessions_table")
def test_session_owned_by_another_user_returns_403(mock_table):
    session = completed_session()
    session["Item"]["userId"] = USER_B
    mock_table.get_item.return_value = session
    result = gfr.lambda_handler(make_event(), None)
    assert result["statusCode"] == 403
    assert json.loads(result["body"])["error"] == "Forbidden"


@patch.object(gfr, "_sessions_table")
def test_session_not_test_completed_returns_409(mock_table):
    session = completed_session()
    session["Item"]["status"] = "test_in_progress"
    mock_table.get_item.return_value = session
    result = gfr.lambda_handler(make_event(), None)
    assert result["statusCode"] == 409
    assert "domain test" in json.loads(result["body"])["error"].lower()


@patch.object(gfr, "_sessions_table")
def test_missing_jwt_returns_401(mock_table):
    result = gfr.lambda_handler(make_event(sub=None), None)
    assert result["statusCode"] == 401


# ---------------------------------------------------------------------------
# Happy path + persistence
# ---------------------------------------------------------------------------


@patch.object(gfr, "_call_groq")
@patch.object(gfr, "_scan_jobs")
@patch.object(gfr, "_sessions_table")
def test_success_persists_ranked_jobs_and_status(mock_table, mock_scan, mock_groq):
    mock_table.get_item.return_value = completed_session()
    mock_scan.return_value = {
        "Items": [
            listing("job-low", skills=["Java", "Python"]),
            listing("job-high", skills=["Python"]),
            listing("closed", skills=["Python"], status="closed"),
            listing("no-skill", skills=["Java"]),
        ]
    }
    mock_groq.return_value = groq_payload(
        explanations={
            "job-high": "Strong Python match.",
            "job-low": "Partial skill overlap.",
        },
        summary="Solid readiness.",
    )

    result = gfr.lambda_handler(make_event(), None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])

    assert body["status"] == "recommendation_complete"
    assert body["explanationsAvailable"] is True
    assert body["readinessSummary"] == "Solid readiness."
    assert [j["canonical_id"] for j in body["rankedJobs"]] == ["job-high", "job-low"]
    assert body["rankedJobs"][0]["whyThisFits"] == "Strong Python match."
    assert body["rankedJobs"][0]["matchScore"] >= body["rankedJobs"][1]["matchScore"]

    mock_table.update_item.assert_called_once()
    kwargs = mock_table.update_item.call_args.kwargs
    expr_vals = kwargs["ExpressionAttributeValues"]
    assert expr_vals[":status"] == "recommendation_complete"
    assert expr_vals[":explained"] is True
    assert expr_vals[":summary"] == "Solid readiness."
    assert "recommendationCompletedAt" in kwargs["UpdateExpression"]
    assert "rankedJobs" in kwargs["UpdateExpression"]
    persisted_ids = [j["canonical_id"] for j in expr_vals[":ranked"]]
    assert persisted_ids == ["job-high", "job-low"]
    assert isinstance(expr_vals[":ranked"][0]["matchScore"], Decimal)


@patch.object(gfr, "_call_groq")
@patch.object(gfr, "_scan_jobs")
@patch.object(gfr, "_sessions_table")
def test_groq_called_exactly_once_when_jobs_exist(mock_table, mock_scan, mock_groq):
    mock_table.get_item.return_value = completed_session()
    mock_scan.return_value = {"Items": [listing("only-one", skills=["Python"])]}
    mock_groq.return_value = groq_payload(
        explanations={"only-one": "Fits well."},
        summary="Ready.",
    )

    result = gfr.lambda_handler(make_event(), None)
    assert result["statusCode"] == 200
    assert mock_groq.call_count == 1


@patch.object(gfr, "_call_groq")
@patch.object(gfr, "_scan_jobs")
@patch.object(gfr, "_sessions_table")
def test_zero_matches_still_calls_groq_for_summary(mock_table, mock_scan, mock_groq):
    mock_table.get_item.return_value = completed_session(skill="Python")
    mock_scan.return_value = {
        "Items": [
            listing("java-only", skills=["Java"]),
            listing("closed-py", skills=["Python"], status="closed"),
        ]
    }
    mock_groq.return_value = groq_payload(
        explanations={},
        summary="No listings matched; consider broadening skills.",
    )

    result = gfr.lambda_handler(make_event(), None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["rankedJobs"] == []
    assert body["explanationsAvailable"] is True
    assert "No listings" in body["readinessSummary"]
    assert mock_groq.call_count == 1

    # Prompt should mention no matches (user message)
    messages = mock_groq.call_args.args[0]
    user_content = messages[1]["content"]
    assert "No active job listings" in user_content


@patch.object(gfr, "_call_groq")
@patch.object(gfr, "_scan_jobs")
@patch.object(gfr, "_sessions_table")
def test_groq_failure_still_returns_ranking(mock_table, mock_scan, mock_groq):
    mock_table.get_item.return_value = completed_session()
    mock_scan.return_value = {
        "Items": [
            listing("a", skills=["Python"]),
            listing("b", skills=["Python", "Go"]),
        ]
    }
    mock_groq.side_effect = URLError("network down")

    result = gfr.lambda_handler(make_event(), None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["explanationsAvailable"] is False
    assert body["readinessSummary"] == ""
    assert len(body["rankedJobs"]) == 2
    assert all(j["whyThisFits"] == "" for j in body["rankedJobs"])
    assert body["status"] == "recommendation_complete"

    expr_vals = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert expr_vals[":explained"] is False
    assert expr_vals[":status"] == "recommendation_complete"


@patch.object(gfr, "_call_groq")
@patch.object(gfr, "_scan_jobs")
@patch.object(gfr, "_sessions_table")
def test_llm_does_not_change_rank_order(mock_table, mock_scan, mock_groq):
    mock_table.get_item.return_value = completed_session()
    mock_scan.return_value = {
        "Items": [
            listing("high", skills=["Python"]),
            listing("low", skills=["Python", "Java", "Go", "Rust"]),
        ]
    }
    # Groq returns explanations in reverse order of preference — must not reorder.
    mock_groq.return_value = groq_payload(
        explanations={
            "low": "Mentioned first by LLM",
            "high": "Mentioned second by LLM",
        },
        summary="ok",
    )

    result = gfr.lambda_handler(make_event(), None)
    body = json.loads(result["body"])
    assert [j["canonical_id"] for j in body["rankedJobs"]] == ["high", "low"]
    assert body["rankedJobs"][0]["whyThisFits"] == "Mentioned second by LLM"

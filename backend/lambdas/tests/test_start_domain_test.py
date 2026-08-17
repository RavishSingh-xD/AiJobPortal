"""
Local unit tests for start_domain_test.py.
No real AWS or Groq calls -- DynamoDB, jobs scan, and Groq are mocked.

Run with (from the backend/ directory):
    PYTHONPATH=. pytest lambdas/tests/test_start_domain_test.py -v
"""

import json
from unittest.mock import patch
from botocore.exceptions import ClientError

from lambdas.match import start_domain_test as sdt

USER_A = "USER_A"
USER_B = "USER_B"
SESSION_ID = "session-123"


def make_event(body_dict=None, sub=USER_A, session_id=SESSION_ID):
    event = {"body": json.dumps(body_dict or {})}
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


def awaiting_session():
    return {
        "Item": {
            "sessionId": SESSION_ID,
            "userId": USER_A,
            "status": "awaiting_test",
            "powScore": 32,
        }
    }


def groq_questions():
    return [
        {
            "questionText": f"Question {i}?",
            "options": ["A", "B", "C", "D"],
            "correctIndex": i % 4,
        }
        for i in range(15)
    ]


def valid_body(difficulty="medium"):
    return {
        "domain": "Engineering",
        "skill": "Python",
        "difficulty": difficulty,
    }


def assert_response_has_no_answers(body):
    dumped = json.dumps(body)
    assert "correctIndex" not in dumped
    assert "correctIndex" not in body
    assert "difficulty" not in body
    assert set(body["options"]) == {"A", "B", "C", "D"}
    assert body["questionId"] == "q1"
    assert body["totalQuestions"] == 15
    assert body["currentQuestionIndex"] == 0
    assert "timeLimitSeconds" in body


def test_invalid_domain_returns_400():
    result = sdt.lambda_handler(make_event({
        "domain": "engineering",
        "skill": "Python",
        "difficulty": "easy",
    }), None)
    assert result["statusCode"] == 400
    error = json.loads(result["body"])["error"]
    assert "Engineering" in error
    assert "Design" in error


def test_invalid_difficulty_returns_400():
    result = sdt.lambda_handler(make_event({
        "domain": "Engineering",
        "skill": "Python",
        "difficulty": "Easy",
    }), None)
    assert result["statusCode"] == 400
    error = json.loads(result["body"])["error"]
    assert "easy" in error
    assert "mixed" in error


@patch.object(sdt, "_sessions_table")
def test_missing_session_returns_403(mock_table):
    mock_table.get_item.return_value = {}
    result = sdt.lambda_handler(make_event(valid_body()), None)
    assert result["statusCode"] == 403
    assert json.loads(result["body"])["error"] == "Forbidden"
    mock_table.update_item.assert_not_called()


@patch.object(sdt, "_sessions_table")
def test_session_owned_by_another_user_returns_403(mock_table):
    mock_table.get_item.return_value = {
        "Item": {"sessionId": SESSION_ID, "userId": USER_B, "status": "awaiting_test"}
    }
    result = sdt.lambda_handler(make_event(valid_body()), None)
    assert result["statusCode"] == 403
    assert json.loads(result["body"])["error"] == "Forbidden"
    mock_table.update_item.assert_not_called()


@patch.object(sdt, "_sessions_table")
def test_wrong_status_returns_409(mock_table):
    mock_table.get_item.return_value = {
        "Item": {
            "sessionId": SESSION_ID,
            "userId": USER_A,
            "status": "in_progress",
        }
    }
    result = sdt.lambda_handler(make_event(valid_body()), None)
    assert result["statusCode"] == 409
    assert "not yet available" in json.loads(result["body"])["error"]
    mock_table.update_item.assert_not_called()


def _run_successful_start(mock_table, mock_skills, mock_groq, difficulty):
    mock_table.get_item.return_value = awaiting_session()
    mock_skills.return_value = "Python, React"
    mock_groq.return_value = json.dumps(groq_questions())
    result = sdt.lambda_handler(make_event(valid_body(difficulty)), None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert_response_has_no_answers(body)
    stored = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    questions = stored[":questions"]
    assert len(questions) == 15
    assert all("correctIndex" in q for q in questions)
    assert stored[":status"] == "test_in_progress"
    assert stored[":difficulty"] == difficulty
    return body, questions


@patch.object(sdt, "_call_groq")
@patch.object(sdt, "_sample_in_demand_skills")
@patch.object(sdt, "_sessions_table")
def test_successful_start_easy(mock_table, mock_skills, mock_groq):
    body, questions = _run_successful_start(mock_table, mock_skills, mock_groq, "easy")
    assert body["timeLimitSeconds"] == 45
    assert all(q["difficulty"] == "easy" and q["timeLimitSeconds"] == 45 for q in questions)


@patch.object(sdt, "_call_groq")
@patch.object(sdt, "_sample_in_demand_skills")
@patch.object(sdt, "_sessions_table")
def test_successful_start_medium(mock_table, mock_skills, mock_groq):
    body, questions = _run_successful_start(mock_table, mock_skills, mock_groq, "medium")
    assert body["timeLimitSeconds"] == 90
    assert all(q["difficulty"] == "medium" and q["timeLimitSeconds"] == 90 for q in questions)


@patch.object(sdt, "_call_groq")
@patch.object(sdt, "_sample_in_demand_skills")
@patch.object(sdt, "_sessions_table")
def test_successful_start_hard(mock_table, mock_skills, mock_groq):
    body, questions = _run_successful_start(mock_table, mock_skills, mock_groq, "hard")
    assert 120 <= body["timeLimitSeconds"] <= 150
    assert all(q["difficulty"] == "hard" for q in questions)
    assert all(120 <= q["timeLimitSeconds"] <= 150 for q in questions)


@patch.object(sdt, "_call_groq")
@patch.object(sdt, "_sample_in_demand_skills")
@patch.object(sdt, "_sessions_table")
def test_successful_start_mixed(mock_table, mock_skills, mock_groq):
    body, questions = _run_successful_start(mock_table, mock_skills, mock_groq, "mixed")
    assert all(q["difficulty"] in ("easy", "medium", "hard") for q in questions)
    limits = {"easy": 45, "medium": 90}
    for question in questions:
        if question["difficulty"] == "hard":
            assert 120 <= question["timeLimitSeconds"] <= 150
        else:
            assert question["timeLimitSeconds"] == limits[question["difficulty"]]
    assert "correctIndex" not in json.dumps(body)


@patch.object(sdt, "_call_groq", return_value="not json")
@patch.object(sdt, "_sample_in_demand_skills", return_value="")
@patch.object(sdt, "_sessions_table")
def test_invalid_groq_payload_returns_500_and_does_not_write(
    mock_table, mock_skills, mock_groq
):
    mock_table.get_item.return_value = awaiting_session()
    result = sdt.lambda_handler(make_event(valid_body()), None)
    assert result["statusCode"] == 500
    mock_table.update_item.assert_not_called()
    assert mock_groq.call_count == 2


@patch.object(sdt, "_sessions_table")
def test_jobs_scan_failure_still_starts_test(mock_table):
    mock_table.get_item.return_value = awaiting_session()
    with patch.object(
        sdt,
        "_sample_in_demand_skills",
        side_effect=ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "missing"}},
            "Scan",
        ),
    ), patch.object(sdt, "_call_groq", return_value=json.dumps(groq_questions())):
        result = sdt.lambda_handler(make_event(valid_body("easy")), None)
    assert result["statusCode"] == 200
    mock_table.update_item.assert_called_once()

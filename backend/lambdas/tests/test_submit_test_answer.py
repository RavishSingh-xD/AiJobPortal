"""
Local unit tests for submit_test_answer.py.
No real AWS calls -- DynamoDB is mocked.

Run with (from the backend/ directory):
    PYTHONPATH=. pytest lambdas/tests/test_submit_test_answer.py -v
"""

import json
import datetime
from decimal import Decimal
from unittest.mock import patch

from lambdas.match import submit_test_answer as sta

USER_A = "USER_A"
USER_B = "USER_B"
SESSION_ID = "session-123"


def make_event(body_dict=None, sub=USER_A, session_id=SESSION_ID):
    event = {"body": json.dumps(body_dict if body_dict is not None else {})}
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


def make_questions():
    questions = []
    for i in range(15):
        questions.append(
            {
                "questionId": f"q{i + 1}",
                "questionText": f"Question {i + 1}?",
                "options": ["A", "B", "C", "D"],
                "correctIndex": 1,
                "difficulty": "easy",
                "timeLimitSeconds": 45,
            }
        )
    return questions


def served_at(seconds_ago=5):
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - datetime.timedelta(seconds=seconds_ago)).isoformat()


def in_progress_session(index=0, seconds_ago=5, answers=None):
    return {
        "Item": {
            "sessionId": SESSION_ID,
            "userId": USER_A,
            "status": "test_in_progress",
            "currentQuestionIndex": index,
            "questionServedAt": served_at(seconds_ago),
            "questions": make_questions(),
            "answers": answers or [],
        }
    }


def recorded_answer(mock_table):
    values = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    return values[":newAnswer"][0]


@patch.object(sta, "_sessions_table")
def test_missing_session_returns_403(mock_table):
    mock_table.get_item.return_value = {}
    result = sta.lambda_handler(make_event({"questionId": "q1", "selectedIndex": 1}), None)
    assert result["statusCode"] == 403
    assert json.loads(result["body"])["error"] == "Forbidden"
    mock_table.update_item.assert_not_called()


@patch.object(sta, "_sessions_table")
def test_session_owned_by_another_user_returns_403(mock_table):
    session = in_progress_session()
    session["Item"]["userId"] = USER_B
    mock_table.get_item.return_value = session
    result = sta.lambda_handler(make_event({"questionId": "q1", "selectedIndex": 1}), None)
    assert result["statusCode"] == 403
    assert json.loads(result["body"])["error"] == "Forbidden"
    mock_table.update_item.assert_not_called()


@patch.object(sta, "_sessions_table")
def test_wrong_status_returns_409(mock_table):
    session = in_progress_session()
    session["Item"]["status"] = "awaiting_test"
    mock_table.get_item.return_value = session
    result = sta.lambda_handler(make_event({"questionId": "q1", "selectedIndex": 1}), None)
    assert result["statusCode"] == 409
    mock_table.update_item.assert_not_called()


@patch.object(sta, "_sessions_table")
def test_question_id_mismatch_returns_409(mock_table):
    mock_table.get_item.return_value = in_progress_session(index=0)
    result = sta.lambda_handler(make_event({"questionId": "q2", "selectedIndex": 1}), None)
    assert result["statusCode"] == 409
    assert "no longer current" in json.loads(result["body"])["error"]
    mock_table.update_item.assert_not_called()


def test_invalid_selected_index_type_returns_400():
    result = sta.lambda_handler(
        make_event({"questionId": "q1", "selectedIndex": True}),
        None,
    )
    assert result["statusCode"] == 400
    assert "selectedIndex" in json.loads(result["body"])["error"]


def test_invalid_selected_index_range_returns_400():
    result = sta.lambda_handler(
        make_event({"questionId": "q1", "selectedIndex": 4}),
        None,
    )
    assert result["statusCode"] == 400


@patch.object(sta, "_sessions_table")
def test_correct_answer_within_time_limit(mock_table):
    mock_table.get_item.return_value = in_progress_session(index=0, seconds_ago=5)
    result = sta.lambda_handler(make_event({"questionId": "q1", "selectedIndex": 1}), None)
    assert result["statusCode"] == 200
    answer = recorded_answer(mock_table)
    assert answer["correct"] is True
    assert answer["timedOut"] is False
    assert answer["selectedIndex"] == 1


@patch.object(sta, "_sessions_table")
def test_incorrect_answer_within_time_limit(mock_table):
    mock_table.get_item.return_value = in_progress_session(index=0, seconds_ago=5)
    result = sta.lambda_handler(make_event({"questionId": "q1", "selectedIndex": 0}), None)
    assert result["statusCode"] == 200
    answer = recorded_answer(mock_table)
    assert answer["correct"] is False
    assert answer["timedOut"] is False
    body = json.loads(result["body"])
    assert "correct" not in body
    assert "correctIndex" not in json.dumps(body)


@patch.object(sta, "_sessions_table")
def test_timeout_marks_wrong_even_if_selected_index_matches(mock_table):
    mock_table.get_item.return_value = in_progress_session(index=0, seconds_ago=120)
    result = sta.lambda_handler(make_event({"questionId": "q1", "selectedIndex": 1}), None)
    assert result["statusCode"] == 200
    answer = recorded_answer(mock_table)
    assert answer["timedOut"] is True
    assert answer["correct"] is False
    assert answer["timeTakenSeconds"] == Decimal("45.0")


@patch.object(sta, "_sessions_table")
def test_missing_selected_index_is_incorrect(mock_table):
    mock_table.get_item.return_value = in_progress_session(index=0, seconds_ago=5)
    result = sta.lambda_handler(make_event({"questionId": "q1"}), None)
    assert result["statusCode"] == 200
    answer = recorded_answer(mock_table)
    assert answer["selectedIndex"] is None
    assert answer["correct"] is False
    assert answer["timedOut"] is False


@patch.object(sta, "_sessions_table")
def test_non_final_question_returns_next_sanitized_question(mock_table):
    mock_table.get_item.return_value = in_progress_session(index=0, seconds_ago=5)
    result = sta.lambda_handler(make_event({"questionId": "q1", "selectedIndex": 1}), None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["testCompleted"] is False
    assert body["questionId"] == "q2"
    assert body["currentQuestionIndex"] == 1
    assert body["totalQuestions"] == 15
    assert "correctIndex" not in json.dumps(body)
    assert "difficulty" not in body
    assert "correct" not in body
    values = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":index"] == 1
    expr = mock_table.update_item.call_args.kwargs["UpdateExpression"]
    assert "list_append" in expr
    assert "if_not_exists" in expr


@patch.object(sta, "_sessions_table")
def test_final_question_completes_test_with_score_percent(mock_table):
    prior = [
        {
            "questionId": f"q{i}",
            "selectedIndex": 1,
            "correct": True,
            "timedOut": False,
            "timeTakenSeconds": Decimal("10"),
        }
        for i in range(1, 15)
    ]
    mock_table.get_item.return_value = in_progress_session(
        index=14, seconds_ago=5, answers=prior
    )
    result = sta.lambda_handler(make_event({"questionId": "q15", "selectedIndex": 1}), None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body == {
        "testCompleted": True,
        "scorePercent": 100.0,
        "totalQuestions": 15,
    }
    assert "questionId" not in body
    assert "correct" not in body
    values = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":status"] == "test_completed"
    assert values[":score"] == Decimal("100.0")
    assert values[":newAnswer"][0]["correct"] is True


@patch.object(sta, "_sessions_table")
def test_final_question_score_percent_rounded_to_one_decimal(mock_table):
    prior = [
        {
            "questionId": f"q{i}",
            "selectedIndex": 1 if i <= 10 else 0,
            "correct": i <= 10,
            "timedOut": False,
            "timeTakenSeconds": Decimal("10"),
        }
        for i in range(1, 15)
    ]
    mock_table.get_item.return_value = in_progress_session(
        index=14, seconds_ago=5, answers=prior
    )
    result = sta.lambda_handler(make_event({"questionId": "q15", "selectedIndex": 0}), None)
    body = json.loads(result["body"])
    # 10 of 14 prior correct, this one wrong -> 10/15 = 66.666... -> 66.7
    assert body["testCompleted"] is True
    assert body["scorePercent"] == 66.7
    values = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":newAnswer"][0]["correct"] is False

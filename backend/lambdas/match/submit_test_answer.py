"""
API Gateway-triggered Lambda: records one domain-test answer and either
serves the next sanitized question or completes the test.

Handler: submit_test_answer.lambda_handler

Expected request (API Gateway HTTP API, JWT authorizer):
    POST /match/{sessionId}/test/answer
    {
        "questionId": "q1",
        "selectedIndex": 2
    }

selectedIndex may be omitted or null if the client timed out without
choosing an answer.

Required IAM permissions (submitTestAnswerRole -- create when deploying):
    dynamodb:GetItem, dynamodb:UpdateItem on match_sessions

Environment variables:
    MATCH_SESSIONS_TABLE  (default: "match_sessions")
    AWS_REGION            (default fallback: "ap-south-1")
"""

import os
import json
import logging
import datetime
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MATCH_SESSIONS_TABLE = os.environ.get("MATCH_SESSIONS_TABLE", "match_sessions")
REGION = os.environ.get("AWS_REGION", "ap-south-1")

FORBIDDEN_MESSAGE = "Forbidden"
QUESTION_COUNT = 15
STATUS_REQUIRED = "test_in_progress"
CONFLICT_NOT_IN_PROGRESS = "Domain test is not in progress."
CONFLICT_STALE_QUESTION = (
    "This question is no longer current -- you may have already "
    "answered it or the session state changed"
)

_dynamodb = boto3.resource("dynamodb", region_name=REGION)
_sessions_table = _dynamodb.Table(MATCH_SESSIONS_TABLE)


def _cors_headers():
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "OPTIONS,POST",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
    }


def _json_default(obj):
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _response(status_code: int, body_dict: dict):
    return {
        "statusCode": status_code,
        "headers": _cors_headers(),
        "body": json.dumps(body_dict, default=_json_default),
    }


def _get_authenticated_user_id(event):
    try:
        user_id = (
            event.get("requestContext", {})
            .get("authorizer", {})
            .get("jwt", {})
            .get("claims", {})
            .get("sub")
        )
    except (AttributeError, TypeError):
        return None

    if not user_id or not isinstance(user_id, str):
        return None

    return user_id


def _coerce_selected_index(value):
    if isinstance(value, bool):
        raise ValueError("selectedIndex must be an integer 0-3")
    if isinstance(value, int):
        index = value
    elif isinstance(value, float) and value == int(value):
        index = int(value)
    else:
        raise ValueError("selectedIndex must be an integer 0-3")
    if index < 0 or index > 3:
        raise ValueError("selectedIndex must be an integer 0-3")
    return index


def _as_int(value, default=0):
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, Decimal):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_served_at(raw):
    if not raw or not isinstance(raw, str):
        return None
    try:
        return datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None


def _sanitize_question(question: dict) -> dict:
    return {
        "questionId": question["questionId"],
        "questionText": question["questionText"],
        "options": question["options"],
        "timeLimitSeconds": _as_int(question.get("timeLimitSeconds"), 0),
    }


def lambda_handler(event, context):
    user_id = _get_authenticated_user_id(event)
    if user_id is None:
        return _response(401, {"error": "Unauthorized"})

    path_params = event.get("pathParameters") or {}
    session_id = path_params.get("sessionId")
    if not session_id or not isinstance(session_id, str):
        return _response(400, {"error": "sessionId is required"})

    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _response(400, {"error": "Request body must be valid JSON"})

    question_id = body.get("questionId")
    if not question_id or not isinstance(question_id, str) or not question_id.strip():
        return _response(400, {"error": "questionId is required"})
    question_id = question_id.strip()

    if "selectedIndex" not in body or body.get("selectedIndex") is None:
        selected_index = None
    else:
        try:
            selected_index = _coerce_selected_index(body.get("selectedIndex"))
        except ValueError:
            return _response(400, {"error": "selectedIndex must be an integer 0-3"})

    try:
        get_response = _sessions_table.get_item(Key={"sessionId": session_id})
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB GetItem failed for match_sessions: %s", error_code)
        return _response(500, {"error": "Could not look up match session"})

    session_item = get_response.get("Item")
    if session_item is None:
        return _response(403, {"error": FORBIDDEN_MESSAGE})

    if session_item.get("userId") != user_id:
        return _response(403, {"error": FORBIDDEN_MESSAGE})

    if session_item.get("status") != STATUS_REQUIRED:
        return _response(409, {"error": CONFLICT_NOT_IN_PROGRESS})

    questions = session_item.get("questions") or []
    current_index = _as_int(session_item.get("currentQuestionIndex"), 0)
    if current_index < 0 or current_index >= len(questions):
        logger.error(
            "Invalid currentQuestionIndex=%s sessionId=%s", current_index, session_id
        )
        return _response(409, {"error": CONFLICT_STALE_QUESTION})

    current_question = questions[current_index]
    if current_question.get("questionId") != question_id:
        return _response(409, {"error": CONFLICT_STALE_QUESTION})

    now = datetime.datetime.now(datetime.timezone.utc)
    served_at = _parse_served_at(session_item.get("questionServedAt"))
    time_limit = _as_int(current_question.get("timeLimitSeconds"), 0)
    if served_at is None:
        elapsed = time_limit + 1
    else:
        if served_at.tzinfo is None:
            served_at = served_at.replace(tzinfo=datetime.timezone.utc)
        elapsed = max(0.0, (now - served_at).total_seconds())

    timed_out = elapsed > time_limit
    stored_correct = _as_int(current_question.get("correctIndex"), -1)
    if timed_out or selected_index is None:
        is_correct = False
    else:
        is_correct = selected_index == stored_correct

    time_taken = min(elapsed, time_limit) if timed_out else elapsed
    answer_record = {
        "questionId": question_id,
        "selectedIndex": selected_index,
        "correct": is_correct,
        "timedOut": timed_out,
        "timeTakenSeconds": Decimal(str(round(time_taken, 1))),
    }

    now_iso = now.isoformat()
    is_last = current_index >= QUESTION_COUNT - 1
    expr_values = {
        ":empty": [],
        ":newAnswer": [answer_record],
        ":expectedIndex": current_index,
        ":inProgress": STATUS_REQUIRED,
    }

    if is_last:
        prior_answers = session_item.get("answers") or []
        correct_count = sum(1 for item in prior_answers if item.get("correct") is True)
        if is_correct:
            correct_count += 1
        score_percent = round((correct_count / QUESTION_COUNT) * 100, 1)
        update_expression = (
            "SET answers = list_append(if_not_exists(answers, :empty), :newAnswer), "
            "#status = :status, scorePercent = :score, testCompletedAt = :completed"
        )
        expr_values[":status"] = "test_completed"
        expr_values[":score"] = Decimal(str(score_percent))
        expr_values[":completed"] = now_iso
        response_body = {
            "testCompleted": True,
            "scorePercent": score_percent,
            "totalQuestions": QUESTION_COUNT,
        }
    else:
        next_index = current_index + 1
        if next_index >= len(questions):
            logger.error("Missing next question sessionId=%s index=%s", session_id, next_index)
            return _response(500, {"error": "Could not record test answer"})
        next_question = questions[next_index]
        update_expression = (
            "SET answers = list_append(if_not_exists(answers, :empty), :newAnswer), "
            "currentQuestionIndex = :index, questionServedAt = :served"
        )
        expr_values[":index"] = next_index
        expr_values[":served"] = now_iso
        sanitized = _sanitize_question(next_question)
        response_body = {
            **sanitized,
            "totalQuestions": QUESTION_COUNT,
            "currentQuestionIndex": next_index,
            "testCompleted": False,
        }

    try:
        _sessions_table.update_item(
            Key={"sessionId": session_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues=expr_values,
            ConditionExpression=(
                "attribute_exists(sessionId) AND currentQuestionIndex = :expectedIndex "
                "AND #status = :inProgress"
            ),
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB UpdateItem failed for match_sessions: %s", error_code)
        if error_code == "ConditionalCheckFailedException":
            return _response(409, {"error": CONFLICT_STALE_QUESTION})
        return _response(500, {"error": "Could not record test answer"})

    logger.info(
        "Recorded test answer sessionId=%s questionId=%s last=%s",
        session_id,
        question_id,
        is_last,
    )
    return _response(200, response_body)

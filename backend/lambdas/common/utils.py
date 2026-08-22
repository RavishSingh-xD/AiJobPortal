"""
Shared HTTP / JWT helpers for API Gateway HTTP API (JWT authorizer) Lambdas.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj: Any):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super().default(obj)


def get_user_id(event: dict) -> str:
    """Extract Cognito `sub` from API Gateway JWT authorizer claims."""
    try:
        sub = event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Missing or invalid JWT claims in request context") from exc
    if not sub or not isinstance(sub, str):
        raise ValueError("Missing or invalid JWT claims in request context")
    return sub


def response(status_code: int, body: Any, *, cors: bool = False) -> dict:
    """Build an API Gateway proxy response with JSON body."""
    headers = {"Content-Type": "application/json"}
    if cors:
        headers.update(
            {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,Authorization",
                "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
            }
        )
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, cls=DecimalEncoder),
    }


def parse_json_body(event: dict) -> dict:
    """Parse event['body'] as JSON object; return {} for empty body."""
    raw = event.get("body")
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Request body must be a JSON object")
    return parsed

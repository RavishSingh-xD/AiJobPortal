"""
saved_jobs.py -- Lambda handling POST/DELETE/GET for a user's saved
opportunities (renamed from "Saved Internships" -- real save/unsave,
not a placeholder).

Table: SavedJobs
  PK: userId (string)
  SK: canonicalId (string)
  Attrs: jobTitle, company, domain, applyUrl, savedAt
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
SAVED_JOBS_TABLE_NAME = os.environ.get("SAVED_JOBS_TABLE_NAME", "SavedJobs")
saved_jobs_table = dynamodb.Table(SAVED_JOBS_TABLE_NAME)

VALID_DOMAINS = {"Engineering", "Business", "Healthcare", "Design"}
_DOMAIN_BY_LOWER = {d.lower(): d for d in VALID_DOMAINS}


def _normalize_domain(value):
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    return _DOMAIN_BY_LOWER.get(stripped.lower(), stripped)


def _get_user_id(event: dict) -> str:
    try:
        sub = event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
    except (KeyError, TypeError):
        raise ValueError("Missing or invalid JWT claims in request context")
    if not sub or not isinstance(sub, str):
        raise ValueError("Missing or invalid JWT claims in request context")
    return sub


def _response(status_code: int, body) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _handle_post(user_id: str, body: dict) -> dict:
    if not isinstance(body, dict):
        return _response(400, {"error": "Invalid request body"})

    canonical_id = body.get("canonicalId")
    job_title = body.get("jobTitle")
    company = body.get("company")
    domain = _normalize_domain(body.get("domain"))
    apply_url = body.get("applyUrl")

    errors = {}
    if not canonical_id or not isinstance(canonical_id, str):
        errors["canonicalId"] = "Required"
    if not job_title or not isinstance(job_title, str):
        errors["jobTitle"] = "Required"
    if not company or not isinstance(company, str):
        errors["company"] = "Required"
    if domain not in VALID_DOMAINS:
        errors["domain"] = f"Must be one of {sorted(VALID_DOMAINS)}"
    if not apply_url or not isinstance(apply_url, str):
        errors["applyUrl"] = "Required"

    if errors:
        return _response(400, {"errors": errors})

    item = {
        "userId": user_id,
        "canonicalId": canonical_id,
        "jobTitle": job_title,
        "company": company,
        "domain": domain,
        "applyUrl": apply_url,
        "savedAt": datetime.now(timezone.utc).isoformat(),
    }

    saved_jobs_table.put_item(Item=item)
    return _response(201, item)


def _handle_delete(user_id: str, canonical_id: str) -> dict:
    if not canonical_id:
        return _response(400, {"error": "canonicalId is required"})

    saved_jobs_table.delete_item(
        Key={"userId": user_id, "canonicalId": canonical_id}
    )
    return _response(200, {"deleted": True, "canonicalId": canonical_id})


def _handle_get(user_id: str) -> dict:
    result = saved_jobs_table.query(
        KeyConditionExpression=Key("userId").eq(user_id)
    )
    items = result.get("Items", [])
    items.sort(key=lambda i: i.get("savedAt", ""), reverse=True)
    return _response(200, {"savedJobs": items})


def handler(event, context):
    try:
        user_id = _get_user_id(event)
    except ValueError as e:
        return _response(401, {"error": str(e)})

    http_method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
    )

    if http_method == "POST":
        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _response(400, {"error": "Invalid JSON body"})
        return _handle_post(user_id, body)

    if http_method == "DELETE":
        canonical_id = (event.get("queryStringParameters") or {}).get("canonicalId")
        return _handle_delete(user_id, canonical_id)

    if http_method == "GET":
        return _handle_get(user_id)

    return _response(405, {"error": f"Unsupported method: {http_method}"})

"""
saved_searches.py -- Saved search criteria with in-app new-match alerts.

Table: SavedSearches
  PK: userId (string)
  SK: searchId (string, uuid)

Endpoints (API Gateway HTTP API, JWT authorizer):
  POST   /saved-searches              create saved search
  GET    /saved-searches              list saved searches (+ new match counts)
  GET    /saved-searches/alerts       new listings since last seen per search
  POST   /saved-searches/ack          mark canonicalIds as seen for a search
  DELETE /saved-searches?searchId=... remove saved search
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

try:
    from lambdas.match import listing_utils as lu
except ImportError:
    import listing_utils as lu

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
SAVED_SEARCHES_TABLE_NAME = os.environ.get("SAVED_SEARCHES_TABLE_NAME", "SavedSearches")
saved_searches_table = dynamodb.Table(SAVED_SEARCHES_TABLE_NAME)

VALID_DOMAINS = {"Engineering", "Business", "Healthcare"}
_DOMAIN_BY_LOWER = {domain.lower(): domain for domain in VALID_DOMAINS}
MAX_SEEN_IDS = 200
SCAN_LIMIT = 100
DOMAIN_TABLE_MAP = {
    "Engineering": "jobs_engineering",
    "Business": "jobs_business",
    "Healthcare": "jobs_healthcare",
}


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
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
        },
        "body": json.dumps(body, default=str),
    }


def _route_path(event: dict) -> str:
    return (event.get("rawPath") or event.get("path") or "").rstrip("/")


def _matches_saved_search(item: dict, skill: str, employment_type: str) -> bool:
    if not lu.is_open_listing(item):
        return False
    if employment_type:
        if str(item.get("employment_type") or "").strip().lower() != employment_type.strip().lower():
            return False
    if skill and not lu.skill_matches(item.get("required_skills"), skill):
        return False
    return True


def _scan_domain_jobs(domain: str):
    table_name = DOMAIN_TABLE_MAP.get(domain)
    if not table_name:
        return []
    table = dynamodb.Table(table_name)
    try:
        response = table.scan(Limit=SCAN_LIMIT)
    except ClientError as e:
        logger.warning("Scan failed for domain=%s: %s", domain, e)
        return []
    return response.get("Items") or []


def _listing_preview(item: dict, domain: str) -> dict:
    listing = lu.public_listing(item)
    listing["domain"] = domain
    return listing


def _find_new_matches(search_item: dict) -> list[dict]:
    domain = search_item.get("domain")
    skill = (search_item.get("skill") or "").strip()
    employment_type = (search_item.get("employmentType") or "").strip()
    seen = set(search_item.get("seenCanonicalIds") or [])

    matches = []
    for item in _scan_domain_jobs(domain):
        if not isinstance(item, dict):
            continue
        if not _matches_saved_search(item, skill, employment_type):
            continue
        canonical_id = item.get("canonical_id")
        if not canonical_id or canonical_id in seen:
            continue
        matches.append(_listing_preview(item, domain))
    return matches


def _handle_post(user_id: str, body: dict) -> dict:
    if not isinstance(body, dict):
        return _response(400, {"error": "Invalid request body"})

    domain = _normalize_domain(body.get("domain"))
    skill = body.get("skill") or ""
    employment_type = body.get("employmentType") or ""
    label = body.get("label") or ""

    errors = {}
    if domain not in VALID_DOMAINS:
        errors["domain"] = f"Must be one of {sorted(VALID_DOMAINS)}"
    if skill is not None and not isinstance(skill, str):
        errors["skill"] = "Must be a string"
    if employment_type is not None and not isinstance(employment_type, str):
        errors["employmentType"] = "Must be a string"
    if label is not None and not isinstance(label, str):
        errors["label"] = "Must be a string"

    if errors:
        return _response(400, {"errors": errors})

    search_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "userId": user_id,
        "searchId": search_id,
        "domain": domain,
        "skill": skill.strip(),
        "employmentType": employment_type.strip(),
        "label": label.strip(),
        "createdAt": now,
        "lastCheckedAt": now,
        "seenCanonicalIds": [],
    }
    saved_searches_table.put_item(Item=item)
    return _response(201, item)


def _handle_delete(user_id: str, search_id: str) -> dict:
    if not search_id:
        return _response(400, {"error": "searchId is required"})

    saved_searches_table.delete_item(Key={"userId": user_id, "searchId": search_id})
    return _response(200, {"deleted": True, "searchId": search_id})


def _handle_list(user_id: str) -> dict:
    result = saved_searches_table.query(KeyConditionExpression=Key("userId").eq(user_id))
    items = result.get("Items", [])
    items.sort(key=lambda row: row.get("createdAt", ""), reverse=True)

    enriched = []
    for item in items:
        new_matches = _find_new_matches(item)
        enriched.append(
            {
                **item,
                "newMatchCount": len(new_matches),
                "newMatchesPreview": new_matches[:3],
            }
        )
    return _response(200, {"savedSearches": enriched})


def _handle_alerts(user_id: str) -> dict:
    result = saved_searches_table.query(KeyConditionExpression=Key("userId").eq(user_id))
    alerts = []
    for item in result.get("Items", []):
        new_matches = _find_new_matches(item)
        if not new_matches:
            continue
        alerts.append(
            {
                "searchId": item.get("searchId"),
                "label": item.get("label") or item.get("domain"),
                "domain": item.get("domain"),
                "skill": item.get("skill"),
                "employmentType": item.get("employmentType"),
                "newMatchCount": len(new_matches),
                "newMatches": new_matches[:10],
            }
        )
    return _response(200, {"alerts": alerts, "alertCount": len(alerts)})


def _handle_ack(user_id: str, body: dict) -> dict:
    if not isinstance(body, dict):
        return _response(400, {"error": "Invalid request body"})

    search_id = body.get("searchId")
    canonical_ids = body.get("canonicalIds")
    if not search_id or not isinstance(search_id, str):
        return _response(400, {"error": "searchId is required"})
    if not isinstance(canonical_ids, list):
        return _response(400, {"error": "canonicalIds must be an array"})

    get_response = saved_searches_table.get_item(
        Key={"userId": user_id, "searchId": search_id}
    )
    item = get_response.get("Item")
    if not item:
        return _response(404, {"error": "Saved search not found"})

    seen = list(item.get("seenCanonicalIds") or [])
    for canonical_id in canonical_ids:
        if isinstance(canonical_id, str) and canonical_id and canonical_id not in seen:
            seen.append(canonical_id)
    seen = seen[-MAX_SEEN_IDS:]

    now = datetime.now(timezone.utc).isoformat()
    saved_searches_table.update_item(
        Key={"userId": user_id, "searchId": search_id},
        UpdateExpression="SET seenCanonicalIds = :seen, lastCheckedAt = :checked",
        ExpressionAttributeValues={":seen": seen, ":checked": now},
    )
    return _response(200, {"acknowledged": True, "searchId": search_id})


def handler(event, context):
    try:
        user_id = _get_user_id(event)
    except ValueError as e:
        return _response(401, {"error": str(e)})

    http_method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
    )
    path = _route_path(event)

    if http_method == "POST" and path.endswith("/saved-searches/ack"):
        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _response(400, {"error": "Invalid JSON body"})
        return _handle_ack(user_id, body)

    if http_method == "POST":
        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _response(400, {"error": "Invalid JSON body"})
        return _handle_post(user_id, body)

    if http_method == "GET" and path.endswith("/saved-searches/alerts"):
        return _handle_alerts(user_id)

    if http_method == "GET":
        return _handle_list(user_id)

    if http_method == "DELETE":
        search_id = (event.get("queryStringParameters") or {}).get("searchId")
        return _handle_delete(user_id, search_id)

    return _response(405, {"error": f"Unsupported method: {http_method}"})

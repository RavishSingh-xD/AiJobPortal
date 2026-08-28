"""
profile.py -- Lambda handling GET/PUT for a user's profile.

Fields: linkedinUrl, githubUrl -- stored as two new attributes on the
existing Users table (no new table, DynamoDB is schemaless beyond keys).

userId is ALWAYS derived from the JWT sub claim
(event.requestContext.authorizer.jwt.claims.sub), never from client
input -- same security pattern as generate_upload_url.py.

On GET, if the Cognito PostConfirmation trigger failed to create a Users
row, this handler backfills a minimal record from JWT claims so the rest
of the app (verify-id, match, profile) can proceed.

completionPct is computed server-side from which profile fields are
filled in. Extend COMPLETION_FIELDS as more profile fields are added.
"""

import json
import logging
import os
import datetime
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
USERS_TABLE_NAME = os.environ.get("USERS_TABLE_NAME", "Users")
users_table = dynamodb.Table(USERS_TABLE_NAME)

LINKEDIN_DOMAIN = "linkedin.com"
GITHUB_DOMAIN = "github.com"

COMPLETION_FIELDS = ["linkedinUrl", "githubUrl"]


def _valid_url(url: str, expected_domain: str) -> bool:
    """Validate that `url` is an https URL whose netloc matches
    `expected_domain` (or a subdomain of it).

    IMPORTANT: checks the URL's netloc via urlparse, not whether the
    domain string merely appears somewhere in the URL. A naive substring
    check (`expected_domain in url.lower()`) would incorrectly accept
    https://not-linkedin.com/x as a valid LinkedIn URL, since the string
    "linkedin.com" is literally contained inside "not-linkedin.com".
    """
    if not url or not isinstance(url, str):
        return False
    if not url.startswith("https://"):
        return False
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return False
    return netloc == expected_domain or netloc.endswith("." + expected_domain)


def _get_user_id(event: dict) -> str:
    try:
        sub = event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
    except (KeyError, TypeError):
        raise ValueError("Missing or invalid JWT claims in request context")
    if not sub or not isinstance(sub, str):
        raise ValueError("Missing or invalid JWT claims in request context")
    return sub


def _jwt_claims(event: dict) -> dict:
    try:
        claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    except (KeyError, TypeError):
        return {}
    return claims if isinstance(claims, dict) else {}


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _compute_completion_pct(item: dict) -> int:
    if not COMPLETION_FIELDS:
        return 0
    filled = sum(1 for field in COMPLETION_FIELDS if item.get(field))
    return round((filled / len(COMPLETION_FIELDS)) * 100)


def _profile_payload(item: dict) -> dict:
    return {
        "linkedinUrl": item.get("linkedinUrl", ""),
        "githubUrl": item.get("githubUrl", ""),
        "completionPct": _compute_completion_pct(item),
        "verificationStatus": item.get("verificationStatus", ""),
        "verificationType": item.get("verificationType", ""),
        "email": item.get("email", ""),
        "name": item.get("name", ""),
    }


def _ensure_users_record(user_id: str, claims: dict) -> dict:
    """Return the Users item, creating a minimal row from JWT if missing."""
    try:
        result = users_table.get_item(Key={"userId": user_id})
    except ClientError as e:
        logger.error(
            "Users GetItem failed for userId=%s: %s",
            user_id,
            e.response.get("Error", {}).get("Code", "Unknown"),
        )
        raise

    item = result.get("Item")
    if item:
        return item

    email = str(claims.get("email") or "").strip().lower()
    name = str(claims.get("name") or "").strip()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    verification_type = (
        str(claims.get("custom:verification_type") or "manual").strip() or "manual"
    )
    verification_status = (
        str(claims.get("custom:verification_status") or "pending_review").strip()
        or "pending_review"
    )
    college_name = str(claims.get("custom:college_name") or "").strip()

    item = {
        "userId": user_id,
        "email": email,
        "name": name,
        "role": "student",
        "collegeName": college_name,
        "verificationType": verification_type,
        "verificationStatus": verification_status,
        "createdAt": now,
        "updatedAt": now,
    }

    try:
        users_table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(userId)",
        )
        logger.info("Backfilled missing Users record for userId=%s", user_id)
        return item
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "Unknown")
        if code == "ConditionalCheckFailedException":
            result = users_table.get_item(Key={"userId": user_id})
            return result.get("Item") or item
        logger.error("Users PutItem backfill failed for userId=%s: %s", user_id, code)
        raise


def _handle_get(user_id: str, claims: dict) -> dict:
    item = _ensure_users_record(user_id, claims)
    return _response(200, _profile_payload(item))


def _handle_put(user_id: str, body: dict, claims: dict) -> dict:
    if not isinstance(body, dict):
        return _response(400, {"error": "Invalid request body"})

    # Guarantee the base Users row exists before UpdateItem.
    _ensure_users_record(user_id, claims)

    errors = {}

    if "linkedinUrl" in body:
        linkedin_url = body.get("linkedinUrl") or ""
        if linkedin_url and not _valid_url(linkedin_url, LINKEDIN_DOMAIN):
            errors["linkedinUrl"] = "Must be a valid https://linkedin.com URL"

    if "githubUrl" in body:
        github_url = body.get("githubUrl") or ""
        if github_url and not _valid_url(github_url, GITHUB_DOMAIN):
            errors["githubUrl"] = "Must be a valid https://github.com URL"

    if errors:
        return _response(400, {"errors": errors})

    update_expr_parts = []
    expr_attr_values = {}
    expr_attr_names = {}

    if "linkedinUrl" in body:
        update_expr_parts.append("#linkedinUrl = :linkedinUrl")
        expr_attr_names["#linkedinUrl"] = "linkedinUrl"
        expr_attr_values[":linkedinUrl"] = body.get("linkedinUrl") or ""

    if "githubUrl" in body:
        update_expr_parts.append("#githubUrl = :githubUrl")
        expr_attr_names["#githubUrl"] = "githubUrl"
        expr_attr_values[":githubUrl"] = body.get("githubUrl") or ""

    if not update_expr_parts:
        return _response(400, {"error": "No valid fields to update"})

    update_expr_parts.append("updatedAt = :updatedAt")
    expr_attr_values[":updatedAt"] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()

    users_table.update_item(
        Key={"userId": user_id},
        UpdateExpression="SET " + ", ".join(update_expr_parts),
        ExpressionAttributeNames=expr_attr_names,
        ExpressionAttributeValues=expr_attr_values,
    )

    result = users_table.get_item(Key={"userId": user_id})
    item = result.get("Item", {})
    return _response(200, _profile_payload(item))


def handler(event, context):
    try:
        user_id = _get_user_id(event)
    except ValueError as e:
        return _response(401, {"error": str(e)})

    claims = _jwt_claims(event)

    http_method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
    )

    if http_method == "GET":
        return _handle_get(user_id, claims)

    if http_method == "PUT":
        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _response(400, {"error": "Invalid JSON body"})
        return _handle_put(user_id, body, claims)

    return _response(405, {"error": f"Unsupported method: {http_method}"})

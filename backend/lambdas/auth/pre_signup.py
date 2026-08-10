

import os
import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

COLLEGE_DOMAINS_TABLE = os.environ.get("COLLEGE_DOMAINS_TABLE", "CollegeDomains")
REGION = os.environ.get("AWS_REGION", "ap-south-1")

_dynamodb = boto3.resource("dynamodb", region_name=REGION)
_table = _dynamodb.Table(COLLEGE_DOMAINS_TABLE)


def _extract_domain(email: str) -> str | None:
    """
    Normalizes and extracts the domain from an email address.
    Returns None if the email is missing, empty, or malformed (no '@').
    """
    if not email or not isinstance(email, str):
        return None

    email = email.strip().lower()

    if "@" not in email:
        return None

    domain = email.split("@")[-1]

    if not domain:
        return None

    return domain


def _is_approved_domain(domain: str) -> bool:
    """
    Looks up the domain in CollegeDomains via GetItem.
    Returns True if found, False if not found.
    Raises on unexpected DynamoDB errors (caller decides how to fail safe).
    """
    try:
        response = _table.get_item(Key={"domain": domain})
    except ClientError as e:
        # Log the error code/type, never log full request/response payloads
        # or anything that could contain PII.
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB GetItem failed for CollegeDomains lookup: %s", error_code)
        raise

    return "Item" in response


def lambda_handler(event, context):
    """
    Cognito Pre Sign-up trigger entrypoint.

    event["request"]["userAttributes"]["email"] -- the signup email.
    event["response"]["autoConfirmUser"] / ["autoVerifyEmail"] -- what we set.

    Always returns the event, per Cognito Lambda trigger contract.
    """
    email = event.get("request", {}).get("userAttributes", {}).get("email")
    domain = _extract_domain(email)

    if domain is None:
        # Missing or malformed email -- do not block signup, do not guess.
        # Just leave the response untouched and let normal Cognito flow proceed.
        logger.info("Pre sign-up: no usable email domain found, skipping auto-confirm check")
        return event

    try:
        approved = _is_approved_domain(domain)
    except ClientError:
        # Fail safe: if the lookup itself breaks, don't block signup.
        # Treat as "not an approved domain" and let normal OTP flow proceed.
        # (This mirrors what post_confirmation.py will independently decide,
        # since it re-checks the domain itself rather than trusting this
        # trigger's outcome.)
        logger.warning("Pre sign-up: CollegeDomains lookup failed, defaulting to non-approved")
        return event

    if approved:
        logger.info("Pre sign-up: domain matched CollegeDomains, auto-confirming user")
        event["response"]["autoConfirmUser"] = True
        event["response"]["autoVerifyEmail"] = True
    else:
        logger.info("Pre sign-up: domain not in CollegeDomains, normal confirmation flow applies")
        # No changes needed -- Cognito's default OTP flow proceeds untouched.

    return event
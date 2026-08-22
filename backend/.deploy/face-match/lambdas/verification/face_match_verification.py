"""
S3-triggered Lambda: verifies identity via Rekognition face match AND
PaddleOCR + Groq name match on the uploaded ID card.

Handler: face_match_verification.lambda_handler
"""

import os
import re
import logging
import datetime

import boto3
from botocore.exceptions import ClientError

from lambdas.verification.name_verification import verify_id_name

logger = logging.getLogger()
logger.setLevel(logging.INFO)

VERIFICATION_BUCKET = os.environ.get("VERIFICATION_BUCKET")
USERS_TABLE = os.environ.get("USERS_TABLE", "Users")
USER_POOL_ID = os.environ.get("USER_POOL_ID")
SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "85"))
NAME_MATCH_REQUIRED = os.environ.get("NAME_MATCH_REQUIRED", "true").lower() in (
    "1",
    "true",
    "yes",
)
REGION = os.environ.get("AWS_REGION", "ap-south-1")

_s3 = boto3.client("s3", region_name=REGION)
_rekognition = boto3.client("rekognition", region_name=REGION)
_dynamodb = boto3.resource("dynamodb", region_name=REGION)
_users_table = _dynamodb.Table(USERS_TABLE)
_cognito = boto3.client("cognito-idp", region_name=REGION)

KEY_PATTERN = re.compile(r"^verification/([^/]+)/(selfie|id_card)\.jpg$")


def _extract_user_id(key: str):
    match = KEY_PATTERN.match(key)
    if not match:
        return None
    return match.group(1)


def _object_exists(bucket: str, key: str) -> bool:
    try:
        _s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def _get_user_record(user_id: str) -> dict:
    try:
        response = _users_table.get_item(Key={"userId": user_id})
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("DynamoDB GetItem failed for userId=%s: %s", user_id, error_code)
        raise
    return response.get("Item") or {}


def _run_face_comparison(bucket: str, user_id: str):
    selfie_key = f"verification/{user_id}/selfie.jpg"
    id_card_key = f"verification/{user_id}/id_card.jpg"

    try:
        response = _rekognition.compare_faces(
            SourceImage={"S3Object": {"Bucket": bucket, "Name": selfie_key}},
            TargetImage={"S3Object": {"Bucket": bucket, "Name": id_card_key}},
            SimilarityThreshold=1,
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "InvalidParameterException":
            logger.warning(
                "Rekognition could not process images for userId=%s: %s", user_id, error_code
            )
            return "rejected", None, "face_not_detected"
        logger.error("Rekognition CompareFaces failed for userId=%s: %s", user_id, error_code)
        return "rejected", None, f"rekognition_error:{error_code}"

    face_matches = response.get("FaceMatches", [])
    if not face_matches:
        return "rejected", 0.0, "no_match_found"

    best_match = max(face_matches, key=lambda m: m["Similarity"])
    similarity = best_match["Similarity"]

    if similarity >= SIMILARITY_THRESHOLD:
        return "verified", similarity, "match_above_threshold"
    return "rejected", similarity, "match_below_threshold"


def _combine_results(face_status, face_similarity, face_reason, name_result: dict):
    """Face match must pass; name match required when NAME_MATCH_REQUIRED."""
    if face_status != "verified":
        return "rejected", face_similarity, face_reason

    if not NAME_MATCH_REQUIRED:
        return "verified", face_similarity, "face_match_only"

    if name_result.get("match"):
        return "verified", face_similarity, "face_and_name_match"

    name_reason = name_result.get("reason") or "name_mismatch"
    return "rejected", face_similarity, f"name_{name_reason}"


def _update_user_record(
    user_id: str,
    status: str,
    similarity,
    reason: str,
    name_result: dict | None = None,
):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    update_expr = (
        "SET verificationStatus = :status, faceMatchReason = :reason, updatedAt = :now"
    )
    expr_values = {":status": status, ":reason": reason, ":now": now}

    if similarity is not None:
        update_expr += ", faceMatchScore = :score"
        expr_values[":score"] = str(round(similarity, 2))

    if name_result:
        update_expr += (
            ", idNameMatch = :idNameMatch, idNameMatchReason = :idNameReason"
            ", idNameMatchConfidence = :idNameConf, idNameOnCard = :idNameOnCard"
            ", idNameMatchMethod = :idNameMethod"
        )
        expr_values[":idNameMatch"] = bool(name_result.get("match"))
        expr_values[":idNameReason"] = str(name_result.get("reason") or "")
        expr_values[":idNameConf"] = str(name_result.get("confidence", 0))
        expr_values[":idNameOnCard"] = str(name_result.get("nameOnCard") or "")
        expr_values[":idNameMethod"] = str(name_result.get("method") or "")

    _users_table.update_item(
        Key={"userId": user_id},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
    )


def _sync_cognito_verification_status(user_id: str, status: str):
    if status not in ("verified", "rejected"):
        return

    user_item = _get_user_record(user_id)
    if not user_item:
        logger.error("User record not found for userId=%s during Cognito sync", user_id)
        return

    email = user_item.get("email")
    if not email or not isinstance(email, str):
        logger.warning("Users record for userId=%s has no email; skipping Cognito sync", user_id)
        return

    _cognito.admin_update_user_attributes(
        UserPoolId=USER_POOL_ID,
        Username=email,
        UserAttributes=[{"Name": "custom:verification_status", "Value": status}],
    )


def lambda_handler(event, context):
    if VERIFICATION_BUCKET is None or USER_POOL_ID is None:
        logger.error("VERIFICATION_BUCKET or USER_POOL_ID environment variable is not set")
        return {"status": "skipped", "reason": "server_misconfiguration"}

    results = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        key = key.replace("+", " ")

        user_id = _extract_user_id(key)
        if user_id is None:
            logger.info("Ignoring S3 event for non-matching key: %s", key)
            continue

        selfie_key = f"verification/{user_id}/selfie.jpg"
        id_card_key = f"verification/{user_id}/id_card.jpg"

        if not (_object_exists(bucket, selfie_key) and _object_exists(bucket, id_card_key)):
            logger.info("Waiting on second upload for userId=%s -- not processing yet", user_id)
            continue

        user_item = _get_user_record(user_id)
        registered_name = str(user_item.get("name") or "").strip()

        face_status, similarity, face_reason = _run_face_comparison(bucket, user_id)
        name_result = verify_id_name(
            _s3, bucket, id_card_key, registered_name, rekognition_client=_rekognition
        )
        status, similarity, reason = _combine_results(
            face_status, similarity, face_reason, name_result
        )

        try:
            _update_user_record(user_id, status, similarity, reason, name_result)
            _sync_cognito_verification_status(user_id, status)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error("Failed to persist result for userId=%s: %s", user_id, error_code)
            raise

        logger.info(
            "Verification complete userId=%s status=%s similarity=%s reason=%s "
            "nameMatch=%s nameMethod=%s",
            user_id,
            status,
            similarity,
            reason,
            name_result.get("match"),
            name_result.get("method"),
        )
        results.append(
            {
                "userId": user_id,
                "status": status,
                "similarity": similarity,
                "reason": reason,
                "nameMatch": name_result.get("match"),
                "nameOnCard": name_result.get("nameOnCard"),
                "nameMethod": name_result.get("method"),
            }
        )

    return {"status": "processed", "results": results}

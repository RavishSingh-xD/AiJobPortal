"""
S3-triggered Lambda: automatically verifies a student's identity by
comparing their selfie against the photo on their uploaded ID card, using
Amazon Rekognition's CompareFaces API. Fully automatic -- no human review.

Handler: face_match_verification.lambda_handler
S3 trigger: ObjectCreated events on the verification bucket, prefix
"verification/" (fires once per file -- selfie.jpg and id_card.jpg upload
in parallel from the frontend, so this runs twice per user, but only acts
once both files are present).

Decision logic:
    - Both files not yet present -> no-op, wait for the second upload's
      trigger to fire.
    - Rekognition finds a face match >= SIMILARITY_THRESHOLD -> verified.
    - Rekognition runs successfully but finds no match, or similarity is
      below threshold -> rejected (genuine mismatch).
    - Rekognition CANNOT PROCESS the images at all (no face detected in
      either image, image too small/corrupt, etc.) -> manual_review, NOT
      rejected. This distinction matters: a processing failure (bad photo
      quality) is not evidence the person is lying, and auto-rejecting on
      technical failure would incorrectly lock out legitimate students
      over a blurry photo. Only a completed comparison with low similarity
      counts as a genuine mismatch.

Required IAM permissions (faceMatchVerificationRole):
    rekognition:CompareFaces
    s3:GetObject on the verification bucket (Rekognition reads the images
      via the calling Lambda's own S3 permissions, not its own)
    dynamodb:GetItem, dynamodb:UpdateItem on Users
    cognito-idp:AdminUpdateUserAttributes on the User Pool ARN

Environment variables:
    VERIFICATION_BUCKET     (required, no default)
    USERS_TABLE             (default: "Users")
    USER_POOL_ID            (required, no default)
    SIMILARITY_THRESHOLD    (default: "85" -- percent, 0-100)
    AWS_REGION              (default fallback: "ap-south-1")
"""

import os
import re
import logging
import datetime

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

VERIFICATION_BUCKET = os.environ.get("VERIFICATION_BUCKET")
USERS_TABLE = os.environ.get("USERS_TABLE", "Users")
USER_POOL_ID = os.environ.get("USER_POOL_ID")
SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "85"))
REGION = os.environ.get("AWS_REGION", "ap-south-1")

_s3 = boto3.client("s3", region_name=REGION)
_rekognition = boto3.client("rekognition", region_name=REGION)
_dynamodb = boto3.resource("dynamodb", region_name=REGION)
_users_table = _dynamodb.Table(USERS_TABLE)
_cognito = boto3.client("cognito-idp", region_name=REGION)

KEY_PATTERN = re.compile(r"^verification/([^/]+)/(selfie|id_card)\.jpg$")


def _extract_user_id(key: str):
    """Returns the userId from a key like verification/<userId>/selfie.jpg, or None if malformed."""
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


def _run_face_comparison(bucket: str, user_id: str):
    """
    Runs CompareFaces between the two uploaded images.
    Returns a tuple: (status, similarity_or_none, reason)
      status is one of "verified", "rejected", "manual_review"
    """
    selfie_key = f"verification/{user_id}/selfie.jpg"
    id_card_key = f"verification/{user_id}/id_card.jpg"

    try:
        response = _rekognition.compare_faces(
            SourceImage={"S3Object": {"Bucket": bucket, "Name": selfie_key}},
            TargetImage={"S3Object": {"Bucket": bucket, "Name": id_card_key}},
            SimilarityThreshold=1,  # low threshold here -- we apply our own cutoff below
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "InvalidParameterException":
            # Most commonly: no face detected in one of the images.
            # This is a processing failure, not evidence of a mismatch.
            logger.warning("Rekognition could not process images for userId=%s: %s", user_id, error_code)
            return "manual_review", None, "face_not_detected"
        logger.error("Rekognition CompareFaces failed for userId=%s: %s", user_id, error_code)
        return "manual_review", None, f"rekognition_error:{error_code}"

    face_matches = response.get("FaceMatches", [])

    if not face_matches:
        # Rekognition processed both images fine but found no matching face
        # -- this is a genuine mismatch, not a processing failure.
        return "rejected", 0.0, "no_match_found"

    best_match = max(face_matches, key=lambda m: m["Similarity"])
    similarity = best_match["Similarity"]

    if similarity >= SIMILARITY_THRESHOLD:
        return "verified", similarity, "match_above_threshold"
    else:
        return "rejected", similarity, "match_below_threshold"


def _update_user_record(user_id: str, status: str, similarity, reason: str):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    update_expr = "SET verificationStatus = :status, faceMatchReason = :reason, updatedAt = :now"
    expr_values = {":status": status, ":reason": reason, ":now": now}

    if similarity is not None:
        update_expr += ", faceMatchScore = :score"
        expr_values[":score"] = str(round(similarity, 2))

    _users_table.update_item(
        Key={"userId": user_id},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
    )


def _sync_cognito_if_verified(user_id: str, status: str):
    if status != "verified":
        return

    get_response = _users_table.get_item(Key={"userId": user_id})
    user_item = get_response.get("Item")
    if user_item is None:
        logger.error("User record not found for userId=%s during Cognito sync", user_id)
        return

    email = user_item.get("email")
    _cognito.admin_update_user_attributes(
        UserPoolId=USER_POOL_ID,
        Username=email,
        UserAttributes=[{"Name": "custom:verification_status", "Value": "verified"}],
    )


def lambda_handler(event, context):
    if VERIFICATION_BUCKET is None or USER_POOL_ID is None:
        logger.error("VERIFICATION_BUCKET or USER_POOL_ID environment variable is not set")
        return {"status": "skipped", "reason": "server_misconfiguration"}

    results = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        # S3 event keys are URL-encoded (e.g. spaces become '+') -- decode defensively
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

        status, similarity, reason = _run_face_comparison(bucket, user_id)

        try:
            _update_user_record(user_id, status, similarity, reason)
            _sync_cognito_if_verified(user_id, status)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error("Failed to persist result for userId=%s: %s", user_id, error_code)
            raise

        logger.info(
            "Face match complete userId=%s status=%s similarity=%s reason=%s",
            user_id, status, similarity, reason
        )
        results.append({"userId": user_id, "status": status, "similarity": similarity, "reason": reason})

    return {"status": "processed", "results": results}
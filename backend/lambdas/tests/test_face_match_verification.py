"""
Local unit tests for face_match_verification.py.
No real AWS calls -- S3, Rekognition, DynamoDB, and Cognito clients are all mocked.

Run with (from the backend/ directory):
    python3 -m pytest lambdas/tests/test_face_match_verification.py -v
"""

from unittest.mock import patch
from lambdas.verification import face_match_verification as fmv


def make_s3_event(bucket, key):
    return {
        "Records": [
            {"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}
        ]
    }


@patch.object(fmv, "_cognito")
@patch.object(fmv, "_users_table")
@patch.object(fmv, "_rekognition")
@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_high_similarity_match_verifies_and_syncs_cognito(mock_s3, mock_rekognition, mock_users_table, mock_cognito):
    mock_s3.head_object.return_value = {}  # both files "exist"
    mock_rekognition.compare_faces.return_value = {
        "FaceMatches": [{"Similarity": 96.5, "Face": {}}]
    }
    mock_users_table.get_item.return_value = {"Item": {"email": "student@iitb.ac.in"}}

    event = make_s3_event("test-bucket", "verification/user-1/selfie.jpg")
    result = fmv.lambda_handler(event, None)

    assert result["results"][0]["status"] == "verified"
    assert result["results"][0]["similarity"] == 96.5

    update_kwargs = mock_users_table.update_item.call_args.kwargs
    assert update_kwargs["ExpressionAttributeValues"][":status"] == "verified"

    cognito_kwargs = mock_cognito.admin_update_user_attributes.call_args.kwargs
    assert cognito_kwargs["Username"] == "student@iitb.ac.in"


@patch.object(fmv, "_cognito")
@patch.object(fmv, "_users_table")
@patch.object(fmv, "_rekognition")
@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_low_similarity_rejects_without_cognito_sync(mock_s3, mock_rekognition, mock_users_table, mock_cognito):
    mock_s3.head_object.return_value = {}
    mock_rekognition.compare_faces.return_value = {
        "FaceMatches": [{"Similarity": 42.0, "Face": {}}]
    }

    event = make_s3_event("test-bucket", "verification/user-2/id_card.jpg")
    result = fmv.lambda_handler(event, None)

    assert result["results"][0]["status"] == "rejected"
    mock_cognito.admin_update_user_attributes.assert_not_called()


@patch.object(fmv, "_cognito")
@patch.object(fmv, "_users_table")
@patch.object(fmv, "_rekognition")
@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_no_face_matches_found_rejects(mock_s3, mock_rekognition, mock_users_table, mock_cognito):
    mock_s3.head_object.return_value = {}
    mock_rekognition.compare_faces.return_value = {"FaceMatches": []}

    event = make_s3_event("test-bucket", "verification/user-3/selfie.jpg")
    result = fmv.lambda_handler(event, None)

    assert result["results"][0]["status"] == "rejected"
    assert result["results"][0]["reason"] == "no_match_found"


@patch.object(fmv, "_cognito")
@patch.object(fmv, "_users_table")
@patch.object(fmv, "_rekognition")
@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_no_face_detected_goes_to_manual_review_not_rejected(mock_s3, mock_rekognition, mock_users_table, mock_cognito):
    from botocore.exceptions import ClientError

    mock_s3.head_object.return_value = {}
    mock_rekognition.compare_faces.side_effect = ClientError(
        {"Error": {"Code": "InvalidParameterException", "Message": "no face detected"}},
        "CompareFaces"
    )

    event = make_s3_event("test-bucket", "verification/user-4/selfie.jpg")
    result = fmv.lambda_handler(event, None)

    # Critical: must NOT be "rejected" -- a processing failure isn't evidence of a mismatch
    assert result["results"][0]["status"] == "manual_review"
    assert result["results"][0]["reason"] == "face_not_detected"
    mock_cognito.admin_update_user_attributes.assert_not_called()


@patch.object(fmv, "_rekognition")
@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_only_one_file_uploaded_does_not_process_yet(mock_s3, mock_rekognition):
    from botocore.exceptions import ClientError

    def head_object_side_effect(Bucket, Key):
        if "selfie" in Key:
            return {}
        raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")

    mock_s3.head_object.side_effect = head_object_side_effect

    event = make_s3_event("test-bucket", "verification/user-5/selfie.jpg")
    result = fmv.lambda_handler(event, None)

    assert result["results"] == []
    mock_rekognition.compare_faces.assert_not_called()


@patch.object(fmv, "_cognito")
@patch.object(fmv, "_users_table")
@patch.object(fmv, "_rekognition")
@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_verified_but_no_users_record_does_not_crash(mock_s3, mock_rekognition, mock_users_table, mock_cognito):
    # Simulates a userId with no corresponding Users item (e.g. test data,
    # or a real edge case where the record is somehow missing) -- should
    # log and skip the Cognito sync, not raise.
    mock_s3.head_object.return_value = {}
    mock_rekognition.compare_faces.return_value = {
        "FaceMatches": [{"Similarity": 99.0, "Face": {}}]
    }
    mock_users_table.get_item.return_value = {}  # no "Item" key

    event = make_s3_event("test-bucket", "verification/nonexistent-user/selfie.jpg")
    result = fmv.lambda_handler(event, None)  # should not raise

    assert result["results"][0]["status"] == "verified"
    mock_cognito.admin_update_user_attributes.assert_not_called()


@patch.object(fmv, "_cognito")
@patch.object(fmv, "_users_table")
@patch.object(fmv, "_rekognition")
@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_verified_but_missing_email_does_not_crash(mock_s3, mock_rekognition, mock_users_table, mock_cognito):
    mock_s3.head_object.return_value = {}
    mock_rekognition.compare_faces.return_value = {
        "FaceMatches": [{"Similarity": 99.0, "Face": {}}]
    }
    mock_users_table.get_item.return_value = {"Item": {"userId": "user-6"}}  # no email field

    event = make_s3_event("test-bucket", "verification/user-6/selfie.jpg")
    result = fmv.lambda_handler(event, None)  # should not raise

    assert result["results"][0]["status"] == "verified"
    mock_cognito.admin_update_user_attributes.assert_not_called()


def test_missing_env_vars_skips_processing():
    with patch.object(fmv, "VERIFICATION_BUCKET", None):
        event = make_s3_event("test-bucket", "verification/user-1/selfie.jpg")
        result = fmv.lambda_handler(event, None)
        assert result["status"] == "skipped"


@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_malformed_key_is_ignored(mock_s3):
    event = make_s3_event("test-bucket", "some/other/path.jpg")
    result = fmv.lambda_handler(event, None)

    assert result["results"] == []
    mock_s3.head_object.assert_not_called()
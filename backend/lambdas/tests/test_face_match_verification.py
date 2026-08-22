"""
Local unit tests for face_match_verification.py.
No real AWS calls -- S3, Rekognition, DynamoDB, and Cognito clients are all mocked.

Run with (from the backend/ directory):
    python3 -m pytest lambdas/tests/test_face_match_verification.py -v
"""

from unittest.mock import patch
from lambdas.verification import face_match_verification as fmv

NAME_MATCH_OK = {
    "match": True,
    "reason": "name_match",
    "nameOnCard": "Student Name",
    "confidence": 95.0,
    "method": "groq",
}


def make_s3_event(bucket, key):
    return {
        "Records": [
            {"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}
        ]
    }


@patch.object(fmv, "verify_id_name", return_value=NAME_MATCH_OK)
@patch.object(fmv, "_cognito")
@patch.object(fmv, "_users_table")
@patch.object(fmv, "_rekognition")
@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_high_similarity_match_verifies_and_syncs_cognito(
    mock_s3, mock_rekognition, mock_users_table, mock_cognito, mock_name
):
    mock_s3.head_object.return_value = {}
    mock_rekognition.compare_faces.return_value = {
        "FaceMatches": [{"Similarity": 96.5, "Face": {}}]
    }
    mock_users_table.get_item.return_value = {
        "Item": {"email": "student@iitb.ac.in", "name": "Student Name"}
    }

    event = make_s3_event("test-bucket", "verification/user-1/selfie.jpg")
    result = fmv.lambda_handler(event, None)

    assert result["results"][0]["status"] == "verified"
    assert result["results"][0]["similarity"] == 96.5

    update_kwargs = mock_users_table.update_item.call_args.kwargs
    assert update_kwargs["ExpressionAttributeValues"][":status"] == "verified"

    cognito_kwargs = mock_cognito.admin_update_user_attributes.call_args.kwargs
    assert cognito_kwargs["Username"] == "student@iitb.ac.in"
    assert cognito_kwargs["UserAttributes"] == [
        {"Name": "custom:verification_status", "Value": "verified"}
    ]


@patch.object(fmv, "verify_id_name", return_value=NAME_MATCH_OK)
@patch.object(fmv, "_cognito")
@patch.object(fmv, "_users_table")
@patch.object(fmv, "_rekognition")
@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_low_similarity_rejects_and_syncs_cognito(
    mock_s3, mock_rekognition, mock_users_table, mock_cognito, mock_name
):
    mock_s3.head_object.return_value = {}
    mock_rekognition.compare_faces.return_value = {
        "FaceMatches": [{"Similarity": 42.0, "Face": {}}]
    }
    mock_users_table.get_item.return_value = {
        "Item": {"email": "student@iitb.ac.in", "name": "Student Name"}
    }

    event = make_s3_event("test-bucket", "verification/user-2/id_card.jpg")
    result = fmv.lambda_handler(event, None)

    assert result["results"][0]["status"] == "rejected"
    assert result["results"][0]["reason"] == "match_below_threshold"

    cognito_kwargs = mock_cognito.admin_update_user_attributes.call_args.kwargs
    assert cognito_kwargs["UserAttributes"] == [
        {"Name": "custom:verification_status", "Value": "rejected"}
    ]


@patch.object(fmv, "verify_id_name", return_value=NAME_MATCH_OK)
@patch.object(fmv, "_cognito")
@patch.object(fmv, "_users_table")
@patch.object(fmv, "_rekognition")
@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_no_face_matches_found_rejects(
    mock_s3, mock_rekognition, mock_users_table, mock_cognito, mock_name
):
    mock_s3.head_object.return_value = {}
    mock_rekognition.compare_faces.return_value = {"FaceMatches": []}
    mock_users_table.get_item.return_value = {
        "Item": {"email": "student@iitb.ac.in", "name": "Student Name"}
    }

    event = make_s3_event("test-bucket", "verification/user-3/selfie.jpg")
    result = fmv.lambda_handler(event, None)

    assert result["results"][0]["status"] == "rejected"
    assert result["results"][0]["reason"] == "no_match_found"


@patch.object(fmv, "verify_id_name", return_value=NAME_MATCH_OK)
@patch.object(fmv, "_cognito")
@patch.object(fmv, "_users_table")
@patch.object(fmv, "_rekognition")
@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_no_face_detected_rejects_with_face_not_detected_reason(
    mock_s3, mock_rekognition, mock_users_table, mock_cognito, mock_name
):
    from botocore.exceptions import ClientError

    mock_s3.head_object.return_value = {}
    mock_rekognition.compare_faces.side_effect = ClientError(
        {"Error": {"Code": "InvalidParameterException", "Message": "no face detected"}},
        "CompareFaces"
    )
    mock_users_table.get_item.return_value = {
        "Item": {"email": "student@iitb.ac.in", "name": "Student Name"}
    }

    event = make_s3_event("test-bucket", "verification/user-4/selfie.jpg")
    result = fmv.lambda_handler(event, None)

    assert result["results"][0]["status"] == "rejected"
    assert result["results"][0]["reason"] == "face_not_detected"

    cognito_kwargs = mock_cognito.admin_update_user_attributes.call_args.kwargs
    assert cognito_kwargs["UserAttributes"] == [
        {"Name": "custom:verification_status", "Value": "rejected"}
    ]


@patch.object(fmv, "verify_id_name", return_value=NAME_MATCH_OK)
@patch.object(fmv, "_cognito")
@patch.object(fmv, "_users_table")
@patch.object(fmv, "_rekognition")
@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_other_rekognition_error_rejects_with_rekognition_error_reason(
    mock_s3, mock_rekognition, mock_users_table, mock_cognito, mock_name
):
    from botocore.exceptions import ClientError

    mock_s3.head_object.return_value = {}
    mock_rekognition.compare_faces.side_effect = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "rate exceeded"}},
        "CompareFaces"
    )
    mock_users_table.get_item.return_value = {
        "Item": {"email": "student@iitb.ac.in", "name": "Student Name"}
    }

    event = make_s3_event("test-bucket", "verification/user-4b/selfie.jpg")
    result = fmv.lambda_handler(event, None)

    assert result["results"][0]["status"] == "rejected"
    assert result["results"][0]["reason"].startswith("rekognition_error:")


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
def test_verified_but_no_users_record_rejects_on_name_check(
    mock_s3, mock_rekognition, mock_users_table, mock_cognito
):
    mock_s3.head_object.return_value = {}
    mock_rekognition.compare_faces.return_value = {
        "FaceMatches": [{"Similarity": 99.0, "Face": {}}]
    }
    mock_users_table.get_item.return_value = {}

    event = make_s3_event("test-bucket", "verification/nonexistent-user/selfie.jpg")
    result = fmv.lambda_handler(event, None)

    assert result["results"][0]["status"] == "rejected"
    assert result["results"][0]["reason"].startswith("name_")
    mock_cognito.admin_update_user_attributes.assert_not_called()


@patch.object(fmv, "_cognito")
@patch.object(fmv, "_users_table")
@patch.object(fmv, "_rekognition")
@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_verified_but_missing_name_rejects(mock_s3, mock_rekognition, mock_users_table, mock_cognito):
    mock_s3.head_object.return_value = {}
    mock_rekognition.compare_faces.return_value = {
        "FaceMatches": [{"Similarity": 99.0, "Face": {}}]
    }
    mock_users_table.get_item.return_value = {"Item": {"userId": "user-6", "email": "a@b.com"}}

    event = make_s3_event("test-bucket", "verification/user-6/selfie.jpg")
    result = fmv.lambda_handler(event, None)

    assert result["results"][0]["status"] == "rejected"
    assert result["results"][0]["reason"].startswith("name_")
    cognito_kwargs = mock_cognito.admin_update_user_attributes.call_args.kwargs
    assert cognito_kwargs["Username"] == "a@b.com"
    assert cognito_kwargs["UserAttributes"] == [
        {"Name": "custom:verification_status", "Value": "rejected"}
    ]


@patch.object(fmv, "verify_id_name", return_value=NAME_MATCH_OK)
@patch.object(fmv, "_cognito")
@patch.object(fmv, "_users_table")
@patch.object(fmv, "_rekognition")
@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_rejected_but_missing_email_does_not_call_cognito(
    mock_s3, mock_rekognition, mock_users_table, mock_cognito, mock_name
):
    mock_s3.head_object.return_value = {}
    mock_rekognition.compare_faces.return_value = {"FaceMatches": []}
    mock_users_table.get_item.return_value = {"Item": {"userId": "user-7", "name": "Student Name"}}

    event = make_s3_event("test-bucket", "verification/user-7/selfie.jpg")
    result = fmv.lambda_handler(event, None)

    assert result["results"][0]["status"] == "rejected"
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


@patch.object(
    fmv,
    "verify_id_name",
    return_value={
        "match": False,
        "reason": "name_mismatch",
        "nameOnCard": "Wrong Person",
        "confidence": 88.0,
        "method": "groq",
    },
)
@patch.object(fmv, "_cognito")
@patch.object(fmv, "_users_table")
@patch.object(fmv, "_rekognition")
@patch.object(fmv, "_s3")
@patch.object(fmv, "VERIFICATION_BUCKET", "test-bucket")
@patch.object(fmv, "USER_POOL_ID", "ap-south-1_TESTPOOL")
def test_name_mismatch_rejects_despite_high_face_score(
    mock_s3, mock_rekognition, mock_users_table, mock_cognito, mock_name
):
    mock_s3.head_object.return_value = {}
    mock_rekognition.compare_faces.return_value = {
        "FaceMatches": [{"Similarity": 98.0, "Face": {}}]
    }
    mock_users_table.get_item.return_value = {
        "Item": {"email": "student@iitb.ac.in", "name": "Jane Doe"}
    }

    event = make_s3_event("test-bucket", "verification/user-8/selfie.jpg")
    result = fmv.lambda_handler(event, None)

    assert result["results"][0]["status"] == "rejected"
    assert result["results"][0]["reason"] == "name_name_mismatch"
    cognito_kwargs = mock_cognito.admin_update_user_attributes.call_args.kwargs
    assert cognito_kwargs["UserAttributes"] == [
        {"Name": "custom:verification_status", "Value": "rejected"}
    ]

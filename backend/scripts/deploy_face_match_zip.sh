#!/usr/bin/env bash
# Zip deploy for faceMatchVerification (uses Rekognition DetectText when PaddleOCR
# is not installed). For full PaddleOCR, use deploy_face_match_verification.sh (container).

set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
ACCOUNT_ID="${AWS_ACCOUNT_ID:-470361396576}"
FUNCTION_NAME="${LAMBDA_FUNCTION:-faceMatchVerification}"
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="${ROOT_DIR}/backend/.deploy/face-match"
ZIP="${STAGE}/faceMatchVerification.zip"

rm -rf "$STAGE"
mkdir -p "$STAGE/lambdas/verification" "$STAGE/lambdas/common"

cp "${ROOT_DIR}/backend/lambdas/verification/face_match_verification.py" "$STAGE/lambdas/verification/"
cp "${ROOT_DIR}/backend/lambdas/verification/name_verification.py" "$STAGE/lambdas/verification/"
cp "${ROOT_DIR}/backend/lambdas/verification/paddle_ocr.py" "$STAGE/lambdas/verification/"
touch "$STAGE/lambdas/__init__.py" "$STAGE/lambdas/verification/__init__.py"

cd "$STAGE"
zip -rq "$ZIP" lambdas

aws lambda update-function-code \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME" \
  --zip-file "fileb://${ZIP}"

aws lambda wait function-updated --region "$REGION" --function-name "$FUNCTION_NAME"

aws lambda update-function-configuration \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME" \
  --timeout 120 \
  --memory-size 512 \
  --handler lambdas.verification.face_match_verification.lambda_handler \
  --environment "Variables={VERIFICATION_BUCKET=aijobportal-verification-${ACCOUNT_ID},USERS_TABLE=Users,USER_POOL_ID=ap-south-1_s0f7Kwug8,SIMILARITY_THRESHOLD=90,NAME_MATCH_REQUIRED=true,NAME_VERIFICATION_ENABLED=true,GROQ_API_KEY_PARAM=/aijobportal/groq-api-key,GROQ_MODEL=openai/gpt-oss-120b,OCR_MIN_LINE_CONFIDENCE=0.80}"

echo "Deployed zip to $FUNCTION_NAME (Rekognition OCR fallback; PaddleOCR requires container deploy)."

#!/usr/bin/env bash
# Build and deploy faceMatchVerification as a container Lambda (PaddleOCR).
#
# Usage (from repo root):
#   ./backend/scripts/deploy_face_match_verification.sh
#
# Prerequisites: docker, aws cli, ECR repo, Lambda function faceMatchVerification

set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
ACCOUNT_ID="${AWS_ACCOUNT_ID:-470361396576}"
REPO_NAME="${ECR_REPO:-aijobportal-face-match}"
FUNCTION_NAME="${LAMBDA_FUNCTION:-faceMatchVerification}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
IMAGE_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO_NAME}:${IMAGE_TAG}"

echo "==> Logging in to ECR"
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "==> Ensuring ECR repository exists"
aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$REGION" >/dev/null 2>&1 || \
  aws ecr create-repository --repository-name "$REPO_NAME" --region "$REGION"

echo "==> Building container image"
docker build \
  -f "${BACKEND_DIR}/Dockerfile.face-match" \
  -t "${REPO_NAME}:${IMAGE_TAG}" \
  "${BACKEND_DIR}"

docker tag "${REPO_NAME}:${IMAGE_TAG}" "$IMAGE_URI"

echo "==> Pushing $IMAGE_URI"
docker push "$IMAGE_URI"

echo "==> Updating Lambda $FUNCTION_NAME"
aws lambda update-function-code \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME" \
  --image-uri "$IMAGE_URI"

aws lambda wait function-updated --region "$REGION" --function-name "$FUNCTION_NAME"

aws lambda update-function-configuration \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME" \
  --timeout 180 \
  --memory-size 3008 \
  --environment "Variables={
VERIFICATION_BUCKET=aijobportal-verification-${ACCOUNT_ID},
USERS_TABLE=Users,
USER_POOL_ID=ap-south-1_s0f7Kwug8,
SIMILARITY_THRESHOLD=85,
NAME_MATCH_REQUIRED=true,
NAME_VERIFICATION_ENABLED=true,
GROQ_API_KEY_PARAM=/aijobportal/groq-api-key,
GROQ_MODEL=openai/gpt-oss-120b,
AWS_REGION=${REGION}
}"

echo "==> Deploy complete: $IMAGE_URI"

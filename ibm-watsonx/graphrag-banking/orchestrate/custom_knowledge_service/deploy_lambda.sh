#!/usr/bin/env bash
# Create or update the Lambda function and its Function URL.
# Run from the graphrag-banking folder, after build_lambda.sh:
#   ./orchestrate/custom_knowledge_service/deploy_lambda.sh
#
# AWS credentials come from the default profile, or from AWS_PROFILE. The
# shared key is KNOWLEDGE_SERVICE_API_KEY in .env. When .env has none, the
# script generates one and appends it to .env.
#
# Orchestrate cannot sign requests with AWS credentials, so the Function URL
# uses auth type NONE and the service checks the shared key itself.
set -euo pipefail

if [ -z "${KNOWLEDGE_SERVICE_API_KEY:-}" ]; then
  KNOWLEDGE_SERVICE_API_KEY=$(sed -n 's/^KNOWLEDGE_SERVICE_API_KEY=//p' .env | tr -d "'\"")
fi
if [ -z "$KNOWLEDGE_SERVICE_API_KEY" ]; then
  KNOWLEDGE_SERVICE_API_KEY=$(openssl rand -hex 16)
  printf '\nKNOWLEDGE_SERVICE_API_KEY=%s\n' "$KNOWLEDGE_SERVICE_API_KEY" >> .env
  echo "Added KNOWLEDGE_SERVICE_API_KEY to .env" >&2
fi
export KNOWLEDGE_SERVICE_API_KEY
FUNCTION=${FUNCTION_NAME:-neo4j-knowledge-service}
ROLE=${FUNCTION}-role
ZIP=orchestrate/build/knowledge_service.zip
[ -f "$ZIP" ] || { echo "Run build_lambda.sh first" >&2; exit 1; }

# Function settings from .env plus the shared key, as JSON. Nothing is printed.
ENV_JSON=$(python3 - <<'PY'
import json
import os
from pathlib import Path

wanted = {
    "NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE",
    "OPENAI_API_KEY", "OPENAI_EMBEDDING_MODEL", "DEMO_AS_OF",
    "DEMO_CUSTOMER_ID", "DEMO_BANKER_ID",
}
values = {}
for line in Path(".env").read_text().splitlines():
    key, sep, value = line.partition("=")
    if sep and key.strip() in wanted:
        values[key.strip()] = value.strip().strip("'\"")
values["KNOWLEDGE_SERVICE_API_KEY"] = os.environ["KNOWLEDGE_SERVICE_API_KEY"]
print(json.dumps({"Variables": values}))
PY
)

if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
    >/dev/null
  aws iam attach-role-policy --role-name "$ROLE" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  sleep 10  # a new role takes a few seconds to become usable
fi
ROLE_ARN=$(aws iam get-role --role-name "$ROLE" --query Role.Arn --output text)

if aws lambda get-function --function-name "$FUNCTION" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "$FUNCTION" \
    --zip-file "fileb://$ZIP" >/dev/null
  aws lambda wait function-updated --function-name "$FUNCTION"
  aws lambda update-function-configuration --function-name "$FUNCTION" \
    --environment "$ENV_JSON" >/dev/null
else
  aws lambda create-function --function-name "$FUNCTION" \
    --runtime python3.13 --architectures arm64 \
    --handler lambda_handler.handler --role "$ROLE_ARN" \
    --timeout 30 --memory-size 512 \
    --zip-file "fileb://$ZIP" --environment "$ENV_JSON" >/dev/null
  aws lambda wait function-active --function-name "$FUNCTION"
  aws lambda create-function-url-config --function-name "$FUNCTION" \
    --auth-type NONE >/dev/null
  aws lambda add-permission --function-name "$FUNCTION" \
    --statement-id FunctionURLAllowPublicAccess \
    --action lambda:InvokeFunctionUrl --principal '*' \
    --function-url-auth-type NONE >/dev/null
  aws lambda add-permission --function-name "$FUNCTION" \
    --statement-id FunctionURLInvokeAllowPublicAccess \
    --action lambda:InvokeFunction --principal '*' \
    --invoked-via-function-url >/dev/null
fi

aws lambda get-function-url-config --function-name "$FUNCTION" \
  --query FunctionUrl --output text

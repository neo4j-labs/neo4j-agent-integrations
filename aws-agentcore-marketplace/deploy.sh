#!/bin/bash

# Deploy Neo4j MCP (AWS Marketplace) to Amazon Bedrock AgentCore
#
# This script creates the required IAM role and AgentCore runtime
# for the Neo4j MCP server from the AWS Marketplace.
#
# Usage: ./deploy.sh
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - Amazon Bedrock AgentCore access enabled in your account

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────
# Edit these values to match your Neo4j environment.

REGION="us-east-1"
RUNTIME_NAME="neo4j_mcp"
CONTAINER_URI="709825985650.dkr.ecr.us-east-1.amazonaws.com/neo4j/mcp:v0.1.7"

NEO4J_URI="neo4j+s://demo.neo4jlabs.com:7687"
NEO4J_DATABASE="companies"
NEO4J_READ_ONLY="true"

# ── Derived values ─────────────────────────────────────────────────

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
TIMESTAMP=$(date +%Y%m%d%H%M%S)
ROLE_NAME="Neo4jMCPRole-${TIMESTAMP}"

echo "Account:  ${ACCOUNT_ID}"
echo "Region:   ${REGION}"
echo "Runtime:  ${RUNTIME_NAME}"
echo "Neo4j:    ${NEO4J_URI} / ${NEO4J_DATABASE}"
echo ""

# ── 1. Create IAM Role ────────────────────────────────────────────

echo "Creating IAM role ${ROLE_NAME}..."

aws iam create-role \
  --role-name "${ROLE_NAME}" \
  --assume-role-policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
      \"Sid\": \"AssumeRolePolicy\",
      \"Effect\": \"Allow\",
      \"Principal\": {\"Service\": \"bedrock-agentcore.amazonaws.com\"},
      \"Action\": \"sts:AssumeRole\"
    }]
  }"

# ── 2. Attach Inline Policy ───────────────────────────────────────

echo "Attaching inline policy..."

aws iam put-role-policy \
  --role-name "${ROLE_NAME}" \
  --policy-name Neo4jMCPRuntimePolicy \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [
      {
        \"Sid\": \"ECRImageAccess\",
        \"Effect\": \"Allow\",
        \"Action\": [\"ecr:BatchGetImage\", \"ecr:GetDownloadUrlForLayer\"],
        \"Resource\": \"arn:aws:ecr:${REGION}:*:repository/*\"
      },
      {
        \"Sid\": \"ECRTokenAccess\",
        \"Effect\": \"Allow\",
        \"Action\": \"ecr:GetAuthorizationToken\",
        \"Resource\": \"*\"
      },
      {
        \"Sid\": \"CloudWatchLogsGroup\",
        \"Effect\": \"Allow\",
        \"Action\": [\"logs:CreateLogGroup\", \"logs:DescribeLogGroups\"],
        \"Resource\": \"arn:aws:logs:${REGION}:${ACCOUNT_ID}:log-group:/aws/bedrock-agentcore/runtimes/*\"
      },
      {
        \"Sid\": \"CloudWatchLogsStream\",
        \"Effect\": \"Allow\",
        \"Action\": [\"logs:CreateLogStream\", \"logs:DescribeLogStreams\", \"logs:PutLogEvents\"],
        \"Resource\": \"arn:aws:logs:${REGION}:${ACCOUNT_ID}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*\"
      },
      {
        \"Sid\": \"XRayTracing\",
        \"Effect\": \"Allow\",
        \"Action\": [\"xray:PutTraceSegments\", \"xray:PutTelemetryRecords\", \"xray:GetSamplingRules\", \"xray:GetSamplingTargets\"],
        \"Resource\": \"*\"
      },
      {
        \"Sid\": \"CloudWatchMetrics\",
        \"Effect\": \"Allow\",
        \"Action\": \"cloudwatch:PutMetricData\",
        \"Resource\": \"*\",
        \"Condition\": {\"StringEquals\": {\"cloudwatch:namespace\": \"bedrock-agentcore\"}}
      }
    ]
  }"

# ── 3. Create AgentCore Runtime ────────────────────────────────────

ROLE_ARN=$(aws iam get-role --role-name "${ROLE_NAME}" --query Role.Arn --output text)

echo "Waiting for IAM role to propagate..."
sleep 10

echo "Creating AgentCore runtime ${RUNTIME_NAME}..."

aws bedrock-agentcore-control create-agent-runtime \
  --region "${REGION}" \
  --agent-runtime-name "${RUNTIME_NAME}" \
  --description "Neo4j MCP for Amazon Bedrock AgentCore" \
  --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"${CONTAINER_URI}\"}}" \
  --role-arn "${ROLE_ARN}" \
  --network-configuration '{"networkMode":"PUBLIC"}' \
  --protocol-configuration '{"serverProtocol":"MCP"}' \
  --request-header-configuration '{"requestHeaderAllowlist": ["X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization"]}' \
  --environment-variables "{
    \"NEO4J_URI\":\"${NEO4J_URI}\",
    \"NEO4J_DATABASE\":\"${NEO4J_DATABASE}\",
    \"NEO4J_READ_ONLY\":\"${NEO4J_READ_ONLY}\",
    \"NEO4J_HTTP_ALLOW_UNAUTHENTICATED_PING\":\"true\",
    \"NEO4J_HTTP_AUTH_HEADER_NAME\":\"X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization\"
  }"

echo ""
echo "Done. Use the AgentRuntimeId from the output above to check status:"
echo "  aws bedrock-agentcore-control get-agent-runtime --agent-runtime-id <ID>"

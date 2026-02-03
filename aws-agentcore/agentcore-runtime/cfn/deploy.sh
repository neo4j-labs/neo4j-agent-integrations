#!/bin/bash
# Deploy Neo4j MCP Agent to AgentCore via CloudFormation
#
# Usage:
#   ./deploy.sh basic-agent              # Deploy basic-agent
#   ./deploy.sh orchestrator-agent       # Deploy orchestrator-agent
#   ./deploy.sh basic-agent my-stack     # Custom stack name
#
# Prerequisites:
#   - AWS CLI configured with credentials
#   - Docker installed and running
#   - .mcp-credentials.json in the agent directory

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
AGENT_TYPE="${1:-basic-agent}"
STACK_NAME="${2:-neo4j-${AGENT_TYPE}}"
AWS_REGION="${AWS_REGION:-us-west-2}"
NETWORK_MODE="${NETWORK_MODE:-PUBLIC}"

# Validate agent type
if [[ "$AGENT_TYPE" != "basic-agent" && "$AGENT_TYPE" != "orchestrator-agent" ]]; then
    echo -e "${RED}ERROR: Invalid agent type: $AGENT_TYPE${NC}"
    echo "Usage: $0 [basic-agent|orchestrator-agent] [stack-name]"
    exit 1
fi

AGENT_DIR="$PROJECT_DIR/$AGENT_TYPE"
AGENT_NAME="${STACK_NAME//-/_}"  # CloudFormation names use underscores

# Check prerequisites
if [ ! -d "$AGENT_DIR" ]; then
    echo -e "${RED}ERROR: Agent directory not found: $AGENT_DIR${NC}"
    exit 1
fi

if [ ! -f "$AGENT_DIR/Dockerfile" ]; then
    echo -e "${RED}ERROR: Dockerfile not found in $AGENT_DIR${NC}"
    echo "Create a Dockerfile first, or run from the agent directory."
    exit 1
fi

if [ ! -f "$AGENT_DIR/.mcp-credentials.json" ]; then
    echo -e "${YELLOW}WARNING: .mcp-credentials.json not found in $AGENT_DIR${NC}"
    echo "The agent may fail to connect to the MCP Gateway without credentials."
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Deploying $AGENT_TYPE to AgentCore${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Agent Type:   $AGENT_TYPE"
echo "Stack Name:   $STACK_NAME"
echo "Agent Name:   $AGENT_NAME"
echo "Region:       $AWS_REGION"
echo "Network Mode: $NETWORK_MODE"
echo ""

# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "AWS Account:  $ACCOUNT_ID"
echo ""

# ECR repository name (lowercase, no special chars)
ECR_REPO_NAME="agentcore/${AGENT_TYPE//-/}"
ECR_URI="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME"
IMAGE_TAG="latest"
FULL_IMAGE_URI="$ECR_URI:$IMAGE_TAG"

# Step 1: Create ECR repository if it doesn't exist
echo -e "${GREEN}Step 1: Ensuring ECR repository exists...${NC}"
if ! aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --region "$AWS_REGION" &>/dev/null; then
    echo "Creating ECR repository: $ECR_REPO_NAME"
    aws ecr create-repository \
        --repository-name "$ECR_REPO_NAME" \
        --region "$AWS_REGION" \
        --image-scanning-configuration scanOnPush=true \
        --encryption-configuration encryptionType=AES256
else
    echo "ECR repository already exists: $ECR_REPO_NAME"
fi
echo ""

# Step 2: Build Docker image (ARM64 for AgentCore)
echo -e "${GREEN}Step 2: Building Docker image (ARM64)...${NC}"
cd "$AGENT_DIR"
docker build --platform linux/arm64 -t "$ECR_REPO_NAME:$IMAGE_TAG" .
echo ""

# Step 3: Authenticate Docker to ECR
echo -e "${GREEN}Step 3: Authenticating Docker to ECR...${NC}"
aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
echo ""

# Step 4: Tag and push image to ECR
echo -e "${GREEN}Step 4: Pushing image to ECR...${NC}"
docker tag "$ECR_REPO_NAME:$IMAGE_TAG" "$FULL_IMAGE_URI"
docker push "$FULL_IMAGE_URI"
echo ""

# Step 5: Deploy CloudFormation stack
echo -e "${GREEN}Step 5: Deploying CloudFormation stack...${NC}"
cd "$SCRIPT_DIR"

aws cloudformation deploy \
    --template-file agent-runtime.yaml \
    --stack-name "$STACK_NAME" \
    --parameter-overrides \
        ECRImageUri="$FULL_IMAGE_URI" \
        AgentName="$AGENT_NAME" \
        NetworkMode="$NETWORK_MODE" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "$AWS_REGION" \
    --no-fail-on-empty-changeset

echo ""

# Step 6: Get stack outputs
echo -e "${GREEN}Step 6: Retrieving stack outputs...${NC}"
AGENT_RUNTIME_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$AWS_REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`AgentRuntimeArn`].OutputValue' \
    --output text)

INVOCATION_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$AWS_REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`InvocationEndpoint`].OutputValue' \
    --output text)

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Agent Runtime ARN:"
echo "  $AGENT_RUNTIME_ARN"
echo ""
echo "Invocation Endpoint:"
echo "  $INVOCATION_ENDPOINT"
echo ""
echo -e "${YELLOW}To invoke the agent:${NC}"
echo ""
echo "  aws bedrock-agentcore invoke-agent-runtime \\"
echo "    --agent-runtime-arn \"$AGENT_RUNTIME_ARN\" \\"
echo "    --runtime-session-id \"\$(uuidgen)\" \\"
echo "    --payload '{\"prompt\":\"What is the database schema?\"}' \\"
echo "    --region $AWS_REGION"
echo ""
echo -e "${YELLOW}To check runtime status:${NC}"
echo ""
echo "  aws bedrock-agentcore-control get-agent-runtime \\"
echo "    --agent-runtime-id \"${AGENT_RUNTIME_ARN##*/}\" \\"
echo "    --region $AWS_REGION"
echo ""
echo -e "${YELLOW}To view logs:${NC}"
echo ""
echo "  aws logs tail /aws/bedrock-agentcore/runtimes/${AGENT_RUNTIME_ARN##*/} \\"
echo "    --region $AWS_REGION --follow"
echo ""

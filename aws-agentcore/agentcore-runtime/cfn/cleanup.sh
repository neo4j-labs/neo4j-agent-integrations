#!/bin/bash
# Cleanup Neo4j MCP Agent from AgentCore
#
# Usage:
#   ./cleanup.sh basic-agent              # Cleanup basic-agent
#   ./cleanup.sh orchestrator-agent       # Cleanup orchestrator-agent
#   ./cleanup.sh basic-agent my-stack     # Custom stack name
#   ./cleanup.sh basic-agent my-stack --delete-ecr  # Also delete ECR repo
#
# Options:
#   --delete-ecr    Also delete the ECR repository and images

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
AGENT_TYPE="${1:-basic-agent}"
STACK_NAME="${2:-neo4j-${AGENT_TYPE}}"
DELETE_ECR=false
AWS_REGION="${AWS_REGION:-us-west-2}"

# Parse additional arguments
for arg in "$@"; do
    case $arg in
        --delete-ecr)
            DELETE_ECR=true
            ;;
    esac
done

# Validate agent type
if [[ "$AGENT_TYPE" != "basic-agent" && "$AGENT_TYPE" != "orchestrator-agent" ]]; then
    echo -e "${RED}ERROR: Invalid agent type: $AGENT_TYPE${NC}"
    echo "Usage: $0 [basic-agent|orchestrator-agent] [stack-name] [--delete-ecr]"
    exit 1
fi

ECR_REPO_NAME="agentcore/${AGENT_TYPE//-/}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Cleaning up $AGENT_TYPE from AgentCore${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Stack Name:   $STACK_NAME"
echo "Region:       $AWS_REGION"
echo "Delete ECR:   $DELETE_ECR"
echo ""

# Step 1: Check if stack exists
echo -e "${GREEN}Step 1: Checking if CloudFormation stack exists...${NC}"
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" &>/dev/null; then
    echo "Stack found: $STACK_NAME"

    # Get agent runtime ARN before deletion (for logging purposes)
    AGENT_RUNTIME_ARN=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`AgentRuntimeArn`].OutputValue' \
        --output text 2>/dev/null || echo "N/A")
    echo "Agent Runtime ARN: $AGENT_RUNTIME_ARN"
    echo ""

    # Step 2: Delete CloudFormation stack
    echo -e "${GREEN}Step 2: Deleting CloudFormation stack...${NC}"
    aws cloudformation delete-stack \
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION"

    echo "Waiting for stack deletion to complete..."
    aws cloudformation wait stack-delete-complete \
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION"

    echo -e "${GREEN}Stack deleted successfully.${NC}"
else
    echo -e "${YELLOW}Stack not found: $STACK_NAME${NC}"
    echo "Nothing to delete."
fi
echo ""

# Step 3: Optionally delete ECR repository
if [ "$DELETE_ECR" = true ]; then
    echo -e "${GREEN}Step 3: Deleting ECR repository...${NC}"

    if aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --region "$AWS_REGION" &>/dev/null; then
        echo "Deleting ECR repository: $ECR_REPO_NAME"
        aws ecr delete-repository \
            --repository-name "$ECR_REPO_NAME" \
            --region "$AWS_REGION" \
            --force
        echo -e "${GREEN}ECR repository deleted.${NC}"
    else
        echo -e "${YELLOW}ECR repository not found: $ECR_REPO_NAME${NC}"
    fi
else
    echo -e "${YELLOW}Step 3: Skipping ECR repository deletion (use --delete-ecr to remove)${NC}"
    echo "ECR repository retained: $ECR_REPO_NAME"
fi
echo ""

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Cleanup Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if [ "$DELETE_ECR" = false ]; then
    echo -e "${YELLOW}Note: ECR repository was not deleted.${NC}"
    echo "To also delete ECR, run: $0 $AGENT_TYPE $STACK_NAME --delete-ecr"
    echo ""
fi

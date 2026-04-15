#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

STACK_NAME="${STACK_NAME:-Neo4jMCPRuntimeStack}"
COMMAND="${1:-deploy}"

# --- Load .env ---
if [ -f .env ]; then
  set -a
  source .env
  set +a
else
  echo "Error: .env file not found. Copy .env.sample to .env and fill in your values."
  exit 1
fi

# --- Check prerequisites ---
check_prerequisites() {
  missing=()
  command -v aws    >/dev/null 2>&1 || missing+=("aws cli")
  command -v cdk    >/dev/null 2>&1 || missing+=("aws-cdk (npm install -g aws-cdk)")
  command -v uv     >/dev/null 2>&1 || missing+=("uv (https://docs.astral.sh/uv/)")
  command -v docker >/dev/null 2>&1 || missing+=("docker")

  if [ ${#missing[@]} -gt 0 ]; then
    echo "Error: missing prerequisites:"
    printf '  - %s\n' "${missing[@]}"
    exit 1
  fi
}

# --- Build CDK context arguments ---
build_cdk_context() {
  : "${NEO4J_URI:?NEO4J_URI must be set in .env}"
  : "${NEO4J_DATABASE:?NEO4J_DATABASE must be set in .env}"

  CDK_CONTEXT_ARGS=(
    -c "neo4j_uri=$NEO4J_URI"
    -c "neo4j_database=$NEO4J_DATABASE"
  )

  if [ -n "${NEO4J_MCP_CONTAINER_URI:-}" ]; then
    echo "Using pre-built container image: $NEO4J_MCP_CONTAINER_URI"
    CDK_CONTEXT_ARGS+=(-c "neo4j_mcp_container_uri=$NEO4J_MCP_CONTAINER_URI")
  else
    echo "No NEO4J_MCP_CONTAINER_URI set -- CDK will build a local Docker image from docker/Dockerfile"
    CDK_CONTEXT_ARGS+=(-c "neo4j_mcp_container_uri=")
  fi
}

# --- Write deployment outputs to .env ---
write_outputs_to_env() {
  local runtime_arn
  runtime_arn=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`Neo4jMcpRuntimeArn`].OutputValue' \
    --output text 2>/dev/null || true)

  if [ -z "$runtime_arn" ]; then
    echo "Warning: Could not retrieve Runtime ARN from stack outputs."
    return
  fi

  if grep -q "^AGENTCORE_RUNTIME_ARN=" .env 2>/dev/null; then
    sed -i.bak "s|^AGENTCORE_RUNTIME_ARN=.*|AGENTCORE_RUNTIME_ARN=$runtime_arn|" .env && rm -f .env.bak
  elif grep -q "^# AGENTCORE_RUNTIME_ARN=" .env 2>/dev/null; then
    sed -i.bak "s|^# AGENTCORE_RUNTIME_ARN=.*|AGENTCORE_RUNTIME_ARN=$runtime_arn|" .env && rm -f .env.bak
  else
    echo "" >> .env
    echo "# Auto-populated by deploy.sh after successful deployment" >> .env
    echo "AGENTCORE_RUNTIME_ARN=$runtime_arn" >> .env
  fi

  echo "Runtime ARN written to .env: $runtime_arn"
}

# --- Commands ---

do_deploy() {
  check_prerequisites
  build_cdk_context

  echo "Installing dependencies..."
  uv sync

  echo "Bootstrapping CDK..."
  cdk bootstrap

  echo "Deploying $STACK_NAME..."
  cdk deploy "$STACK_NAME" \
    "${CDK_CONTEXT_ARGS[@]}" \
    --require-approval never

  write_outputs_to_env

  echo ""
  echo "Deployment complete. Run './deploy.sh status' to check or './deploy.sh destroy' to tear down."
}

do_status() {
  echo "Stack: $STACK_NAME"
  echo ""
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].{Status:StackStatus,Created:CreationTime,Updated:LastUpdatedTime,Outputs:Outputs[*].{Key:OutputKey,Value:OutputValue}}' \
    --output table 2>/dev/null || echo "Stack not found or not deployed."
}

do_destroy() {
  echo "Destroying $STACK_NAME..."
  cdk destroy "$STACK_NAME" --force
  echo "Stack destroyed."
}

usage() {
  echo "Usage: ./deploy.sh [command]"
  echo ""
  echo "Commands:"
  echo "  deploy   Deploy the stack (default)"
  echo "  status   Show stack status and outputs"
  echo "  destroy  Tear down the stack"
}

# --- Main ---
case "$COMMAND" in
  deploy)  do_deploy ;;
  status)  do_status ;;
  destroy) do_destroy ;;
  *)
    echo "Unknown command: $COMMAND"
    usage
    exit 1
    ;;
esac

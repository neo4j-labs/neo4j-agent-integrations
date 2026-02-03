#!/bin/bash
#
# Neo4j MCP Server - AgentCore Deployment Script (CDK)
#
# Builds the Neo4j MCP server image, pushes to ECR, and deploys via AWS CDK.
#
# Usage:
#   ./deploy.sh              # Full deployment (build, push, stack)
#   ./deploy.sh redeploy     # Fast redeploy (build, push, update runtime)
#   ./deploy.sh stack        # Deploy CDK stack only (assumes image in ECR)
#   ./deploy.sh synth        # Synthesize CloudFormation template (dry run)
#   ./deploy.sh status       # Show stack status and outputs
#   ./deploy.sh cleanup      # Delete stack and ECR repository
#   ./deploy.sh help         # Show this help
#

set -e

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE=".env"
NEO4J_MCP_REPO="/Users/ryanknight/projects/mcp"
CDK_DIR="$SCRIPT_DIR/cdk"

# Defaults (can be overridden in .env)
DEFAULT_REGION="us-west-2"
DEFAULT_STACK_NAME="neo4j-agentcore-mcp-server"
DEFAULT_ECR_REPO_NAME="neo4j-mcp-server"
DEFAULT_IMAGE_TAG="latest"

# ============================================================================
# Helper Functions
# ============================================================================

log_info() {
    echo "INFO  $1"
}

log_error() {
    echo "ERROR $1" >&2
}

log_success() {
    echo "OK    $1"
}

log_step() {
    echo ""
    echo "======================================================================"
    echo "$1"
    echo "======================================================================"
}

# Load environment variables from .env file
load_env() {
    if [[ ! -f "$ENV_FILE" ]]; then
        log_error ".env file not found in current directory"
        log_error "Copy .env.sample to .env and fill in your credentials"
        exit 1
    fi

    set -a
    source "$ENV_FILE"
    set +a

    # Apply defaults
    AWS_REGION="${AWS_REGION:-$DEFAULT_REGION}"
    STACK_NAME="${STACK_NAME:-$DEFAULT_STACK_NAME}"
    ECR_REPO_NAME="${ECR_REPO_NAME:-$DEFAULT_ECR_REPO_NAME}"
    IMAGE_TAG="${IMAGE_TAG:-$DEFAULT_IMAGE_TAG}"
}

# Validate required environment variables
validate_env() {
    local missing=()

    [[ -z "$NEO4J_URI" ]] && missing+=("NEO4J_URI")
    [[ -z "$NEO4J_DATABASE" ]] && missing+=("NEO4J_DATABASE")
    [[ -z "$NEO4J_USERNAME" ]] && missing+=("NEO4J_USERNAME")
    [[ -z "$NEO4J_PASSWORD" ]] && missing+=("NEO4J_PASSWORD")

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required environment variables in .env:"
        for var in "${missing[@]}"; do
            log_error "  - $var"
        done
        exit 1
    fi
}

# Test Neo4j connectivity
test_neo4j_connection() {
    log_info "Testing Neo4j connectivity..."

    # Check for cypher-shell
    if ! command -v cypher-shell &> /dev/null; then
        log_error "cypher-shell not found - cannot verify Neo4j connectivity"
        log_error "Install with: brew install cypher-shell"
        log_error "Continuing without connectivity check..."
        return 0
    fi

    # Test connection
    if echo "RETURN 1 AS test;" | cypher-shell \
        -a "$NEO4J_URI" \
        -u "$NEO4J_USERNAME" \
        -p "$NEO4J_PASSWORD" \
        -d "$NEO4J_DATABASE" \
        --non-interactive \
        --format plain &> /dev/null; then
        log_success "Neo4j connection successful"
        return 0
    else
        log_error "Cannot connect to Neo4j database"
        log_error "  URI:      $NEO4J_URI"
        log_error "  Database: $NEO4J_DATABASE"
        log_error "  Username: $NEO4J_USERNAME"
        log_error ""
        log_error "Please verify:"
        log_error "  - Neo4j credentials are correct"
        log_error "  - Neo4j database is running and accessible"
        log_error "  - Network connectivity (firewall, VPN, etc.)"
        log_error ""
        log_error "Test manually with: ./test-neo4j-connection.sh"
        exit 1
    fi
}

# Get AWS account ID
get_account_id() {
    aws sts get-caller-identity --query Account --output text --region "$AWS_REGION"
}

# Get ECR repository URI
get_ecr_uri() {
    local account_id="$1"
    echo "${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"
}

# Check if ECR repository exists
ecr_repo_exists() {
    aws ecr describe-repositories \
        --repository-names "$ECR_REPO_NAME" \
        --region "$AWS_REGION" \
        >/dev/null 2>&1
}

# Check if CloudFormation stack exists (CDK stacks are CFN stacks)
stack_exists() {
    aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION" \
        >/dev/null 2>&1
}

# Setup CDK virtual environment
setup_cdk_venv() {
    if [[ ! -d "$CDK_DIR/.venv" ]]; then
        log_info "Creating CDK virtual environment..."
        python3 -m venv "$CDK_DIR/.venv"
    fi

    source "$CDK_DIR/.venv/bin/activate"

    # Install dependencies if needed
    if ! pip show aws-cdk-lib >/dev/null 2>&1; then
        log_info "Installing CDK dependencies..."
        pip install -q -r "$CDK_DIR/requirements.txt"
    fi
}

# ============================================================================
# Build Command
# ============================================================================

cmd_build() {
    log_step "Building Neo4j MCP Server Image (ARM64)"

    if [[ ! -d "$NEO4J_MCP_REPO" ]]; then
        log_error "Neo4j MCP repository not found at $NEO4J_MCP_REPO"
        exit 1
    fi

    if [[ ! -f "$NEO4J_MCP_REPO/Dockerfile" ]]; then
        log_error "Dockerfile not found in $NEO4J_MCP_REPO"
        exit 1
    fi

    log_info "Repository: $NEO4J_MCP_REPO"
    log_info "Image: ${ECR_REPO_NAME}:${IMAGE_TAG}"
    log_info "Platform: linux/arm64"
    echo ""

    # Build for ARM64 using buildx
    docker buildx build \
        --platform linux/arm64 \
        --tag "${ECR_REPO_NAME}:${IMAGE_TAG}" \
        --load \
        "$NEO4J_MCP_REPO"

    log_success "Image built successfully"
}

# ============================================================================
# Push Command
# ============================================================================

cmd_push() {
    log_step "Pushing Image to ECR"

    local account_id
    account_id=$(get_account_id)
    local ecr_uri
    ecr_uri=$(get_ecr_uri "$account_id")

    log_info "Account: $account_id"
    log_info "Region: $AWS_REGION"
    log_info "Repository: $ECR_REPO_NAME"
    log_info "ECR URI: $ecr_uri"
    echo ""

    # Create ECR repository if it doesn't exist
    if ! ecr_repo_exists; then
        log_info "Creating ECR repository: $ECR_REPO_NAME"
        aws ecr create-repository \
            --repository-name "$ECR_REPO_NAME" \
            --region "$AWS_REGION" \
            --image-scanning-configuration scanOnPush=true \
            >/dev/null
        log_success "ECR repository created"
    else
        log_info "ECR repository already exists"
    fi

    # Authenticate with ECR
    log_info "Authenticating with ECR..."
    aws ecr get-login-password --region "$AWS_REGION" | \
        docker login --username AWS --password-stdin "${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com"

    # Tag and push
    log_info "Tagging image..."
    docker tag "${ECR_REPO_NAME}:${IMAGE_TAG}" "${ecr_uri}:${IMAGE_TAG}"

    log_info "Pushing image to ECR..."
    docker push "${ecr_uri}:${IMAGE_TAG}"

    log_success "Image pushed successfully: ${ecr_uri}:${IMAGE_TAG}"
}

# ============================================================================
# Stack Command (CDK Deploy)
# ============================================================================

cmd_stack() {
    log_step "Deploying CDK Stack"

    local account_id
    account_id=$(get_account_id)
    local ecr_uri
    ecr_uri=$(get_ecr_uri "$account_id")
    local full_image_uri="${ecr_uri}:${IMAGE_TAG}"

    log_info "Stack Name: $STACK_NAME"
    log_info "Region: $AWS_REGION"
    log_info "Image URI: $full_image_uri"
    log_info "Neo4j URI: $NEO4J_URI"
    echo ""

    # Setup CDK environment
    setup_cdk_venv

    # Check if CDK is bootstrapped
    if ! aws cloudformation describe-stacks \
        --stack-name "CDKToolkit" \
        --region "$AWS_REGION" >/dev/null 2>&1; then
        log_info "CDK not bootstrapped in this region, bootstrapping..."
        cd "$CDK_DIR"
        cdk bootstrap "aws://${account_id}/${AWS_REGION}"
    fi

    # Deploy CDK stack (with retry logic for Gateway timing issues)
    log_info "Deploying CDK stack (this may take 5-10 minutes)..."
    cd "$CDK_DIR"

    # First attempt
    if JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 \
       STACK_NAME="$STACK_NAME" AWS_REGION="$AWS_REGION" \
       cdk deploy "$STACK_NAME" \
           --require-approval never \
           --parameters "ECRImageUri=${full_image_uri}" \
           --parameters "Neo4jUri=${NEO4J_URI}" \
           --parameters "Neo4jDatabase=${NEO4J_DATABASE}" \
           --parameters "Neo4jUsername=${NEO4J_USERNAME}" \
           --parameters "Neo4jPassword=${NEO4J_PASSWORD}" 2>&1; then
        log_success "Stack deployment complete"
    else
        # Check if it failed due to ROLLBACK_COMPLETE (timing issue with Gateway)
        local stack_status
        stack_status=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --query "Stacks[0].StackStatus" \
            --output text \
            --region "$AWS_REGION" 2>/dev/null || echo "DOES_NOT_EXIST")

        if [[ "$stack_status" == "ROLLBACK_COMPLETE" ]]; then
            log_info "First deployment failed (Runtime may need time to stabilize). Cleaning up and retrying..."

            # Delete the failed stack
            aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$AWS_REGION"
            aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region "$AWS_REGION"

            # Wait for services to stabilize
            log_info "Waiting 30 seconds for services to stabilize..."
            sleep 30

            # Retry deployment
            log_info "Retrying deployment..."
            JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 \
            STACK_NAME="$STACK_NAME" AWS_REGION="$AWS_REGION" \
            cdk deploy "$STACK_NAME" \
                --require-approval never \
                --parameters "ECRImageUri=${full_image_uri}" \
                --parameters "Neo4jUri=${NEO4J_URI}" \
                --parameters "Neo4jDatabase=${NEO4J_DATABASE}" \
                --parameters "Neo4jUsername=${NEO4J_USERNAME}" \
                --parameters "Neo4jPassword=${NEO4J_PASSWORD}"

            log_success "Stack deployment complete (on retry)"
        else
            log_error "Deployment failed with status: $stack_status"
            exit 1
        fi
    fi
    echo ""

    # Show outputs
    cmd_status
}

# ============================================================================
# Synth Command (Dry Run)
# ============================================================================

cmd_synth() {
    log_step "Synthesizing CloudFormation Template"

    local account_id
    account_id=$(get_account_id)
    local ecr_uri
    ecr_uri=$(get_ecr_uri "$account_id")
    local full_image_uri="${ecr_uri}:${IMAGE_TAG}"

    # Setup CDK environment
    setup_cdk_venv

    cd "$CDK_DIR"
    JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 \
    STACK_NAME="$STACK_NAME" AWS_REGION="$AWS_REGION" \
    cdk synth "$STACK_NAME"

    log_success "Template synthesized successfully"
    log_info "Output is in cdk/cdk.out/"
}

# ============================================================================
# Status Command
# ============================================================================

cmd_status() {
    log_step "Stack Status and Outputs"

    if ! stack_exists; then
        log_error "Stack '$STACK_NAME' does not exist in region '$AWS_REGION'"
        exit 1
    fi

    # Get stack status
    local status
    status=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].StackStatus' \
        --output text \
        --region "$AWS_REGION")

    log_info "Stack Status: $status"
    echo ""

    if [[ "$status" == *"COMPLETE"* ]] && [[ "$status" != *"DELETE"* ]]; then
        echo "Stack Outputs:"
        echo "--------------------------------------------------------------------"

        # Get key outputs
        local gateway_url client_id runtime_arn token_url

        gateway_url=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --query 'Stacks[0].Outputs[?OutputKey==`GatewayUrl`].OutputValue' \
            --output text \
            --region "$AWS_REGION")

        client_id=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --query 'Stacks[0].Outputs[?OutputKey==`CognitoMachineClientId`].OutputValue' \
            --output text \
            --region "$AWS_REGION")

        runtime_arn=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --query 'Stacks[0].Outputs[?OutputKey==`MCPServerRuntimeArn`].OutputValue' \
            --output text \
            --region "$AWS_REGION")

        token_url=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --query 'Stacks[0].Outputs[?OutputKey==`CognitoTokenUrl`].OutputValue' \
            --output text \
            --region "$AWS_REGION")

        echo "  Gateway URL: $gateway_url"
        echo "  Cognito Client ID: $client_id"
        echo "  Token URL: $token_url"
        echo "  Runtime ARN: $runtime_arn"
        echo ""
        echo "Next steps:"
        echo "  1. Generate credentials:  ./deploy.sh credentials"
        echo "  2. Test the deployment:   ./cloud.sh"
    fi
}

# ============================================================================
# Cleanup Command
# ============================================================================

cmd_cleanup() {
    log_step "Cleanup: Delete Stack and ECR Repository"

    log_info "This will delete:"
    log_info "  - CDK stack: $STACK_NAME"
    log_info "  - ECR repository: $ECR_REPO_NAME"
    echo ""

    read -p "Are you sure you want to proceed? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Cleanup cancelled"
        exit 0
    fi

    # Delete CDK stack
    if stack_exists; then
        log_info "Deleting CDK stack: $STACK_NAME"

        # Setup CDK environment
        setup_cdk_venv

        cd "$CDK_DIR"
        JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 \
        STACK_NAME="$STACK_NAME" AWS_REGION="$AWS_REGION" \
        cdk destroy "$STACK_NAME" --force

        log_success "Stack deleted"
    else
        log_info "Stack does not exist, skipping"
    fi

    # Delete ECR repository
    if ecr_repo_exists; then
        log_info "Deleting ECR repository: $ECR_REPO_NAME"
        aws ecr delete-repository \
            --repository-name "$ECR_REPO_NAME" \
            --force \
            --region "$AWS_REGION" \
            >/dev/null

        log_success "ECR repository deleted"
    else
        log_info "ECR repository does not exist, skipping"
    fi

    log_success "Cleanup complete"
}

# ============================================================================
# Redeploy Command (build + push + update runtime)
# ============================================================================

cmd_redeploy() {
    log_step "Redeploying MCP Server (build + push + update runtime)"

    if ! stack_exists; then
        log_error "Stack '$STACK_NAME' does not exist. Run './deploy.sh' for initial deployment."
        exit 1
    fi

    # Build and push new image
    cmd_build
    cmd_push

    # Get runtime info from stack outputs
    log_info "Getting runtime configuration from stack..."

    local runtime_id role_arn
    runtime_id=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`MCPServerRuntimeId`].OutputValue' \
        --output text \
        --region "$AWS_REGION")

    role_arn=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`AgentExecutionRoleArn`].OutputValue' \
        --output text \
        --region "$AWS_REGION")

    if [[ -z "$runtime_id" ]] || [[ -z "$role_arn" ]]; then
        log_error "Could not retrieve runtime info from stack outputs"
        exit 1
    fi

    local account_id ecr_uri full_image_uri
    account_id=$(get_account_id)
    ecr_uri=$(get_ecr_uri "$account_id")
    full_image_uri="${ecr_uri}:${IMAGE_TAG}"

    log_step "Updating AgentCore Runtime"
    log_info "Runtime ID: $runtime_id"
    log_info "New Image: $full_image_uri"
    echo ""

    # Update the runtime with new container image
    aws bedrock-agentcore-control update-agent-runtime \
        --agent-runtime-id "$runtime_id" \
        --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"$full_image_uri\"}}" \
        --role-arn "$role_arn" \
        --network-configuration "{\"networkMode\":\"PUBLIC\"}" \
        --region "$AWS_REGION"

    log_success "Runtime update initiated"
    log_info "The runtime will redeploy with the new image."
    log_info "Check status with: ./deploy.sh status"
}

# ============================================================================
# Credentials Command
# ============================================================================

cmd_credentials() {
    log_step "Generating MCP Credentials"

    if ! stack_exists; then
        log_error "Stack '$STACK_NAME' does not exist. Run ./deploy.sh first."
        exit 1
    fi

    # Get stack outputs
    log_info "Retrieving stack outputs..."

    local gateway_url user_pool_id client_id token_url scope

    gateway_url=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`GatewayUrl`].OutputValue' \
        --output text \
        --region "$AWS_REGION")

    user_pool_id=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`CognitoUserPoolId`].OutputValue' \
        --output text \
        --region "$AWS_REGION")

    client_id=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`CognitoMachineClientId`].OutputValue' \
        --output text \
        --region "$AWS_REGION")

    token_url=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`CognitoTokenUrl`].OutputValue' \
        --output text \
        --region "$AWS_REGION")

    scope=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`CognitoScope`].OutputValue' \
        --output text \
        --region "$AWS_REGION")

    if [[ -z "$gateway_url" ]] || [[ -z "$client_id" ]]; then
        log_error "Could not retrieve required stack outputs"
        exit 1
    fi

    log_info "Gateway URL: $gateway_url"
    log_info "Client ID: $client_id"

    # Get client secret and JWT token using Python
    log_info "Fetching client secret and JWT token..."

    # Ensure venv exists
    if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
        python3 -m venv "$SCRIPT_DIR/.venv"
        source "$SCRIPT_DIR/.venv/bin/activate"
        pip install --quiet boto3 httpx
    else
        source "$SCRIPT_DIR/.venv/bin/activate"
    fi

    python3 << PYEOF
import json
import base64
import socket
import time
import sys
import boto3
import httpx
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

# Configuration
USER_POOL_ID = "$user_pool_id"
CLIENT_ID = "$client_id"
TOKEN_URL = "$token_url"
SCOPE = "$scope"
GATEWAY_URL = "$gateway_url"
REGION = "$AWS_REGION"
STACK_NAME = "$STACK_NAME"
OUTPUT_FILE = "$SCRIPT_DIR/.mcp-credentials.json"

def wait_for_dns(hostname: str, max_attempts: int = 30, delay: int = 10) -> bool:
    """Wait for DNS to resolve for the given hostname."""
    print(f"   Waiting for DNS propagation for {hostname}...")
    for attempt in range(max_attempts):
        try:
            socket.gethostbyname(hostname)
            print(f"   DNS resolved successfully")
            return True
        except socket.gaierror:
            if attempt < max_attempts - 1:
                print(f"   DNS not ready, waiting {delay}s... (attempt {attempt + 1}/{max_attempts})")
                time.sleep(delay)
    return False

# Get client secret from Cognito
print("   Getting client secret from Cognito...")
cognito = boto3.client("cognito-idp", region_name=REGION)
response = cognito.describe_user_pool_client(
    UserPoolId=USER_POOL_ID,
    ClientId=CLIENT_ID
)
client_secret = response["UserPoolClient"]["ClientSecret"]
print(f"   Client secret retrieved ({len(client_secret)} chars)")

# Wait for Cognito domain DNS to propagate before requesting token
parsed_url = urlparse(TOKEN_URL)
if not wait_for_dns(parsed_url.hostname):
    print(f"   ERROR: DNS did not resolve for {parsed_url.hostname} after multiple attempts")
    print(f"   The Cognito domain may still be propagating. Try again in a few minutes:")
    print(f"   ./deploy.sh credentials")
    sys.exit(1)

# Get JWT token using client credentials flow with retry
print("   Requesting JWT token...")
credentials = base64.b64encode(f"{CLIENT_ID}:{client_secret}".encode()).decode()
headers = {
    "Authorization": f"Basic {credentials}",
    "Content-Type": "application/x-www-form-urlencoded",
}
data = {"grant_type": "client_credentials", "scope": SCOPE}

max_retries = 3
for retry in range(max_retries):
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(TOKEN_URL, headers=headers, data=data)
            resp.raise_for_status()
            token_response = resp.json()
        break
    except httpx.ConnectError as e:
        if retry < max_retries - 1:
            print(f"   Connection error, retrying in 10s... ({retry + 1}/{max_retries})")
            time.sleep(10)
        else:
            print(f"   ERROR: Failed to connect to token endpoint after {max_retries} attempts")
            print(f"   Error: {e}")
            sys.exit(1)

access_token = token_response["access_token"]
expires_in = token_response.get("expires_in", 3600)  # Default 1 hour
expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

print(f"   Token retrieved (expires in {expires_in}s)")

# Write credentials file
credentials_data = {
    "gateway_url": GATEWAY_URL,
    "token_url": TOKEN_URL,
    "client_id": CLIENT_ID,
    "client_secret": client_secret,
    "scope": SCOPE,
    "access_token": access_token,
    "token_expires_at": expires_at.isoformat(),
    "region": REGION,
    "stack_name": STACK_NAME
}

with open(OUTPUT_FILE, "w") as f:
    json.dump(credentials_data, f, indent=2)

print(f"   Credentials written to .mcp-credentials.json")
PYEOF

    log_success "Credentials file generated"
    echo ""
    echo "Usage:"
    echo "  - File: .mcp-credentials.json"
    echo "  - Token expires at the time shown in token_expires_at"
    echo "  - Run './deploy.sh credentials' to refresh the token"
}

# ============================================================================
# Help Command
# ============================================================================

cmd_help() {
    cat << EOF
Neo4j MCP Server - AgentCore Deployment Script (CDK)

Usage: $0 [command] [options]

Commands:
  (none)       Full deployment: build image, push to ECR, deploy stack
  redeploy     Fast redeploy: build, push, and update runtime (no stack changes)
  stack        Deploy CDK stack only (assumes image in ECR)
  synth        Synthesize CloudFormation template (dry run)
  status       Show stack status and outputs
  credentials  Generate .mcp-credentials.json with Gateway URL and JWT token
  cleanup      Delete the stack and ECR repository
  help         Show this help message

Options:
  --skip-build    Skip Docker build, just push existing image and deploy

Environment Variables (from .env):
  Required:
    NEO4J_URI          Neo4j connection string
    NEO4J_DATABASE     Database name
    NEO4J_USERNAME     Neo4j username (passed to container)
    NEO4J_PASSWORD     Neo4j password (passed to container)

  Optional:
    AWS_REGION         AWS region (default: us-west-2)
    STACK_NAME         CDK stack name (default: neo4j-agentcore-mcp-server)
    ECR_REPO_NAME      ECR repository name (default: neo4j-mcp-server)
    IMAGE_TAG          Docker image tag (default: latest)

Examples:
  $0                   # Full deployment (build + push + stack)
  $0 redeploy          # Fast redeploy (build + push + update runtime)
  $0 --skip-build      # Push existing image and deploy stack
  $0 stack             # Deploy stack only
  $0 synth             # Generate CloudFormation template
  $0 status            # Check deployment status
  $0 credentials       # Generate credentials file for MCP clients
  $0 cleanup           # Remove everything

EOF
}

# ============================================================================
# Main Entry Point
# ============================================================================

main() {
    local command="${1:-}"
    local skip_build=false

    # Parse options
    for arg in "$@"; do
        case "$arg" in
            --skip-build)
                skip_build=true
                ;;
        esac
    done

    # Help doesn't need env
    if [[ "$command" == "help" || "$command" == "--help" || "$command" == "-h" ]]; then
        cmd_help
        exit 0
    fi

    # Load and validate environment
    load_env
    validate_env

    # Test Neo4j connectivity before any deployment steps
    # Skip for commands that don't need Neo4j
    case "$command" in
        status|cleanup|credentials|redeploy|help)
            # These commands don't need Neo4j connectivity
            ;;
        *)
            test_neo4j_connection
            ;;
    esac

    log_info "Configuration:"
    log_info "  Region: $AWS_REGION"
    log_info "  Stack Name: $STACK_NAME"
    log_info "  ECR Repository: $ECR_REPO_NAME"

    case "$command" in
        ""|--skip-build)
            # Full deployment (optionally skip build)
            if [[ "$skip_build" == "true" ]]; then
                log_info "Skipping Docker build (--skip-build)"
            else
                cmd_build
            fi
            cmd_push
            cmd_stack
            ;;
        redeploy)
            cmd_redeploy
            ;;
        stack)
            cmd_stack
            ;;
        synth)
            cmd_synth
            ;;
        status)
            cmd_status
            ;;
        credentials)
            cmd_credentials
            ;;
        cleanup)
            cmd_cleanup
            ;;
        *)
            log_error "Unknown command: $command"
            echo ""
            cmd_help
            exit 1
            ;;
    esac
}

main "$@"

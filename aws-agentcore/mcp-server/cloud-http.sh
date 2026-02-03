#!/bin/bash
# ==============================================================================
# CLOUD-HTTP.SH - Neo4j MCP Server Raw HTTP Debugging Script
# ==============================================================================
#
# PURPOSE:
#   Tests the deployed Neo4j MCP server DIRECTLY (bypassing Gateway) using raw
#   HTTP requests. Useful for debugging connection issues or understanding the
#   underlying JSON-RPC protocol.
#
# TARGET:
#   Direct AgentCore Runtime (not via Gateway)
#
# AUTHENTICATION:
#   M2M OAuth2 - uses client_credentials flow with the machine client.
#   No username/password needed - credentials are retrieved automatically.
#
# TESTS:
#   1. MCP initialize (JSON-RPC)
#   2. tools/list (JSON-RPC)
#
# ENVIRONMENT (from .env):
#   AWS_REGION      AWS region (default: us-west-2)
#   STACK_NAME      CDK stack name (default: neo4j-agentcore-mcp-server)
#
# SEE ALSO:
#   ./local.sh  - Local Docker server testing (no auth)
#   ./cloud.sh  - Gateway testing with MCP client library (recommended)
#
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

# Load environment
if [[ -f "$ENV_FILE" ]]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

# Defaults
STACK_NAME="${STACK_NAME:-neo4j-agentcore-mcp-server}"
REGION="${AWS_REGION:-us-west-2}"

# Get stack outputs
echo "=== Direct Runtime HTTP Test ==="
echo "Stack: $STACK_NAME"
echo "Region: $REGION"
echo ""

USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`CognitoUserPoolId`].OutputValue' \
    --output text \
    --region "$REGION")

MACHINE_CLIENT_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`CognitoMachineClientId`].OutputValue' \
    --output text \
    --region "$REGION")

TOKEN_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`CognitoTokenUrl`].OutputValue' \
    --output text \
    --region "$REGION")

SCOPE=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`CognitoScope`].OutputValue' \
    --output text \
    --region "$REGION")

RUNTIME_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`MCPServerRuntimeArn`].OutputValue' \
    --output text \
    --region "$REGION")

if [[ -z "$USER_POOL_ID" ]] || [[ -z "$MACHINE_CLIENT_ID" ]] || [[ -z "$RUNTIME_ARN" ]]; then
    echo "ERROR: Could not get stack outputs. Is the stack deployed?"
    exit 1
fi

echo "User Pool ID: $USER_POOL_ID"
echo "Machine Client ID: $MACHINE_CLIENT_ID"
echo "Token URL: $TOKEN_URL"
echo "Scope: $SCOPE"
echo "Runtime ARN: $RUNTIME_ARN"
echo ""

# Ensure venv exists
if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/.venv"
    source "$SCRIPT_DIR/.venv/bin/activate"
    pip install --quiet boto3 "botocore[crt]" httpx
else
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

python3 << PYEOF
import os
import sys
import json
import base64
import boto3
import httpx
import urllib.parse

# Configuration from environment
USER_POOL_ID = "$USER_POOL_ID"
MACHINE_CLIENT_ID = "$MACHINE_CLIENT_ID"
TOKEN_URL = "$TOKEN_URL"
SCOPE = "$SCOPE"
RUNTIME_ARN = "$RUNTIME_ARN"
REGION = "$REGION"

# Build endpoint URL (URL-encode the ARN)
encoded_arn = urllib.parse.quote(RUNTIME_ARN, safe='')
ENDPOINT = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

print(f"Endpoint: {ENDPOINT[:80]}...")
print("")

# Step 1: Get client secret from Cognito
print("1. Getting client secret from Cognito...")
try:
    cognito = boto3.client("cognito-idp", region_name=REGION)
    response = cognito.describe_user_pool_client(
        UserPoolId=USER_POOL_ID,
        ClientId=MACHINE_CLIENT_ID
    )
    client_secret = response["UserPoolClient"]["ClientSecret"]
    print(f"   Client secret OK: {len(client_secret)} chars")
except Exception as e:
    print(f"   FAILED: {e}")
    sys.exit(1)

# Step 2: Get M2M token using client credentials
print("")
print("2. Getting M2M token (client_credentials flow)...")
try:
    credentials = base64.b64encode(f"{MACHINE_CLIENT_ID}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"grant_type": "client_credentials", "scope": SCOPE}

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(TOKEN_URL, headers=headers, data=data)
        resp.raise_for_status()
        token = resp.json()["access_token"]
        print(f"   Token OK: {len(token)} chars")
except Exception as e:
    print(f"   FAILED: {e}")
    sys.exit(1)

# Prepare headers
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream"
}

# Test 3: MCP Initialize
print("")
print("3. Testing MCP initialize...")
init_payload = {
    "jsonrpc": "2.0",
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-http", "version": "1.0.0"}
    },
    "id": 1
}

try:
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(ENDPOINT, json=init_payload, headers=headers)
        print(f"   Status: {resp.status_code}")
        body = resp.text
        if len(body) > 300:
            print(f"   Body: {body[:300]}...")
        else:
            print(f"   Body: {body}")

        if resp.status_code == 200:
            print("   PASSED")
        else:
            print("   FAILED: Non-200 response")
except Exception as e:
    print(f"   FAILED: {e}")
    sys.exit(1)

# Test 4: List tools
print("")
print("4. Testing tools/list...")
list_payload = {
    "jsonrpc": "2.0",
    "method": "tools/list",
    "params": {},
    "id": 2
}

try:
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(ENDPOINT, json=list_payload, headers=headers)
        print(f"   Status: {resp.status_code}")
        body = resp.text
        if len(body) > 300:
            print(f"   Body: {body[:300]}...")
        else:
            print(f"   Body: {body}")

        if resp.status_code == 200:
            print("   PASSED")
except Exception as e:
    print(f"   FAILED: {e}")

print("")
print("=== Test Complete ===")
PYEOF

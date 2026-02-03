# Using the Neo4j MCP Server with Claude Desktop

This guide explains how to connect your deployed Neo4j MCP server (running on AWS Bedrock AgentCore) to Claude Desktop.

## Overview

The MCP server deployed on AgentCore uses **Cognito JWT authentication**. Claude Desktop's native "Connectors" feature only supports OAuth or authless servers directly. To bridge this gap, we use [mcp-remote](https://github.com/geelen/mcp-remote) to forward requests with custom authorization headers.

## Prerequisites

- Claude Desktop installed ([download](https://claude.ai/download))
- Node.js installed (for `npx`)
- The MCP server deployed via `./deploy.sh`
- Cognito credentials configured in `.env`

## Step 1: Get Your Stack Configuration

After deploying, retrieve your stack outputs:

```bash
aws cloudformation describe-stacks \
    --stack-name <STACK_NAME> \
    --region <AWS_REGION> \
    --query 'Stacks[0].Outputs'
```

You'll need:
- **CognitoUserPoolClientId** - The Cognito client ID for authentication
- **MCPServerRuntimeArn** - The ARN of your deployed MCP server

## Step 2: Build the MCP Endpoint URL

The MCP endpoint URL follows this format:

```
https://bedrock-agentcore.<AWS_REGION>.amazonaws.com/runtimes/<URL_ENCODED_ARN>/invocations?qualifier=DEFAULT
```

To URL-encode the ARN:
```bash
# Example: encode the runtime ARN
RUNTIME_ARN="arn:aws:bedrock-agentcore:<REGION>:<ACCOUNT_ID>:runtime/<RUNTIME_ID>"
ENCODED_ARN=$(echo "$RUNTIME_ARN" | sed 's/:/%3A/g' | sed 's/\//%2F/g')
echo "https://bedrock-agentcore.<REGION>.amazonaws.com/runtimes/${ENCODED_ARN}/invocations?qualifier=DEFAULT"
```

## Step 3: Get a JWT Token

Generate a JWT token using the provided script:

```bash
cd /path/to/neo4j-agentcore-mcp-server
source .venv/bin/activate
python3 get_token.py <COGNITO_CLIENT_ID> <USERNAME> <PASSWORD> <AWS_REGION>
```

Or source your `.env` and run:
```bash
source ../.env
./test.sh token
```

Copy the access token from the output.

## Step 4: Configure Claude Desktop

Edit the Claude Desktop configuration file:

| OS | Config File Location |
|----|---------------------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

Add the MCP server configuration:

```json
{
  "mcpServers": {
    "neo4j-mcp": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "<MCP_ENDPOINT_URL>",
        "--header",
        "Authorization:${AUTH_HEADER}"
      ],
      "env": {
        "AUTH_HEADER": "Bearer <YOUR_JWT_TOKEN>"
      }
    }
  }
}
```

### Configuration Placeholders

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `<MCP_ENDPOINT_URL>` | The full URL-encoded MCP endpoint | `https://bedrock-agentcore.us-west-2.amazonaws.com/runtimes/arn%3Aaws%3A.../invocations?qualifier=DEFAULT` |
| `<YOUR_JWT_TOKEN>` | The JWT token from Step 3 | `eyJhbGciOiJSUzI1NiIs...` |

### Windows Note

Due to a [known bug](https://github.com/geelen/mcp-remote#windows-workaround) in Cursor and Claude Desktop on Windows, avoid spaces in args. The configuration above uses `Authorization:${AUTH_HEADER}` (no space after colon) with the space included in the env var value.

## Step 5: Restart Claude Desktop

After saving the configuration, fully restart Claude Desktop:
1. Quit Claude Desktop completely
2. Reopen Claude Desktop
3. The MCP server should appear in your available tools

## Token Expiration

JWT tokens from Cognito expire (typically within 1 hour). When your token expires:

1. Generate a new token (Step 3)
2. Update `claude_desktop_config.json` with the new token
3. Restart Claude Desktop

### Automation Script (Optional)

Create a helper script to refresh your config:

```bash
#!/bin/bash
# refresh-claude-token.sh

# Load environment
source /path/to/.env

# Get new token
TOKEN=$(python3 /path/to/get_token.py \
    "$COGNITO_CLIENT_ID" \
    "$AGENT_USERNAME" \
    "$AGENT_PASSWORD" \
    "$AWS_REGION" 2>&1 | grep -A1 "Access Token:" | tail -n1 | tr -d '[:space:]')

# Update Claude Desktop config (macOS)
CONFIG_FILE="$HOME/Library/Application Support/Claude/claude_desktop_config.json"

# Use jq to update the token
jq --arg token "Bearer $TOKEN" \
   '.mcpServers["neo4j-mcp"].env.AUTH_HEADER = $token' \
   "$CONFIG_FILE" > "$CONFIG_FILE.tmp" && mv "$CONFIG_FILE.tmp" "$CONFIG_FILE"

echo "Token updated. Restart Claude Desktop to apply."
```

## Alternative: Native OAuth Support

For a more seamless experience without manual token management, consider setting up OAuth integration:

1. Configure Cognito with OAuth 2.0 authorization code flow
2. Set up API Gateway to handle OAuth metadata endpoints
3. Use Claude Desktop's native Connectors feature (Settings > Connectors)

See: [Building a Remote MCP Server with OAuth Authorization Using Amazon API Gateway and Cognito](https://dev.to/aws-builders/building-a-remote-mcp-server-with-oauth-authorization-using-amazon-api-gateway-and-cognito-19ab)

## Troubleshooting

### "Connection failed" or timeout errors
- Verify the MCP endpoint URL is correctly URL-encoded
- Check that the JWT token hasn't expired
- Ensure your network can reach `bedrock-agentcore.<region>.amazonaws.com`

### "Unauthorized" errors
- Regenerate the JWT token
- Verify the Cognito user has proper permissions
- Check that `USER_PASSWORD_AUTH` is enabled on the Cognito client

### MCP server not appearing in Claude Desktop
- Ensure `npx` is available in your PATH
- Check Claude Desktop logs for errors
- Verify the JSON syntax in your config file

### Testing the connection manually
```bash
# Test with the MCP client directly
./test.sh tools
```

## References

- [mcp-remote GitHub](https://github.com/geelen/mcp-remote) - Bridge for remote MCP servers
- [Claude Desktop MCP Documentation](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers) - Official Claude remote server docs
- [MCP Specification](https://modelcontextprotocol.io/) - Model Context Protocol documentation
- [AWS Cognito OAuth Guide](https://dev.to/aws-builders/building-a-remote-mcp-server-with-oauth-authorization-using-amazon-api-gateway-and-cognito-19ab) - Setting up OAuth with Cognito

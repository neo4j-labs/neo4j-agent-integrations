#!/bin/bash

set -e

# Ensure we run from the script's directory
cd "$(dirname "$0")"

PROFILE_FLAG=""
APP_NAME=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --profile)
      PROFILE_FLAG="--profile $2"
      shift 2
      ;;
    --app-name)
      APP_NAME="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

if [[ -z "$APP_NAME" ]]; then
  echo "❌ --app-name is required (must start with 'mcp-')"
  echo ""
  echo "Usage: ./deploy.sh --app-name mcp-neo4j [--profile <databricks-profile>]"
  exit 1
fi

if [[ "$APP_NAME" != mcp-* ]]; then
  echo "❌ App name must start with 'mcp-' for Databricks to treat it as an MCP server."
  exit 1
fi

auth=$(databricks current-user me $PROFILE_FLAG)
if [[ $auth != *'"active":true'* ]]; then
  echo "❌ Databricks CLI unauthenticated."
  echo ""
  echo "You must login first:"
  echo "databricks auth login --host https://<your-databricks-workspace>"
  echo ""
  exit 1
fi

echo "✅ Databricks CLI authenticated"
echo "Deploying app '$APP_NAME'..."

# Clean stale local bundle state to avoid Terraform conflicts
rm -rf .bundle/

# Generate databricks.yml with the app name baked in
cat > databricks.yml <<EOF
bundle:
  name: ${APP_NAME}

resources:
  apps:
    neo4j-mcp:
      name: ${APP_NAME}
      source_code_path: ./app
      resources:
        - name: 'neo4j-uri'
          secret:
            scope: 'neo4j-agent'
            key: 'neo4j-uri'
            permission: 'READ'
        - name: 'username'
          secret:
            scope: 'neo4j-agent'
            key: 'username'
            permission: 'READ'
        - name: 'password'
          secret:
            scope: 'neo4j-agent'
            key: 'password'
            permission: 'READ'
EOF

databricks bundle deploy $PROFILE_FLAG

echo "✅ App '$APP_NAME' deployed successfully"

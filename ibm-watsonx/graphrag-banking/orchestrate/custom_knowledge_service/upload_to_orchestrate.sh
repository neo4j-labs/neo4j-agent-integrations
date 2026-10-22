#!/usr/bin/env bash
# Upload the Neo4j knowledge source and its test agent to watsonx Orchestrate.
# Run from the graphrag-banking folder, after deploy_lambda.sh:
#   ./orchestrate/custom_knowledge_service/upload_to_orchestrate.sh
#
# It does three things, and is safe to run again:
#   1. Creates the neo4j_graph_search connection when the tenant has none. A
#      connection made in the dashboard is left alone.
#   2. Imports the neo4j_graph_knowledge knowledge base.
#   3. Imports the graph_knowledge_demo agent and deploys it, so it appears in
#      the Chat page.
#
# The service URL comes from KNOWLEDGE_SERVICE_URL, or from the Lambda function
# URL in the default AWS profile. The KNOWLEDGE_FILTER variable sets the
# business name the service screens on every search. It defaults to Ortega.
set -euo pipefail
cd "$(dirname "$0")/../.."

SERVICE_DIR=orchestrate/custom_knowledge_service
OUT=orchestrate/build/custom_knowledge_service
APP_ID=neo4j_graph_search

env_value() { sed -n "s/^$1=//p" .env | tr -d "'\"" | tail -n 1; }

URL=${KNOWLEDGE_SERVICE_URL:-$(env_value KNOWLEDGE_SERVICE_URL)}
if [ -z "$URL" ]; then
  URL=$(aws lambda get-function-url-config \
    --function-name "${FUNCTION_NAME:-neo4j-knowledge-service}" \
    --query FunctionUrl --output text)
fi
FILTER=${KNOWLEDGE_FILTER:-Ortega}

# Read the list into a variable first. With pipefail, grep -q closing the pipe
# early makes orchestrate fail, and the check would report a missing connection.
CONNECTIONS=$(orchestrate connections list 2>/dev/null)
if ! grep -q "\b$APP_ID\b" <<< "$CONNECTIONS"; then
  KEY=$(env_value KNOWLEDGE_SERVICE_API_KEY)
  [ -n "$KEY" ] || { echo "KNOWLEDGE_SERVICE_API_KEY is not in .env" >&2; exit 1; }
  orchestrate connections add --app-id "$APP_ID"
  for env in draft live; do
    orchestrate connections configure --app-id "$APP_ID" --environment "$env" \
      --kind api_key --type team --server-url "$URL"
    orchestrate connections set-credentials --app-id "$APP_ID" \
      --environment "$env" --api-key "$KEY"
  done
  echo "Created connection $APP_ID."
else
  echo "Connection $APP_ID already exists, leaving it as is."
fi

rm -rf "$OUT"
mkdir -p "$OUT"
sed -e "s|__URL__|$URL|" -e "s|__FILTER__|$FILTER|" \
  "$SERVICE_DIR/knowledge_base.yaml" > "$OUT/knowledge_base.yaml"

orchestrate knowledge-bases import -f "$OUT/knowledge_base.yaml"
orchestrate agents import -f "$SERVICE_DIR/demo_agent.yaml"
# An import makes a draft. The Chat page lists only deployed agents.
orchestrate agents deploy --name graph_knowledge_demo

echo "Imported neo4j_graph_knowledge and deployed graph_knowledge_demo."

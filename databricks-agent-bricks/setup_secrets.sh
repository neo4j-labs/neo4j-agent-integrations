#!/bin/bash

set -e

SCOPE="neo4j-agent"
PROFILE_FLAG=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --profile)
      PROFILE_FLAG="--profile $2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

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

# ---- load .env ----
if [ ! -f .env ]; then
  echo "❌ File .env not found. Please create one with the necessary environment variables."
  exit 1
fi

set -o allexport
source .env
set +o allexport

# ---- create scope ----
echo "Creating scope (if not exists)..."
databricks secrets create-scope $SCOPE $PROFILE_FLAG >/dev/null 2>&1 || echo "Scope already exists, skipping creation."

# ---- upload secrets ----
echo "Uploading secrets..."

databricks secrets put-secret $SCOPE neo4j-uri $PROFILE_FLAG \
  --string-value "$NEO4J_URI"

databricks secrets put-secret $SCOPE username $PROFILE_FLAG \
  --string-value "$NEO4J_USERNAME"

databricks secrets put-secret $SCOPE password $PROFILE_FLAG \
  --string-value "$NEO4J_PASSWORD"

databricks secrets put-secret $SCOPE database $PROFILE_FLAG \
  --string-value "$NEO4J_DATABASE"

echo "✅ Secrets uploaded successfully"

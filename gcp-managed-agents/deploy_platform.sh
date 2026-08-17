#!/bin/bash
set -euo pipefail

# ---- Load .env ----
if [ ! -f .env ]; then
  echo "[ERROR] Missing .env. Copy .env.example to .env and fill it in."
  exit 1
fi
export $(grep -v '^#' .env | grep -v '^$' | xargs)

# ---- Require everything ----
: "${GCP_PROJECT_ID:?}" ; : "${GCP_LOCATION:?}" ; : "${GCS_BUCKET_NAME:?}"
: "${MEMORY_BANK_ID:?}" ; : "${MEMORY_BANK_LOCATION:?}"
: "${MCP_SERVER_URL:?}" ; : "${MCP_USER:?}" ; : "${MCP_PASSWORD:?}"
: "${NEO4J_URI:?}" ; : "${NEO4J_USER:?}" ; : "${NEO4J_PASSWORD:?}" ; : "${NEO4J_DATABASE:?}"

export MCP_AUTH_BASE64=$(printf '%s:%s' "$MCP_USER" "$MCP_PASSWORD" | base64 | tr -d '\n')
export BASE_URL="https://aiplatform.googleapis.com/v1beta1/projects/${GCP_PROJECT_ID}/locations/${GCP_LOCATION}"

# ---- Render skill scripts into .build/  ----
echo "== Rendering skill scripts =="
rm -rf .build && mkdir -p .build/skills
cp -r skills/* .build/skills/

# memory client
sed -i \
  -e "s|__PROJECT_ID__|${GCP_PROJECT_ID}|g" \
  -e "s|__MEMORY_BANK_ID__|${MEMORY_BANK_ID}|g" \
  -e "s|__MEMORY_BANK_LOCATION__|${MEMORY_BANK_LOCATION}|g" \
  .build/skills/gcp_memory_bank/gcp_vertex_client.py

# investment skill
sed -i \
  -e "s|__NEO4J_URI__|${NEO4J_URI}|g" \
  -e "s|__NEO4J_USER__|${NEO4J_USER}|g" \
  -e "s|__NEO4J_PASSWORD__|${NEO4J_PASSWORD}|g" \
  -e "s|__NEO4J_DATABASE__|${NEO4J_DATABASE}|g" \
  .build/skills/custom_investments/main.py

if grep -rq "__[A-Z_]*__" .build/skills; then
  echo "[ERROR] Unrendered placeholder remains:"; grep -rn "__[A-Z_]*__" .build/skills; exit 1
fi

# ---- Sync to GCS ----
echo "== Syncing skills to ${GCS_BUCKET_NAME} =="
gcloud storage cp -r .build/skills/custom_investments "${GCS_BUCKET_NAME}/skills/"
gcloud storage cp -r .build/skills/gcp_memory_bank     "${GCS_BUCKET_NAME}/skills/"

# ---- Render + post agent config ----
echo "== Deploying managed agent =="
CURL_DATA=$(eval "echo \"$(sed 's/\"/\\\"/g' config/agent_config.json)\"")

RESP=$(curl -s -X POST "${BASE_URL}/agents" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -d "${CURL_DATA}")

echo "Raw API response:"; echo "${RESP}"
if echo "${RESP}" | grep -q '"error"'; then
  echo "[ERROR] Deploy failed."; exit 1
fi
echo "✓ Deploy submitted."
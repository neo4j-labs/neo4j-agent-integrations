#!/bin/bash
set -e

# Load local environment configuration if available
if [ -f .env ]; then
    echo "Loading active integration parameters out of local workspace .env file..."
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "[ERROR] Missing required .env file template inside work directory root path."
    exit 1
fi

export BASE_URL="https://aiplatform.googleapis.com/v1beta1/projects/${GCP_PROJECT_ID}/locations/${GCP_LOCATION}"
export AUTH_HEADER="Authorization: Bearer $(gcloud auth print-access-token)"

echo "============= [1/2] Syncing Skills Matrix Assets to Storage ============="
# Syncing the explicit singular directory path structure
gcloud storage cp -r skills/custom_investment "${GCS_BUCKET_NAME}/skills/"

echo -e "\n✓ Skill code assets successfully synced to target cloud storage bucket."
echo "------------------------------------------------------------------"

echo "============= [2/2] Launching Managed Workspace Sandbox ============="

# Dynamically calculate the Base64 auth string on the fly from environment parameters
export MCP_AUTH_BASE64=$(echo -n "${MCP_USER}:${MCP_PASSWORD}" | base64)

# Render environment metrics directly into the template blueprint
CURL_DATA=$(eval "echo \"$(cat config/agent_config.json | sed 's/"/\\"/g')\"")

OPERATION_RESPONSE=$(curl -s -X POST "${BASE_URL}/agents" \
  -H "Content-Type: application/json" \
  -H "${AUTH_HEADER}" \
  -d "${CURL_DATA}")

OPERATION_PATH=$(echo $OPERATION_RESPONSE | grep -o '"name": "[^"]*' | grep -o 'projects/.*' || echo "Conflict or configuration error observed.")

echo -e "\nManaged Agent Deployment Successfully Activated."
echo "Asynchronous Operation Tracking Path:"
echo "--> ${OPERATION_PATH}"
echo "========================================================================"
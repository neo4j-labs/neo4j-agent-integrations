# Google Gemini Enterprise + Neo4j A2A Integration

## Overview

Here we are showcasing neo4j mcp integration with ADK agent that is Agent-to-Agent (A2A) complaint and connect with Google Gemini Enterprise.

This architecture utilizes the Google ADK and the official Neo4j Model Context Protocol (MCP) server deployed on Google Cloud Run. 
It features a custom Starlette/FastAPI middleware layer to securely validate end-user OAuth 2.0 Access Tokens directly against Google's identity servers.

## Key Features

- **Native Graph Querying**: Uses the official Neo4j MCP binary to autonomously explore graph schemas and execute Cypher queries.
- **Custom Python Tools**: Extends MCP capabilities with specialized, hardcoded business logic (e.g., `get_investments`).
- **Secure Token Validation**: Intercepts and validates Gemini Enterprise OAuth 2.0 access tokens in real-time.

## Architecture Flow

1.  **Discovery**: Gemini Enterprise sends an unauthenticated `GET /` request. The service returns the AgentCard (manifest) detailing the agent's skills and confirming it requires authentication.
2.  **Authentication**: Gemini prompts the user to log in via Google OAuth 2.0.
3.  **Execution**: Gemini sends a `POST /` request containing the user's prompt and the `Authorization: Bearer <TOKEN>` header.
4.  **Validation**: The custom Python middleware intercepts the request, calls Google's `tokeninfo` endpoint to verify the token, and either rejects it (401) or passes it to the executor.
5.  **Reasoning**: The Google ADK `LlmAgent` determines whether to use the Neo4j MCP schema tools or the custom investment tools to formulate a response.

## Prerequisites

Before deploying, ensure you have the following:

-   Google Cloud Project with billing enabled.
-   Google Cloud CLI (`gcloud`) installed and authenticated.
-   Neo4j Database (AuraDB or self-hosted) with credentials.
-   Google Cloud APIs Enabled:
    -   Cloud Run API (`run.googleapis.com`)
    -   Secret Manager API (`secretmanager.googleapis.com`)

## Step 1: Secure Configuration (Secret Manager)

Do not store credentials in `.env` files for production. We use Google Cloud Secret Manager.

1.  Create the secrets:

    ```bash
    echo -n "your-neo4j-password" | gcloud secrets create NEO4J_PASSWORD --data-file=-
    echo -n "your-google-api-key" | gcloud secrets create GOOGLE_API_KEY --data-file=-
    echo -n "your-neo4j-uri" | gcloud secrets create NEO4J_URI --data-file=-
    echo -n "neo4j" | gcloud secrets create NEO4J_USERNAME --data-file=-
    echo -n "neo4j" | gcloud secrets create NEO4J_DATABASE --data-file=-
    echo -n "https://your-expected-cloud-run-url" | gcloud secrets create SERVICE_URL --data-file=-
    ```

2.  Grant Cloud Run access to read the secrets:

    ```bash
    # Grants the Secret Accessor role to the default Compute Engine service account
    export PROJECT_ID=$(gcloud config get-value project)
    export PROJECT_NUM=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

    gcloud projects add-iam-policy-binding $PROJECT_ID 
      --member="serviceAccount:${PROJECT_NUM}-compute@developer.gserviceaccount.com" 
      --role="roles/secretmanager.secretAccessor"
    ```

## Step 2: Deployment

Deploy the container to Cloud Run. We must use `--allow-unauthenticated` so the service can be reached publicly, relying entirely on our Python middleware for authorization.

```bash
gcloud run deploy neo4j-a2a-service 
  --source . 
  --region us-central1 
  --allow-unauthenticated 
  --set-secrets="NEO4J_URI=NEO4J_URI:latest,NEO4J_USERNAME=NEO4J_USERNAME:latest,NEO4J_PASSWORD=NEO4J_PASSWORD:latest,NEO4J_DATABASE=NEO4J_DATABASE:latest,GOOGLE_API_KEY=GOOGLE_API_KEY:latest,SERVICE_URL=SERVICE_URL:latest"
```

## Step 3: Gemini Enterprise Configuration

Register the deployed agent in the Gemini Enterprise portal.

1.  Navigate to the add agent configuration in Gemini Enterprise.
2.  Provide the agent card , can be retrieved from (e.g., `https://neo4j-a2a-service-xxxx-uc.a.run.app/.well-known/agent.card`).
3.  Set the Authentication type to **OAuth 2.0**.
4.  Fill in the OAuth details using your GCP Credentials (APIs & Services -> Credentials -> OAuth 2.0 Client IDs):
    -   **Client ID**: `your-client-id.apps.googleusercontent.com`
    -   **Client Secret**: `your-client-secret`
    -   **Authorization URL**: `https://accounts.google.com/o/oauth2/v2/auth`
    -   **Token URL**: `https://oauth2.googleapis.com/token`
    -   **Scope**: `openid https://www.googleapis.com/auth/cloud-platform`

## Gemini Enterprise UI.
-  Ask question in gemini enterprise chatbot UI related to your database or as per your custom tool definition.
- Login via oauth when prompted.
- GE responds with answer from adk agent using mcp tool/custom tools.

## Referral Documentation
Neo4j
• [Neo4j & MCP](http://neo4j.com/docs/mcp/current/)

ADK agent
• [Agent Development Kit](https://docs.cloud.google.com/agent-builder/agent-development-kit/overview)

A2A Protocol 
• [A2A Protocol](https://a2a-protocol.org/latest/)

Gemini Enterprise & Agents
• [Gemini for Google Workspace / Enterprise](https://cloud.google.com/gemini/enterprise)
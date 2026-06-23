# Neo4j & Vertex AI Managed Agent Platform

This repository provides a declarative, infrastructure-led blueprint for deploying a secure, serverless graph database analyst using the Vertex AI Managed Agent platform (Antigravity engine) connected to an enterprise Neo4j Graph Database.

---

## 1. Architecture & System Flow

The platform decouples application logic from security boundaries, enforcing content safety at the ingress perimeter and network control at the egress perimeter.

![Vertex AI Managed Agent + Neo4j MCP Integration](architecture_managed_agent.png)

* **Ingress Protection (Model Armor):** Intercepts user queries at the project front door. Malicious inputs or prompt injections are identified and blocked before any container resources are provisioned.
* **Isolated Execution (Managed Agent Sandbox):** Valid queries spin up an on-demand container sandbox. The sandbox loads connection strings from environment variables and mounts custom Python modules directly from the central Skill Registry.
* **Egress Control (Agent Gateway):** Outbound network calls are screened against a strict destination allowlist. General graph operations route over HTTPS (Port 443) to an external Cloud Run Model Context Protocol (MCP) server, while custom portfolio lookups run locally inside the container filesystem. Both tracks securely target the destination Neo4j instance.

---

## 2. Project Directory Structure

```text
.
├── example.env                   # Environment variables configuration template
├── deploy_platform.sh            # Automated deployment and skills registration script
├── test_agent.py                 # CLI Python verification client to stream test queries
├── config/
│   ├── agent_config.json         # Declarative agent configuration blueprint
│   ├── gateway_config.json       # Agent Egress Gateway reference template
│   └── model_armor_policy.json   # Model Armor content security reference template
├── skills/
│   └── custom-investments/
│       ├── main.py               # Container-native Python tool logic
│       └── SKILL.md              # Skill Registry manifest and package dependencies
└── adk_proxy_ui/                 # Local developer web UI proxy interface
    ├── requirements.txt          # Frontend proxy package dependencies
    ├── __init__.py               # Package initialization file for ADK module loader
    └── agent.py                  # Local pass-through proxy agent logic
```

---

## 3. Pre-Deployment Cloud Console Setup

The following cloud resources must be configured manually within the Google Cloud Console before running the automation pipeline:

### Step 1: Model Armor Policy
1. Navigate to **Model Armor** in the GCP Console.
2. Create a template named `neo4j-agent-armor` in region `us-central1`.
3. Enable **Prompt Injection & Jailbreak Filters** (Confidence threshold: `Medium and Above`) and turn on basic **Sensitive Data Protection (SDP)** filters.

### Step 2: Agent Egress Gateway
1. Navigate to **Gemini Enterprise Agent Platform** > **Govern** > **Agent Gateways**.
2. Create a gateway named `neo4j-egress-gateway` in region `us-central1`.
3. Set **Routing Mode** to `Agent-to-Anywhere (egress)` and **Enforcement Mode** to `AUDIT`.
4. Bind the `neo4j-agent-armor` policy template directly to this gateway instance.

### Step 3: Cloud IAM Storage Permissions
Ensure the sandbox runtime can fetch code assets. Grant the **Storage Object Viewer** (`roles/storage.objectViewer`) role on your staging storage bucket (e.g., `gs://neo4j-gateway-agent-code-bucket`) to the core Vertex AI Service Agent principal identity.

---

## 4. Backend Deployment & Verification

### Step 1: Configure Environment Variables
Copy the template configuration file to a local active `.env` file and fill out your live project coordinates, bucket destinations, and Neo4j connection keys:

```bash
cp example.env .env
```

### Step 2: Run the Automated Deployment Script
Execute the deployment script to upload local skill modules to Cloud Storage, register the workspace manifests, compute basic authentication hashes on the fly, and build the persistent Managed Agent configuration via the Vertex API:

```bash
./deploy_platform.sh
```

### Step 3: Run the CLI Verification Client
Execute the test script to open a live streaming interaction with the deployed cloud architecture using the official `google-genai` SDK:

```bash
pip install google-genai
python3 test_agent.py "How many Organization nodes are currently in the graph?"
```

---

## 5. Visual Developer Interface (ADK Proxy Setup)

The backend Managed Agent runs completely serverless in the cloud and exposes an API endpoint without a native graphic UI. To showcase its performance inside a visual chat interface without writing a custom web frontend, you can deploy the optional local ADK Proxy UI.

### How it Works
The Google Agent Development Kit framework includes a visual workspace canvas (`adk web`). We initialize a local `root_agent` using `gemini-3.5-flash` to host this UI layout. When a message is entered into the browser chat bubble, the local agent catches the text and forwards it to the `query_managed_agent` function. This function initializes the enterprise SDK client, executes the query directly against your secure, cloud-hosted Managed Agent, and returns the live cloud response tokens directly back to the UI interface.

### Running the UI

1. Install the required client-side interface packages:
   ```bash
   pip install -r adk_proxy_ui/requirements.txt
   ```

2. Navigate to your parent project directory context and start up the local developer server plane:
   ```bash
   adk web --port 8085
   ```

3. Open your browser and navigate to `http://localhost:8085` to interact with your secure cloud platform integration visually.

---

## 6. Official References & Documentation

For deeper configuration details regarding the underlying frameworks used in this deployment, refer to the official documentation channels:

* **Vertex AI Managed Agents & Sandboxes:** [Google Cloud Vertex AI Agent Platform Documentation](https://cloud.google.com/vertex-ai/docs/agents/overview)
* **Model Context Protocol (MCP):** [Official MCP Specification and Core Ecosystem](https://modelcontextprotocol.io/)
* **Google Agent Development Kit (ADK):** [Google ADK Session & Memory Management Reference](https://adk.dev/sessions/memory/)
* **Google GenAI Python SDK:** [Official `google-genai` GitHub Repository & SDK Guide](https://github.com/googleapis/python-genai)
* **Neo4j Python Integration:** [Neo4j Graph Database Driver Manual for Python Developers](https://neo4j.com/docs/python-manual/current/)

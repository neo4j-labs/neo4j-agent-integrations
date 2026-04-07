# Neo4j Agent Integrations for Google Gemini Enterprise

This repository contains a suite of reference implementations for connecting **Neo4j Graph Databases** to **Google Gemini Enterprise**. 

Using the **Agent-to-Agent (A2A) protocol** and the **Google Agent Development Kit (ADK)**, these patterns allow organizations to move beyond simple RAG and into high-reasoning GraphRAG workflows.

---

## 📂 Repository Structure

Choose the architecture that best fits your deployment needs:

### 1. [a2a-mcp-wrapper](./1-a2a-mcp-wrapper)

**Focus:** Modularity and Official Tooling.
**How it works:** This version wraps the **Official Neo4j Model Context Protocol (MCP)** server. It uses a decoupled architecture where the reasoning agent and the database tool service scale independently on Cloud Run.
**Best for:** Developers who want to leverage the standard MCP ecosystem and prefer a clean separation between the LLM planner and the database driver.


### 2. [a2a-direct-service](./2-a2a-direct-service)

**Focus:** Internal Multi-Tenancy and Simplicity.
**How it works:** A streamlined version of our agent that uses **Native Google Workspace Authentication**. It features a `/setup` portal where users can map their own Neo4j credentials to their Google email address.
**Best for:** Internal enterprise tools where different teams need to access their specific graphs using their existing corporate Google identities.


### 3. [a2a-ge-marketplace](./3-a2a-ge-marketplace)

**Focus:** Agent-as-a-Service (AaaS) & Commercialization.
**How it works:** The full-featured **Google Cloud Marketplace** implementation. Includes automated onboarding via Pub/Sub, Dynamic Client Registration (DCR), custom OAuth 2.0 flows, and automated token-based billing.
**Best for:** Partners and SaaS providers looking to publish a "Paid" or "Freemium" agent directly on the Google Cloud Marketplace.


---

## ⚖️ Comparison at a Glance

| Feature | MCP Wrapper | Direct Service | Marketplace (AaaS) |
| :--- | :--- | :--- | :--- |
| **Multi-Tenancy** | Optional | Email-Based | Entitlement-Based |
| **Authentication** | Google OAuth | Google OAuth | Custom OAuth + DCR |
| **Provisioning** | Manual | Self-Service (/setup) | Automated (Pub/Sub) |
| **Billing** | N/A | Usage Tracking | GCP Marketplace Lifecycle |
| **Architecture** | Decoupled (Agent + MCP) | Monolithic (All-in-one) | Monolithic (All-in-one) |

---

## 🛠️ Common Prerequisites

Regardless of the version you choose, you will generally need:

**Google Cloud Project** with Vertex AI and Cloud Run APIs enabled.
**Secret Manager** to handle your Neo4j credentials and internal keys.
**A Neo4j Instance** (AuraDB, Self-Hosted, or Docker).
**OAuth 2.0 Client IDs** configured in the Google Cloud Console.


---

## 📚 Key Resources


[Agent Development Kit (ADK)](https://docs.cloud.google.com/agent-builder/agent-development-kit/overview)
[A2A Protocol Specification](https://a2a-protocol.org/latest/)
[Neo4j & Model Context Protocol (MCP)](https://neo4j.com/docs/mcp/current/)
[Gemini for Google Workspace](https://cloud.google.com/gemini/enterprise)


---
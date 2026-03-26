# Salesforce Agentforce + Neo4j Integration

## Overview

**Salesforce Agentforce** is Salesforce's enterprise AI agent platform powered by the **Atlas Reasoning Engine (ARE)** — a ReAct-style orchestration loop that plans, selects tools, observes results, and iterates to answer user queries.

**Key Features:**
- Atlas Reasoning Engine (plan → act → observe → decide loop)
- Topics (semantic routing layer) + Actions (tool execution layer)
- Native MCP client (Pilot July 2025, Beta features October 2025)
- External Service Actions — import any OpenAPI 3.0 spec as agent tools
- Apex Actions — full Java-like server-side code for complex integrations
- BYOM (Bring Your Own Model) — connect Claude, GPT-4, Gemini via your accounts
- Einstein Trust Layer — PII masking, zero data retention with LLM providers
- Agent API — invoke agents from external Python/Java/REST clients

**Official Resources:**
- Website: https://www.salesforce.com/agentforce/
- MCP Support: https://www.salesforce.com/agentforce/mcp-support/
- Developer Docs: https://developer.salesforce.com/docs/einstein/genai/guide/get-started-agents.html
- Agent API: https://developer.salesforce.com/docs/ai/agentforce/guide/agent-api.html

---

## Extension Points

This section outlines the primary methods to extend Salesforce Agentforce capabilities with Neo4j. The architecture diagram below serves as a foundational blueprint, illustrating the standard request flow from the user to the database, which you can customize using any of the three integration tracks.

### Architecture

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                         Salesforce Agentforce                           │
│                                                                         │
│ 1. User: "Provide me insights about the company Microsoft"              │
│ 2. Agent captures "Microsoft" and triggers Prompt Template action       │
│                                │                                        │
│                       ┌────────▼────────┐                               │
│                       │ Prompt Template │                               │
│                       └────────┬────────┘                               │
│                                │ 3. Describes intent & response format  │
│                                │ 4. Invokes Flow                        │
│                       ┌────────▼────────┐                               │
│                       │ Salesforce Flow │                               │
│                       └────────┬────────┘                               │
│                                │ 5. Calls Apex class                    │
│                       ┌────────▼────────┐                               │
│                       │   Salesforce    │                               │
│                       │    Bindings     │                               │
│                       └────────┬────────┘                               │
└────────────────────────────────┼────────────────────────────────────────┘
                                 │ HTTPS (Named Credential)
                                 ▼
                     ┌──────────────────────┐
                     │. Neo4j MCP Server    │                      
                     │. Neo4j HTTP QueryAPI │
                     │. Remote API bridge   │
                     └───────────┬──────────┘
                                 │
                                 ▼
                      ┌────────────────────┐
                      │   Neo4j Database   │
                      └────────────────────┘
```

**Design Considerations:**

1. **The agent has to be instruction light** and delegate additional work to other elements (like Prompt Templates)
2. **Why use Prompt Templates?**
   - **Grounding and Formatting:** A Prompt Template effectively grounds the LLM. Rather than letting the agent arbitrarily decide how to present the raw data coming from Neo4j, the template explicitly defines the intent, structure (e.g., bullet points, summaries), persona, and tone of the final response.
   - **Reduced Hallucinations:** By firmly constraining the instructions on how to interpret the retrieved data, it minimizes the risk of the model hallucinating or omitting critical data points.
   - **Declarative Control:** Admins can iterate on the LLM's prompt and output formatting dynamically without touching any code.

3. **Why use Salesforce Flow to wrap Apex?**
   - **Orchestration and Decoupling:** Flow acts as a declarative orchestration layer. It decouples the business logic (the Apex callout to Neo4j) from the agent's prompt presentation logic.
   - **Data Enrichment:** Before returning the data to the Prompt Template, a Flow can seamlessly combine the Neo4j Graph responses with local Salesforce CRM data (e.g., fetching Account records, past Opportunities), providing a unified context to the LLM.
   - **Flexibility and Reusability:** If error handling, routing, or additional logic needs to change, Salesforce admins can update the Flow without requiring a developer to modify and deploy new Apex code.

Three integration tracks — implementations of "Salesforce Bindings":
 - Native MCP Client
 - External Service Actions
 - Apex Actions

### Track A: Native MCP Client 

**⚠️ THIS SECTION IS A WORK IN PROGRESS**

Agentforce now includes a native MCP (Model Context Protocol) client. Register any MCP server — including Neo4j's — and it becomes available as an agent tool with no custom code.

⚠️ Custom MCP server support in Salesforce is currently in beta and not available for general use (Pilot July 2025, Beta October 2025, GA April 2026).

### Track B: External Service Actions  

Deploy a custom REST adapter and import its OpenAPI spec into Salesforce External Services. Zero Apex code — fully declarative. The REST adapter serves as a bridge between Salesforce and Neo4j's Query API, allowing you to execute Cypher statements against a Neo4j server through HTTP requests.

We provide a sample bridge server based on `nodejs` and `itty-router`, which exposes a relevant `openapi.json` schema endpoint for Salesforce to discover. The server can be easily deployed to platforms like [Cloudflare Workers](https://workers.dev).

Once the bridge is set up, the required Salesforce configuration involves importing the service to Salesforce External Services (`Setup → Integrations → External Services → New`). The newly created action is then available to be referenced in tools like Salesforce Flow.


### Track C: Apex Actions

Write Apex classes with `@InvocableMethod` annotations. These become agent actions with full access to Salesforce platform features (CRM records, flows, etc.).

```apex
@InvocableMethod(
    label='Get Neo4j Organization Insights' 
    description='Queries Neo4j for strategic insights about an organization, including competitors, suppliers, and geographic presence.')
    public static List<Response> getInsights(List<Request> requests) {
    }
```

The complete, deployable, and tested Apex code is in the `examples/apex` folder. Once the Apex classes are deployed, the code is available to be referenced as an action in Salesforce Flow.

### Advanced UI and Graph Visualization (LWC)

Beyond feeding Neo4j data into an LLM, you can use **Lightning Web Components (LWC)** to visualize graph data directly within the Salesforce UI. By reusing the same Apex classes (using the `@AuraEnabled` annotation alongside `@InvocableMethod`), you can fetch graph data and render it using a JavaScript visualization library (like D3.js, vis.js, or Cytoscape).

**Use Cases:**
1. **Rich Agentforce Responses:** Return an interactive LWC inside the Agentforce chat window instead of a plain text summary.
2. **Standalone Record Pages:** Embed a Neo4j Knowledge Graph widget directly onto a standard Salesforce Account or Contact record page to show localized connections.

Once appropriate Apex method is annotated with `@AuraEnabled(cacheable=true)`, resolving the method from an LWC can work as follows:

```
// Imperatively fetch fresh data from Neo4j through your Apex service
const rawData = await getInsights([{ recordId: this.recordId }]);
this.processNeo4jData(rawData);
 ```

A starter implementation of a Neo4j Graph Widget can be found in the `examples/lwc/neo4jGraphWidget` directory.

### Code Examples

See the `examples/` directory:

| File | Description |
| --- | --- |
| `examples/track-c/agent.yaml` | YAML script defining the agent |
| `examples/apex/*` | Apex files with tests |
| `examples/track-b/neo4j-bridge/index.ts` | A sample Neo4j bridge server |

---

## Salesforce Configuration

The following steps provide the foundational setup required for all tracks to connect to external services.

**1. External Credentials — Setup → Security → External Credentials → New**

Create custom external credentials for Neo4j authentication:
```
Label: `demo_companies_neo4jlabs_auth` (or descriptive name)
Name: `demo_companies_neo4jlabs_auth`
Principal: Named Principal
Authentication Protocol: Basic Authentication

Create a Principal with parameters:
  - Parameter Name: "username" → Value: "companies"
  - Parameter Name: "password" → Value: "companies"
```

**Important notes:**
- External Credentials allow Named Credentials to manage authentication securely without hardcoding credentials
- The "Generate Authorization Header" option should be enabled or handled via Custom Headers
- For HTTP transport with legacy setups, ensure the custom headers are properly configured

**2. Named Credentials — Setup → Security → Named Credentials → New**

Create a Named Credential that references the External Credential:
```
Name: demo_companies_neo4jlabs_url (must match ENDPOINT constant in your Apex code)
URL: https://demo.neo4jlabs.com:7473
External Credential: demo_companies_neo4jlabs_auth (from Step 1)
Allow Merge Fields in HTTP Body: ☑ (enables dynamic Cypher parameters)
Allowed Namespaces for Callouts: Ensure your namespace (or 'None') is allowed
```

**Key considerations:**
- The Named Credential name must match the `callout:` prefix in your Apex code (e.g., `callout:demo_companies_neo4jlabs_url`)
- This centralizes authentication — update credentials here without modifying Apex code
- Authorization headers are automatically managed by the Named Credential

**3. Remote Site Settings — Setup → Security → Remote Site Settings**

Although Named Credentials bypass Remote Site Settings for the specific URL:
```
Remote Site Name: Neo4j Demo Companies
Remote Site URL: https://demo.neo4jlabs.com:7473
☑ Disable Protocol Security (if using non-HTTPS in dev environments only)
```

**When to add:**
- If not using Named Credentials for other integrations
- If other Salesforce features need direct access to this endpoint
- To ensure org-wide connectivity for this server

**4. Permissions — Setup → Users/Profiles/Permission Sets**

Grant users access to the Neo4j integration:
```
Permission Set: Create or select existing
Enable Permissions:
  → External Credential Principal Access: 
    [Select] demo_companies_neo4jlabs_auth
  → Execute Named Credential: 
    [Select] demo_companies_neo4jlabs_url
  → (If using Apex) Execute Apex Classes: 
    [Select] Neo4jService, Neo4jAction
```

**Monitoring and Troubleshooting:**
```
Setup → AgentForce → Agents → [Your Agent] → Debug Logs
# View ARE reasoning traces and action execution logs

Setup → Security → Named Credentials → [Your NC] → Test Connection
# Verify authentication is working

Setup → Integrations → External Services → [Your ES] → Test Operations
# Test individual API calls
```

### Problems and Limitations

As of March 2026, there are networking limitations between AuraDB (Neo4j's Cloud Offering) and Salesforce. HTTP calls initiated directly from Salesforce (via Apex code) are blocked and result in a `400 Bad Request` response. An intermediary workaround is to place a proxy between them (for example, using [Cloudflare Workers](https://workers.dev)). This allows the Apex `HttpRequest` to succeed.

```
export default {
    async fetch(request, env) {
        // my Aura instance
        const neo4jUrl = "https://xxxxxxx.databases.neo4j.io/db/xxxxx/query/v2";

        // Clone the request but strip all Salesforce headers
        const newRequest = new Request(neo4jUrl, {
            method: request.method,
            body: await request.arrayBuffer(),
            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json",

                // Pass through your Authorization header from SF
                "Authorization": request.headers.get("Authorization"),
                "User-Agent": "curl/7.68.0" // Mimic curl
            }
        });

     return fetch(newRequest);
    }
};
```


---

## Get company insights — Implementation

### Scenario

The **Industry Research Agent** queries the Neo4j Company News Knowledge Graph (250k entities) to provide:
1. Company profiles (industry, location, leadership)
2. Semantic news search (vector similarity over article embeddings)
3. Organizational relationship mapping
4. Competitors, suppliers and subsidiaries

### Dataset

**Company News Knowledge Graph (Demo Access):**
```python
NEO4J_URI      = "neo4j+s://demo.neo4jlabs.com:7687"
NEO4J_USERNAME = "companies"
NEO4J_PASSWORD = "companies"
NEO4J_DATABASE = "companies"
```

**Data Model:**
```
(:Organization)-[:HAS_CEO]->(:Person)
(:Organization)-[:HAS_COMPETITOR|HAS_SUPPLIER|HAS_SUBSIDIARY]->(:Person)
(:Article)-[:MENTIONS]->(:Organization)
```

**Cypher query**
```cypher
MATCH (org:Organization {name: "Neo4j"})
OPTIONAL MATCH (org)-[:HAS_CEO]->(ceo:Person)

// 1. Get Network (Competitors, Suppliers, Subsidiaries) with their CEOs as complete nodes
WITH org, ceo,
     [(org)-[:HAS_COMPETITOR]-(comp) | {organization: comp, ceo: [(comp)-[:HAS_CEO]->(c) | c][0]}] AS competitors,
     [(org)-[:HAS_SUPPLIER]->(supp) | {organization: supp, ceo: [(supp)-[:HAS_CEO]->(c) | c][0]}] AS suppliers,
     [(org)-[:HAS_SUBSIDIARY]->(sub) | {organization: sub, ceo: [(sub)-[:HAS_CEO]->(c) | c][0]}] AS subsidiaries

// 2. Fetch exactly 10 articles mentioning any entity in the network
CALL (org, competitors, suppliers, subsidiaries) {
    WITH [c IN competitors | c.organization] + 
         [s IN suppliers | s.organization] + 
         [sub IN subsidiaries | sub.organization] + 
         [org] AS targets
    UNWIND targets AS target
    WITH DISTINCT target WHERE target IS NOT NULL
    MATCH (article:Article)-[:MENTIONS]->(target)
    RETURN DISTINCT article
    LIMIT 10
}

// 3. Return everything as complete nodes
RETURN 
    org, 
    ceo, 
    competitors, 
    suppliers, 
    subsidiaries, 
    collect(article) AS related_articles
```

---

## Resources

- **AgentForce Developer Docs**: https://developer.salesforce.com/docs/einstein/genai/guide/get-started-agents.html
- **Agent API Reference**: https://developer.salesforce.com/docs/ai/agentforce/guide/agent-api.html
- **External Service Actions**: https://developer.salesforce.com/blogs/2025/05/call-third-party-apis-from-an-agent-with-external-service-actions
- **MCP Support**: https://developer.salesforce.com/blogs/2025/06/introducing-mcp-support-across-salesforce
- **Python SDK (PyPI)**: https://pypi.org/project/salesforce-agentforce/
- **Neo4j MCP Official**: https://github.com/neo4j/mcp
- **Neo4j MCP Labs**: https://github.com/neo4j-contrib/mcp-neo4j
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)
- **BYOM Guide**: https://developer.salesforce.com/blogs/2024/10/build-generative-ai-solutions-with-llm-open-connector


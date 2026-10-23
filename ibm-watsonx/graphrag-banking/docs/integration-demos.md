# Integration demos: what we tried

The goal is to show the Neo4j integration inside the watsonx Orchestrate dashboard, with no second browser window and without relying on agents alone. This page records what was checked on October 21, 2026, what was ruled out, and what is still open. The setup steps for the flow are in [integrations.md](integrations.md).

## Constraints

- The demo must run inside the dashboard. A Neo4j Browser, Bloom, or Aura window in another tab does not count.
- The demo must show the graph database at work. A page of plain text documents does not.
- The existing agents already show Neo4j through Chat. The question is what else the dashboard can show.

## What the dashboard has

These are the pages seen on the tenant at `dl.watson-orchestrate.ibm.com`. The tenant is a trial with 17 days left.

| Area | What it holds |
|---|---|
| Home | Dashboard with usage, adoption, quality, and reliability tabs. It reports 4 agents, all native. |
| Chat | Chat with a selected agent. |
| Catalog | Four tabs: Agents (354), MCP Servers (30), Tools (1,141), and Skills (0). |
| Active inventory | Agents, Assistants, Agentic workflows, Tools, Knowledge, and Voice configurations. |
| Agentops | Optimization and Observability. |
| Govern and operate | Controls, Agent identity, Connections, and Credentials. |
| AI Gateway | Overview, Models, MCP servers, Agent directory, Discover agents, and Platforms. |

The Build agents and tools page lists 17 agents, 17 tools, and 1 knowledge base. The Home page counts 4 agents. The gap was not investigated.

## Tried and ruled out

### Knowledge base next to the graph

**Result:** Ruled out as a graph demo.

Active inventory > Knowledge holds one entry, `banking_policies`. It contains the bank's fee, hold, overdraft, wire, and compliance policies as text documents. It is used by 2 agents. It is a vector search over text, so it shows the baseline and not the graph.

The dashboard has no graph view. A side-by-side with the graph needs a second window, which breaks the constraint. The only in-dashboard side-by-side is the same question asked to `banking_baseline` and to a graph-backed agent in Chat. That is an agent demo.

### The `fraud_referral` flow

**Result:** Ruled out as the lead demo. Kept as a closing step.

The flow calls two tools, `create_fraud_referral` and `resolve_fraud_referral`. It does not call agents. The tools write one `FraudReferral` node, link it to the banker, application, reviewer, connected group, and cited rules, then set its status. The multi-hop detection happens earlier, in the fraud investigator's tools. The flow adds no graph reasoning.

Other findings:

- Active inventory > Agentic workflows shows 0 workflows. The flow is in the repo but is not imported into this tenant.
- `build_referral_tools.sh` stops until `FRAUD_REVIEWER_EMAIL` is exported in the shell. It does not read `.env`.
- `bank_supervisor` does not list the flow as a tool, so Chat cannot start it.
- No button to run a flow on its own was seen. The known way to run it is through an agent. This has not been tested.
- The flow builder is for deterministic processes with forms, branches, and approvals. It shows Orchestrate's workflow features more than it shows Neo4j.

## Open options

None of these has been built or tested.

| Option | What it would show | What is unknown |
|---|---|---|
| Knowledge > Create knowledge > Custom service | A Neo4j-backed retrieval source listed next to `banking_policies`. | The request and response format the wizard expects. The wizard has a Learn more link that was not followed. |
| A read-heavy flow | Steps that call `get_connected_group`, `find_circular_flows`, and `screen_business`, then branch on the results, with no LLM in the loop. | Whether a flow can be started from the dashboard without an agent. The New workflow editor was not opened. |
| AI Gateway > MCP servers | A Neo4j MCP server registered once and used by any agent. | Whether this tenant accepts a custom MCP server and can reach one. The page was not opened. |
| Observability | A trace of a `bank_supervisor` turn that shows the Cypher tool calls behind the answer. | What the trace shows for tool inputs and outputs. No trace was opened, and the Home page showed no messages in the last 7 days. |
| Tools page | Each Neo4j tool with its input and output schema. | Whether the page shows the Cypher or only the schema. |
| Connections and Credentials | How the Neo4j credentials are held and scoped. | What the page shows for a key-value connection such as `banker_creds`. |

## Not checked

- The Catalog's MCP Servers tab was not searched for Neo4j.
- The New workflow editor was not opened, so the step types it offers on this tenant are unknown.
- A web search for the Custom service contract was started and then stopped.

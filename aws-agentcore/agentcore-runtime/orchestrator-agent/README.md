# Multi-Agent Orchestrator - AgentCore Runtime

A supervisor agent that routes queries to specialized workers using LangGraph's Supervisor pattern.

## Architecture

```
                         User Query
                              │
                              ▼
                ┌─────────────────────────┐
                │   Orchestrator Agent    │
                │      (Supervisor)       │
                │                         │
                │  Classifies → Routes    │
                └───────────┬─────────────┘
                            │
               ┌────────────┴────────────┐
               │                         │
               ▼                         ▼
    ┌───────────────────┐     ┌───────────────────┐
    │ Maintenance Agent │     │ Operations Agent  │
    │     (Worker)      │     │     (Worker)      │
    │                   │     │                   │
    │ • Faults          │     │ • Flights         │
    │ • Components      │     │ • Delays          │
    │ • Sensors         │     │ • Routes          │
    │ • Reliability     │     │ • Airports        │
    └─────────┬─────────┘     └─────────┬─────────┘
              │                         │
              └───────────┬─────────────┘
                          ▼
                  Neo4j MCP Server
```

## Agent Responsibilities

### Orchestrator (Supervisor)

Routes queries based on intent classification:

| Query Contains | Routes To |
|----------------|-----------|
| maintenance, fault, repair, failure | Maintenance Agent |
| component, sensor, reading, reliability | Maintenance Agent |
| flight, delay, schedule, on-time | Operations Agent |
| airport, route, departure, arrival | Operations Agent |
| Both domains | Both → Synthesize |

### Maintenance Agent (Worker)

Expert for aircraft health and reliability:
- Fault analysis and patterns
- Component failures
- Sensor readings
- System diagnostics

### Operations Agent (Worker)

Expert for flight operations:
- Delay analysis
- Route performance
- Operator metrics
- Airport traffic

## Quick Start

```bash
# 1. Install dependencies
./agent.sh setup

# 2. Copy credentials from basic-agent
cp ../basic-agent/.mcp-credentials.json .
```

---

## Cloud Deployment & Testing

Deploy and test the orchestrator on AWS AgentCore Runtime.

### Deploy to Cloud

```bash
# Configure for AWS deployment
./agent.sh configure

# Deploy to AgentCore Runtime (takes several minutes)
./agent.sh deploy

# Check deployment status
./agent.sh status
```

### Test in Cloud

```bash
# Invoke with default question (maintenance faults)
./agent.sh invoke-cloud

# Invoke with a specific query
./agent.sh invoke-cloud "What are the most common maintenance faults?"
./agent.sh invoke-cloud "Which routes have the most delays?"
```

### Cloud Load Testing

Run continuous load tests using queries from `queries.txt`:

```bash
# Load test with random queries every 5 seconds
./agent.sh load-test

# Custom interval (10 seconds between queries)
./agent.sh load-test 10
```

### Cloud Commands Reference

| Command | Description |
|---------|-------------|
| `./agent.sh configure` | Configure for AWS deployment |
| `./agent.sh deploy` | Deploy to AgentCore Runtime |
| `./agent.sh status` | Check deployment status |
| `./agent.sh invoke-cloud` | Send default question to deployed agent |
| `./agent.sh invoke-cloud "prompt"` | Send custom question to deployed agent |
| `./agent.sh load-test` | Cloud load test (random queries every 5s) |
| `./agent.sh load-test N` | Cloud load test with N-second interval |
| `./agent.sh destroy` | Remove from AgentCore |

---

## Local Development

Run and test the orchestrator locally before deploying.

### Start Locally

```bash
# Start orchestrator on port 8080
./agent.sh start

# Stop local orchestrator
./agent.sh stop
```

### Test Locally

```bash
# Test routing to different agents
./agent.sh test-maintenance   # Routes to Maintenance Agent
./agent.sh test-operations    # Routes to Operations Agent
./agent.sh test               # Test with general query
```

### Local Commands Reference

| Command | Description |
|---------|-------------|
| `./agent.sh setup` | Install dependencies |
| `./agent.sh start` | Start orchestrator locally (port 8080) |
| `./agent.sh stop` | Stop local orchestrator |
| `./agent.sh test` | Test with general query |
| `./agent.sh test-maintenance` | Test Maintenance Agent routing |
| `./agent.sh test-operations` | Test Operations Agent routing |

## Files

| File | Purpose |
|------|---------|
| `orchestrator_agent.py` | Main entry point - supervisor that routes queries |
| `maintenance_agent.py` | Worker for reliability/faults/components |
| `operations_agent.py` | Worker for flights/delays/routes |
| `invoke_agent.py` | Cloud invocation and load testing |
| `queries.txt` | 20 test queries (10 maintenance, 10 operations) |
| `pyproject.toml` | Dependencies including langgraph-supervisor |
| `agent.sh` | CLI wrapper for all operations |

## Observability Benefits

With 3 agents, CloudWatch traces show:

```
[Orchestrator] Query received: "aircraft with hydraulic failures"
  │
  ├── Classification: Maintenance domain
  ├── Decision: Route to Maintenance Agent
  │
  └── [Maintenance Agent] Processing query
        │
        ├── Tool: execute-query (Cypher)
        ├── Results: 5 failures found
        │
        └── Response returned

[Orchestrator] Final response delivered
```

**Dashboard Insights:**
- Routing distribution (% maintenance vs operations)
- Per-agent latency and error rates
- Tool usage patterns by domain
- Session traces spanning multiple agents

## Example Queries

Sample queries to test routing to different agents (use with `invoke-cloud` or local tests):

**Maintenance Agent (reliability, faults, components):**
- "What are the most common maintenance faults?"
- "Which components have the most failures?"
- "Show hydraulic system issues"
- "What is the reliability history of avionics components?"

**Operations Agent (flights, delays, routes):**
- "What are the most common delay causes?"
- "Which routes have the most delays?"
- "Compare on-time performance by airline"
- "Which airports have the highest traffic volume?"

**Cross-Domain (Both Agents):**
- "How do maintenance issues affect flight delays?"

See `queries.txt` for a full list of 20 test queries (10 per domain).

## Load Test Output

When running `./agent.sh load-test`, you'll see output like:

```
======================================================================
[2026-01-18 20:55:00] Iteration 1
Query #9 | Expected Agent: Maintenance
======================================================================
Query: Show me the maintenance events with the highest severity in the last year.
----------------------------------------------------------------------

Based on the analysis of maintenance events...

----------------------------------------------------------------------
Elapsed: 15.2s | Stats: M=1 O=0 E=0
Waiting 5 seconds...
```

The load test:
- Randomly selects from 20 queries in `queries.txt`
- 10 maintenance queries (route to Maintenance Agent)
- 10 operations queries (route to Operations Agent)
- Shows expected agent and response time
- Tracks statistics (M=Maintenance, O=Operations, E=Errors)

## Key Technologies

- **LangGraph Supervisor** - Multi-agent orchestration pattern
- **Amazon Bedrock AgentCore** - Managed runtime for AI agents
- **Claude Sonnet 4** - LLM powering all agents
- **Neo4j MCP Server** - Graph database via Model Context Protocol

## See Also

- [../ORCHESTRATOR.md](../ORCHESTRATOR.md) - Detailed architecture design
- [../basic-agent/](../basic-agent/) - Single-agent version

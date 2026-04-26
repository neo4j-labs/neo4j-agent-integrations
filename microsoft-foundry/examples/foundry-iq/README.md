# Foundry IQ + Neo4j Aura Agent

Use this pattern when one agent needs both enterprise knowledge retrieval and graph reasoning.

Foundry IQ knowledge bases retrieve permission-aware enterprise content with citations. Neo4j Aura Agent gives the same Foundry agent a domain-specific graph agent over entities, events, accounts, documents, or operational systems. Aura Agent can be made available externally as an MCP server endpoint, so Foundry can call it as another tool.

## Shape

```mermaid
flowchart LR
    user["User"] --> agent["Foundry agent"]
    agent --> iq["Foundry IQ knowledge base"]
    agent --> neo4j["Neo4j Aura Agent MCP endpoint"]
    iq --> docs["Enterprise content + citations"]
    neo4j --> graph["Graph relationships + domain reasoning"]
```

## Coming Soon

This example will cover:

1. A Foundry IQ knowledge base for document retrieval.
2. A Neo4j Aura Agent published as an MCP endpoint for graph reasoning.
3. A Foundry agent with both tools attached.
4. A prompt that needs both sources, for example: "Which supplier risks are mentioned in recent documents, and how are those suppliers connected to affected products?"

Important: MCP is used at the agent/tool layer. A Neo4j Aura Agent MCP endpoint is not a Foundry IQ knowledge source by itself. Use Foundry IQ for document retrieval and the Aura Agent MCP endpoint for graph traversal and domain reasoning.

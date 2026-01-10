# n8n + Neo4j Integration

## Overview

**n8n** is a workflow automation platform with 1400+ integrations, visual workflows, and MCP support added in 2025.

**Official Resources:**
- Website: https://n8n.io
- Documentation: https://docs.n8n.io/
- Neo4j Integration (Community): https://github.com/Kurea/n8n-nodes-neo4j (Note: Neo4j support is via community nodes, not official built-in)

## Extension Points

### 1. Native Neo4j Node

```json
{
  "nodes": [
    {
      "type": "n8n-nodes-base.neo4j",
      "credentials": {
        "neo4j": {
          "host": "demo.neo4jlabs.com",
          "port": 7687,
          "user": "companies",
          "password": "companies",
          "database": "companies"
        }
      },
      "parameters": {
        "operation": "execute",
        "query": "MATCH (o:Organization {name: $name}) RETURN o"
      }
    }
  ]
}
```

### 2. MCP Workflow Nodes (2025)

Connect to Neo4j MCP server as workflow node.

### 3. HTTP Request Node

Call Neo4j MCP server via HTTP:

```json
{
  "type": "n8n-nodes-base.httpRequest",
  "url": "http://localhost:8000/mcp",
  "method": "POST",
  "headers": {
    "Authorization": "Bearer YOUR_TOKEN"
  }
}
```

## MCP Authentication

✅ **Workflow auth** - 1400+ authentication types

✅ **OAuth nodes** - OAuth 2.0

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#13-other-platforms-brief-overview)

## Resources

- **n8n Docs**: https://docs.n8n.io/
- **Neo4j Node**: https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.neo4j/
- **Demo Database**: bolt://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ Native Neo4j node
- ✅ MCP support (2025)
- ✅ Visual workflows
- **Effort Score**: 3/10
- **Impact Score**: 5/10

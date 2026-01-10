# ServiceNow AI Agents + Neo4j Integration

## Overview

**ServiceNow AI Agents** with AI Agent Studio provides low-code/no-code agent development with thousands of pre-built integrations. Supports MCP + A2A Protocol (Zurich Patch 4 / Yokohama Patch 11).

**Key Features:**
- AI Agent Studio (no-code)
- AI Control Tower for governance
- Workflow Data Fabric
- Thousands of pre-built agents
- MCP + A2A Protocol support
- Microsoft Foundry/Copilot integration

**Official Resources:**
- Website: https://www.servicenow.com/products/ai-agents.html
- Community: https://www.servicenow.com/community/now-assist-articles/enable-mcp-and-a2a/ta-p/3373907

## Extension Points

### 1. MCP Client

Add Neo4j MCP server in AI Agent Studio:
1. AI Agent Studio → Add MCP Server tool
2. Create Provider with MCP server URL
3. Create Connection & Credential alias
4. Choose auth (API Key or OAuth 2.1)

### 2. Integration Hub

Use pre-built connectors with custom Neo4j integration.

## MCP Authentication

✅ **API Keys** - Via Connection & Credential alias

✅ **OAuth 2.1** (Primary) - Modern M2M authentication

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#10-servicenow-ai-agents--now-assist)

## Resources

- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ MCP + A2A support
- ✅ OAuth 2.1
- **Effort Score**: 9/10
- **Impact Score**: 8/10

# Salesforce Agentforce + Neo4j Integration

## Overview

**Salesforce Agentforce** is Salesforce's agent platform with Atlas Reasoning Engine and deep CRM integration. Uses proprietary Agent Communication Protocol (ACP) with OpenAI Bridge for MCP support.

**Key Features:**
- Atlas Reasoning Engine
- Workflow automation
- CRM data integration
- Memory (CRM records)
- Proprietary ACP + OpenAI Bridge

**Official Resources:**
- Website: https://www.salesforce.com/agentforce/
- Documentation: https://developer.salesforce.com/docs/einstein/genai/

## Extension Points

### 1. OpenAI Bridge

Connect via ChatGPT Apps bridge (uses MCP):
- Build ChatGPT App with Neo4j MCP server
- Connect to Agentforce via OpenAI Bridge

### 2. Direct API Integration

Use Salesforce API with Neo4j queries:

```apex
public class Neo4jService {
    public static Map<String, Object> queryCompany(String companyName) {
        HttpRequest req = new HttpRequest();
        req.setEndpoint('https://your-neo4j-api/query');
        req.setMethod('POST');
        req.setBody(JSON.serialize(new Map<String, Object>{
            'query' => 'MATCH (o:Organization {name: $company}) RETURN o',
            'params' => new Map<String, Object>{'name' => companyName}
        }));

        Http http = new Http();
        HttpResponse res = http.send(req);
        return (Map<String, Object>)JSON.deserializeUntyped(res.getBody());
    }
}
```

## MCP Authentication

✅ **API Keys** - Salesforce API tokens

✅ **OAuth 2.0** - Client credentials with Connected Apps

✅ **JWT Bearer** - Server-to-server M2M

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#7-salesforce-agentforce)

## Resources

- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- 🔶 Bridge/Proprietary protocol
- ✅ OpenAI Bridge for MCP
- **Effort Score**: 7.8/10
- **Impact Score**: 7.9/10

# AWS AgentCore Bedrock + Neo4j Integration

## Overview

**AWS AgentCore Bedrock** is Amazon's framework-agnostic agent runtime and orchestration platform, launched GA in October 2025. It provides 8-hour execution windows, episodic memory, and comprehensive observability for production agent deployments.

**Key Features:**
- Framework-agnostic runtime (supports any Python/JavaScript framework)
- MCP + A2A Protocol support (native)
- Episodic memory with automatic context management
- Browser and Code Interpreter capabilities
- Comprehensive AWS IAM integration
- Policy controls and governance
- Built-in evaluations

**Official Resources:**
- Website: https://aws.amazon.com/bedrock/agentcore/
- Documentation: https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html
- MCP Runtime: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html
- Gateway: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using-mcp.html

## Extension Points

### 1. MCP Integration (Primary)

AgentCore has **native first-class MCP support** with dedicated runtime and gateway components.

**MCP Runtime:**
```bash
# Configure MCP server
agentcore configure -e my_neo4j_mcp.py --protocol MCP

# Deploy with OAuth
agentcore configure -e my_neo4j_mcp.py --protocol MCP \
  --oauth-discovery-url https://auth0.com/.well-known/openid-configuration \
  --oauth-audience https://bedrock-agentcore.region.amazonaws.com/runtimes/{ARN}/invocations
```

**AgentCore Gateway:**
Acts as a reverse proxy, handling inbound OAuth authentication and outbound connections to MCP servers:

```
External Agent
  → [OAuth token via Cognito/Auth0]
  → AgentCore Gateway (validates JWT)
  → [IAM role or OAuth]
  → Neo4j MCP Server
```

### 2. Direct AWS Lambda Integration

Deploy Neo4j query functions as Lambda targets:

```python
import boto3
from neo4j import GraphDatabase

def lambda_handler(event, context):
    driver = GraphDatabase.driver(
        os.environ['NEO4J_URI'],
        auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD'])
    )

    records, summary, keys = driver.execute_query(
        event['query'],
        **event.get('params', {}),
        database_=os.environ.get('NEO4J_DATABASE', 'neo4j')
    )
    return {'data': [record.data() for record in records]}
```

### 3. Smithy Protocol Integration

Define Neo4j tools using AWS Smithy IDL for type-safe integration.

## MCP Authentication

**Supported Mechanisms:**

✅ **API Keys** - AWS Access Keys (not recommended for production M2M)

✅ **IAM Roles and Policies** (Primary for M2M)
- Service-Linked Roles with automatic workload identity (Oct 2025+)
- Cross-account role assumption
- Resource-based policies

✅ **M2M OIDC**
- IAM OIDC Provider integration
- Amazon Cognito M2M flows (client credentials grant)
- OAuth 2.1 with Dynamic Client Registration (DCR)
- JWT bearer token validation

**Other Mechanisms:**
- **SigV4**: AWS Signature Version 4 signing
- **Workload Identity**: Automatic OAuth provisioning for MCP runtimes
- **Resource Policies**: Fine-grained access control
- **Lambda Auth**: Custom authorization via Lambda functions

### Service-Linked Role (SLR) - Recommended

Introduced October 2025, automatically provisions workload identity for MCP runtimes:

```bash
agentcore configure -e neo4j_mcp.py --protocol MCP
# Prompts for OAuth setup
# Discovery URL: https://dev-xxxxx.auth0.com/.well-known/openid-configuration
# Audience: https://bedrock-agentcore.region.amazonaws.com/runtimes/{ARN}/invocations
```

**Benefits:**
- Eliminates user account dependencies
- Automatic token refresh
- Supports OAuth M2M with Auth0, Cognito
- Includes audience parameter for JWT tokens

### AgentCore Gateway Authentication

**Inbound (to Gateway):**
- OAuth 2.0 resource server
- Client credentials flow (2LO) for M2M
- Multiple approved client IDs and audiences
- Supports Amazon Cognito, Auth0, Okta, custom OAuth providers

**Outbound (Gateway to backends):**
- **Lambda/Smithy targets**: IAM authorization
- **OpenAPI targets**: OAuth, API keys, custom headers
- **MCP Server targets**: Bearer tokens, OAuth

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#6-aws-agentcore-bedrock-strands-agents)

## Industry Research Agent Example

### Scenario

Deploy a multi-agent investment research system on AWS infrastructure using AgentCore to orchestrate:
1. Neo4j MCP server for company data queries
2. Vector search over news articles
3. Analyst synthesis and reporting

### Architecture

```
┌─────────────────────┐
│  AgentCore Runtime  │
│  (8-hour window)    │
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     │           │
┌────▼────┐ ┌───▼────────┐
│ Neo4j   │ │  Bedrock   │
│ MCP     │ │  Claude 4  │
│ Server  │ │            │
└────┬────┘ └────────────┘
     │
┌────▼─────────────┐
│ Neo4j Database   │
│ (demo instance)  │
└──────────────────┘
```

### Dataset Setup

**Company News Knowledge Graph:**
```python
import os

# Store in AWS Secrets Manager
os.environ['NEO4J_URI'] = 'neo4j+s://demo.neo4jlabs.com:7687'
os.environ['NEO4J_USERNAME'] = 'companies'
os.environ['NEO4J_PASSWORD'] = 'companies'
os.environ['NEO4J_DATABASE'] = 'companies'
```

### Implementation

**1. Deploy Neo4j MCP Server on Lambda**

```python
# neo4j_mcp_server.py
from mcp.server import Server
from neo4j import GraphDatabase
import os

server = Server("neo4j-company-research")
driver = GraphDatabase.driver(
    os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USERNAME'], os.environ['NEO4J_PASSWORD'])
)

@server.tool()
def query_company(company_name: str) -> dict:
    """Query organization data from Neo4j."""
    query = """
        MATCH (o:Organization {name: $company})
        RETURN o.name as name,
               [(o)-[:LOCATED_IN]->(loc:Location) | loc.name] as locations,
               [(o)-[:IN_INDUSTRY]->(ind:Industry) | ind.name] as industries,
               [(o)<-[:WORKS_FOR]-(p:Person) | {name: p.name, title: p.title}][..5] as leadership
        LIMIT 1
    """
    records, summary, keys = driver.execute_query(
        query,
        company=company_name,
        database_=os.environ['NEO4J_DATABASE']
    )
    return records[0].data() if records else {}

@server.tool()
def search_news(company_name: str, query: str, limit: int = 5) -> list:
    """Vector search over news articles mentioning a company."""
    query_str = """
        MATCH (o:Organization {name: $company_name})<-[:MENTIONS]-(a:Article)
        MATCH (a)-[:HAS_CHUNK]->(c:Chunk)
        CALL db.index.vector.queryNodes('news', $limit, $embedding)
        YIELD node, score
        WHERE node = c
        RETURN a.title as title, a.date as date, c.text as text, score
        ORDER BY score DESC
    """
    records, summary, keys = driver.execute_query(
        query_str,
        company_name=company_name,
        limit=limit,
        embedding=embed_query(query),
        database_=os.environ['NEO4J_DATABASE']
    )
    return [r.data() for r in records]

if __name__ == "__main__":
    server.run()
```

**2. Configure AgentCore with OAuth**

```bash
# Configure the MCP runtime
agentcore configure -e neo4j_mcp_server.py --protocol MCP

# Set up OAuth with Cognito
agentcore configure \
  --oauth-discovery-url https://cognito-idp.us-east-1.amazonaws.com/us-east-1_XXXXX/.well-known/openid-configuration \
  --oauth-audience arn:aws:bedrock:us-east-1:123456789:runtime/neo4j-mcp
```

**3. Create Research Agent**

```python
# research_agent.py
import boto3
import json

bedrock = boto3.client('bedrock-runtime')
agentcore = boto3.client('bedrock-agentcore')

def research_company(company_name: str):
    """
    Multi-agent research workflow using AgentCore.
    """
    session_id = agentcore.create_session(
        runtimeArn='arn:aws:bedrock:us-east-1:123456789:runtime/research-agent',
        timeout=28800  # 8 hour window
    )

    # Phase 1: Query company data via MCP
    company_response = agentcore.invoke_tool(
        sessionId=session_id,
        toolName='query_company',
        toolInput={'company_name': company_name}
    )

    # Phase 2: Search relevant news
    news_response = agentcore.invoke_tool(
        sessionId=session_id,
        toolName='search_news',
        toolInput={
            'company_name': company_name,
            'query': f'Recent developments and news about {company_name}',
            'limit': 10
        }
    )

    # Phase 3: Synthesize with Claude via Bedrock
    synthesis_prompt = f"""
    Based on the following data, create an investment research report:

    Company Data: {json.dumps(company_response['output'])}
    Recent News: {json.dumps(news_response['output'])}

    Provide: Executive summary, key developments, risk factors, and outlook.
    """

    report = bedrock.invoke_model(
        modelId='anthropic.claude-4-sonnet-20250514',
        body=json.dumps({
            'anthropic_version': 'bedrock-2023-05-31',
            'messages': [{'role': 'user', 'content': synthesis_prompt}],
            'max_tokens': 4096
        })
    )

    return json.loads(report['body'].read())

# Execute research
result = research_company("Google")
print(result['content'][0]['text'])
```

**4. Deploy with AWS CDK**

```python
# cdk_stack.py
from aws_cdk import (
    Stack, aws_lambda, aws_iam, aws_secretsmanager
)

class Neo4jResearchStack(Stack):
    def __init__(self, scope, id, **kwargs):
        super().__init__(scope, id, **kwargs)

        # Store Neo4j credentials in Secrets Manager
        neo4j_secret = aws_secretsmanager.Secret(
            self, "Neo4jCredentials",
            secret_object_value={
                "uri": "neo4j+s://demo.neo4jlabs.com:7687",
                "username": "companies",
                "password": "companies",
                "database": "companies"
            }
        )

        # Lambda for MCP server
        mcp_lambda = aws_lambda.Function(
            self, "Neo4jMCPServer",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            handler="neo4j_mcp_server.handler",
            code=aws_lambda.Code.from_asset("lambda"),
            environment={
                "SECRET_ARN": neo4j_secret.secret_arn
            }
        )

        neo4j_secret.grant_read(mcp_lambda)

        # Grant AgentCore access
        mcp_lambda.grant_invoke(
            aws_iam.ServicePrincipal("bedrock.amazonaws.com")
        )
```

### Multi-Agent Pattern with Episodic Memory

```python
# AgentCore maintains episodic memory automatically
session = agentcore.create_session(
    runtimeArn=runtime_arn,
    timeout=28800,
    memoryConfiguration={
        'enableEpisodicMemory': True,
        'storageType': 'DYNAMODB'  # or use Neo4j as custom backend
    }
)

# Memory is preserved across tool invocations
# Agent can refer back to earlier company queries
```

## Challenges and Gaps

### Current Limitations

1. **MCP Server Cold Starts**
   - Lambda cold starts can affect MCP response times
   - Mitigation: Use provisioned concurrency or keep-warm strategies

2. **Neo4j Connection Pooling**
   - Lambda environments are ephemeral
   - Need to implement connection pooling carefully
   - Consider using Lambda Layers for Neo4j driver

3. **Large Result Sets**
   - Lambda payload limits (6MB synchronous, 256KB asynchronous)
   - Need to paginate or stream large graph query results

4. **Cost Optimization**
   - 8-hour AgentCore sessions can be expensive
   - Monitor usage and implement timeout strategies

### Workarounds

**Connection Pooling:**
```python
# Use singleton pattern for Neo4j driver
_driver = None

def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(...)
    return _driver
```

**Result Pagination:**
```python
@server.tool()
def query_companies_paginated(skip: int = 0, limit: int = 100):
    """Paginate large result sets."""
    query = """
        MATCH (o:Organization)
        RETURN o
        SKIP $skip LIMIT $limit
    """
    # Return iterator with next_token
```

## Additional Integration Opportunities

### 1. Neo4j as Episodic Memory Backend

Replace DynamoDB with Neo4j for richer episodic memory:
- Store conversation graphs
- Track entity relationships across sessions
- Enable semantic memory retrieval

### 2. AgentCore Gateway + API Management

Front Neo4j MCP server with API Gateway:
- Rate limiting
- API key management
- Custom authentication flows

### 3. EventBridge Integration

Trigger agents based on Neo4j CDC events:
```
Neo4j CDC → EventBridge → AgentCore Agent → Take action
```

### 4. Step Functions Orchestration

Use Step Functions for complex multi-agent workflows:
```
Step Functions State Machine
  ├─> AgentCore Agent 1 (Data Collection)
  ├─> AgentCore Agent 2 (Analysis)
  └─> AgentCore Agent 3 (Reporting)
```

## Deployment Guide

### Prerequisites
- AWS Account with Bedrock access
- Neo4j database (demo or production)
- AWS CLI and CDK installed

### Steps

1. **Package MCP Server**
```bash
pip install mcp neo4j -t lambda/
cp neo4j_mcp_server.py lambda/
```

2. **Deploy Infrastructure**
```bash
cdk deploy Neo4jResearchStack
```

3. **Configure AgentCore**
```bash
agentcore configure -e lambda/neo4j_mcp_server.py --protocol MCP
```

4. **Test**
```bash
python research_agent.py
```

## Resources

- **AWS AgentCore Docs**: https://docs.aws.amazon.com/bedrock-agentcore/
- **Neo4j MCP Server**: https://github.com/neo4j/mcp
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)
- **CDK Examples**: See `examples/cdk/`

## Status

- ✅ Native MCP support in AgentCore
- ✅ OAuth 2.1 with DCR fully supported
- ✅ Service-Linked Roles for automatic workload identity
- ✅ 8-hour execution windows for long-running research tasks
- ⚠️ Lambda cold starts need mitigation strategies
- 🔄 Active AWS investment and feature development

# AWS AgentCore + Neo4j Integration

## Overview

**AWS AgentCore** is Amazon's framework-agnostic agent runtime and orchestration platform. 
It provides managed runtimes, gateway capabilities, episodic memory, and comprehensive observability for production agent deployments.

**Key Features:**
- Framework-agnostic runtime (supports any Python/JavaScript framework)
- Native MCP + A2A Protocol support
- Multiple deployment models: Docker images, code-based (S3), and gateway proxying
- IAM and OAuth 2.0 authentication
- Comprehensive AWS CDK infrastructure-as-code support

**Official Resources:**
- [AgentCore Overview](https://aws.amazon.com/bedrock/agentcore/)
- [AgentCore Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [MCP Runtime Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)
- [Gateway Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using-mcp.html)

## Samples

This directory contains three end-to-end samples, each demonstrating a different integration pattern between AWS AgentCore
and Neo4j via the [Neo4j MCP server](https://github.com/neo4j/mcp).
All samples are deployed with AWS CDK and use the public Neo4j companies demo database: `neo4j+s://demo.neo4jlabs.com:7687` by default.

| # | Sample | Pattern | Auth Model | Deployment |
|---|--------|---------|------------|------------|
| 1 | [MCP Runtime - Docker](samples/1-mcp-runtime-docker/) | AgentCore Runtime with custom Docker image | IAM + per-request Neo4j credentials via custom header | ECR image built & pushed by CDK |
| 2 | [Gateway - External MCP](samples/2-gateway-external-mcp/) | AgentCore Gateway proxying to Fargate-hosted MCP | OAuth 2.0 → Lambda Interceptor → Basic Auth | ECS Fargate + ALB + custom domain |
| 3 | [MCP Runtime - Neo4j Python SDK](samples/3-mcp-runtime-neo4j-sdk/) | AgentCore Runtime with code-based Python MCP server | IAM + Secrets Manager | Python bundle uploaded to S3 by CDK |

### Sample 1: MCP Runtime - Docker

Deploys the official [Neo4j MCP Docker image](https://hub.docker.com/mcp/server/neo4j/overview) as an AgentCore Runtime.
The Docker image is extended locally, built and pushed to ECR by CDK, and run as a managed runtime.
Neo4j credentials are passed per-request via the `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization` header.

→ **[Full documentation](samples/1-mcp-runtime-docker/README.md)**

### Sample 2: Gateway - External MCP

Uses the AgentCore Gateway as a reverse proxy in front of an official Neo4j MCP server running on ECS Fargate behind a
public ALB with a custom domain and TLS. A Lambda Request Interceptor translates inbound OAuth tokens into
Neo4j Basic Auth credentials retrieved from Secrets Manager.

→ **[Full documentation](samples/2-gateway-external-mcp/README.md)**

### Sample 3: MCP Runtime - Neo4j Python SDK

Deploys a custom MCP server written in Python (FastMCP + Neo4j Python driver) as a code-based AgentCore Runtime.
The Python source is bundled with dependencies via `uv`, uploaded to S3, and run directly - no Docker image needed.
Neo4j credentials are loaded from Secrets Manager at startup.

→ **[Full documentation](samples/3-mcp-runtime-neo4j-sdk/README.md)**

## Prerequisites

All samples require:
- AWS Account with Bedrock and AgentCore access
- AWS CLI configured with appropriate credentials
- AWS CDK installed (`npm install -g aws-cdk`)
- Python 3.9+

Sample 2 additionally requires a Route53 hosted zone and an ACM certificate for the custom domain.

## Resources

- [Neo4j MCP Server](https://github.com/neo4j/mcp)
- [Neo4j Demo Database](neo4j+s://demo.neo4jlabs.com:7687) - `companies` / `companies`
- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)

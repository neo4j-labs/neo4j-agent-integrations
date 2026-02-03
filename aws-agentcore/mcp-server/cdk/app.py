#!/usr/bin/env python3
"""CDK app entry point for Neo4j MCP Server on AgentCore Runtime."""

import os
import aws_cdk as cdk
from neo4j_mcp_stack import Neo4jMcpStack

app = cdk.App()

# Get configuration from environment variables or context
stack_name = os.environ.get("STACK_NAME", app.node.try_get_context("stack_name") or "neo4j-agentcore-mcp-server")

Neo4jMcpStack(
    app,
    stack_name,
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("AWS_REGION") or os.environ.get("CDK_DEFAULT_REGION", "us-west-2"),
    ),
    description="Neo4j MCP Server on AgentCore Runtime with Cognito JWT authentication",
)

app.synth()

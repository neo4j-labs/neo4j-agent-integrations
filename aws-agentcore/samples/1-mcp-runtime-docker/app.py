#!/usr/bin/env python3
import os

import aws_cdk as cdk

from neo4j_mcp_runtime.neo4j_mcp_runtime_stack import Neo4jMCPRuntimeStack


app = cdk.App()
Neo4jMCPRuntimeStack(app, "Neo4jMCPRuntimeStack",
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION'))
)

app.synth()

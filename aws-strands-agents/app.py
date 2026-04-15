#!/usr/bin/env python3
import os

import aws_cdk as cdk

from cdk.neo4j_strands_agent_stack import Neo4jStrandsAgentStack

app = cdk.App()
Neo4jStrandsAgentStack(
    app, "Neo4jStrandsAgentStack",
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION'))
)

app.synth()

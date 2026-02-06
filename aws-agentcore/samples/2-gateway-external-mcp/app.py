#!/usr/bin/env python3
import os
import aws_cdk as cdk
from stacks.agent_gateway_stack import AgentCoreGatewayStack

app = cdk.App()

AgentCoreGatewayStack(
    app, "AgentCoreGatewayStack",
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
)

app.synth()

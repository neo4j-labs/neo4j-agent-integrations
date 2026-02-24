#!/usr/bin/env python3
import os

import aws_cdk as cdk

from neo4j_sdk_runtime.neo4j_sdk_runtime_stack import Neo4jSdkRuntimeStack

app = cdk.App()
Neo4jSdkRuntimeStack(
    app, "Neo4jSdkRuntimeStack",
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION'))
)

app.synth()

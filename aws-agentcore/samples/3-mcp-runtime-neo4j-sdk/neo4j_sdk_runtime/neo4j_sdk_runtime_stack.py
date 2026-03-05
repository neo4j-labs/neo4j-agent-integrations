import os

from aws_cdk import (
    Aws,
    Stack,
    CfnOutput,
    BundlingOptions,
    DockerImage,
    BundlingOutput,
    aws_bedrockagentcore as bedrockagentcore,
    aws_iam as iam,
    aws_s3_assets as s3_assets,
    aws_secretsmanager as secretsmanager, RemovalPolicy, SecretValue,
)
from constructs import Construct


class Neo4jSdkRuntimeStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. Build the mcp_app as a deployment zip and upload to S3 via CDK asset
        #    The bundling step installs dependencies for linux/aarch64 and packages
        #    everything into a flat directory that CDK will zip and upload to S3.
        mcp_app_dir = os.path.join(os.path.dirname(__file__), "..", "mcp_app")

        mcp_app_asset = s3_assets.Asset(
            self, "McpAppAsset",
            path=mcp_app_dir,
            bundling=BundlingOptions(
                image=DockerImage.from_registry("ghcr.io/astral-sh/uv:python3.13-bookworm"),
                environment={
                    "UV_CACHE_DIR": "/tmp/uv-cache",
                    "HOME": "/tmp",
                },
                command=[
                    "bash", "-c",
                    "cp /asset-input/mcp_server.py /asset-output/"
                    " && uv pip install"
                    " --no-cache"
                    " --link-mode=copy"
                    " --python-platform manylinux_2_17_aarch64"
                    " --python-version 3.13"
                    " --target /asset-output"
                    " --only-binary :all:"
                    " -r /asset-input/requirements.txt",
                ],
                output_type=BundlingOutput.NOT_ARCHIVED,
            ),
        )

        # 2. Create a Secrets Manager secret for Neo4j connection credentials.
        #    Default values are supplied via CDK context (cdk.json) and can be
        #    overridden at deployment time:
        #      cdk deploy -c neo4j_uri=neo4j+s://... -c neo4j_password=...
        #    In production, pre-create the secret or use ``Secret.from_secret_name_v2``
        #    and manage the value outside CDK entirely.
        neo4j_uri = self.node.try_get_context("neo4j_uri")
        neo4j_username = self.node.try_get_context("neo4j_username")
        neo4j_password = self.node.try_get_context("neo4j_password")
        neo4j_database = self.node.try_get_context("neo4j_database")

        neo4j_secret = secretsmanager.Secret(
            self, "Neo4jSecret",
            secret_name="neo4j-sdk-runtime/neo4j-credentials",
            description="Neo4j connection credentials (NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE)",
            secret_object_value={
                "NEO4J_URI": SecretValue.unsafe_plain_text(neo4j_uri),
                "NEO4J_USERNAME": SecretValue.unsafe_plain_text(neo4j_username),
                "NEO4J_PASSWORD": SecretValue.unsafe_plain_text(neo4j_password),
                "NEO4J_DATABASE": SecretValue.unsafe_plain_text(neo4j_database),
            },
            removal_policy=RemovalPolicy.DESTROY
        )

        # 3. Create IAM Role for AgentCore Runtime
        runtime_policy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    sid="S3CodeAccess",
                    effect=iam.Effect.ALLOW,
                    actions=["s3:GetObject"],
                    resources=[f"arn:aws:s3:::{mcp_app_asset.s3_bucket_name}/{mcp_app_asset.s3_object_key}"],
                ),
                iam.PolicyStatement(
                    sid="SecretsManagerAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "secretsmanager:GetSecretValue",
                        "secretsmanager:DescribeSecret",
                    ],
                    resources=[neo4j_secret.secret_arn],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["logs:DescribeLogStreams"],
                    resources=[
                        f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/runtimes/*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["logs:CreateLogGroup"],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["logs:DescribeLogGroups"],
                    resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                    resources=[
                        f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "xray:PutTraceSegments",
                        "xray:PutTelemetryRecords",
                        "xray:GetSamplingRules",
                        "xray:GetSamplingTargets",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["cloudwatch:PutMetricData"],
                    resources=["*"],
                    conditions={
                        "StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}
                    },
                ),
                iam.PolicyStatement(
                    sid="GetAgentAccessToken",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "bedrock-agentcore:GetWorkloadAccessToken",
                        "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                        "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
                    ],
                    resources=[
                        f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:workload-identity-directory/default",
                        f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:workload-identity-directory/default/workload-identity/agentName-*",
                    ],
                ),
            ]
        )

        runtime_role = iam.Role(
            self, "Neo4jSdkRuntimeExecutionRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="IAM role for Bedrock AgentCore Runtime",
            inline_policies={"RuntimeAccessPolicy": runtime_policy},
        )

        # 4. Create the AgentCore Runtime with code-based deployment from S3
        runtime_instance = bedrockagentcore.CfnRuntime(
            self, "Neo4jSdkRuntime",
            agent_runtime_name="Neo4jSdkRuntime",
            description="Neo4j MCP Server deployed as code via S3",
            agent_runtime_artifact=bedrockagentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                code_configuration=bedrockagentcore.CfnRuntime.CodeConfigurationProperty(
                    code=bedrockagentcore.CfnRuntime.CodeProperty(
                        s3=bedrockagentcore.CfnRuntime.S3LocationProperty(
                            bucket=mcp_app_asset.s3_bucket_name,
                            prefix=mcp_app_asset.s3_object_key,
                        )
                    ),
                    entry_point=["mcp_server.py"],
                    runtime="PYTHON_3_13"
                ),
            ),
            role_arn=runtime_role.role_arn,
            protocol_configuration="MCP",
            network_configuration=bedrockagentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="PUBLIC",
            ),
            environment_variables={
                "SECRET_ARN": neo4j_secret.secret_arn,
                # AgentCore Runtime does not set the region correctly, so we do it here
                "AWS_DEFAULT_REGION": Aws.REGION,
            },
        )

        # Ensure the runtime is created only after the IAM role and secret are fully provisioned
        runtime_instance.node.add_dependency(runtime_role)
        runtime_instance.node.add_dependency(neo4j_secret)

        # 5. Outputs
        CfnOutput(
            self, "McpAppS3Bucket",
            value=mcp_app_asset.s3_bucket_name,
            description="S3 bucket containing the mcp_app deployment package",
        )

        CfnOutput(
            self, "McpAppS3Key",
            value=mcp_app_asset.s3_object_key,
            description="S3 object key of the mcp_app deployment package",
        )

        CfnOutput(
            self, "Neo4jSdkRuntimeArn",
            value=runtime_instance.attr_agent_runtime_arn,
            description="ARN of the AgentCore Runtime",
        )

        CfnOutput(
            self, "AgentRuntimeRoleArn",
            value=runtime_role.role_arn,
            description="ARN of the IAM Role for AgentCore Runtime",
        )

        CfnOutput(
            self, "Neo4jSecretArn",
            value=neo4j_secret.secret_arn,
            description="ARN of the Secrets Manager secret for Neo4j credentials",
        )

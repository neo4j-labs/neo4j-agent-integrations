import os

from aws_cdk import (
    Aws,
    Stack,
    CfnOutput,
    BundlingOptions,
    DockerImage,
    BundlingOutput,
    RemovalPolicy,
    SecretValue,
    aws_bedrockagentcore as bedrockagentcore,
    aws_iam as iam,
    aws_s3_assets as s3_assets,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class Neo4jStrandsAgentStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ---------------------------------------------------------------------
        # 1. CDK context parameters
        #    Pass at deploy time:  cdk deploy -c cognito_client_id=... etc.
        # ---------------------------------------------------------------------
        cognito_client_id = self.node.try_get_context("cognito_client_id")
        cognito_client_secret = self.node.try_get_context("cognito_client_secret")
        cognito_scope = self.node.try_get_context("cognito_scope")
        cognito_token_endpoint = self.node.try_get_context("cognito_token_endpoint")
        gateway_url = self.node.try_get_context("gateway_url")
        model_id = self.node.try_get_context("model_id")

        # ---------------------------------------------------------------------
        # 2. Bundle the strands_agent/ application code and upload to S3
        # ---------------------------------------------------------------------
        agent_app_dir = os.path.join(os.path.dirname(__file__), "..", "strands_agent")

        agent_app_asset = s3_assets.Asset(
            self, "StrandsAgentAsset",
            path=agent_app_dir,
            bundling=BundlingOptions(
                image=DockerImage.from_registry(
                    "ghcr.io/astral-sh/uv:python3.13-bookworm"
                ),
                environment={
                    "UV_CACHE_DIR": "/tmp/uv-cache",
                    "HOME": "/tmp",
                },
                command=[
                    "bash", "-c",
                    # Copy application source files, then install dependencies
                    "cp -r /asset-input/* /asset-output/"
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

        # ---------------------------------------------------------------------
        # 3. Secrets Manager — Cognito credentials (sensitive)
        # ---------------------------------------------------------------------
        cognito_secret = secretsmanager.Secret(
            self, "CognitoSecret",
            secret_name="neo4j-strands-agent/cognito-credentials",
            description="Cognito OAuth client credentials for the Neo4j Strands Agent",
            secret_object_value={
                "COGNITO_CLIENT_ID": SecretValue.unsafe_plain_text(cognito_client_id),
                "COGNITO_CLIENT_SECRET": SecretValue.unsafe_plain_text(cognito_client_secret),
            },
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ---------------------------------------------------------------------
        # 4. IAM Role for the AgentCore Runtime
        # ---------------------------------------------------------------------
        runtime_policy = iam.PolicyDocument(
            statements=[
                # Read the bundled code from S3
                iam.PolicyStatement(
                    sid="S3CodeAccess",
                    effect=iam.Effect.ALLOW,
                    actions=["s3:GetObject"],
                    resources=[
                        f"arn:aws:s3:::{agent_app_asset.s3_bucket_name}/{agent_app_asset.s3_object_key}"
                    ],
                ),
                # Read Cognito credentials from Secrets Manager
                iam.PolicyStatement(
                    sid="SecretsManagerAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "secretsmanager:GetSecretValue",
                        "secretsmanager:DescribeSecret",
                    ],
                    resources=[cognito_secret.secret_arn],
                ),
                # Invoke Bedrock foundation models (for Strands agent)
                iam.PolicyStatement(
                    sid="BedrockModelAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "bedrock:InvokeModel",
                        "bedrock:InvokeModelWithResponseStream",
                    ],
                    resources=[
                        # Foundation models — regional ARNs
                        f"arn:aws:bedrock:*::foundation-model/*",
                        # Cross-region / global inference profiles (owned by the account)
                        f"arn:aws:bedrock:*:{self.account}:inference-profile/*",
                        # System-defined cross-region inference profiles (no account)
                        f"arn:aws:bedrock:*::inference-profile/*",
                    ],
                ),
                # AgentCore Memory access
                iam.PolicyStatement(
                    sid="AgentCoreMemoryAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "bedrock-agentcore:GetMemory",
                        "bedrock-agentcore:ListMemories",
                        "bedrock-agentcore:SaveMemoryRecords",
                        "bedrock-agentcore:ListMemoryRecords",
                        "bedrock-agentcore:GetMemoryRecord",
                        "bedrock-agentcore:DeleteMemoryRecord",
                        "bedrock-agentcore:RetrieveMemoryRecords",
                        "bedrock-agentcore:SaveConversation",
                        "bedrock-agentcore:GetConversation",
                        "bedrock-agentcore:ListConversations",
                        "bedrock-agentcore:DeleteConversation",
                        # Event operations
                        "bedrock-agentcore:CreateEvent",
                        "bedrock-agentcore:ListEvents",
                        "bedrock-agentcore:SaveEvents",
                        "bedrock-agentcore:GetEvent",
                        "bedrock-agentcore:DeleteEvent",
                    ],
                    resources=[
                        f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:memory/*",
                    ],
                ),
                # CloudWatch Logs
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["logs:DescribeLogStreams", "logs:CreateLogGroup"],
                    resources=[
                        f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/runtimes/*"
                    ],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["logs:DescribeLogGroups"],
                    resources=[
                        f"arn:aws:logs:{self.region}:{self.account}:log-group:*"
                    ],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                    resources=[
                        f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
                    ],
                ),
                # X-Ray tracing
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
                # CloudWatch metrics
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["cloudwatch:PutMetricData"],
                    resources=["*"],
                    conditions={
                        "StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}
                    },
                ),
                # Workload identity tokens
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
            self, "StrandsAgentRuntimeRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="IAM role for the Neo4j Strands Agent AgentCore Runtime",
            inline_policies={"RuntimeAccessPolicy": runtime_policy},
        )

        # ---------------------------------------------------------------------
        # 5. AgentCore Memory Resource
        # ---------------------------------------------------------------------
        agent_core_memory = bedrockagentcore.CfnMemory(
            self, "Neo4jStrandsAgentCoreMemory",
            name="Neo4jStrandsAgentCoreMemory",
            event_expiry_duration=30,
            description="Memory resource with 30 days event expiry",
            memory_strategies=[
                bedrockagentcore.CfnMemory.MemoryStrategyProperty(
                    user_preference_memory_strategy=bedrockagentcore.CfnMemory.UserPreferenceMemoryStrategyProperty(
                        name="UserPreferences",
                        namespaces=["/users/{actorId}/preferences/"],
                        description="Instance of built-in user preference memory strategy"
                    )
                ),
            ],
        )

        # ---------------------------------------------------------------------
        # 6. AgentCore Runtime — code-based deployment from S3
        # ---------------------------------------------------------------------
        agent_runtime = bedrockagentcore.CfnRuntime(
            self, "Neo4jStrandsAgentRuntime",
            agent_runtime_name="Neo4jStrandsAgent",
            description="Neo4j Strands Agent deployed as code via S3",
            agent_runtime_artifact=bedrockagentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                code_configuration=bedrockagentcore.CfnRuntime.CodeConfigurationProperty(
                    code=bedrockagentcore.CfnRuntime.CodeProperty(
                        s3=bedrockagentcore.CfnRuntime.S3LocationProperty(
                            bucket=agent_app_asset.s3_bucket_name,
                            prefix=agent_app_asset.s3_object_key,
                        )
                    ),
                    entry_point=["main.py"],
                    runtime="PYTHON_3_13",
                ),
            ),
            role_arn=runtime_role.role_arn,
            protocol_configuration="HTTP",
            network_configuration=bedrockagentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="PUBLIC",
            ),
            environment_variables={
                # Secret ARN — the agent reads Cognito creds from Secrets Manager
                "SECRET_ARN": cognito_secret.secret_arn,
                "BEDROCK_AGENTCORE_MEMORY_ID": agent_core_memory.attr_memory_id,
                # Non-sensitive configuration
                "GATEWAY_URL": gateway_url,
                "COGNITO_SCOPE": cognito_scope,
                "COGNITO_TOKEN_ENDPOINT": cognito_token_endpoint,
                "MODEL_ID": model_id,
                # Region must be set explicitly for AgentCore runtimes
                "AWS_DEFAULT_REGION": Aws.REGION,
            },
        )

        # Ensure proper ordering
        agent_runtime.node.add_dependency(runtime_role)
        agent_runtime.node.add_dependency(cognito_secret)
        agent_runtime.node.add_dependency(agent_core_memory)

        # ---------------------------------------------------------------------
        # 7. Outputs
        # ---------------------------------------------------------------------
        CfnOutput(
            self, "AgentRuntimeArn",
            value=agent_runtime.attr_agent_runtime_arn,
            description="ARN of the Neo4j Strands Agent AgentCore Runtime",
        )

        CfnOutput(
            self, "AgentRuntimeRoleArn",
            value=runtime_role.role_arn,
            description="ARN of the IAM Role for AgentCore Runtime",
        )

        CfnOutput(
            self, "CognitoSecretArn",
            value=cognito_secret.secret_arn,
            description="ARN of the Secrets Manager secret for Cognito credentials",
        )

        CfnOutput(
            self, "AgentAppS3Bucket",
            value=agent_app_asset.s3_bucket_name,
            description="S3 bucket containing the agent deployment package",
        )

        CfnOutput(
            self, "AgentAppS3Key",
            value=agent_app_asset.s3_object_key,
            description="S3 object key of the agent deployment package",
        )

        CfnOutput(
            self, "AgentCoreMemoryId",
            value=agent_core_memory.attr_memory_id,
            description="ID of the AgentCore Memory resource",
        )

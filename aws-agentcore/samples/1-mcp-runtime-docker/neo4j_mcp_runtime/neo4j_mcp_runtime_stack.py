from aws_cdk import (
    Stack,
    CfnOutput,
    aws_bedrockagentcore as bedrockagentcore,
    aws_iam as iam,
)
from aws_cdk import aws_ecr_assets as ecr_assets
from constructs import Construct


class Neo4jMCPRuntimeStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. Build the adjusted neo4j mcp docker image
        mcp_image_asset = ecr_assets.DockerImageAsset(
            self, "Neo4jMcpImage",
            # AgentCore requires runtimes to have arm64 platform
            platform=ecr_assets.Platform.LINUX_ARM64,
            directory="docker",
        )

        # 2. create a Policy for the AgentCore runtime
        # taken from https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html#runtime-permissions-execution
        runtime_policy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    sid="ECRImageAccess",
                    effect=iam.Effect.ALLOW,
                    actions=["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                    resources=[f"arn:aws:ecr:{self.region}:{self.account}:repository/*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["logs:DescribeLogStreams", "logs:CreateLogGroup"],
                    resources=[
                        f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/runtimes/*"],
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
                    sid="ECRTokenAccess",
                    effect=iam.Effect.ALLOW,
                    actions=["ecr:GetAuthorizationToken"],
                    resources=["*"],
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

        # 3. Create IAM Role for AgentCore Runtime using the previously created policy
        runtime_role = iam.Role(
            self, "AgentCoreRuntimeRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="IAM role for Bedrock AgentCore Runtime",
            inline_policies={"RuntimeAccessPolicy": runtime_policy},
        )

        # since AgentCore uses the `Authorization` header for AWS IAM, we need to pass the neo4j basic auth via a
        # custom header. Such custom headers must be prefixed by `X-Amzn-Bedrock-AgentCore-Runtime-Custom-`
        auth_header_name = "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization"

        # 4. Create the Runtime for our MCP server
        mcp_runtime = bedrockagentcore.CfnRuntime(
            self, "Neo4jMcpRuntime",
            agent_runtime_name="Neo4jMcpRuntime",
            description="A Neo4j MCP Server https://github.com/neo4j/mcp",
            environment_variables={
                "NEO4J_URI": "neo4j+s://demo.neo4jlabs.com:7687",
                "NEO4J_DATABASE": "companies",
                "NEO4J_READ_ONLY": "true",
                "NEO4J_LOG_FORMAT": "text",
                "NEO4J_HTTP_AUTH_HEADER_NAME": auth_header_name,
                "NEO4J_HTTP_ALLOW_UNAUTHENTICATED_PING": "true",
            },
            role_arn=runtime_role.role_arn,
            agent_runtime_artifact=bedrockagentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                container_configuration=bedrockagentcore.CfnRuntime.ContainerConfigurationProperty(
                    container_uri=mcp_image_asset.image_uri
                )
            ),
            protocol_configuration="MCP",
            network_configuration=bedrockagentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="PUBLIC",
            ),
            request_header_configuration=bedrockagentcore.CfnRuntime.RequestHeaderConfigurationProperty(
                # only headers in this list will be passed through to the runtime
                request_header_allowlist=[auth_header_name]
            ),
        )

        # 5. Outputs
        CfnOutput(
            self, "Neo4jMcpImageUri",
            value=mcp_image_asset.image_uri,
            description="The URI of the docker image",
        )

        CfnOutput(
            self, "Neo4jMcpRuntimeArn",
            value=mcp_runtime.attr_agent_runtime_arn,
            description="ARN of the AgentCore Runtime"
        )

        CfnOutput(
            self, "AgentRuntimeRoleArn",
            value=runtime_role.role_arn,
            description="ARN of the IAM Role for AgentCore Runtime"
        )

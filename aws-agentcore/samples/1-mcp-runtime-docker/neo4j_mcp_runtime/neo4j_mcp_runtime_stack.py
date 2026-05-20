from aws_cdk import (
    Stack,
    CfnOutput,
    Tags,
    aws_bedrockagentcore as bedrockagentcore,
    aws_ecr_assets as ecr_assets,
    aws_iam as iam,
)
from constructs import Construct

# AWS Partner Revenue Measurement: attribute resource usage to Neo4j.
# https://docs.aws.amazon.com/PRM/latest/aws-prm-onboarding-guide/prm-resource-tagging.html
AWS_PRM_PRODUCT_CODE = "prod-vfprhasjyi4ug"


class Neo4jMCPRuntimeStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        Tags.of(self).add("aws-apn-id", f"pc:{AWS_PRM_PRODUCT_CODE}")

        # 1. create a Policy for the AgentCore runtime
        # taken from https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html#runtime-permissions-execution
        runtime_policy = iam.PolicyDocument(
            statements=[
                # Use "*" to support cross-account ECR images (e.g. AWS Marketplace containers)
                iam.PolicyStatement(
                    sid="ECRImageAccess",
                    effect=iam.Effect.ALLOW,
                    actions=["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                    resources=["*"],
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

        # 2. Create IAM Role for AgentCore Runtime using the previously created policy
        # Trust policy includes confused deputy protection conditions as recommended by AWS docs:
        # https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html
        runtime_role = iam.Role(
            self, "AgentCoreRuntimeRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {
                        "aws:SourceAccount": self.account,
                    },
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:*",
                    },
                },
            ),
            description="IAM role for Bedrock AgentCore Runtime",
            inline_policies={"RuntimeAccessPolicy": runtime_policy},
        )

        # since AgentCore uses the `Authorization` header for AWS IAM, we need to pass the neo4j basic auth via a
        # custom header. Such custom headers must be prefixed by `X-Amzn-Bedrock-AgentCore-Runtime-Custom-`
        auth_header_name = "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization"

        container_uri = self.node.try_get_context("neo4j_mcp_container_uri")

        # If a pre-built container URI is provided, use it directly.
        # Otherwise, build the Docker image locally from docker/Dockerfile.
        if container_uri:
            image_uri = container_uri
        else:
            mcp_image_asset = ecr_assets.DockerImageAsset(
                self, "Neo4jMcpImage",
                # AgentCore requires runtimes to have arm64 platform
                platform=ecr_assets.Platform.LINUX_ARM64,
                directory="docker",
            )
            image_uri = mcp_image_asset.image_uri

        neo4j_uri = self.node.try_get_context("neo4j_uri")
        neo4j_database = self.node.try_get_context("neo4j_database")

        # 3. Create the Runtime for our MCP server
        mcp_runtime = bedrockagentcore.CfnRuntime(
            self, "Neo4jMcpRuntime",
            agent_runtime_name="Neo4jMcpRuntime",
            description="A Neo4j MCP Server https://github.com/neo4j/mcp",
            environment_variables={
                "NEO4J_URI": neo4j_uri,
                "NEO4J_DATABASE": neo4j_database,
                "NEO4J_TRANSPORT_MODE": "http",
                "NEO4J_MCP_HTTP_HOST": "0.0.0.0",
                "NEO4J_MCP_HTTP_PORT": "8000",
                "NEO4J_READ_ONLY": "true",
                "NEO4J_LOG_FORMAT": "text",
                "NEO4J_HTTP_AUTH_HEADER_NAME": auth_header_name,
                "NEO4J_HTTP_ALLOW_UNAUTHENTICATED_PING": "true",
            },
            role_arn=runtime_role.role_arn,
            agent_runtime_artifact=bedrockagentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                container_configuration=bedrockagentcore.CfnRuntime.ContainerConfigurationProperty(
                    container_uri=image_uri
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

        # Ensure the runtime is created only after the IAM role is fully provisioned
        mcp_runtime.node.add_dependency(runtime_role)

        # 4. Outputs

        if not container_uri:
            CfnOutput(
                self, "Neo4jMcpImageUri",
                value=mcp_image_asset.image_uri,
                description="The URI of the locally built docker image",
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

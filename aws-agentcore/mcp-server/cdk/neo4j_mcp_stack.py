"""CDK Stack for Neo4j MCP Server on AgentCore Runtime with Gateway.

This stack creates:
1. Cognito User Pool with domain for OAuth2 token endpoint
2. MCP Server Runtime for Neo4j queries
3. AgentCore Gateway with JWT authorizer
4. Gateway Target connecting to the MCP Runtime
5. OAuth2 Credential Provider for Gateway -> Runtime authentication
"""

from aws_cdk import (
    Stack,
    CfnParameter,
    CfnOutput,
    Duration,
    RemovalPolicy,
    CustomResource,
    Fn,
    Tags,
    aws_cognito as cognito,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_bedrockagentcore as bedrockagentcore,
)
from constructs import Construct
import os


class Neo4jMcpStack(Stack):
    """Stack deploying Neo4j MCP Server on Amazon Bedrock AgentCore Runtime with Gateway."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._create_parameters()
        self._create_auth_resources()
        self._create_iam_roles()
        self._create_agent_runtime()
        self._create_gateway()
        self._create_outputs()
        self._apply_tags()

    def _apply_tags(self):
        """Apply standard tags to all resources in the stack."""
        Tags.of(self).add("Application", "neo4j-mcp-server")
        Tags.of(self).add("ManagedBy", "CDK")
        Tags.of(self).add("Stack", self.stack_name)

    def _create_parameters(self):
        self.ecr_image_uri = CfnParameter(
            self,
            "ECRImageUri",
            type="String",
            description="Full URI of the Neo4j MCP server image in ECR",
            allowed_pattern=r"^[0-9]+\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/.+$",
            constraint_description="Must be a valid ECR image URI",
        )

        self.neo4j_uri = CfnParameter(
            self,
            "Neo4jUri",
            type="String",
            description="Neo4j connection URI (e.g., neo4j+s://xxx.databases.neo4j.io)",
            allowed_pattern=r"^neo4j(\+s|\+ssc)?://.*$",
            constraint_description="Must be a valid Neo4j URI",
        )

        self.neo4j_database = CfnParameter(
            self,
            "Neo4jDatabase",
            type="String",
            default="neo4j",
            description="Neo4j database name",
        )

        self.neo4j_username = CfnParameter(
            self,
            "Neo4jUsername",
            type="String",
            default="neo4j",
            description="Neo4j database username",
        )

        self.neo4j_password = CfnParameter(
            self,
            "Neo4jPassword",
            type="String",
            no_echo=True,
            description="Neo4j database password",
            min_length=1,
        )

        self.agent_name = CfnParameter(
            self,
            "AgentName",
            type="String",
            default="Neo4jMCPServer",
            description="Name for the MCP server runtime",
            allowed_pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,47}$",
            constraint_description="Must start with a letter, max 48 chars, alphanumeric and underscores only",
        )

        self.network_mode = CfnParameter(
            self,
            "NetworkMode",
            type="String",
            default="PUBLIC",
            description="Network mode for AgentCore runtime",
            allowed_values=["PUBLIC", "PRIVATE"],
        )

    def _create_auth_resources(self):
        # User Pool
        self.user_pool = cognito.UserPool(
            self,
            "CognitoUserPool",
            user_pool_name=f"{self.stack_name}-user-pool",
            self_sign_up_enabled=False,
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_uppercase=False,
                require_lowercase=False,
                require_digits=False,
                require_symbols=False,
            ),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=False, mutable=True)
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # User Pool Domain (required for OAuth2 token endpoint)
        self.user_pool_domain = cognito.UserPoolDomain(
            self,
            "UserPoolDomain",
            user_pool=self.user_pool,
            cognito_domain=cognito.CognitoDomainOptions(
                # Domain must be globally unique - include account ID
                domain_prefix=f"{self.stack_name.lower()}-{self.account}"
            ),
        )

        # Resource Server with custom scope for M2M authentication
        self.resource_server = cognito.CfnUserPoolResourceServer(
            self,
            "ResourceServer",
            user_pool_id=self.user_pool.user_pool_id,
            identifier=f"{self.stack_name.lower()}-mcp",
            name="Neo4j MCP Resource Server",
            scopes=[
                cognito.CfnUserPoolResourceServer.ResourceServerScopeTypeProperty(
                    scope_name="invoke",
                    scope_description="Invoke Neo4j MCP tools through Gateway",
                )
            ],
        )

        # Machine Client for client credentials flow (M2M via Gateway)
        self.machine_client = cognito.CfnUserPoolClient(
            self,
            "MachineClient",
            client_name=f"{self.stack_name}-machine-client",
            user_pool_id=self.user_pool.user_pool_id,
            generate_secret=True,
            allowed_o_auth_flows=["client_credentials"],
            allowed_o_auth_flows_user_pool_client=True,
            allowed_o_auth_scopes=[f"{self.stack_name.lower()}-mcp/invoke"],
            supported_identity_providers=["COGNITO"],
            # Token validity: 12 hours for access tokens
            access_token_validity=12,
            token_validity_units=cognito.CfnUserPoolClient.TokenValidityUnitsProperty(
                access_token="hours",
            ),
        )
        self.machine_client.add_dependency(self.resource_server)

        # Construct OAuth URLs
        self.cognito_domain_url = f"https://{self.stack_name.lower()}-{self.account}.auth.{self.region}.amazoncognito.com"
        self.discovery_url = f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool.user_pool_id}/.well-known/openid-configuration"

    def _create_iam_roles(self):
        # Custom Resource Role for Lambda (handles OAuth provider, runtime health check)
        self.custom_resource_role = iam.Role(
            self,
            "CustomResourceRole",
            role_name=f"{self.stack_name}-custom-resource-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
            inline_policies={
                "CognitoPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="CognitoClientAccess",
                            effect=iam.Effect.ALLOW,
                            actions=["cognito-idp:DescribeUserPoolClient"],
                            resources=[self.user_pool.user_pool_arn],
                        ),
                    ]
                ),
                "AgentCorePolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="OAuthProviderAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock-agentcore:CreateOAuth2CredentialProvider",
                                "bedrock-agentcore:DeleteOAuth2CredentialProvider",
                                "bedrock-agentcore:GetOAuth2CredentialProvider",
                                "bedrock-agentcore:ListOAuth2CredentialProviders",
                                "bedrock-agentcore:CreateTokenVault",
                                "bedrock-agentcore:GetTokenVault",
                            ],
                            resources=[
                                f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:oauth2-credential-provider/*",
                                f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:token-vault/*",
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="RuntimeAccess",
                            effect=iam.Effect.ALLOW,
                            actions=["bedrock-agentcore:GetAgentRuntime"],
                            resources=[
                                f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:runtime/*"
                            ],
                        ),
                    ]
                ),
                "SecretsManagerPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="SecretsAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "secretsmanager:CreateSecret",
                                "secretsmanager:DeleteSecret",
                                "secretsmanager:GetSecretValue",
                                "secretsmanager:PutSecretValue",
                            ],
                            # Note: CreateOauth2CredentialProvider API internally creates secrets
                            # with AWS-controlled naming. We scope to this account/region.
                            resources=[
                                f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:*"
                            ],
                        ),
                    ]
                ),
            },
        )

        # Agent Execution Role for AgentCore
        self.agent_execution_role = iam.Role(
            self,
            "AgentExecutionRole",
            role_name=f"{self.stack_name}-agent-execution-role",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:*"
                    },
                },
            ),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("BedrockAgentCoreFullAccess")
            ],
            inline_policies={
                "AgentCoreExecutionPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="ECRImageAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "ecr:BatchGetImage",
                                "ecr:GetDownloadUrlForLayer",
                                "ecr:BatchCheckLayerAvailability",
                            ],
                            resources=[f"arn:aws:ecr:{self.region}:{self.account}:repository/*"],
                        ),
                        iam.PolicyStatement(
                            sid="ECRTokenAccess",
                            effect=iam.Effect.ALLOW,
                            actions=["ecr:GetAuthorizationToken"],
                            resources=["*"],  # Required - GetAuthorizationToken does not support resource-level permissions
                        ),
                        iam.PolicyStatement(
                            sid="CloudWatchLogs",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:DescribeLogStreams",
                                "logs:CreateLogGroup",
                                "logs:DescribeLogGroups",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            resources=[
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/*",
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/*:*",
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="XRayTracing",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "xray:PutTraceSegments",
                                "xray:PutTelemetryRecords",
                                "xray:GetSamplingRules",
                                "xray:GetSamplingTargets",
                            ],
                            resources=["*"],  # X-Ray does not support resource-level permissions
                        ),
                        iam.PolicyStatement(
                            sid="CloudWatchMetrics",
                            effect=iam.Effect.ALLOW,
                            actions=["cloudwatch:PutMetricData"],
                            resources=["*"],  # PutMetricData does not support resource-level permissions
                            conditions={
                                "StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}
                            },
                        ),
                    ]
                )
            },
        )

        # Gateway Execution Role for AgentCore Gateway
        self.gateway_execution_role = iam.Role(
            self,
            "GatewayExecutionRole",
            role_name=f"{self.stack_name}-gateway-execution-role",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            inline_policies={
                "GatewayPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="InvokeRuntime",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock-agentcore:InvokeRuntime",
                                "bedrock-agentcore:InvokeRuntimeWithResponseStream",
                            ],
                            resources=[
                                f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:runtime/*"
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="CloudWatchLogs",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            resources=[
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/*"
                            ],
                        ),
                        # OAuth provider access for outbound authentication
                        iam.PolicyStatement(
                            sid="OAuthProviderAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock-agentcore:GetOAuth2CredentialProvider",
                                "bedrock-agentcore:GetTokenVault",
                                "bedrock-agentcore:GetWorkloadAccessToken",
                                "bedrock-agentcore:GetResourceOauth2Token",
                                "secretsmanager:GetSecretValue",
                            ],
                            resources=[
                                f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:token-vault/*",
                                f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:workload-identity-directory/*",
                                f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:*",
                            ],
                        ),
                        # Bedrock model access (for tool search)
                        iam.PolicyStatement(
                            sid="BedrockModelAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock:InvokeModel",
                                "bedrock:InvokeModelWithResponseStream",
                            ],
                            resources=[
                                "arn:aws:bedrock:*::foundation-model/*",
                                f"arn:aws:bedrock:*:{self.account}:inference-profile/*",
                            ],
                        ),
                    ]
                )
            },
        )

    def _create_agent_runtime(self):
        # Convert stack name to underscore format for runtime name
        self.runtime_name = f"{self.stack_name.replace('-', '_')}_{self.agent_name.value_as_string}"

        # MCP Server Runtime using CfnRuntime (L1 construct)
        # Only machine_client allowed (Gateway-only access)
        self.mcp_server_runtime = bedrockagentcore.CfnRuntime(
            self,
            "MCPServerRuntime",
            agent_runtime_name=self.runtime_name,
            description=f"Neo4j MCP server runtime - {self.stack_name}",
            role_arn=self.agent_execution_role.role_arn,
            agent_runtime_artifact=bedrockagentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                container_configuration=bedrockagentcore.CfnRuntime.ContainerConfigurationProperty(
                    container_uri=self.ecr_image_uri.value_as_string
                )
            ),
            network_configuration=bedrockagentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode=self.network_mode.value_as_string
            ),
            protocol_configuration="MCP",
            authorizer_configuration=bedrockagentcore.CfnRuntime.AuthorizerConfigurationProperty(
                custom_jwt_authorizer=bedrockagentcore.CfnRuntime.CustomJWTAuthorizerConfigurationProperty(
                    allowed_clients=[self.machine_client.ref],
                    discovery_url=self.discovery_url,
                )
            ),
            environment_variables={
                "NEO4J_URI": self.neo4j_uri.value_as_string,
                "NEO4J_DATABASE": self.neo4j_database.value_as_string,
                "NEO4J_USERNAME": self.neo4j_username.value_as_string,
                "NEO4J_PASSWORD": self.neo4j_password.value_as_string,
                "NEO4J_MCP_TRANSPORT": "http",
                "NEO4J_MCP_HTTP_HOST": "0.0.0.0",
                "NEO4J_MCP_HTTP_PORT": "8000",
                "NEO4J_MCP_HTTP_AUTH_MODE": "env",
                "NEO4J_LOG_LEVEL": "debug",
                "NEO4J_READ_ONLY": "true",
            },
        )

    def _create_gateway(self):
        """Create AgentCore Gateway with OAuth2 authentication to the MCP Runtime."""
        current_dir = os.path.dirname(os.path.realpath(__file__))

        # OAuth Provider Lambda - creates OAuth2 Credential Provider for Gateway
        oauth_provider_lambda_path = os.path.join(
            current_dir, "resources", "oauth_provider"
        )
        self.oauth_provider_function = lambda_.Function(
            self,
            "OAuthProviderFunction",
            function_name=f"{self.stack_name}-oauth-provider",
            description="Creates OAuth2 Credential Provider for Gateway",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            role=self.custom_resource_role,
            timeout=Duration.minutes(5),
            code=lambda_.Code.from_asset(oauth_provider_lambda_path),
        )

        # OAuth Provider Custom Resource
        provider_name = f"{self.stack_name.lower().replace('-', '_')}_oauth_provider"
        self.oauth_provider = CustomResource(
            self,
            "OAuthProvider",
            service_token=self.oauth_provider_function.function_arn,
            properties={
                "ProviderName": provider_name,
                "UserPoolId": self.user_pool.user_pool_id,
                "ClientId": self.machine_client.ref,
                "DiscoveryUrl": self.discovery_url,
                "Region": self.region,
            },
        )
        self.oauth_provider.node.add_dependency(self.machine_client)

        oauth_provider_arn = self.oauth_provider.get_att_string("ProviderArn")

        # Runtime Health Check Lambda - waits for Runtime to be ready
        runtime_health_check_lambda_path = os.path.join(
            current_dir, "resources", "runtime_health_check"
        )
        self.runtime_health_check_function = lambda_.Function(
            self,
            "RuntimeHealthCheckFunction",
            function_name=f"{self.stack_name}-runtime-health-check",
            description="Waits for Runtime to be ready before creating GatewayTarget",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            role=self.custom_resource_role,
            timeout=Duration.minutes(10),
            code=lambda_.Code.from_asset(runtime_health_check_lambda_path),
        )

        # Runtime Health Check Custom Resource
        self.runtime_health_check = CustomResource(
            self,
            "RuntimeHealthCheck",
            service_token=self.runtime_health_check_function.function_arn,
            properties={
                "RuntimeArn": self.mcp_server_runtime.attr_agent_runtime_arn,
                "Region": self.region,
            },
        )
        self.runtime_health_check.node.add_dependency(self.mcp_server_runtime)

        # Gateway with JWT authorizer
        self.gateway = bedrockagentcore.CfnGateway(
            self,
            "Gateway",
            name=f"{self.stack_name.lower()}-gateway",
            role_arn=self.gateway_execution_role.role_arn,
            protocol_type="MCP",
            protocol_configuration=bedrockagentcore.CfnGateway.GatewayProtocolConfigurationProperty(
                mcp=bedrockagentcore.CfnGateway.MCPGatewayConfigurationProperty(
                    supported_versions=["2025-03-26"]
                )
            ),
            authorizer_type="CUSTOM_JWT",
            authorizer_configuration=bedrockagentcore.CfnGateway.AuthorizerConfigurationProperty(
                custom_jwt_authorizer=bedrockagentcore.CfnGateway.CustomJWTAuthorizerConfigurationProperty(
                    allowed_clients=[self.machine_client.ref],
                    discovery_url=self.discovery_url,
                )
            ),
            description=f"Neo4j MCP Gateway - {self.stack_name}",
        )

        # Construct Runtime URL for Gateway Target (URL encode the ARN)
        # Use Fn.join/split for CloudFormation-safe URL encoding
        encoded_arn = Fn.join(
            "%2F",
            Fn.split(
                "/",
                Fn.join("%3A", Fn.split(":", self.mcp_server_runtime.attr_agent_runtime_arn)),
            ),
        )
        runtime_invocation_url = Fn.join(
            "",
            [
                f"https://bedrock-agentcore.{self.region}.amazonaws.com/runtimes/",
                encoded_arn,
                "/invocations",
            ],
        )

        # OAuth scope for the resource server
        oauth_scope = f"{self.stack_name.lower()}-mcp/invoke"

        # Gateway Target connecting to the MCP Runtime
        self.gateway_target = bedrockagentcore.CfnGatewayTarget(
            self,
            "GatewayTarget",
            gateway_identifier=self.gateway.attr_gateway_identifier,
            name="neo4j-mcp-server-target",
            description="Target for Neo4j MCP Server Runtime",
            target_configuration=bedrockagentcore.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=bedrockagentcore.CfnGatewayTarget.McpTargetConfigurationProperty(
                    mcp_server=bedrockagentcore.CfnGatewayTarget.McpServerTargetConfigurationProperty(
                        endpoint=runtime_invocation_url
                    )
                )
            ),
            credential_provider_configurations=[
                bedrockagentcore.CfnGatewayTarget.CredentialProviderConfigurationProperty(
                    credential_provider_type="OAUTH",
                    credential_provider=bedrockagentcore.CfnGatewayTarget.CredentialProviderProperty(
                        oauth_credential_provider=bedrockagentcore.CfnGatewayTarget.OAuthCredentialProviderProperty(
                            provider_arn=oauth_provider_arn,
                            scopes=[oauth_scope],
                        )
                    ),
                )
            ],
        )
        self.gateway_target.add_dependency(self.gateway)
        self.gateway_target.add_dependency(self.mcp_server_runtime)
        self.gateway_target.node.add_dependency(self.runtime_health_check)
        self.gateway_target.node.add_dependency(self.oauth_provider)

    def _create_outputs(self):
        # ===== Runtime Outputs =====
        CfnOutput(
            self,
            "MCPServerRuntimeId",
            description="ID of the Neo4j MCP server runtime",
            value=self.mcp_server_runtime.attr_agent_runtime_id,
            export_name=f"{self.stack_name}-MCPServerRuntimeId",
        )

        CfnOutput(
            self,
            "MCPServerRuntimeArn",
            description="ARN of the Neo4j MCP server runtime",
            value=self.mcp_server_runtime.attr_agent_runtime_arn,
            export_name=f"{self.stack_name}-MCPServerRuntimeArn",
        )

        CfnOutput(
            self,
            "MCPServerInvocationURL",
            description="URL to invoke the Neo4j MCP server (ARN needs URL-encoding)",
            value=f"https://bedrock-agentcore.{self.region}.amazonaws.com/runtimes/ENCODED_ARN/invocations?qualifier=DEFAULT",
        )

        # ===== Gateway Outputs =====
        CfnOutput(
            self,
            "GatewayUrl",
            description="AgentCore Gateway URL (use this for MCP clients)",
            value=self.gateway.attr_gateway_url,
            export_name=f"{self.stack_name}-GatewayUrl",
        )

        CfnOutput(
            self,
            "GatewayId",
            description="AgentCore Gateway ID",
            value=self.gateway.attr_gateway_identifier,
            export_name=f"{self.stack_name}-GatewayId",
        )

        CfnOutput(
            self,
            "GatewayTargetName",
            description="Gateway Target Name (tools are prefixed with this)",
            value="neo4j-mcp-server-target",
        )

        # ===== Cognito Outputs =====
        CfnOutput(
            self,
            "CognitoUserPoolId",
            description="ID of the Cognito User Pool",
            value=self.user_pool.user_pool_id,
            export_name=f"{self.stack_name}-CognitoUserPoolId",
        )

        CfnOutput(
            self,
            "CognitoMachineClientId",
            description="ID of the Machine Client (for Gateway M2M access)",
            value=self.machine_client.ref,
            export_name=f"{self.stack_name}-MachineClientId",
        )

        CfnOutput(
            self,
            "CognitoTokenUrl",
            description="Cognito Token URL for OAuth2 client credentials flow",
            value=f"{self.cognito_domain_url}/oauth2/token",
            export_name=f"{self.stack_name}-TokenUrl",
        )

        CfnOutput(
            self,
            "CognitoScope",
            description="OAuth2 Scope for M2M authentication via Gateway",
            value=f"{self.stack_name.lower()}-mcp/invoke",
        )

        CfnOutput(
            self,
            "CognitoDiscoveryUrl",
            description="Cognito OIDC Discovery URL",
            value=self.discovery_url,
            export_name=f"{self.stack_name}-CognitoDiscoveryUrl",
        )

        # ===== IAM Role Outputs =====
        CfnOutput(
            self,
            "AgentExecutionRoleArn",
            description="ARN of the agent execution role",
            value=self.agent_execution_role.role_arn,
            export_name=f"{self.stack_name}-AgentExecutionRoleArn",
        )

        CfnOutput(
            self,
            "GatewayExecutionRoleArn",
            description="ARN of the gateway execution role",
            value=self.gateway_execution_role.role_arn,
            export_name=f"{self.stack_name}-GatewayExecutionRoleArn",
        )
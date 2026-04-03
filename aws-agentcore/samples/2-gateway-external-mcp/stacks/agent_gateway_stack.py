from aws_cdk import (
    Stack,
    CfnOutput,
    SecretValue,
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_secretsmanager as secretsmanager,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_route53 as route53,
    aws_certificatemanager as acm,
    aws_bedrockagentcore as bedrockagentcore,
    aws_cognito as cognito,
)
from constructs import Construct


class AgentCoreGatewayStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Domain configuration (set via CDK context) ──────────────────────
        # Set in cdk.json "context" or pass on the CLI:
        #   cdk deploy -c domain_name=example.com -c subdomain=mcp -c certificate_arn=arn:aws:acm:...
        # The resulting MCP endpoint will be: https://<subdomain>.<domain_name>/mcp
        domain_name: str = self.node.try_get_context("domain_name")
        subdomain: str = self.node.try_get_context("subdomain") or "mcp"
        certificate_arn: str = self.node.try_get_context("certificate_arn")

        if not domain_name:
            raise ValueError(
                "CDK context variable 'domain_name' is required. "
                "Pass it via cdk.json or: cdk deploy -c domain_name=example.com"
            )
        if not certificate_arn:
            raise ValueError(
                "CDK context variable 'certificate_arn' is required. "
                "Pass it via cdk.json or: cdk deploy -c certificate_arn=arn:aws:acm:..."
            )

        neo4j_uri: str = self.node.try_get_context("neo4j_uri")
        neo4j_username: str = self.node.try_get_context("neo4j_username")
        neo4j_password: str = self.node.try_get_context("neo4j_password")
        neo4j_database: str = self.node.try_get_context("neo4j_database")

        mcp_fqdn = f"{subdomain}.{domain_name}"

        # 1. VPC definition
        # Creating a VPC with public subnets only for cost efficiency in this sample.
        # In a real production environment, you would likely use Private subnets with NAT Gateways.
        vpc = ec2.Vpc(
            self, "AgentCoreVpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                )
            ]
        )

        # 2. ECS Cluster
        cluster = ecs.Cluster(
            self, "AgentCoreCluster",
            vpc=vpc
        )

        # 3. Secrets Manager Secret for Neo4j credentials
        # We create a placeholder secret. The user must update the values in the AWS Console.
        neo4j_secret = secretsmanager.Secret(
            self, "Neo4jCredentials",
            description="Credentials for Neo4j MCP to be used by AgentCore Gateway Interceptor",
            secret_object_value={
                "NEO4J_URI": SecretValue.unsafe_plain_text(neo4j_uri),
                "NEO4J_USERNAME": SecretValue.unsafe_plain_text(neo4j_username),
                "NEO4J_PASSWORD": SecretValue.unsafe_plain_text(neo4j_password),
                "NEO4J_DATABASE": SecretValue.unsafe_plain_text(neo4j_database)
            },
            removal_policy=RemovalPolicy.DESTROY
        )

        # 4. Cognito setup for M2M OAuth (client_credentials)
        cognito_user_pool = cognito.UserPool(
            self, "GatewayUserPool",
            self_sign_up_enabled=False,
            removal_policy=RemovalPolicy.DESTROY
        )

        cognito_user_pool_domain = cognito.UserPoolDomain(
            self, "GatewayUserPoolDomain",
            user_pool=cognito_user_pool,
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"neo4j-mcp-{self.account}-{self.region}"
            )
        )

        gateway_scope = cognito.ResourceServerScope(
            scope_name="invoke",
            scope_description="Invoke the Neo4j MCP Gateway"
        )
        cognito_resource_server = cognito.UserPoolResourceServer(
            self, "GatewayResourceServer",
            user_pool=cognito_user_pool,
            identifier="neo4j-mcp-gateway",
            scopes=[gateway_scope]
        )

        cognito_user_pool_client = cognito.UserPoolClient(
            self, "GatewayM2MClient",
            user_pool=cognito_user_pool,
            generate_secret=True,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(client_credentials=True),
                scopes=[
                    cognito.OAuthScope.resource_server(
                        cognito_resource_server,
                        gateway_scope
                    )
                ]
            )
        )

        cognito_scope = "neo4j-mcp-gateway/invoke"
        cognito_discovery_url = (
            f"https://cognito-idp.{self.region}.amazonaws.com/"
            f"{cognito_user_pool.user_pool_id}/.well-known/openid-configuration"
        )
        cognito_token_endpoint = f"{cognito_user_pool_domain.base_url()}/oauth2/token"

        # 5a. Route53 hosted zone lookup
        hosted_zone = route53.HostedZone.from_lookup(
            self, "HostedZone",
            domain_name=domain_name,
        )

        # 5b. Import existing ACM certificate by ARN (set via 'certificate_arn' context key).
        # The certificate must cover the subdomain (wildcard *.example.com or exact mcp.example.com)
        # and must reside in the same region as the stack.
        certificate = acm.Certificate.from_certificate_arn(
            self, "AlbCertificate",
            certificate_arn=certificate_arn,
        )

        # 5c. Fargate Service (Neo4j MCP) with HTTPS listener
        # Using the ApplicationLoadBalancedFargateService pattern for simplicity.
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "Neo4jMcpService",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=1024,
            desired_count=1,
            runtime_platform=ecs.RuntimePlatform(
                cpu_architecture=ecs.CpuArchitecture.ARM64,
                operating_system_family=ecs.OperatingSystemFamily.LINUX,
            ),
            listener_port=443,
            certificate=certificate,
            domain_name=mcp_fqdn,
            domain_zone=hosted_zone,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_registry("ghcr.io/neo4j-labs/neo4j-mcp-canary:latest"),
                container_port=8080,
                environment={
                    "NEO4J_TRANSPORT_MODE": "http",
                    "NEO4J_MCP_HTTP_PORT": "8080",
                    "NEO4J_MCP_HTTP_HOST": "0.0.0.0",
                    "NEO4J_READ_ONLY": "true",
                    "NEO4J_HTTP_ALLOW_UNAUTHENTICATED_PING": "true",
                    "NEO4J_HTTP_ALLOW_UNAUTHENTICATED_TOOLS_LIST": "true",
                    "NEO4J_HTTP_ALLOW_UNAUTHENTICATED": "true",
                },
                secrets={
                    "NEO4J_URI": ecs.Secret.from_secrets_manager(neo4j_secret, "NEO4J_URI"),
                    "NEO4J_DATABASE": ecs.Secret.from_secrets_manager(neo4j_secret, "NEO4J_DATABASE"),
                },
                enable_logging=True
            ),
            public_load_balancer=True,
            assign_public_ip=True  # Required because we are in Public Subnets
        )

        # Configure ALB health check to use /mcp endpoint
        fargate_service.target_group.configure_health_check(
            path="/mcp",
            healthy_http_codes="200,401"
        )

        # 5. Lambda Request Interceptor
        interceptor_lambda = lambda_.Function(
            self, "GatewayInterceptor",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="interceptor.handler",
            code=lambda_.Code.from_asset("lambda"),
            environment={
                "SECRET_ARN": neo4j_secret.secret_arn
            },
            timeout=Duration.seconds(30)
        )

        # Grant permission to read the secret
        neo4j_secret.grant_read(interceptor_lambda)

        # 6. AgentCore MCP Gateway
        # IAM Role assumed by the AgentCore Gateway service
        gateway_role = iam.Role(
            self, "GatewayRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Role assumed by AgentCore Gateway",
        )

        gateway_role.add_to_policy(iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=[interceptor_lambda.function_arn],
        ))
        interceptor_lambda.grant_invoke(gateway_role)

        # MCP Gateway with Cognito JWT authorizer and Lambda Request Interceptor
        mcp_gateway = bedrockagentcore.CfnGateway(
            self, "McpGateway",
            name="neo4j-mcp-gw",
            authorizer_type="CUSTOM_JWT",
            protocol_type="MCP",
            role_arn=gateway_role.role_arn,
            authorizer_configuration=bedrockagentcore.CfnGateway.AuthorizerConfigurationProperty(
                custom_jwt_authorizer=bedrockagentcore.CfnGateway.CustomJWTAuthorizerConfigurationProperty(
                    discovery_url=cognito_discovery_url,
                    allowed_clients=[cognito_user_pool_client.user_pool_client_id],
                    allowed_scopes=[cognito_scope],
                )
            ),
            description="AgentCore MCP Gateway for Neo4j",
            protocol_configuration=bedrockagentcore.CfnGateway.GatewayProtocolConfigurationProperty(
                mcp=bedrockagentcore.CfnGateway.MCPGatewayConfigurationProperty(
                    supported_versions=["2025-03-26"],
                )
            ),
            interceptor_configurations=[
                bedrockagentcore.CfnGateway.GatewayInterceptorConfigurationProperty(
                    interception_points=["REQUEST"],
                    interceptor=bedrockagentcore.CfnGateway.InterceptorConfigurationProperty(
                        lambda_=bedrockagentcore.CfnGateway.LambdaInterceptorConfigurationProperty(
                            arn=interceptor_lambda.function_arn,
                        )
                    ),
                    input_configuration=bedrockagentcore.CfnGateway.InterceptorInputConfigurationProperty(
                        pass_request_headers=True
                    )
                )
            ],
        )

        # 7. Gateway Target — register the Neo4j MCP custom domain as target
        mcp_gateway_target = bedrockagentcore.CfnGatewayTarget(
            self, "McpGatewayTarget",
            gateway_identifier=mcp_gateway.attr_gateway_identifier,
            name="neo4j-mcp",
            description="Neo4j MCP server running on Fargate behind ALB",
            target_configuration=bedrockagentcore.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=bedrockagentcore.CfnGatewayTarget.McpTargetConfigurationProperty(
                    mcp_server=bedrockagentcore.CfnGatewayTarget.McpServerTargetConfigurationProperty(
                        endpoint=f"https://{mcp_fqdn}/mcp",
                    )
                )
            ),
        )
        mcp_gateway_target.node.add_dependency(fargate_service.service)

        # 8. Outputs
        CfnOutput(
            self, "McpFqdn",
            value=mcp_fqdn,
            description="Custom domain for the Neo4j MCP Service"
        )

        CfnOutput(
            self, "Neo4jSecretArn",
            value=neo4j_secret.secret_arn,
            description="ARN of the Neo4j credentials secret"
        )

        CfnOutput(
            self, "InterceptorLambdaArn",
            value=interceptor_lambda.function_arn,
            description="ARN of the Request Interceptor Lambda"
        )

        CfnOutput(
            self, "McpServiceUrl",
            value=f"https://{mcp_fqdn}",
            description="HTTPS URL of the Neo4j MCP Service"
        )

        CfnOutput(
            self, "GatewayArn",
            value=mcp_gateway.attr_gateway_arn,
            description="ARN of the AgentCore MCP Gateway"
        )

        CfnOutput(
            self, "GatewayUrl",
            value=mcp_gateway.attr_gateway_url,
            description="URL of the AgentCore MCP Gateway"
        )

        CfnOutput(
            self, "CognitoUserPoolId",
            value=cognito_user_pool.user_pool_id,
            description="Cognito User Pool ID used by the Gateway authorizer"
        )

        CfnOutput(
            self, "CognitoAppClientId",
            value=cognito_user_pool_client.user_pool_client_id,
            description="Cognito app client ID for client_credentials OAuth"
        )

        CfnOutput(
            self, "CognitoDiscoveryUrl",
            value=cognito_discovery_url,
            description="OIDC discovery URL used by the Gateway JWT authorizer"
        )

        CfnOutput(
            self, "CognitoTokenEndpoint",
            value=cognito_token_endpoint,
            description="Cognito OAuth2 token endpoint for client_credentials"
        )

        CfnOutput(
            self, "CognitoScope",
            value=cognito_scope,
            description="OAuth scope required for Gateway access"
        )

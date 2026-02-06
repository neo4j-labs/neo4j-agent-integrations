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
)
from constructs import Construct

class AgentCoreGatewayStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

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
                "NEO4J_URI": SecretValue.unsafe_plain_text("neo4j+s://demo.neo4jlabs.com:7687"),
                "NEO4J_USERNAME": SecretValue.unsafe_plain_text("companies"),
                "NEO4J_PASSWORD": SecretValue.unsafe_plain_text("companies"),
                "NEO4J_DATABASE": SecretValue.unsafe_plain_text("companies")
            },
            removal_policy=RemovalPolicy.DESTROY  # Clean up secret when stack is destroyed
        )

        # 4. Fargate Service (Neo4j MCP)
        # Using the ApplicationLoadBalancedFargateService pattern for simplicity
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "Neo4jMcpService",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_registry("mcp/server/neo4j:latest"),
                container_port=8080,
                environment={
                    "NEO4J_TRANSPORT_MODE": "http",
                    "NEO4J_MCP_HTTP_PORT": "8080",
                },
                enable_logging=True
            ),
            public_load_balancer=True,
            assign_public_ip=True # Required because we are in Public Subnets
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

        # 6. Outputs
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
            value=f"http://{fargate_service.load_balancer.load_balancer_dns_name}",
            description="URL of the Neo4j MCP Service (ALB)"
        )

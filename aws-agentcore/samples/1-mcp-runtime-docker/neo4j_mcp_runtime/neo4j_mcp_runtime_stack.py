from aws_cdk import (
    Stack,
    CfnOutput,
    SecretValue,
    aws_secretsmanager as secretsmanager,
    aws_iam as iam,
)
from constructs import Construct

class Neo4jMCPRuntimeStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. Create Secrets Manager Secret for Neo4j credentials
        # Defaulting to the public demo database
        neo4j_secret = secretsmanager.Secret(
            self, "Neo4jCredentials",
            description="Credentials for Neo4j MCP AgentCore Runtime",
            secret_object_value={
                "NEO4J_URI": SecretValue.unsafe_plain_text("neo4j+s://demo.neo4jlabs.com:7687"),
                "NEO4J_USERNAME": SecretValue.unsafe_plain_text("companies"),
                "NEO4J_PASSWORD": SecretValue.unsafe_plain_text("companies"),
                "NEO4J_DATABASE": SecretValue.unsafe_plain_text("companies")
            }
        )

        # 2. Create IAM Role for AgentCore Runtime
        # This role allows the runtime to access the secret and invoke Bedrock models
        runtime_role = iam.Role(
            self, "AgentCoreRuntimeRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="IAM Role for AgentCore Runtime with access to Neo4j credentials",
        )

        # Grant the role permission to read the secret
        neo4j_secret.grant_read(runtime_role)

        # Add Bedrock Full Access (required for the agent to invoke models)
        # In a production environment, you should scope this down to specific models
        runtime_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess")
        )
        
        # Add basic lambda execution role just in case (though AgentCore manages execution)
        # Sometimes helpful for debugging or if the runtime uses lambda under the hood in ways we expose
        runtime_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
        )

        # 3. Outputs
        CfnOutput(
            self, "Neo4jSecretArn",
            value=neo4j_secret.secret_arn,
            description="ARN of the Neo4j credentials secret"
        )

        CfnOutput(
            self, "AgentRuntimeRoleArn",
            value=runtime_role.role_arn,
            description="ARN of the IAM Role for AgentCore Runtime"
        )

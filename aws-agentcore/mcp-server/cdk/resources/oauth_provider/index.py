"""
OAuth2 Credential Provider Lambda Handler

This Lambda creates and manages OAuth2 Credential Providers for AgentCore Gateway.
It is used as a CloudFormation Custom Resource to:
1. Create an OAuth2 credential provider on stack creation
2. Delete the provider on stack deletion

The provider enables the Gateway to authenticate with the MCP Runtime
using OAuth2 client credentials flow.
"""

import boto3
import json
import logging
import urllib3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def send_cfn_response(
    event: dict,
    status: str,
    reason: str = None,
    data: dict = None,
    physical_resource_id: str = None,
) -> dict:
    """Send response back to CloudFormation."""
    response_body = {
        "Status": status,
        "Reason": reason or f"{status}: See CloudWatch logs",
        "PhysicalResourceId": physical_resource_id
        or event.get("PhysicalResourceId", "NONE"),
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "Data": data or {},
    }

    logger.info(
        f'Sending CFN response: Status={status}, PhysicalResourceId={response_body["PhysicalResourceId"]}'
    )

    http = urllib3.PoolManager()
    http.request(
        "PUT",
        event["ResponseURL"],
        body=json.dumps(response_body).encode("utf-8"),
        headers={"Content-Type": ""},
    )
    return response_body


def get_client_secret(cognito_client, user_pool_id: str, client_id: str) -> str:
    """Retrieve the client secret from Cognito."""
    response = cognito_client.describe_user_pool_client(
        UserPoolId=user_pool_id, ClientId=client_id
    )
    return response["UserPoolClient"]["ClientSecret"]


def find_existing_provider(agentcore_client, provider_name: str) -> str | None:
    """Check if a provider with this name already exists."""
    try:
        providers = agentcore_client.list_oauth2_credential_providers()
        for provider in providers.get("items", []):
            if provider["name"] == provider_name:
                logger.info(f"Found existing provider: {provider['credentialProviderArn']}")
                return provider["credentialProviderArn"]
    except Exception as e:
        logger.warning(f"Error checking existing providers: {e}")
    return None


def create_oauth_provider(
    agentcore_client,
    provider_name: str,
    discovery_url: str,
    client_id: str,
    client_secret: str,
) -> str:
    """Create a new OAuth2 Credential Provider."""
    response = agentcore_client.create_oauth2_credential_provider(
        name=provider_name,
        credentialProviderVendor="CustomOauth2",
        oauth2ProviderConfigInput={
            "customOauth2ProviderConfig": {
                "oauthDiscovery": {"discoveryUrl": discovery_url},
                "clientId": client_id,
                "clientSecret": client_secret,
            }
        },
    )
    provider_arn = response["credentialProviderArn"]
    logger.info(f"Created OAuth provider: {provider_arn}")
    return provider_arn


def delete_oauth_provider(agentcore_client, provider_name: str) -> None:
    """Delete an OAuth2 Credential Provider."""
    try:
        agentcore_client.delete_oauth2_credential_provider(name=provider_name)
        logger.info(f"Deleted OAuth provider: {provider_name}")
    except Exception as e:
        logger.warning(f"Could not delete provider {provider_name}: {e}")


def handler(event: dict, context) -> dict:
    """
    CloudFormation Custom Resource handler for OAuth2 Credential Provider.

    Required ResourceProperties:
        - ProviderName: Name for the OAuth2 provider
        - UserPoolId: Cognito User Pool ID
        - ClientId: Cognito App Client ID
        - DiscoveryUrl: OIDC discovery URL
        - Region: AWS region
    """
    logger.info(f'Received {event["RequestType"]} request')
    logger.info(f'ResourceProperties: {json.dumps(event.get("ResourceProperties", {}))}')

    try:
        props = event["ResourceProperties"]
        provider_name = props["ProviderName"]
        region = props["Region"]

        agentcore_client = boto3.client("bedrock-agentcore-control", region_name=region)

        # Handle Delete
        if event["RequestType"] == "Delete":
            delete_oauth_provider(agentcore_client, provider_name)
            return send_cfn_response(event, "SUCCESS", physical_resource_id=provider_name)

        # Handle Create/Update
        user_pool_id = props["UserPoolId"]
        client_id = props["ClientId"]
        discovery_url = props["DiscoveryUrl"]

        # Check for existing provider (idempotency)
        existing_arn = find_existing_provider(agentcore_client, provider_name)
        if existing_arn:
            return send_cfn_response(
                event,
                "SUCCESS",
                data={"ProviderArn": existing_arn},
                physical_resource_id=provider_name,
            )

        # Get client secret from Cognito
        cognito_client = boto3.client("cognito-idp", region_name=region)
        client_secret = get_client_secret(cognito_client, user_pool_id, client_id)

        # Create the provider
        provider_arn = create_oauth_provider(
            agentcore_client, provider_name, discovery_url, client_id, client_secret
        )

        return send_cfn_response(
            event,
            "SUCCESS",
            data={"ProviderArn": provider_arn},
            physical_resource_id=provider_name,
        )

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return send_cfn_response(event, "FAILED", reason=str(e))

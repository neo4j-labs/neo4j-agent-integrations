import json
import logging
import os
import time
from typing import TypedDict, Optional
import httpx
import requests
from mcp.client.streamable_http import streamable_http_client
from strands.tools.mcp.mcp_client import MCPClient

logger = logging.getLogger(__name__)


class TokenCache(TypedDict):
    expires_at: float
    access_token: Optional[str]


_token_cache: TokenCache = {"expires_at": 0, "access_token": None}

# Cache for Secrets Manager values (loaded once)
_secrets_cache: Optional[dict] = None


def _load_secrets() -> dict:
    """
    Load Cognito credentials from AWS Secrets Manager.
    The secret must contain COGNITO_CLIENT_ID and COGNITO_CLIENT_SECRET.
    """
    global _secrets_cache
    if _secrets_cache is not None:
        return _secrets_cache

    secret_arn = os.environ.get("SECRET_ARN")
    if not secret_arn:
        return {}

    import boto3
    session = boto3.session.Session()
    sm_client = session.client(service_name="secretsmanager")
    response = sm_client.get_secret_value(SecretId=secret_arn)
    _secrets_cache = json.loads(response["SecretString"])
    logger.info("Loaded Cognito credentials from Secrets Manager")
    return _secrets_cache


def _get_access_token():
    """
    Make a POST request to the Cognito OAuth token URL using client credentials.
    Credentials are loaded from Secrets Manager (SECRET_ARN) when deployed on
    AgentCore, with a fallback to environment variables for local development.
    """

    now = time.time()
    token_ = _token_cache["access_token"]
    if token_ and now < _token_cache["expires_at"] - 30:
        return _token_cache["access_token"]

    secrets = _load_secrets()
    cognito_token_endpoint = os.getenv("COGNITO_TOKEN_ENDPOINT")
    cognito_client_id = secrets.get("COGNITO_CLIENT_ID") or os.getenv("COGNITO_CLIENT_ID")
    cognito_client_secret = secrets.get("COGNITO_CLIENT_SECRET") or os.getenv("COGNITO_CLIENT_SECRET")
    cognito_scope = os.getenv("COGNITO_SCOPE")

    if not cognito_token_endpoint:
        raise RuntimeError("Missing required configuration: COGNITO_TOKEN_ENDPOINT")
    if not cognito_client_id:
        raise RuntimeError("Missing required configuration: COGNITO_CLIENT_ID")
    if not cognito_client_secret:
        raise RuntimeError("Missing required configuration: COGNITO_CLIENT_SECRET")
    try:
        response = requests.post(
            cognito_token_endpoint,
            auth=(cognito_client_id, cognito_client_secret),
            data={
                "grant_type": "client_credentials",
                "scope": cognito_scope,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError("Failed to obtain access token from Cognito") from exc
    token_response = response.json()
    access_token = token_response.get("access_token")
    if not access_token:
        raise RuntimeError("Cognito token endpoint response did not include 'access_token'")

    _token_cache["access_token"] = access_token
    _token_cache["expires_at"] = now + token_response.get("expires_in", 3600)

    return _token_cache["access_token"]


def get_streamable_http_mcp_client() -> MCPClient:
    """
    Returns an MCP Client for AgentCore Gateway compatible with Strands
    """
    gateway_url = os.getenv("GATEWAY_URL")
    if not gateway_url:
        raise RuntimeError("Missing required environment variable: GATEWAY_URL")
    access_token = _get_access_token()
    http_client = httpx.AsyncClient(headers={"Authorization": f"Bearer {access_token}"})
    return MCPClient(lambda: streamable_http_client(gateway_url, http_client=http_client))

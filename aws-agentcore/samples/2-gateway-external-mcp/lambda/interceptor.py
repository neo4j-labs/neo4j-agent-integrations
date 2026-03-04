import boto3
import json
import base64
import logging
import os
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

session = boto3.session.Session()
client = session.client(
    service_name='secretsmanager'
)

def get_secret(secret_name):
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        raise e

    secret_json: dict = json.loads(get_secret_value_response["SecretString"])
    return secret_json

def handler(event, context):
    gateway_request = event["mcp"]["gatewayRequest"]
    request_body = gateway_request["body"]
    request_headers = dict(gateway_request.get("headers") or event.get("headers") or {})

    secret_name = os.environ.get('SECRET_ARN')
    if not secret_name:
        raise Exception("SECRET_ARN environment variable not set")
    secret_json = get_secret(secret_name)

    username = secret_json.get('NEO4J_USERNAME')
    password = secret_json.get('NEO4J_PASSWORD')

    if not username or not password:
        raise Exception("Secret does not contain NEO4J_USERNAME or NEO4J_PASSWORD")
    auth_str = f"{username}:{password}"
    base64_auth = base64.b64encode(auth_str.encode('ascii')).decode('ascii')

    for k in list(request_headers):
        if k.lower() == 'authorization':
            del request_headers[k]
    request_headers["Authorization"] = f"Basic {base64_auth}"

    response = {
        "interceptorOutputVersion": "1.0",
        "mcp": {
            "transformedGatewayRequest": {
                "body": request_body,
                "headers": request_headers,
            }
        }
    }
    return response

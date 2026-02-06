import boto3
import json
import base64
import os
from botocore.exceptions import ClientError

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

    if 'SecretString' in get_secret_value_response:
        return get_secret_value_response['SecretString']

    return base64.b64decode(get_secret_value_response['SecretBinary'])

def handler(event, context):
    """
    AgentCore Gateway Request Interceptor
    Translates OAuth token to Basic Auth for Neo4j
    """    
    # Get secret ARN/Name from environment variable
    secret_name = os.environ.get('SECRET_ARN')
    if not secret_name:
        raise Exception("SECRET_ARN environment variable not set")
        
    # Retrieve credentials (cached/reused via client)
    secret_str = get_secret(secret_name)
    secret_json = json.loads(secret_str)
    
    username = secret_json.get('NEO4J_USERNAME')
    password = secret_json.get('NEO4J_PASSWORD')
    
    if not username or not password:
        raise Exception("Secret does not contain NEO4J_USERNAME or NEO4J_PASSWORD")
    
    # Create Basic Auth header
    auth_str = f"{username}:{password}"
    auth_bytes = auth_str.encode('ascii')
    base64_bytes = base64.b64encode(auth_bytes)
    base64_auth = base64_bytes.decode('ascii')
    
    # Assuming the event contains 'headers' key.
    headers = event.get('headers', {})
    
    if 'authorization' in headers:
        del headers['authorization']
        
    # Inject Basic Auth
    headers['Authorization'] = f"Basic {base64_auth}"
    
    event['headers'] = headers
    
    return event

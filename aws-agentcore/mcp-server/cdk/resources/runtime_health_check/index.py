"""
Runtime Health Check Lambda Handler

This Lambda waits for an AgentCore Runtime to be ready before allowing
dependent resources (like GatewayTarget) to be created.

It is used as a CloudFormation Custom Resource to ensure the Runtime
container is fully warmed up and able to accept connections.
"""

import boto3
import json
import logging
import time
import urllib3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
MAX_POLL_ATTEMPTS = 30  # Maximum number of polling attempts
POLL_INTERVAL_SECONDS = 10  # Time between polls
WARMUP_WAIT_SECONDS = 30  # Additional wait after Runtime is ready


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
        or event.get("PhysicalResourceId", "health-check"),
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "Data": data or {},
    }

    logger.info(f"Sending CFN response: Status={status}")

    http = urllib3.PoolManager()
    http.request(
        "PUT",
        event["ResponseURL"],
        body=json.dumps(response_body).encode("utf-8"),
        headers={"Content-Type": ""},
    )
    return response_body


def extract_runtime_id(runtime_arn: str) -> str:
    """Extract runtime ID from ARN.

    ARN format: arn:aws:bedrock-agentcore:region:account:runtime/id
    """
    return runtime_arn.split("/")[-1]


def get_runtime_status(agentcore_client, runtime_id: str) -> str:
    """Get the current status of a Runtime."""
    response = agentcore_client.get_agent_runtime(agentRuntimeId=runtime_id)
    return response.get("status", "UNKNOWN")


def wait_for_runtime_ready(agentcore_client, runtime_id: str) -> tuple[bool, str]:
    """
    Poll the Runtime until it reaches a ready state.

    Returns:
        tuple: (success: bool, message: str)
    """
    terminal_states = {"FAILED", "DELETING", "DELETED"}
    ready_states = {"ACTIVE", "READY"}

    for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
        try:
            status = get_runtime_status(agentcore_client, runtime_id)
            logger.info(f"Attempt {attempt}/{MAX_POLL_ATTEMPTS}: Runtime status = {status}")

            if status in ready_states:
                logger.info(
                    f"Runtime is {status}, waiting {WARMUP_WAIT_SECONDS}s for container warmup..."
                )
                time.sleep(WARMUP_WAIT_SECONDS)
                logger.info("Runtime warmup complete")
                return True, f"Runtime ready with status: {status}"

            if status in terminal_states:
                return False, f"Runtime in terminal state: {status}"

        except Exception as e:
            logger.warning(f"Error getting runtime status: {e}")

        time.sleep(POLL_INTERVAL_SECONDS)

    return False, "Timeout waiting for Runtime to be ready"


def handler(event: dict, context) -> dict:
    """
    CloudFormation Custom Resource handler for Runtime health check.

    Required ResourceProperties:
        - RuntimeArn: ARN of the Runtime to check
        - Region: AWS region
    """
    logger.info(f'Received {event["RequestType"]} request')

    try:
        # Handle Delete - nothing to clean up
        if event["RequestType"] == "Delete":
            return send_cfn_response(event, "SUCCESS")

        props = event["ResourceProperties"]
        runtime_arn = props["RuntimeArn"]
        region = props["Region"]

        runtime_id = extract_runtime_id(runtime_arn)
        logger.info(f"Waiting for runtime {runtime_id} to be ready...")

        agentcore_client = boto3.client("bedrock-agentcore-control", region_name=region)

        success, message = wait_for_runtime_ready(agentcore_client, runtime_id)

        if success:
            return send_cfn_response(event, "SUCCESS", data={"RuntimeArn": runtime_arn})
        else:
            return send_cfn_response(event, "FAILED", reason=message)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return send_cfn_response(event, "FAILED", reason=str(e))

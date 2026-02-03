#!/usr/bin/env python3
"""
Invoke Agent Programmatically

Demonstrates how to invoke the deployed Neo4j MCP Agent using boto3.

Usage:
    uv run python invoke_agent.py                          # Uses default prompt
    uv run python invoke_agent.py "What is the schema?"    # Custom prompt
    uv run python invoke_agent.py load-test                # Load test mode (random queries every 5s)
    uv run python invoke_agent.py load-test 10             # Load test with custom interval (10s)

Prerequisites:
    - Agent deployed to AgentCore Runtime (./agent.sh deploy)
    - AWS credentials configured
    - .bedrock_agentcore.yaml exists with agent ARN (created by agentcore configure)
"""

import json
import logging
import random
import re
import sys
import time
import uuid
from pathlib import Path

import boto3
import yaml

# Configure logging (WARNING level to keep output clean)
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_agent_config() -> tuple[str, str]:
    """
    Get the agent ARN and region from .bedrock_agentcore.yaml config file.

    This file is created by 'agentcore configure' command.

    Returns:
        Tuple of (agent_arn, region)
    """
    config_file = ".bedrock_agentcore.yaml"

    try:
        with open(config_file) as f:
            config = yaml.safe_load(f)

        # Get the default agent name
        default_agent = config.get("default_agent")
        if not default_agent:
            raise ValueError(f"default_agent not found in {config_file}")

        # Navigate to the agent's ARN
        agents = config.get("agents", {})
        agent_config = agents.get(default_agent, {})
        arn = agent_config.get("bedrock_agentcore", {}).get("agent_arn")
        region = agent_config.get("aws", {}).get("region", "us-west-2")

        if not arn:
            raise ValueError(f"agent_arn not found for agent '{default_agent}' in {config_file}")

        return arn, region

    except FileNotFoundError:
        logger.error(f"{config_file} not found")
        print(f"ERROR: {config_file} not found")
        print("")
        print("Run './agent.sh configure' and './agent.sh deploy' first")
        sys.exit(1)


def invoke_agent(prompt: str) -> dict:
    """
    Invoke the deployed agent with a prompt.

    Args:
        prompt: The user's question

    Returns:
        The agent's response as a dictionary
    """
    agent_arn, region = get_agent_config()

    logger.info(f"Agent ARN: {agent_arn}")
    logger.info(f"Region: {region}")
    logger.info(f"Prompt: {prompt}")

    # Create the AgentCore client
    client = boto3.client("bedrock-agentcore", region_name=region)

    # Prepare the payload
    payload = json.dumps({"prompt": prompt}).encode()

    # Generate a unique session ID
    session_id = str(uuid.uuid4())

    # Invoke the agent
    logger.info("Invoking agent...")
    response = client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=session_id,
        payload=payload,
        qualifier="DEFAULT",
    )

    # Read and parse the streaming response
    content_parts = []
    errors = []
    raw_buffer = ""

    for chunk in response.get("response", []):
        raw_buffer += chunk.decode("utf-8")

    # Parse SSE format - each message is "data: {...}\n\n"
    for message in raw_buffer.split("\n\n"):
        message = message.strip()
        if not message:
            continue

        # Strip "data: " prefix if present
        if message.startswith("data: "):
            message = message[6:]

        # Try to parse as JSON
        try:
            chunk_data = json.loads(message)

            # Handle different response types
            if chunk_data.get("type") == "chunk":
                content_parts.append(chunk_data.get("data", ""))
            elif chunk_data.get("type") == "error":
                errors.append(chunk_data.get("error", "Unknown error"))
            elif chunk_data.get("type") == "complete":
                pass  # End of response
            else:
                # Handle legacy format (direct response)
                if "response" in chunk_data:
                    content_parts.append(chunk_data["response"])
                elif "data" in chunk_data:
                    content_parts.append(chunk_data["data"])
        except json.JSONDecodeError:
            # Not JSON, could be raw text
            if message:
                content_parts.append(message)

    # Join content and clean up escaped newlines
    full_response = "".join(content_parts)
    full_response = full_response.replace("\\n", "\n")

    if errors:
        return {"status": "error", "errors": errors}

    return {
        "status": "success",
        "response": full_response,
    }


def load_queries() -> list[str]:
    """Load queries from queries.txt file."""
    queries_file = Path(__file__).parent / "queries.txt"

    if not queries_file.exists():
        logger.error(f"queries.txt not found at {queries_file}")
        return []

    queries = []
    with open(queries_file) as f:
        for line in f:
            # Match lines starting with a number followed by a period
            match = re.match(r'^\d+\.\s+(.+)$', line.strip())
            if match:
                queries.append(match.group(1))

    return queries


def run_load_test(interval: int = 5):
    """Run continuous load test with random queries at specified interval."""
    queries = load_queries()

    if not queries:
        print("ERROR: No queries found in queries.txt")
        sys.exit(1)

    print("=" * 70)
    print("Neo4j MCP Agent - Load Test Mode")
    print("=" * 70)
    print(f"Loaded {len(queries)} queries from queries.txt")
    print(f"Running a random query every {interval} seconds...")
    print("Press Ctrl+C to stop")
    print("=" * 70)
    print("")

    iteration = 1

    try:
        while True:
            # Select a random query
            query_idx = random.randint(0, len(queries) - 1)
            query = queries[query_idx]

            print("=" * 70)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Iteration {iteration} - Query #{query_idx + 1}")
            print("=" * 70)
            print(f"Query: {query}")
            print("-" * 70)
            print("")

            result = invoke_agent(query)

            if result.get("status") == "success":
                print(result.get("response", "No response"))
            else:
                print(f"ERROR: {result.get('errors', ['Unknown error'])}")

            print("")
            print("-" * 70)
            print(f"Waiting {interval} seconds before next query...")
            print("")

            iteration += 1
            time.sleep(interval)

    except KeyboardInterrupt:
        print("")
        print("=" * 70)
        print(f"Load test stopped after {iteration - 1} iterations")
        print("=" * 70)


def main():
    # Check for load-test mode
    if len(sys.argv) > 1 and sys.argv[1] == "load-test":
        # Parse optional interval argument (default 5 seconds)
        interval = 5
        if len(sys.argv) > 2:
            try:
                interval = int(sys.argv[2])
            except ValueError:
                print(f"ERROR: Invalid interval '{sys.argv[2]}'. Must be a number.")
                sys.exit(1)
        run_load_test(interval)
        return

    # Get prompt from command line or use default
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = "How many aircraft are in the database?"

    print("=" * 70)
    print("Neo4j MCP Agent - Programmatic Invocation")
    print("=" * 70)
    print("")
    print(f"Prompt: {prompt}")
    print("")

    result = invoke_agent(prompt)

    print("")
    print("=" * 70)
    print("Response:")
    print("=" * 70)

    if result.get("status") == "success":
        print(result.get("response", "No response"))
    else:
        print(f"ERROR: {result.get('errors', ['Unknown error'])}")

    print("")


if __name__ == "__main__":
    main()

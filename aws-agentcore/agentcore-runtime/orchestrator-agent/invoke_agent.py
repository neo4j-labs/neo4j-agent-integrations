#!/usr/bin/env python3
"""
Invoke Multi-Agent Orchestrator - Cloud Load Testing

Invokes the deployed orchestrator agent to test routing between
Maintenance and Operations specialist agents.

Usage:
    uv run python invoke_agent.py                          # Uses default prompt
    uv run python invoke_agent.py "What is the schema?"    # Custom prompt
    uv run python invoke_agent.py load-test                # Load test mode (random queries every 5s)
    uv run python invoke_agent.py load-test --interval 10  # Custom interval in seconds

Prerequisites:
    - Orchestrator deployed to AgentCore Runtime (./agent.sh deploy)
    - AWS credentials configured
    - .bedrock_agentcore.yaml exists with agent ARN
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
from botocore.config import Config
import yaml

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Query routing categories (for display purposes)
MAINTENANCE_QUERIES = set(range(1, 11))  # Queries 1-10
OPERATIONS_QUERIES = set(range(11, 21))  # Queries 11-20


def get_agent_config() -> tuple[str, str]:
    """
    Get the agent ARN and region from .bedrock_agentcore.yaml config file.

    Returns:
        Tuple of (agent_arn, region)
    """
    config_file = ".bedrock_agentcore.yaml"

    try:
        with open(config_file) as f:
            config = yaml.safe_load(f)

        default_agent = config.get("default_agent")
        if not default_agent:
            raise ValueError(f"default_agent not found in {config_file}")

        agents = config.get("agents", {})
        agent_config = agents.get(default_agent, {})
        arn = agent_config.get("bedrock_agentcore", {}).get("agent_arn")
        region = agent_config.get("aws", {}).get("region", "us-west-2")

        if not arn:
            raise ValueError(f"agent_arn not found for agent '{default_agent}'")

        return arn, region

    except FileNotFoundError:
        print(f"ERROR: {config_file} not found")
        print("")
        print("Run './agent.sh configure' and './agent.sh deploy' first")
        sys.exit(1)


def invoke_agent(prompt: str, session_id: str = None) -> dict:
    """
    Invoke the deployed orchestrator with a prompt.

    Args:
        prompt: The user's question
        session_id: Optional session ID for continuity

    Returns:
        The agent's response as a dictionary
    """
    agent_arn, region = get_agent_config()

    # Longer timeout for multi-agent orchestration (default 60s is often too short)
    config = Config(
        read_timeout=300,  # 5 minutes for complex queries
        connect_timeout=10,
        retries={"max_attempts": 2, "mode": "adaptive"},
    )
    client = boto3.client("bedrock-agentcore", region_name=region, config=config)

    payload = json.dumps({"prompt": prompt}).encode()

    if session_id is None:
        session_id = str(uuid.uuid4())

    response = client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=session_id,
        payload=payload,
        qualifier="DEFAULT",
    )

    # Parse streaming response
    content_parts = []
    errors = []
    raw_buffer = ""

    for chunk in response.get("response", []):
        raw_buffer += chunk.decode("utf-8")

    # Parse SSE format
    for message in raw_buffer.split("\n\n"):
        message = message.strip()
        if not message:
            continue

        if message.startswith("data: "):
            message = message[6:]

        try:
            chunk_data = json.loads(message)

            if chunk_data.get("type") == "chunk":
                content_parts.append(chunk_data.get("data", ""))
            elif chunk_data.get("type") == "error":
                errors.append(chunk_data.get("error", "Unknown error"))
            elif chunk_data.get("type") == "complete":
                pass
            else:
                if "response" in chunk_data:
                    content_parts.append(chunk_data["response"])
                elif "data" in chunk_data:
                    content_parts.append(chunk_data["data"])
        except json.JSONDecodeError:
            if message:
                content_parts.append(message)

    full_response = "".join(content_parts)
    full_response = full_response.replace("\\n", "\n")

    if errors:
        return {"status": "error", "errors": errors}

    return {
        "status": "success",
        "response": full_response,
    }


def load_queries() -> list[tuple[int, str, str]]:
    """
    Load queries from queries.txt file.

    Returns:
        List of tuples: (query_number, query_text, expected_agent)
    """
    queries_file = Path(__file__).parent / "queries.txt"

    if not queries_file.exists():
        logger.error(f"queries.txt not found at {queries_file}")
        return []

    queries = []
    with open(queries_file) as f:
        for line in f:
            match = re.match(r'^(\d+)\.\s+(.+)$', line.strip())
            if match:
                query_num = int(match.group(1))
                query_text = match.group(2)

                # Determine expected agent based on query number
                if query_num in MAINTENANCE_QUERIES:
                    expected_agent = "Maintenance"
                elif query_num in OPERATIONS_QUERIES:
                    expected_agent = "Operations"
                else:
                    expected_agent = "Unknown"

                queries.append((query_num, query_text, expected_agent))

    return queries


def run_load_test(interval: int = 5):
    """
    Run continuous load test with random queries.

    Args:
        interval: Seconds between queries (default 5)
    """
    queries = load_queries()

    if not queries:
        print("ERROR: No queries found in queries.txt")
        sys.exit(1)

    # Count by domain
    maintenance_count = sum(1 for q in queries if q[2] == "Maintenance")
    operations_count = sum(1 for q in queries if q[2] == "Operations")

    print("=" * 70)
    print("Multi-Agent Orchestrator - Cloud Load Test")
    print("=" * 70)
    print(f"Loaded {len(queries)} queries from queries.txt")
    print(f"  - Maintenance queries: {maintenance_count}")
    print(f"  - Operations queries: {operations_count}")
    print(f"Running a random query every {interval} seconds...")
    print("Press Ctrl+C to stop")
    print("=" * 70)
    print("")

    iteration = 1
    stats = {"Maintenance": 0, "Operations": 0, "errors": 0}

    try:
        while True:
            # Select a random query
            query_num, query_text, expected_agent = random.choice(queries)

            print("=" * 70)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Iteration {iteration}")
            print(f"Query #{query_num} | Expected Agent: {expected_agent}")
            print("=" * 70)
            print(f"Query: {query_text}")
            print("-" * 70)
            print("")

            start_time = time.time()
            result = invoke_agent(query_text)
            elapsed = time.time() - start_time

            if result.get("status") == "success":
                # Truncate long responses for readability
                response = result.get("response", "No response")
                if len(response) > 1000:
                    response = response[:1000] + "\n... [truncated]"
                print(response)
                stats[expected_agent] += 1
            else:
                print(f"ERROR: {result.get('errors', ['Unknown error'])}")
                stats["errors"] += 1

            print("")
            print("-" * 70)
            print(f"Elapsed: {elapsed:.1f}s | Stats: M={stats['Maintenance']} O={stats['Operations']} E={stats['errors']}")
            print(f"Waiting {interval} seconds...")
            print("")

            iteration += 1
            time.sleep(interval)

    except KeyboardInterrupt:
        print("")
        print("=" * 70)
        print(f"Load test stopped after {iteration - 1} iterations")
        print(f"Final Stats: Maintenance={stats['Maintenance']} Operations={stats['Operations']} Errors={stats['errors']}")
        print("=" * 70)


def main():
    # Check for load-test mode
    if len(sys.argv) > 1 and sys.argv[1] == "load-test":
        # Check for custom interval
        interval = 5
        if "--interval" in sys.argv:
            try:
                idx = sys.argv.index("--interval")
                interval = int(sys.argv[idx + 1])
            except (IndexError, ValueError):
                print("ERROR: --interval requires a number")
                sys.exit(1)

        run_load_test(interval)
        return

    # Single query mode
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = "What are the most common maintenance faults?"

    print("=" * 70)
    print("Multi-Agent Orchestrator - Cloud Invocation")
    print("=" * 70)
    print("")
    print(f"Prompt: {prompt}")
    print("")

    start_time = time.time()
    result = invoke_agent(prompt)
    elapsed = time.time() - start_time

    print("")
    print("=" * 70)
    print(f"Response (elapsed: {elapsed:.1f}s):")
    print("=" * 70)

    if result.get("status") == "success":
        print(result.get("response", "No response"))
    else:
        print(f"ERROR: {result.get('errors', ['Unknown error'])}")

    print("")


if __name__ == "__main__":
    main()

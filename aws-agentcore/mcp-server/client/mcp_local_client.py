#!/usr/bin/env python3
"""
Neo4j MCP Local Client

Full-featured client for managing and testing the Neo4j MCP server running locally
in Docker with env auth mode. Handles server lifecycle (start/stop) and MCP operations.

Usage:
    python mcp_client.py start                           # Start local Docker server
    python mcp_client.py stop                            # Stop local Docker server
    python mcp_client.py test                            # Run full test suite
    python mcp_client.py tools                           # List available tools
    python mcp_client.py call <tool_name> [json_args]    # Call a specific tool
    python mcp_client.py help                            # Show help

Environment:
    MCP_SERVER_URL - Server URL (default: http://localhost:8000/mcp)
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

from mcp_operations import (
    connect_and_run,
    run_full_tests,
    list_tools,
    call_tool,
)

# Configuration
CONTAINER_NAME = "neo4j-mcp-server"
DEFAULT_SERVER_URL = "http://localhost:8000/mcp"
SCRIPT_DIR = Path(__file__).parent.parent  # mcp-server directory
ENV_FILE = SCRIPT_DIR.parent / ".env"


def load_env() -> dict:
    """Load environment variables from .env file."""
    env_vars = {}
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    # Remove quotes if present
                    value = value.strip().strip("'\"")
                    env_vars[key.strip()] = value
    return env_vars


def check_server(url: str = DEFAULT_SERVER_URL, timeout: int = 2) -> bool:
    """Check if the server is responding."""
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(url, method="GET")
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except (urllib.error.URLError, TimeoutError, ConnectionRefusedError):
        return False


def start_server() -> bool:
    """Start the local Docker server with env auth mode."""
    env_vars = load_env()

    # Check required env vars
    required = ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"]
    missing = [k for k in required if k not in env_vars]
    if missing:
        print(f"Error: Missing required environment variables: {', '.join(missing)}")
        print(f"Please set them in {ENV_FILE}")
        return False

    print("Starting Neo4j MCP server (env auth mode)...")
    print()

    # Stop existing container if running
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True,
    )

    # Build docker run command
    docker_cmd = [
        "docker", "run", "-d",
        "--name", CONTAINER_NAME,
        "-p", "8000:8000",
        "-e", f"NEO4J_URI={env_vars['NEO4J_URI']}",
        "-e", f"NEO4J_DATABASE={env_vars.get('NEO4J_DATABASE', 'neo4j')}",
        "-e", f"NEO4J_USERNAME={env_vars['NEO4J_USERNAME']}",
        "-e", f"NEO4J_PASSWORD={env_vars['NEO4J_PASSWORD']}",
        "-e", "NEO4J_MCP_TRANSPORT=http",
        "-e", "NEO4J_MCP_HTTP_HOST=0.0.0.0",
        "-e", "NEO4J_MCP_HTTP_PORT=8000",
        "-e", "NEO4J_MCP_HTTP_AUTH_MODE=env",
        "-e", "NEO4J_LOG_LEVEL=debug",
        "-e", "NEO4J_READ_ONLY=true",
        "neo4j-mcp-server:latest",
    ]

    result = subprocess.run(docker_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error starting container: {result.stderr}")
        return False

    print(f"Container started: {CONTAINER_NAME}")
    print(f"Server URL: {DEFAULT_SERVER_URL}")
    print()
    print("Waiting for server to be ready...")

    # Wait for server to be ready
    for i in range(10):
        time.sleep(2)
        if check_server():
            print("Server is ready!")
            return True
        print(f"  Attempt {i + 1}/10...")

    print(f"Error: Server did not start. Check logs with: docker logs {CONTAINER_NAME}")
    return False


def stop_server() -> None:
    """Stop the local Docker server."""
    print("Stopping Neo4j MCP server...")
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True,
    )
    print("Done")


def show_help(mcp_url: str) -> None:
    """Show help message."""
    print(f"""Neo4j MCP Local Client

Target: Local Docker container at {mcp_url}
Auth:   None (env auth mode - credentials from environment)

Usage: python mcp_client.py <command> [args]

Commands:
  start                 Start local MCP server (Docker, env auth mode)
  stop                  Stop local MCP server
  test                  Run full test suite
  tools                 List available tools
  call <tool> [json]    Call a specific tool
  help                  Show this help message

Examples:
  python mcp_client.py start
  python mcp_client.py test
  python mcp_client.py tools
  python mcp_client.py call get-schema '{{}}'
  python mcp_client.py call read-cypher '{{"query": "MATCH (n) RETURN count(n)"}}'

Environment:
  MCP_SERVER_URL - Server URL (default: {DEFAULT_SERVER_URL})

See also:
  ./cloud.sh      - Cloud AgentCore testing (Cognito auth)
""")


async def run_mcp_command(command: str, args: list) -> int:
    """Run an MCP command that requires server connection."""
    mcp_url = os.getenv("MCP_SERVER_URL", DEFAULT_SERVER_URL)

    # Check if server is running
    if not check_server(mcp_url):
        print(f"Error: Server not responding at {mcp_url}")
        print("Start the server first: python mcp_client.py start")
        return 1

    print(f"Connecting to Neo4j MCP server at {mcp_url}...")
    print("Auth mode: env (no headers needed)")
    print()

    try:
        if command == "test":
            await connect_and_run(mcp_url, run_full_tests)
        elif command == "tools":
            await connect_and_run(mcp_url, list_tools)
        elif command == "call":
            if len(args) < 1:
                print("Error: Tool name required")
                print("Usage: python mcp_client.py call <tool_name> [json_args]")
                return 1
            tool_name = args[0]
            args_json = args[1] if len(args) > 1 else "{}"
            await connect_and_run(mcp_url, call_tool, tool_name, args_json)
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


def main() -> int:
    """Main entry point."""
    mcp_url = os.getenv("MCP_SERVER_URL", DEFAULT_SERVER_URL)

    if len(sys.argv) < 2:
        show_help(mcp_url)
        return 0

    command = sys.argv[1]
    args = sys.argv[2:]

    if command in ("help", "--help", "-h"):
        show_help(mcp_url)
        return 0
    elif command == "start":
        return 0 if start_server() else 1
    elif command == "stop":
        stop_server()
        return 0
    elif command in ("test", "tools", "call"):
        return asyncio.run(run_mcp_command(command, args))
    else:
        print(f"Unknown command: {command}")
        print("Valid commands: start, stop, test, tools, call, help")
        return 1


if __name__ == "__main__":
    sys.exit(main())

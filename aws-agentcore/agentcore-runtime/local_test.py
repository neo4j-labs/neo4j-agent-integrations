#!/usr/bin/env python3
"""
Local Testing Tool for Neo4j MCP Agents

Commands:
    sync-credentials    Copy .mcp-credentials.json to agent directories
    build              Build Docker image for an agent
    run                Run agent container locally
    stop               Stop running agent container
    test               Send test request to running agent
    all                Sync credentials, build, run, and test

Usage:
    uv run local-test sync-credentials
    uv run local-test build basic-agent
    uv run local-test run basic-agent
    uv run local-test test basic-agent
    uv run local-test all basic-agent
"""

import json
import os
import shutil
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(help="Local testing tools for Neo4j MCP agents")
console = Console()

# Project paths
SCRIPT_DIR = Path(__file__).parent.resolve()
MCP_SERVER_DIR = SCRIPT_DIR.parent / "mcp-server"
CREDENTIALS_SOURCE = MCP_SERVER_DIR / ".mcp-credentials.json"

AGENT_DIRS = {
    "basic-agent": SCRIPT_DIR / "basic-agent",
    "orchestrator-agent": SCRIPT_DIR / "orchestrator-agent",
}

CONTAINER_NAME_PREFIX = "neo4j-agent"
DEFAULT_PORT = 8080


class AgentType(str, Enum):
    basic_agent = "basic-agent"
    orchestrator_agent = "orchestrator-agent"


def get_container_name(agent: str) -> str:
    """Get Docker container name for an agent."""
    return f"{CONTAINER_NAME_PREFIX}-{agent}"


def get_image_name(agent: str) -> str:
    """Get Docker image name for an agent."""
    return f"agentcore/{agent.replace('-', '')}"


def run_command(cmd: list[str], cwd: Optional[Path] = None, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a shell command."""
    if capture:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return subprocess.run(cmd, cwd=cwd)


@app.command()
def sync_credentials():
    """Copy .mcp-credentials.json from mcp-server to agent directories."""
    console.print("\n[bold blue]Syncing MCP Credentials[/bold blue]\n")

    # Check source exists
    if not CREDENTIALS_SOURCE.exists():
        console.print(f"[red]ERROR: Source credentials not found:[/red] {CREDENTIALS_SOURCE}")
        console.print("\nMake sure the Neo4j MCP server has been deployed and credentials generated.")
        console.print(f"Expected path: {CREDENTIALS_SOURCE}")
        raise typer.Exit(1)

    # Read source to validate it's valid JSON
    try:
        with open(CREDENTIALS_SOURCE) as f:
            creds = json.load(f)
        console.print(f"[green]✓[/green] Source credentials found: {CREDENTIALS_SOURCE}")
        console.print(f"  Gateway URL: {creds.get('gateway_url', 'N/A')}")
    except json.JSONDecodeError as e:
        console.print(f"[red]ERROR: Invalid JSON in credentials file:[/red] {e}")
        raise typer.Exit(1)

    # Copy to each agent directory
    console.print()
    for agent_name, agent_dir in AGENT_DIRS.items():
        dest = agent_dir / ".mcp-credentials.json"
        if not agent_dir.exists():
            console.print(f"[yellow]⚠[/yellow] Agent directory not found: {agent_dir}")
            continue

        shutil.copy2(CREDENTIALS_SOURCE, dest)
        console.print(f"[green]✓[/green] Copied to {agent_name}/")

    console.print("\n[green]Credentials synced successfully![/green]\n")


@app.command()
def build(
    agent: AgentType = typer.Argument(..., help="Agent to build (basic-agent or orchestrator-agent)"),
    platform: str = typer.Option("linux/arm64", help="Docker platform (linux/arm64 for AgentCore)"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Build without Docker cache"),
):
    """Build Docker image for an agent."""
    agent_name = agent.value
    agent_dir = AGENT_DIRS[agent_name]
    image_name = get_image_name(agent_name)

    console.print(f"\n[bold blue]Building Docker Image: {agent_name}[/bold blue]\n")

    # Check Dockerfile exists
    dockerfile = agent_dir / "Dockerfile"
    if not dockerfile.exists():
        console.print(f"[red]ERROR: Dockerfile not found:[/red] {dockerfile}")
        raise typer.Exit(1)

    # Check credentials exist
    creds_file = agent_dir / ".mcp-credentials.json"
    if not creds_file.exists():
        console.print(f"[yellow]⚠ Warning: .mcp-credentials.json not found in {agent_name}/[/yellow]")
        console.print("  Run 'uv run local-test sync-credentials' first.")
        console.print()

    # Build command
    cmd = ["docker", "build", "--platform", platform, "-t", f"{image_name}:latest"]
    if no_cache:
        cmd.append("--no-cache")
    cmd.append(".")

    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")

    result = run_command(cmd, cwd=agent_dir)
    if result.returncode != 0:
        console.print(f"\n[red]Build failed with exit code {result.returncode}[/red]")
        raise typer.Exit(result.returncode)

    console.print(f"\n[green]✓ Image built successfully: {image_name}:latest[/green]\n")


@app.command()
def run(
    agent: AgentType = typer.Argument(..., help="Agent to run (basic-agent or orchestrator-agent)"),
    port: int = typer.Option(DEFAULT_PORT, help="Port to expose"),
    detach: bool = typer.Option(True, "-d", "--detach", help="Run in background"),
    model: Optional[str] = typer.Option(None, "--model", help="Override MODEL_ID environment variable"),
):
    """Run agent container locally with AWS credentials."""
    agent_name = agent.value
    image_name = get_image_name(agent_name)
    container_name = get_container_name(agent_name)

    console.print(f"\n[bold blue]Running Agent Container: {agent_name}[/bold blue]\n")

    # Stop existing container if running
    stop_result = run_command(["docker", "stop", container_name], capture=True)
    if stop_result.returncode == 0:
        console.print(f"[yellow]Stopped existing container: {container_name}[/yellow]")
        run_command(["docker", "rm", container_name], capture=True)

    # Also stop any other agent container that might be using the port
    for other_agent in AGENT_DIRS:
        if other_agent != agent_name:
            other_container = get_container_name(other_agent)
            check = run_command(["docker", "ps", "-q", "-f", f"name={other_container}"], capture=True)
            if check.stdout.strip():
                console.print(f"[yellow]Stopping {other_container} (port conflict)[/yellow]")
                run_command(["docker", "stop", other_container], capture=True)
                run_command(["docker", "rm", other_container], capture=True)

    # Build docker run command
    cmd = ["docker", "run"]

    if detach:
        cmd.append("-d")

    cmd.extend([
        "--name", container_name,
        "-p", f"{port}:8080",
        # Mount AWS credentials (read-write for SSO cache)
        "-v", f"{Path.home()}/.aws:/root/.aws",
        # Pass AWS environment variables
        "-e", f"AWS_REGION={os.environ.get('AWS_REGION', 'us-west-2')}",
        "-e", f"AWS_PROFILE={os.environ.get('AWS_PROFILE', 'default')}",
    ])

    # Pass through AWS session credentials if present
    for env_var in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]:
        if env_var in os.environ:
            cmd.extend(["-e", env_var])

    # Override model if specified
    if model:
        cmd.extend(["-e", f"MODEL_ID={model}"])

    cmd.append(f"{image_name}:latest")

    console.print(f"[dim]Running: docker run ... {image_name}:latest[/dim]\n")

    result = run_command(cmd)
    if result.returncode != 0:
        console.print(f"\n[red]Failed to start container[/red]")
        raise typer.Exit(result.returncode)

    if detach:
        console.print(f"[green]✓ Container started: {container_name}[/green]")
        console.print(f"  Port: {port}")
        console.print(f"\n[dim]View logs: docker logs -f {container_name}[/dim]")
        console.print(f"[dim]Stop: uv run local-test stop {agent_name}[/dim]\n")

        # Wait a moment for container to start
        console.print("Waiting for container to initialize...")
        time.sleep(3)

        # Check if container is still running
        check = run_command(["docker", "ps", "-q", "-f", f"name={container_name}"], capture=True)
        if not check.stdout.strip():
            console.print(f"\n[red]Container exited unexpectedly. Check logs:[/red]")
            console.print(f"  docker logs {container_name}")
            raise typer.Exit(1)

        console.print(f"[green]✓ Container is running[/green]\n")


@app.command()
def stop(
    agent: AgentType = typer.Argument(..., help="Agent to stop (basic-agent or orchestrator-agent)"),
):
    """Stop running agent container."""
    agent_name = agent.value
    container_name = get_container_name(agent_name)

    console.print(f"\n[bold blue]Stopping Container: {container_name}[/bold blue]\n")

    result = run_command(["docker", "stop", container_name], capture=True)
    if result.returncode == 0:
        run_command(["docker", "rm", container_name], capture=True)
        console.print(f"[green]✓ Container stopped and removed[/green]\n")
    else:
        console.print(f"[yellow]Container not running or not found[/yellow]\n")


@app.command()
def test(
    agent: AgentType = typer.Argument(..., help="Agent to test (basic-agent or orchestrator-agent)"),
    prompt: str = typer.Option("What is the database schema?", "-p", "--prompt", help="Test prompt to send"),
    port: int = typer.Option(DEFAULT_PORT, help="Port the agent is running on"),
    timeout: int = typer.Option(120, help="Request timeout in seconds"),
):
    """Send test request to running agent."""
    agent_name = agent.value
    url = f"http://localhost:{port}/invocations"

    console.print(f"\n[bold blue]Testing Agent: {agent_name}[/bold blue]\n")
    console.print(f"URL: {url}")
    console.print(f"Prompt: {prompt}")
    console.print()

    payload = {"prompt": prompt}

    console.print("[dim]Sending request (this may take a minute)...[/dim]")

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

    except httpx.ConnectError:
        console.print(f"\n[red]ERROR: Could not connect to {url}[/red]")
        console.print("Make sure the agent container is running:")
        console.print(f"  uv run local-test run {agent_name}")
        raise typer.Exit(1)
    except httpx.ReadTimeout:
        console.print(f"\n[red]ERROR: Request timed out after {timeout}s[/red]")
        console.print("The agent may still be processing. Check logs:")
        console.print(f"  docker logs -f {get_container_name(agent_name)}")
        raise typer.Exit(1)

    console.print()
    console.print(f"[bold]Status:[/bold] {response.status_code}")
    console.print()

    try:
        result = response.json()
        console.print(Panel(
            json.dumps(result, indent=2),
            title="Response",
            border_style="green" if response.status_code == 200 else "red",
        ))
    except json.JSONDecodeError:
        console.print(Panel(
            response.text,
            title="Response (raw)",
            border_style="yellow",
        ))

    console.print()


@app.command(name="all")
def run_all(
    agent: AgentType = typer.Argument(..., help="Agent to build, run, and test"),
    prompt: str = typer.Option("What is the database schema?", "-p", "--prompt", help="Test prompt"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Build without Docker cache"),
):
    """Sync credentials, build, run, and test an agent."""
    agent_name = agent.value

    console.print(Panel(
        f"Running full local test for [bold]{agent_name}[/bold]",
        title="Local Test",
        border_style="blue",
    ))

    # Step 1: Sync credentials
    console.print("\n[bold]Step 1/4: Syncing credentials[/bold]")
    sync_credentials()

    # Step 2: Build
    console.print("\n[bold]Step 2/4: Building Docker image[/bold]")
    build(agent, platform="linux/arm64", no_cache=no_cache)

    # Step 3: Run
    console.print("\n[bold]Step 3/4: Starting container[/bold]")
    run(agent, port=DEFAULT_PORT, detach=True, model=None)

    # Give container more time to fully initialize
    console.print("Waiting for agent to be ready...")
    time.sleep(5)

    # Step 4: Test
    console.print("\n[bold]Step 4/4: Testing agent[/bold]")
    test(agent, prompt=prompt, port=DEFAULT_PORT, timeout=120)

    console.print(Panel(
        f"[green]Local test completed successfully![/green]\n\n"
        f"Container: {get_container_name(agent_name)}\n"
        f"Stop with: uv run local-test stop {agent_name}",
        title="Done",
        border_style="green",
    ))


@app.command()
def logs(
    agent: AgentType = typer.Argument(..., help="Agent to view logs for"),
    follow: bool = typer.Option(True, "-f", "--follow", help="Follow log output"),
    tail: int = typer.Option(100, "-n", "--tail", help="Number of lines to show"),
):
    """View logs from running agent container."""
    container_name = get_container_name(agent.value)

    cmd = ["docker", "logs"]
    if follow:
        cmd.append("-f")
    cmd.extend(["--tail", str(tail), container_name])

    console.print(f"[dim]Viewing logs for {container_name}...[/dim]\n")
    os.execvp("docker", cmd)


@app.command()
def status():
    """Show status of agent containers."""
    console.print("\n[bold blue]Agent Container Status[/bold blue]\n")

    for agent_name in AGENT_DIRS:
        container_name = get_container_name(agent_name)
        result = run_command(
            ["docker", "ps", "-a", "--filter", f"name={container_name}", "--format", "{{.Status}}"],
            capture=True,
        )
        status = result.stdout.strip() or "Not created"

        if "Up" in status:
            console.print(f"[green]●[/green] {agent_name}: {status}")
        elif status == "Not created":
            console.print(f"[dim]○[/dim] {agent_name}: {status}")
        else:
            console.print(f"[red]●[/red] {agent_name}: {status}")

    console.print()


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()

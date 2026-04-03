import os
import subprocess
import sys

def neo4j_mcp_server(args: list[str] = []):
    command = ["neo4j-mcp-server"] + args

    print(f"Starting Neo4j MCP Server: {' '.join(command)}", file=sys.stderr)
    print("Neo4j MCP Server listening on http://127.0.0.1:8000", file=sys.stderr)
    print("Press Ctrl+C to stop.", file=sys.stderr)

    try:
        # Execute the process
        process = subprocess.Popen(
            command,
            env=os.environ,
            stderr=sys.stderr, # Server logs appear in your App logs
            stdout=sys.stdout
        )

        # Keep the script waiting for the process to finish
        # This blocks the script until you press Ctrl+C or the server crashes
        process.wait()

    except KeyboardInterrupt:
        print("\nReceived interrupt signal. Stopping the Neo4j MCP Server...", file=sys.stderr)
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        print("Neo4j MCP Server stopped.", file=sys.stderr)
    except Exception as e:
        print(f"Neo4j MCP Error: {e}", file=sys.stderr)
        sys.exit(1)

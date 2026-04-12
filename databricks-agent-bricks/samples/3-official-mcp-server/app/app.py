import os
import sys
import time
import threading
from fastapi import FastAPI, Request, Response
from fastapi.responses import Response as FastAPIResponse
import httpx
import uvicorn
from neo4j_mcp_server_process import neo4j_mcp_server

try:
    URI = os.getenv("NEO4J_URI")
    NEO4J_USER = os.getenv("NEO4J_USER")
    NEO4J_PASS = os.getenv("NEO4J_PASS")
except Exception as e:
    # Fallback for local tests
    # In production on Databricks, this should fail if secrets are missing
    print(f"Warning: Secrets not found ({e}). Check that the application has been configured to access the necessary secrets, that the resource keys are correctly set and that the app.yaml is properly configured to map the resource keys into environment variables.")
    URI = os.getenv("NEO4J_URI", "neo4j://localhost")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASS = os.getenv("NEO4J_PASS", "password")

TARGET_URL = "http://127.0.0.1:8001"  # neo4j-mcp-server local address
CUSTOM_HEADER_NAME = "Authorization"
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASS", "password")
basic_auth = httpx.BasicAuth(NEO4J_USER, NEO4J_PASS)  # Build auth header for the Neo4j server using credentials from environment variables

app = FastAPI()
http_client = httpx.AsyncClient(timeout=60.0)

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy(request: Request, path: str):
    # Build the target URL by combining the base TARGET_URL with the incoming request path and query parameters
    url = f"{TARGET_URL}/{path}"
    if request.url.query:
        url += f"?{request.url.query}"

    # Copy the original headers and add your custom header for authentication to the Neo4j server
    headers = dict(request.headers)
    headers.pop("host", None)  # Remove the Host header to avoid conflicts with the target server
    headers[CUSTOM_HEADER_NAME] = basic_auth._auth_header  # Add the Basic authentication header

    # Read the request body (if any) to forward it to the target server
    body = await request.body()

    try:
        # Forward the request to the Neo4j MCP Server using the httpx client
        resp = await http_client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body,
            follow_redirects=False
        )

        # Prepare the response headers, excluding certain headers that should not be forwarded back to the client
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection', 'keep-alive']
        response_headers = {
            name: value for name, value in resp.headers.items()
            if name.lower() not in excluded_headers
        }

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=response_headers
        )
    except httpx.RequestError as exc:
        return Response(
            content=f"Error contacting target server: {str(exc)}",
            status_code=503
        )

def run_neo4j_server():
    """Wrapper function to start the Neo4j server in a separate thread"""
    print("Starting Neo4j MCP Server...", file=sys.stderr)
    try:
        neo4j_mcp_server(args=[
            '--neo4j-uri', os.getenv("NEO4J_URI", URI),
            '--neo4j-database', os.getenv("NEO4J_DATABASE", "neo4j"),
            '--neo4j-transport-mode', 'http',
            '--neo4j-read-only', 'true',
            '--neo4j-telemetry', 'false',
            '--neo4j-http-host', '0.0.0.0',
            '--neo4j-http-port', '8001',
            '--neo4j-http-allowed-origins', '*'
        ])
    except Exception as e:
        print(f"Critical error in Neo4j server: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':

    # Start the Neo4j server in a separate thread
    t = threading.Thread(target=run_neo4j_server, daemon=True)
    t.start()

    # Small delay to ensure the Neo4j server is listening before starting the proxy
    # You might want to implement a retry loop instead of a fixed sleep
    print("Waiting for Neo4j MCP Server to start...", file=sys.stderr)
    time.sleep(3)

    # 2. Start Uvicorn
    print("Starting FastAPI proxy for Neo4j MCP Server on http://0.0.0.0:8000", file=sys.stderr)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

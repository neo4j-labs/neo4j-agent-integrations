# Neo4j MCP Orchestrator Agent - Dockerfile for AgentCore Runtime
#
# Build: docker build --platform linux/arm64 -t neo4j-orchestrator-agent .
# Test:  docker run -p 8080:8080 neo4j-orchestrator-agent
#
# AgentCore Requirements:
#   - Architecture: ARM64 (aarch64)
#   - Port: 8080
#   - Entry point: Must start HTTP server on port 8080

FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install system dependencies and uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

# Add uv to PATH
ENV PATH="/root/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy dependency files first (for better caching)
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Copy all agent source files
COPY orchestrator_agent.py ./
COPY maintenance_agent.py ./
COPY operations_agent.py ./

# Copy MCP credentials if present (required for Gateway access)
# Use a wildcard to avoid build failure if file doesn't exist
COPY .mcp-credentials.jso[n] ./

# AgentCore expects port 8080
EXPOSE 8080

# Run the orchestrator agent
# Use uv run to ensure we're in the venv
CMD ["uv", "run", "python", "orchestrator_agent.py"]

# Use the official, lightweight Python 3.11 slim image
FROM python:3.11-slim

# Force Python logs to show up immediately in Cloud Logging
ENV PYTHONUNBUFFERED=True

# Install OS-level dependencies needed to fetch the Neo4j MCP binary
RUN apt-get update && apt-get install -y wget tar curl jq && rm -rf /var/lib/apt/lists/*

# Fetch and install the latest Neo4j MCP Linux binary
RUN VERSION=$(curl -s https://api.github.com/repos/neo4j/mcp/releases/latest | jq -r .tag_name) && \
    wget -q https://github.com/neo4j/mcp/releases/download/${VERSION}/neo4j-mcp_Linux_x86_64.tar.gz && \
    tar -xzf neo4j-mcp_Linux_x86_64.tar.gz && \
    chmod +x neo4j-mcp && \
    mv neo4j-mcp /usr/local/bin/ && \
    rm neo4j-mcp_Linux_x86_64.tar.gz

# Set the working directory inside the container
WORKDIR /app

# Copy the dependencies file first to leverage Docker layer caching
COPY requirements.txt .

# Install the dependencies without storing cache to keep the image small
RUN pip install --no-cache-dir -r requirements.txt

# Copy your main.py and any other necessary files into the container
COPY . .

# Expose port 8080 (the default port expected by Google Cloud Run)
EXPOSE 8080

# Start the FastAPI server using Uvicorn on port 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
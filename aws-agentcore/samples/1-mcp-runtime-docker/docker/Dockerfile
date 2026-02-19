#TODO wait for https://github.com/neo4j/mcp/pull/179 to be released and use it
#FROM mcp/neo4j:latest
FROM mcp-neo4j:adjusted-15

ENV NEO4J_MCP_HTTP_HOST=0.0.0.0
ENV NEO4J_MCP_HTTP_PORT=8000
ENV NEO4J_TRANSPORT_MODE=http

EXPOSE 8000
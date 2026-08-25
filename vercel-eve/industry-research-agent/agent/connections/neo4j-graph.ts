import { defineMcpClientConnection } from "eve/connections";
import { MCP_TOOLS, MCP_URL, neo4jMcpHeaders } from "../lib/neo4j";

export default defineMcpClientConnection({
  url: MCP_URL,
  description:
    "The Neo4j knowledge graph of 250k organizations, people, and news articles. " +
    "Read the graph's labels, properties, and relationship types, and run read-only " +
    "Cypher against it. Use for anything structural — investors, subsidiaries, " +
    "industries, counts — as opposed to the article text, which `search_news` covers.",
  headers: neo4jMcpHeaders,

  tools: {
    allow: [...MCP_TOOLS],
  },
});

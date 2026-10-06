// Talks to the local MCP server in mcp-server/ (`npm run chat` starts it).
// If it isn't running, the agent just uses its other tools.
import { defineMcpClientConnection } from "eve/connections";
import { INVESTMENTS_MCP_URL } from "../lib/neo4j";

export default defineMcpClientConnection({
  url: INVESTMENTS_MCP_URL,
  description:
    "Investors in a company, from the Neo4j knowledge graph. Given an exact company " +
    "name, get_investments returns the ids, names, and types of the investors recorded " +
    "against it. Use it for 'who invested in X' instead of writing Cypher by hand.",

  // No auth needed: it only runs on localhost.
  tools: {
    allow: ["get_investments"],
  },
});

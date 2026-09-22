import { defineEval } from "eve/evals";

// Needs the local MCP server running (`npm run mcp` or `npm run chat`).
export default defineEval({
  description: "A 'who invested in X' question goes to the local investments MCP server.",
  tags: ["graph"],
  async test(t) {
    await t.send("Who are the investors in Neo4j?");

    t.succeeded();
    t.calledTool("neo4j-investments__get_investments");
  },
});

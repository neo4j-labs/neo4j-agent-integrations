import { defineEval } from "eve/evals";

export default defineEval({
  description: "A company question is answered from the news graph, not from model recall.",
  tags: ["graph"],
  async test(t) {
    await t.send("What has been written in the news about Neo4j? Use the graph.");

    t.succeeded();
    t.calledTool("search_news");
  },
});

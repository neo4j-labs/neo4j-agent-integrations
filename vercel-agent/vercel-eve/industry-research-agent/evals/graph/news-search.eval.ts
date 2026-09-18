import { defineEval } from "eve/evals";

/**
 * The news graph is the agent's only domain tool now, so the check is that a
 * company question reaches it rather than being answered from model recall.
 *
 * No `includes` assertion on the reply: the demo dataset's article set is
 * fixed but its coverage of any one company is not, and a brittle string check
 * would fail for the wrong reason. `calledTool` is the behaviour under test.
 */
export default defineEval({
  description: "A company question is answered from the news graph, not from model recall.",
  tags: ["graph"],
  async test(t) {
    await t.send("What has been written in the news about Neo4j? Use the graph.");

    t.succeeded();
    t.calledTool("search_news");
  },
});

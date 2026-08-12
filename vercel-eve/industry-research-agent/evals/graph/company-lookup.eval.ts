import { defineEval } from "eve/evals";
import { includes } from "eve/evals/expect";

export default defineEval({
  description: "The agent answers company questions from the graph, not from model recall.",
  tags: ["graph"],
  async test(t) {
    await t.send("Who is the CEO of Neo4j? Use the graph.");

    t.succeeded();
    t.calledTool("company_profile");
    t.check(t.reply, includes("Emil Eifrem"));
  },
});

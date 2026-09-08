import { defineEval } from "eve/evals";
import { includes } from "eve/evals/expect";

/**
 * The check that separates memory from conversation history: a fact stated in
 * one session has to survive into a different session.
 *
 * `t.newSession()` discards the transcript entirely, so anything the agent
 * still knows afterwards came out of NAMS.
 *
 * The recall query reuses the user's own noun ("coverage area"). Retrieval
 * on the hosted NAMS API is lexical, so a paraphrase can miss a memory that is
 * definitely stored.
 */
const COVERAGE_AREA = "undersea cable operators";

export default defineEval({
  description: "A fact stored in one session is recalled in a fresh session.",
  tags: ["memory"],
  async test(t) {
    await t.send(`Remember this about me: my research coverage area is ${COVERAGE_AREA}.`);
    t.succeeded();

    await t.newSession();

    await t.send("What is my research coverage area?");
    t.succeeded();
    t.check(t.reply, includes("undersea cable"));
  },
});

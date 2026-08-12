import { defineEval } from "eve/evals";
import { includes } from "eve/evals/expect";

/**
 * The check that separates memory from conversation history: a fact stated in
 * one session has to survive into a different session.
 *
 * `t.newSession()` discards the transcript entirely, so anything the agent
 * still knows afterwards came out of NAMS.
 *
 * The recall query deliberately reuses the user's own noun ("beat"). Retrieval
 * on the hosted NAMS API is lexical, so a paraphrase can miss a memory that is
 * definitely stored — see the README's "Known limitations".
 */
const BEAT = "undersea cable operators";

export default defineEval({
  description: "A fact stored in one session is recalled in a fresh session.",
  tags: ["memory"],
  async test(t) {
    await t.send(`Remember this about me: my research beat is ${BEAT}.`);
    t.succeeded();

    await t.newSession();

    await t.send("What is my research beat?");
    t.succeeded();
    t.check(t.reply, includes("undersea cable"));
  },
});

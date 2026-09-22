import { defineEval } from "eve/evals";
import { includes } from "eve/evals/expect";

// A new session has no chat history, so the answer must come from NAMS.
// The question reuses the same words, since NAMS matches keywords.
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

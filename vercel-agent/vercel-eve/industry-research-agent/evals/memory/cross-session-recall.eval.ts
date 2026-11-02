import { defineEval } from "eve/evals";
import { includes } from "eve/evals/expect";

// Each t.send() starts a new session with no chat history, so the second
// answer must come from the NAMS memory slot.
// The question reuses the same words, since NAMS matches keywords.
const COVERAGE_AREA = "undersea cable operators";

export default defineEval({
  description: "A fact stored in one session is recalled in a fresh session.",
  tags: ["memory"],
  async test(t) {
    await t.send(`Remember this about me: my research coverage area is ${COVERAGE_AREA}.`);

    const second = await t.send("What is my research coverage area?");
    t.succeeded();
    // Case-insensitive: the model often writes it as a heading ("Undersea cable operators").
    t.check(second.reply, includes(/undersea cable/i));
  },
});

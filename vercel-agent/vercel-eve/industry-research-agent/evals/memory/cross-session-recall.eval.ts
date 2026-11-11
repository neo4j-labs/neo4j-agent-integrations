import { defineEval } from "eve/evals";
import { includes } from "eve/evals/expect";

const COVERAGE_AREA = "undersea cable operators";

export default defineEval({
  description: "A fact stored in one session is recalled in a fresh session.",
  tags: ["memory"],
  async test(t) {
    await t.send(`Remember this about me: my research coverage area is ${COVERAGE_AREA}.`);

    const second = await t.send("What is my research coverage area?");
    t.succeeded();
    t.check(second.reply, includes(/undersea cable/i));
  },
});

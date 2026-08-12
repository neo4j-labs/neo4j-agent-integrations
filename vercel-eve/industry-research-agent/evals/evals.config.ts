import { defineEvalConfig } from "eve/evals";

export default defineEvalConfig({
  // Used by `t.judge.*` assertions.
  judge: { model: process.env.EVAL_JUDGE_MODEL ?? "openai/gpt-5.4-mini" },
  // Memory writes are not instant on the hosted NAMS API, and graph queries hit
  // a public demo instance, so give each eval room.
  timeoutMs: 180_000,
});

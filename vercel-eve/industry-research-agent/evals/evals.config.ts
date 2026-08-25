import { defineEvalConfig } from "eve/evals";

export default defineEvalConfig({
  judge: { model: process.env.EVAL_JUDGE_MODEL ?? "openai/gpt-5.4-mini" },
  timeoutMs: 180_000,
});

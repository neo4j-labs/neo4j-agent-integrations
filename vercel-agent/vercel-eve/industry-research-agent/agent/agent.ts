import { defineAgent } from "eve";
import { baseModel, MODEL_ID, MODEL_ROUTING } from "./lib/model";

export default defineAgent({
  /**
   * A plain model id routes through Vercel AI Gateway and lets eve compile the
   * build-time metadata it wants — routing, credentials, context window.
   *
   * Memory is deliberately not here. It lives in `agent/instructions/memory.ts`
   * (recall) and `agent/hooks/persist-turn.ts` (retention), so what the agent
   * remembers is driven by runtime events rather than by the model choosing to
   * call a save tool. The one case that still needs a resolved model instance
   * is the direct-provider route, for running without a Vercel account.
   */
  model: MODEL_ROUTING === "openai" ? baseModel() : MODEL_ID,

  reasoning: "medium",
});

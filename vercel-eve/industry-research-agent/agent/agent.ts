import { defineAgent, defineDynamic } from "eve";
import { baseModel, MODEL_ID } from "./lib/model";
import { MEMORY_MODE, nams } from "./lib/nams";
import { memoryScope } from "./lib/scope";

export default defineAgent({
  /**
   * In `wrap` mode the model itself carries memory.
   *
   * `nams().wrap(model, scope)` returns a drop-in LanguageModelV4 that
   * retrieves the caller's memories before every model call and persists the
   * turn after it. The harness, tools, and channels are untouched — from eve's
   * point of view this is just a model.
   *
   * `step.started` is the only scope allowed to return a live model object, and
   * it is also where `ctx.session.auth` is settled, so the wrap is bound to
   * whoever is actually calling. Re-resolving per step is cheap: the wrapper is
   * middleware over the same underlying model, so it never re-routes the
   * request or invalidates a prompt cache.
   *
   * The other two modes resolve the same base model unwrapped and get their
   * memory from `agent/instructions/memory.ts` + `agent/hooks/persist-turn.ts`
   * (`hooks`) or `agent/tools/memory.ts` (`tools`).
   *
   * `fallback` is the compiled static model: it anchors build-time metadata and
   * serves only if the resolver fails.
   */
  model: defineDynamic({
    fallback: MODEL_ID,
    events: {
      "step.started": (_event, ctx) => {
        const model = baseModel();
        return MEMORY_MODE === "wrap" ? nams().wrap(model, memoryScope(ctx)) : model;
      },
    },
  }),

  reasoning: "low",
});

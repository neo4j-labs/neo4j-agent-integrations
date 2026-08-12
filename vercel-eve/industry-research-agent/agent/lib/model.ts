/**
 * The base model, before NAMS memory wraps it.
 *
 * Two routes, because `nams().wrap()` needs a resolved `LanguageModelV4`
 * instance and not a model-id string:
 *
 *   gateway — Vercel AI Gateway. No provider key on a Vercel deployment
 *             (project OIDC authenticates it); `AI_GATEWAY_API_KEY` locally.
 *   openai  — a direct provider, for running without a Vercel account.
 *
 * Both return a spec-v4 model, so the wrap is identical either way.
 */
import { gateway } from "ai";
import type { LanguageModelV4 } from "@ai-sdk/provider";
import { openai } from "@ai-sdk/openai";

export const MODEL_ID = process.env.AGENT_MODEL ?? "openai/gpt-5.4";

function hasGatewayCredential(): boolean {
  return Boolean(process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_OIDC_TOKEN || process.env.VERCEL);
}

export const MODEL_ROUTING: "gateway" | "openai" = (() => {
  const explicit = process.env.MODEL_ROUTING?.trim().toLowerCase();
  if (explicit === "gateway" || explicit === "openai") return explicit;
  return !hasGatewayCredential() && process.env.OPENAI_API_KEY ? "openai" : "gateway";
})();

export function baseModel(): LanguageModelV4 {
  if (MODEL_ROUTING === "openai") {
    // Gateway ids are "<provider>/<model>"; the direct provider wants the bare id.
    return openai(MODEL_ID.replace(/^openai\//, "")) as LanguageModelV4;
  }
  return gateway(MODEL_ID) as LanguageModelV4;
}

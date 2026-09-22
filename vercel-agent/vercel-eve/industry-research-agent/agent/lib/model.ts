// Picks how to reach the model: Vercel AI Gateway, or OpenAI directly.
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

export function baseModel(id: string = MODEL_ID): LanguageModelV4 {
  if (MODEL_ROUTING === "openai") {
    return openai(id.replace(/^openai\//, "")) as LanguageModelV4;
  }
  return gateway(id) as LanguageModelV4;
}

export function extractionModel(): LanguageModelV4 {
  return baseModel(process.env.NAMS_EXTRACTION_MODEL?.trim() || MODEL_ID);
}

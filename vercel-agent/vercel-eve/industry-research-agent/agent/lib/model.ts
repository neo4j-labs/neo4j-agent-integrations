// Picks how to reach the model: Vercel AI Gateway, or OpenAI directly.
import { openai } from "@ai-sdk/openai";

export const MODEL_ID = process.env.AGENT_MODEL ?? "openai/gpt-5.6-terra";

function hasGatewayCredential(): boolean {
  return Boolean(process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_OIDC_TOKEN || process.env.VERCEL);
}

export const MODEL_ROUTING: "gateway" | "openai" = (() => {
  const explicit = process.env.MODEL_ROUTING?.trim().toLowerCase();
  if (explicit === "gateway" || explicit === "openai") return explicit;
  return !hasGatewayCredential() && process.env.OPENAI_API_KEY ? "openai" : "gateway";
})();

/** The model object for direct OpenAI. The gateway route passes MODEL_ID as is. */
export function baseModel() {
  return openai(MODEL_ID.replace(/^openai\//, ""));
}

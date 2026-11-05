import { namsMemory } from "@neo4j-labs/nams-ai-provider/eve";
import { defineMemory } from "eve/memory";
import { byPrincipal } from "eve/memory/scope";
import { withReasoningTrace } from "../lib/nams-reasoning";

const connection = {
  apiKey: process.env.NAMS_API_KEY || undefined,
  workspaceId: process.env.WORKSPACE_ID || undefined,
  endpoint: process.env.NAMS_ENDPOINT || undefined,
};

export default defineMemory({
  description:
    "What this user told you in earlier sessions: their coverage, the companies they track, " +
    "and notes saved with remember. From Neo4j Agent Memory.",
  provider: withReasoningTrace(
    namsMemory({
      ...connection,
      maxMemories: Number(process.env.NAMS_MAX_MEMORIES ?? 8),
    }),
    {
      ...connection,
      enabled: process.env.NAMS_REASONING?.trim().toLowerCase() !== "off",
    },
  ),
  scope: byPrincipal,
});

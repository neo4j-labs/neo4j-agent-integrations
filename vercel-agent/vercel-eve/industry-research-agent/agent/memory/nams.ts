import { namsMemory } from "@neo4j-labs/nams-ai-provider/eve";
import { defaultNamespace, defineMemory } from "eve/memory";
import { byPrincipal } from "eve/memory/scope";
import { withReasoningTrace } from "../lib/nams-reasoning";
import { withTraceBack } from "../lib/nams-traceback";

const maxMemories = Number.parseInt(process.env.NAMS_MAX_MEMORIES ?? "", 10);

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
    withTraceBack(
      namsMemory({
        ...connection,
        maxMemories: maxMemories > 0 ? maxMemories : 8,
      }),
      {
        ...connection,
        enabled: process.env.NAMS_TRACEBACK?.trim().toLowerCase() !== "off",
      },
    ),
    {
      ...connection,
      enabled: process.env.NAMS_REASONING?.trim().toLowerCase() !== "off",
    },
  ),
  // eve dev hashes a new snapshot path into the default namespace on every run; pin it so memory survives restarts.
  namespace: (ctx) => defaultNamespace({ ...ctx, appRoot: "industry-research-agent" }),
  scope: byPrincipal,
});

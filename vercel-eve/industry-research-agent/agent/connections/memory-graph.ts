/**
 * NAMS's MCP server, exposed as a read-only view of the agent's own memory.
 *
 * NAMS ships two surfaces: the REST API that `lib/memory-gateway.ts` writes
 * through, and a Streamable-HTTP MCP server at the same host. This connection
 * mounts the second one — not to store anything, but so the model can *traverse*
 * what it already remembers: resolve an entity by name, read an entity's
 * cross-conversation history, pull a reasoning trace, explain a single step.
 *
 * Retention deliberately stays in `hooks/persist-turn.ts`. If the write tools
 * were exposed here too, the model would have a second, optional path to store
 * the same turn, and "did this get remembered?" would depend on a tool call
 * again — the exact failure the hook exists to prevent. Hence `tools.allow`
 * rather than `tools.block`: the safe surface is the one you enumerate.
 *
 * Discovered tools reach the model as `memory-graph__<tool>`.
 */
import { defineMcpClientConnection } from "eve/connections";
import type { ConnectionToolCallDefinition } from "eve/connections";
import { workspaceIdFor } from "../lib/nams";
import { memoryScope } from "../lib/scope";

/**
 * `workspace_id` is application state, not a model decision.
 *
 * Every NAMS MCP tool accepts an optional `workspace_id`, and no request header
 * binds one, so left alone it sits in the model-facing input schema as an
 * argument the model can fill in — the same class of mistake as a `userId` tool
 * parameter, one level out. Declaring it here makes eve strip it from the schema
 * the model sees and inject the resolved value just before the call, so which
 * workspace gets read is decided by the session, never by the prompt.
 *
 * Only declared when a workspace is actually configured: with a
 * workspace-bound key the server resolves it from the key, and sending an empty
 * value would be worse than sending none. `workspaceIdFor` in `lib/nams.ts` is
 * where a workspace-per-tenant policy goes, and it is the same function the
 * memory gateway keys its per-user clients on.
 */
const pinWorkspace: ConnectionToolCallDefinition | undefined = process.env.NAMS_WORKSPACE_ID
  ? {
      providedArguments: {
        workspace_id: (ctx) => workspaceIdFor(memoryScope(ctx).userId) ?? "",
      },
    }
  : undefined;

export default defineMcpClientConnection({
  url: process.env.NAMS_MCP_URL ?? "https://memory.neo4jlabs.com/mcp",

  // Written for the model: this is the main signal `connection_search` ranks on.
  description:
    "The agent's own long-term memory as a graph. Look up what is known about a " +
    "person, company, or topic; read an entity's history across past conversations; " +
    "and pull the recorded reasoning trace behind an earlier answer. Read-only.",

  auth: {
    getToken: async () => ({ token: process.env.NAMS_API_KEY! }),
  },

  /**
   * Five read tools out of the 48 the server publishes. The rest are writes
   * (`memory_add_*`, `memory_record_*`, `memory_create_*`), entity merges
   * (`memory_resolve_entity`), skill management, or workspace administration —
   * which includes `workspace_delete` and `workspace_reprovision`. On a server
   * with a surface like that, an allow-list is not optional.
   */
  tools: {
    allow: [
      "memory_search_entities",
      "memory_get_entity_by_name",
      "memory_get_entity_history",
      "memory_get_trace",
      "memory_explain_decision",
    ],
  },

  ...(pinWorkspace ? { toolCall: pinWorkspace } : {}),
});

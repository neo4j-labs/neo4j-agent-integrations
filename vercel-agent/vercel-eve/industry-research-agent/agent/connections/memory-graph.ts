/**
 * NAMS's MCP server, exposed as a read-only view of the agent's own memory.
 */
import { defineMcpClientConnection } from "eve/connections";
import type { ConnectionToolCallDefinition } from "eve/connections";
import { memoryScope, workspaceIdFor } from "../lib/nams";

const getWorkspace: ConnectionToolCallDefinition | undefined = process.env.NAMS_WORKSPACE_ID
  ? {
    providedArguments: {
      workspace_id: (ctx) => workspaceIdFor(memoryScope(ctx).userId) ?? "",
    },
  }
  : undefined;

export default defineMcpClientConnection({
  url: process.env.NAMS_MCP_URL ?? "https://memory.neo4jlabs.com/mcp",
  description:
    "The agent's own long-term memory as a graph. Look up what is known about a " +
    "person, company, or topic; read an entity's history across past conversations; " +
    "and pull the recorded reasoning trace behind an earlier answer. Read-only.",

  auth: {
    getToken: async () => ({ token: process.env.NAMS_API_KEY! }),
  },

  /**
   * Five read tools out of the 40 the server publishes.
   *
   * The rest are writes (`memory_add_entity`, `memory_add_messages`,
   * `memory_create_conversation`, `memory_create_relation`, `memory_record_*`),
   * entity merges (`memory_resolve_entity`), ontology mutation
   * (`memory_ontology_create` / `_update`), and thirteen `skill_*` tools that
   * let a caller generate, edit, and publish the agent's own skills.
   *
   * Nothing in this project should reach any of them: memory is written by
   * `hooks/`, on the runtime's schedule, not by a model deciding to call a save
   * tool. Naming the five reads is what keeps that true.
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

  ...(getWorkspace ? { toolCall: getWorkspace } : {}),
});

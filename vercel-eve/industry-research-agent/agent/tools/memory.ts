/**
 * Memory mode `tools` — the model drives recall and storage explicitly.
 *
 * Registered dynamically so it exists only when `NAMS_MODE=tools`. In the other
 * two modes this resolver returns `null`, the tools never reach the model, and
 * memory is handled by the model wrapper (`wrap`) or by dynamic instructions
 * plus a hook (`hooks`). Exactly one mode writes, so no turn is stored twice.
 *
 * Neither tool takes a `userId`: the scope comes from `ctx.session.auth`.
 */
import { defineDynamic, defineTool } from "eve/tools";
import { z } from "zod";
import { MAX_MEMORIES, MEMORY_MODE, recall, remember } from "../lib/nams";
import { memoryScope } from "../lib/scope";

export default defineDynamic({
  events: {
    "session.started": (_event, ctx) => {
      if (MEMORY_MODE !== "tools") return null;

      return {
        recall_memory: defineTool({
          description:
            "Recall what you already know about the current user — their sectors, tracked " +
            "companies, stated preferences, and earlier questions. Call this before answering " +
            "anything where prior context would change the answer.",
          inputSchema: z.object({
            query: z
              .string()
              .min(1)
              .describe(
                "Keywords to search for. Matching is lexical, so reuse the user's own nouns " +
                  "('semiconductors', 'Europe') rather than paraphrasing the question, and " +
                  "prefer one or two words over a sentence.",
              ),
            limit: z.number().int().min(1).max(20).default(MAX_MEMORIES),
          }),
          // `execute` must be an inline function: eve reconstructs it from its
          // closure on replay, and does not detect `execute: someNamedFn`.
          async execute({ query, limit }, toolCtx) {
            const memories = await recall(memoryScope(toolCtx), query, limit);
            return {
              found: memories.length > 0,
              count: memories.length,
              memories,
            };
          },
        }),

        remember: defineTool({
          description:
            "Store one durable fact or preference about the current user, so later sessions " +
            "can use it. Store research interests and working preferences — never credentials, " +
            "tokens, or personal data the user did not ask you to keep.",
          inputSchema: z.object({
            content: z.string().min(1).max(2000).describe("The fact, written as a full sentence"),
            type: z
              .enum(["fact", "user_preference", "pattern"])
              .default("fact")
              .describe("'user_preference' for how they want to work, 'fact' for what is true"),
            tags: z.array(z.string()).max(8).default([]),
          }),
          async execute({ content, type, tags }, toolCtx) {
            await remember(memoryScope(toolCtx), { content, type, tags });
            return { stored: true, type, preview: content.slice(0, 120) };
          },
        }),
      };
    },
  },
});

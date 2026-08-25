/**
 * Entity extraction — how a stored memory becomes a graph.
 *
 * A local replacement for the provider's `createGraphExtractor`, kept for two
 * reasons that outlived the bug that first forced it.
 *
 * **The bug (fixed upstream in 0.2.1, still worth knowing).** The 0.2.0 schema
 * marked `description` as `.optional()`, and OpenAI's structured-output mode
 * rejects any object property missing from `required`:
 *
 *   Invalid schema for response_format 'response': ... 'required' is required
 *   to be supplied and to be an array including every key in properties.
 *   Missing 'description'.
 *
 * Every extraction threw, `storeMemory` swallowed it, and the fallback stored
 * one flat entity whose *name was the first 60 characters of the turn* — a
 * graph made of sentences. `.nullable()` says the same "may be absent" while
 * staying in `required`.
 *
 * **The two reasons it stays.**
 *   1. The prompt. The shipped extractor is told to skip "entities about memory,
 *      recall, or stored profiles". Ours is told the opposite about one thing:
 *      *include* the analyst's own identity and coverage areas, because those
 *      are the point of this agent's memory.
 *   2. The filter. See `isNotDomainEntity` below — the shipped default drops any
 *      all-lowercase name as a common noun, which takes real coverage areas with
 *      it.
 *
 * Same signature as the provider's version, so it drops straight into
 * `storeMemory`'s `opts.extractor`.
 */
import { generateText, Output, zodSchema } from "ai";
import type { LanguageModel } from "ai";
import { z } from "zod";
import type { MemoryClient } from "@neo4j-labs/agent-memory";
import type { GraphExtractor } from "@neo4j-labs/nams-ai-provider";
import type { StoreMemoryInput } from "./nams";

const graphSchema = z.object({
  entities: z
    .array(
      z.object({
        name: z.string().describe('Canonical entity name, e.g. "Neo4j", "ArangoDB", "Alex"'),
        type: z
          .string()
          .describe("person | organization | tool | place | concept | preference | event"),
        description: z.string().nullable().describe("One short sentence, or null if unclear."),
      }),
    )
    .describe("Distinct, real, named entities only. Do not invent. May be empty."),
  relationships: z
    .array(
      z.object({
        from: z.string().describe("Source entity name — must match an entity above"),
        to: z.string().describe("Target entity name — must match an entity above"),
        type: z.string().describe("Relationship label, e.g. COMPETES_WITH, WORKS_AT, COVERS"),
      }),
    )
    .describe("May be empty."),
});

/**
 * What the extractor is told to ignore.
 *
 * Extraction runs on raw turn text, which includes turns *about the agent*. An
 * earlier `/channels` turn is what put `analysis`, `final`, `private reasoning`
 * and `concise wrap-up` into the workspace as `Concept` entities — correct
 * extraction of the wrong subject. `hooks/persist-turn.ts` filters slash
 * commands before spending a model call; this catches the rest.
 */
const PROMPT_RULES = [
  "Extract entities and the relationships between them from the memory below.",
  "Rules:",
  "- Only real, named things: companies, people, products, places, sectors, technologies.",
  "- Include the user's own stated identity, role and coverage areas — those are the point.",
  "- Skip anything about the assistant itself: its channels, tools, output format, or how it",
  "  phrased the answer. Those are not domain knowledge.",
  "- Skip generic nouns that are not names ('the market', 'recent news', 'the answer').",
  "- Return empty arrays rather than inventing anything.",
].join("\n");

/**
 * The last line of defence, applied after the model has answered.
 *
 * The prompt rules ask for domain entities only, and the model still returns the
 * agent's own machinery: a live workspace inspection turned up
 * `user -[:USES]-> get_schema`, `user -[:USES]-> search_news tool`, and
 * `user -[:RELATED_TO]-> final` sitting in the Entity Explorer next to Neo4j
 * and ArangoDB. A prompt cannot be relied on to hold a boundary; a filter can.
 * NAMS has no entity delete, so this has to be right going in.
 *
 * Deliberately not the provider's default `skipEntity`, which drops any
 * all-lowercase name as a common noun. That rule also drops
 * "undersea cable operators" and "document database" — a research analyst's
 * coverage areas are lowercase by nature, and they are exactly what this agent
 * is supposed to remember.
 */
const NOT_DOMAIN_ENTITIES = new Set([
  // The conversation's participants are not things the graph should hold.
  "user", "users", "the user", "assistant", "the assistant", "agent", "the agent", "model",
  // The agent's own vocabulary, harvested from turns about how it works.
  "tool", "tools", "skill", "skills", "memory", "conversation", "session", "channel",
  "analysis", "final", "response", "answer", "reasoning", "query", "schema",
  // Generic nouns that are categories, not named things.
  "graph", "database", "dataset", "news", "article", "articles", "company", "companies",
]);

function isNotDomainEntity(name: string): boolean {
  const normalized = name.trim().toLowerCase();
  if (NOT_DOMAIN_ENTITIES.has(normalized)) return true;
  // Tool names reach the extractor verbatim ("search_news",
  // "neo4j-graph__read-cypher") and as prose ("search_news tool"). The
  // underscore is what identifies them: requiring one keeps real hyphenated
  // organizations ("T-Mobile", "Coca-Cola") out of this branch.
  if (/^[a-z0-9-]+_[a-z0-9_-]+( tool)?$/.test(normalized)) return true;
  return normalized.endsWith(" tool") || normalized.endsWith(" tools");
}

/**
 * Whether this deployment's NAMS transport can store relationships at all.
 *
 * The hosted REST API cannot: `addRelationship` answers
 *   NotSupportedError: Method 'add_relationship' has no equivalent in the
 *   hosted Neo4j Agent Memory REST API. It is supported by BridgeTransport only.
 * That is a property of the transport, not of the call, so the first refusal
 * settles it for the life of the instance — otherwise every promoted turn
 * spends round trips to be told the same thing and logs one warning per edge.
 *
 * Entities still land, which is what the Entity Explorer shows. Point NAMS at
 * your own Neo4j (BridgeTransport) and the edges start being written with no
 * change here.
 */
let relationshipsSupported = true;

function isNotSupported(error: unknown): boolean {
  return error instanceof Error && error.name === "NotSupportedError";
}

export function createGraphExtractor(model: LanguageModel): GraphExtractor {
  return async function extractAndStore(client: MemoryClient, input: StoreMemoryInput) {
    const { output } = await generateText({
      model,
      output: Output.object({ schema: zodSchema(graphSchema) }),
      prompt: `${PROMPT_RULES}\n\nMemory (${input.type}):\n${input.content}`,
    });

    const nameToId = new Map<string, string>();
    for (const entity of output.entities) {
      if (isNotDomainEntity(entity.name)) continue;

      const stored = await client.longTerm.addEntity(entity.name, entity.type, {
        description: entity.description ?? input.content,
      });
      if (stored?.id) nameToId.set(entity.name, stored.id);
    }

    for (const rel of output.relationships) {
      if (!relationshipsSupported) break;

      const from = nameToId.get(rel.from);
      const to = nameToId.get(rel.to);
      // A relationship naming an entity the model did not also emit — or one the
      // filter dropped — has nothing to attach to.
      if (!from || !to) continue;

      try {
        await client.longTerm.addRelationship(from, to, rel.type);
      } catch (error) {
        if (isNotSupported(error)) {
          relationshipsSupported = false;
          console.warn(
            "[nams] this transport cannot store relationships — extracting entities only",
          );
          break;
        }
        console.warn("[nams] addRelationship failed", error);
      }
    }
  };
}

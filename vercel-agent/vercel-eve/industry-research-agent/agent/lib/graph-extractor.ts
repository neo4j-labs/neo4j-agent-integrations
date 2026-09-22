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
        name: z.string().describe('Canonical entity name, e.g. "Neo4j", "Alex"'),
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

// Generic words about the agent itself. Dropped before saving, since NAMS
// can't delete entities later. Unlike the default filter, lowercase names stay.
const NOT_DOMAIN_ENTITIES = new Set([
  "user", "users", "the user", "assistant", "the assistant", "agent", "the agent", "model",
  "tool", "tools", "skill", "skills", "memory", "conversation", "session", "channel",
  "analysis", "final", "response", "answer", "reasoning", "query", "schema",
  "graph", "database", "dataset", "news", "article", "articles", "company", "companies",
]);

function isNotDomainEntity(name: string): boolean {
  const normalized = name.trim().toLowerCase();
  if (NOT_DOMAIN_ENTITIES.has(normalized)) return true;
  if (/^[a-z0-9-]+_[a-z0-9_-]+( tool)?$/.test(normalized)) return true;
  return normalized.endsWith(" tool") || normalized.endsWith(" tools");
}

// The hosted API can't save relationships; stop trying after the first refusal.
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

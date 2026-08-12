import { defineTool } from "eve/tools";
import { z } from "zod";
import { readQuery } from "../lib/neo4j";

const RELATIONSHIPS = {
  competitors: "HAS_COMPETITOR",
  suppliers: "HAS_SUPPLIER",
  subsidiaries: "HAS_SUBSIDIARY",
  investors: "HAS_INVESTOR",
} as const;

type Relationship = keyof typeof RELATIONSHIPS;

/**
 * The question a graph answers better than a table: who is connected to whom.
 *
 * The relationship type is whitelisted through `RELATIONSHIPS` rather than
 * interpolated from model output, so the model chooses an edge but never
 * writes Cypher.
 */
export default defineTool({
  description:
    "Traverse an organization's business relationships in the graph. " +
    "'competitors' returns rivals, 'suppliers' its supply chain, " +
    "'subsidiaries' companies it owns, 'investors' who invested in it. " +
    "Use this for competitive landscape, ownership, and supply-chain questions.",
  inputSchema: z.object({
    company: z.string().min(1).describe("Company name, ideally as returned by company_profile"),
    relationship: z
      .enum(["competitors", "suppliers", "subsidiaries", "investors"])
      .describe("Which relationship to traverse"),
    limit: z.number().int().min(1).max(50).default(15),
  }),
  async execute({ company, relationship, limit }) {
    const relType = RELATIONSHIPS[relationship as Relationship];

    const rows = await readQuery<{ name: string; kind: string; industries: string[] }>(
      `
      MATCH (o:Organization) WHERE o.name = $company
      WITH o LIMIT 1
      MATCH (o)-[:${relType}]->(other)
      RETURN other.name AS name,
             labels(other)[0] AS kind,
             [(other)-[:HAS_CATEGORY]->(i) | i.name][0..3] AS industries
      LIMIT toInteger($limit)
      `,
      { company, limit },
    );

    return {
      company,
      relationship,
      count: rows.length,
      results: rows,
      ...(rows.length === 0 && {
        message: `No ${relationship} recorded for "${company}". Confirm the name with company_profile.`,
      }),
    };
  },
});

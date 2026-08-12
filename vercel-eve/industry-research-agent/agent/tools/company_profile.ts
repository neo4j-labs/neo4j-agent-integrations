import { defineTool } from "eve/tools";
import { z } from "zod";
import { readQuery } from "../lib/neo4j";

/**
 * Anchor a research question on one organization.
 *
 * Matches on exact name first, then falls back to the `entity` full-text index
 * so "Neo4j Inc" still finds "Neo4j" instead of returning nothing.
 */
export default defineTool({
  description:
    "Look up an organization in the knowledge graph: description, revenue, headcount, " +
    "public/private status, headquarters cities, industry categories, CEO, and board members. " +
    "Use this first to confirm a company exists and get its canonical name.",
  inputSchema: z.object({
    company: z.string().min(1).describe("Company name, e.g. 'Neo4j' or 'Databricks'"),
  }),
  async execute({ company }) {
    const rows = await readQuery<{
      name: string;
      summary: string | null;
      revenue: number | null;
      employees: number | null;
      isPublic: boolean | null;
      cities: string[];
      industries: string[];
      ceo: string[];
      board: string[];
    }>(
      `
      CALL {
        MATCH (o:Organization) WHERE o.name = $company RETURN o LIMIT 1
        UNION
        CALL db.index.fulltext.queryNodes('entity', $company) YIELD node, score
        WITH node WHERE node:Organization
        RETURN node AS o LIMIT 1
      }
      WITH o LIMIT 1
      RETURN o.name              AS name,
             o.summary           AS summary,
             o.revenue           AS revenue,
             o.nbrEmployees      AS employees,
             o.isPublic          AS isPublic,
             [(o)-[:IN_CITY]->(c:City)              | c.name] AS cities,
             [(o)-[:HAS_CATEGORY]->(i)              | i.name] AS industries,
             [(o)-[:HAS_CEO]->(p:Person)            | p.name] AS ceo,
             [(o)-[:HAS_BOARD_MEMBER]->(p:Person)   | p.name] AS board
      `,
      { company },
    );

    if (rows.length === 0) {
      return { found: false, company, message: `No organization matching "${company}".` };
    }
    return { found: true, ...rows[0] };
  },
});

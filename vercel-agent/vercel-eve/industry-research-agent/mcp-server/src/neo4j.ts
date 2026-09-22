// Has its own driver so mcp-server/ works standalone. Uses the public demo graph by default.
import neo4j, { type Driver } from "neo4j-driver";

const URI = process.env.NEO4J_URI?.trim() || "neo4j+s://demo.neo4jlabs.com:7687";
const USERNAME = process.env.NEO4J_USERNAME?.trim() || "companies";
const PASSWORD = process.env.NEO4J_PASSWORD?.trim() || "companies";
const DATABASE = process.env.NEO4J_DATABASE?.trim() || "companies";

let driver: Driver | undefined;

function getDriver(): Driver {
  driver ??= neo4j.driver(URI, neo4j.auth.basic(USERNAME, PASSWORD), {
    maxConnectionPoolSize: 10,
    connectionAcquisitionTimeout: 10_000,
  });
  return driver;
}

export async function closeDriver(): Promise<void> {
  await driver?.close();
  driver = undefined;
}

export function describeTarget(): string {
  return `${URI} (database: ${DATABASE})`;
}

const INVESTMENTS_QUERY = `
MATCH (o:Organization)-[:HAS_INVESTOR]->(i)
WHERE o.name = $company
RETURN i.id AS id, i.name AS name, head(labels(i)) AS type
`;

/** Returns errors as text, so the model can try another name. */
export async function getInvestments(company: string): Promise<string> {
  try {
    const { records } = await getDriver().executeQuery(
      INVESTMENTS_QUERY,
      { company },
      { database: DATABASE, routing: "READ" },
    );

    if (records.length === 0) {
      return `No investors recorded for "${company}". Company names in this graph are exact — try the shorter or more common form of the name.`;
    }

    return JSON.stringify(records.map((record) => toPlain(record.toObject())), null, 2);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`[mcp] get_investments("${company}") failed: ${message}`);
    return `Could not read investors from the graph: ${message}`;
  }
}

/** Turn Neo4j values (big ints, dates) into plain JSON. */
function toPlain(value: unknown): unknown {
  if (value === null || value === undefined) return null;
  if (neo4j.isInt(value)) {
    return value.inSafeRange() ? value.toNumber() : value.toString();
  }
  if (Array.isArray(value)) return value.map(toPlain);
  if (value instanceof Date) return value.toISOString();
  if (typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, toPlain(v)]));
  }
  return value;
}

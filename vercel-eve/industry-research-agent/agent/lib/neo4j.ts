/**
 * Read-only access to the Company News knowledge graph.
 *
 * Defaults to the public Neo4j demo instance (250k Diffbot entities:
 * organizations, people, cities, industry categories, and news articles with
 * vector embeddings). Point the NEO4J_* vars at your own database to swap it.
 */
import neo4j, { type Driver } from "neo4j-driver";

const URI = process.env.NEO4J_URI ?? "neo4j+s://demo.neo4jlabs.com:7687";
const USERNAME = process.env.NEO4J_USERNAME ?? "companies";
const PASSWORD = process.env.NEO4J_PASSWORD ?? "companies";
const DATABASE = process.env.NEO4J_DATABASE ?? "companies";

let driver: Driver | undefined;

function getDriver(): Driver {
  driver ??= neo4j.driver(URI, neo4j.auth.basic(USERNAME, PASSWORD), {
    // Serverless invocations are short-lived; a small pool avoids holding
    // connections open past the request that opened them.
    maxConnectionPoolSize: 10,
    connectionAcquisitionTimeout: 10_000,
  });
  return driver;
}

/**
 * Run a read-only Cypher query and return plain JSON rows.
 *
 * `READ` access mode is enforced here rather than trusted to the query text,
 * and Neo4j integers are narrowed to JS numbers so results survive eve's
 * durable JSON boundary.
 */
export async function readQuery<T = Record<string, unknown>>(
  cypher: string,
  params: Record<string, unknown> = {},
): Promise<T[]> {
  const { records } = await getDriver().executeQuery(cypher, params, {
    database: DATABASE,
    routing: "READ",
  });
  return records.map((record) => toPlain(record.toObject()) as T);
}

/** Recursively convert Neo4j Integers (and other driver types) to JSON-safe values. */
function toPlain(value: unknown): unknown {
  if (value === null || value === undefined) return null;
  if (neo4j.isInt(value)) {
    return value.inSafeRange() ? value.toNumber() : value.toString();
  }
  if (Array.isArray(value)) return value.map(toPlain);
  if (value instanceof Date) return value.toISOString();
  if (typeof value === "object") {
    // Temporal types (Date, DateTime, ...) all stringify usefully.
    if ("toString" in value && value.constructor?.name?.startsWith("Date")) {
      return String(value);
    }
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, toPlain(v)]));
  }
  return value;
}

export const GRAPH_DESCRIPTION = `Company News knowledge graph (${DATABASE} @ ${URI})`;


import neo4j, { type Driver } from 'neo4j-driver';

// ── Environment ───────────────────────────────────────────────────────────────
const MEMORY_URI = process.env.MEMORY_NEO4J_URI!;
const MEMORY_USER = process.env.MEMORY_NEO4J_USERNAME ?? 'neo4j';
const MEMORY_PASS = process.env.MEMORY_NEO4J_PASSWORD!;
const MEMORY_DB = process.env.MEMORY_NEO4J_DATABASE ?? 'neo4j';

if (!MEMORY_URI || !MEMORY_PASS) {
  throw new Error(
    'Missing MEMORY_NEO4J_URI or MEMORY_NEO4J_PASSWORD. Copy .env.local.example → .env.local.'
  );
}

let _driver: Driver | null = null;

function getDriver(): Driver {
  if (!_driver) {
    _driver = neo4j.driver(
      MEMORY_URI,
      neo4j.auth.basic(MEMORY_USER, MEMORY_PASS),
      { disableLosslessIntegers: true }
    );
  }
  return _driver;
}

export function createSessionId(seed?: string): string {
  return seed ? `session-${seed}` : `session-${Date.now()}`;
}

export async function storeMessage(
  sessionId: string,
  role: 'user' | 'assistant',
  content: string
): Promise<void> {
  const driver = getDriver();
  await driver.executeQuery(
    `
    MERGE (s:MemorySession {id: $sessionId})
    CREATE (m:MemoryMessage {
      role:      $role,
      content:   $content,
      timestamp: datetime()
    })
    CREATE (s)-[:HAS_MESSAGE]->(m)
    `,
    { sessionId, role, content },
    { database: MEMORY_DB }
  );
}


export async function getRecentMessages(
  sessionId: string,
  limit = 20
): Promise<Array<{ role: 'user' | 'assistant'; content: string }>> {
  const driver = getDriver();
  const safeLimit = Math.max(0, Math.trunc(Number(limit) || 0));
  const { records } = await driver.executeQuery(
    `
    MATCH (s:MemorySession {id: $sessionId})-[:HAS_MESSAGE]->(m:MemoryMessage)
    RETURN m.role AS role, m.content AS content
    ORDER BY m.timestamp ASC
    LIMIT toInteger($limit)
    `,
    { sessionId, limit: neo4j.int(safeLimit) },
    { database: MEMORY_DB }
  );

  return records.map((r) => ({
    role: r.get('role') as 'user' | 'assistant',
    content: r.get('content') as string,
  }));
}

export async function clearSession(sessionId: string): Promise<void> {
  const driver = getDriver();
  await driver.executeQuery(
    `
    MATCH (s:MemorySession {id: $sessionId})-[r:HAS_MESSAGE]->(m:MemoryMessage)
    DELETE r, m
    `,
    { sessionId },
    { database: MEMORY_DB }
  );
}

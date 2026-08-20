import {
  defineMcpConnection,
  type McpConnectionDefinition,
} from '@flue/runtime';

const DEFAULT_MCP_URL = 'http://localhost:8000/mcp';
const DEFAULT_NEO4J_USERNAME = 'companies';
const DEFAULT_NEO4J_PASSWORD = 'companies';
type Environment = Readonly<Record<string, string | undefined>>;

function readEnvironment(
  environment: Environment,
  name: string,
  fallback: string,
): string {
  const value = environment[name]?.trim();
  return value || fallback;
}

export function createNeo4jMcpDefinition(
  environment: Environment = process.env,
): McpConnectionDefinition {
  const username = readEnvironment(
    environment,
    'NEO4J_USERNAME',
    DEFAULT_NEO4J_USERNAME,
  );
  const password = readEnvironment(
    environment,
    'NEO4J_PASSWORD',
    DEFAULT_NEO4J_PASSWORD,
  );
  const authorization = `Basic ${Buffer.from(
    `${username}:${password}`,
  ).toString('base64')}`;

  return defineMcpConnection({
    name: 'neo4j',
    url: readEnvironment(environment, 'NEO4J_MCP_URL', DEFAULT_MCP_URL),
    tools: ['get-schema', 'read-cypher'],
    timeoutMs: 60_000,
    headers: { Authorization: authorization },
  });
}

export const neo4jMcp = createNeo4jMcpDefinition();

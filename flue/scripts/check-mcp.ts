import { createMcpConnection } from '@flue/runtime';
import { neo4jMcp } from '../src/connections/neo4j-mcp.ts';

const expectedTools = [
  'mcp__neo4j__get-schema',
  'mcp__neo4j__read-cypher',
];

const connection = await createMcpConnection(neo4jMcp);

try {
  const toolNames = connection.tools.map((tool) => tool.name);
  const missingTools = expectedTools.filter((name) => !toolNames.includes(name));

  if (missingTools.length > 0) {
    throw new Error(
      `Neo4j MCP connected but did not expose: ${missingTools.join(', ')}`,
    );
  }

  console.log(`Connected to ${neo4jMcp.url}`);
  console.log(`Available tools: ${toolNames.join(', ')}`);
} finally {
  await connection.close();
}

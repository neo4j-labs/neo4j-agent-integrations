type MemoryService = import('neo4j-agent-memory').MemoryService;

type MemoryConfig = {
  uri: string;
  username: string;
  password: string;
  database?: string;
};

declare global {
  // eslint-disable-next-line no-var
  var __MEMORY_SERVICE_PROMISE__: Promise<MemoryService | null> | undefined;
}

function readEnv(key: string): string | undefined {
  return process.env[key];
}

function resolveMemoryConfig(): MemoryConfig | null {
  const uri = readEnv('MEMORY_NEO4J_URI') || readEnv('NEO4J_URI');
  const username = readEnv('MEMORY_NEO4J_USERNAME') || readEnv('NEO4J_USERNAME');
  const password = readEnv('MEMORY_NEO4J_PASSWORD') || readEnv('NEO4J_PASSWORD');
  const database = readEnv('MEMORY_NEO4J_DATABASE') || readEnv('NEO4J_DATABASE');

  if (!uri || !username || !password) {
    return null;
  }

  return {
    uri,
    username,
    password,
    database,
  };
}

export function getMemoryConfigSourceLabel(): string {
  if (readEnv('MEMORY_NEO4J_URI')) return 'MEMORY_NEO4J_*';
  if (readEnv('NEO4J_URI')) return 'NEO4J_*';
  return 'not-configured';
}

export function isMemoryConfigured(): boolean {
  return resolveMemoryConfig() !== null;
}

export async function getMemoryService(): Promise<MemoryService | null> {
  if (!globalThis.__MEMORY_SERVICE_PROMISE__) {
    globalThis.__MEMORY_SERVICE_PROMISE__ = (async () => {
      const cfg = resolveMemoryConfig();
      if (!cfg) {
        console.log('[memoryService] Memory config not found, memory disabled');
        return null;
      }

      try {
        console.log('[memoryService] Initializing Neo4j Agent Memory...');
        const { createMemoryService } = await import('neo4j-agent-memory');
        const memoryService = await createMemoryService({
          neo4j: {
            uri: cfg.uri,
            username: cfg.username,
            password: cfg.password,
            database: cfg.database,
          },
          vectorIndex: readEnv('MEMORY_VECTOR_INDEX') || 'memoryEmbedding',
          fulltextIndex: readEnv('MEMORY_FULLTEXT_INDEX') || 'memoryText',
        });

        console.log('[memoryService] Neo4j Agent Memory initialized successfully');
        return memoryService;
      } catch (error) {
        console.error('[memoryService] Failed to initialize Neo4j Agent Memory:', error);
        return null;
      }
    })();
  }

  return globalThis.__MEMORY_SERVICE_PROMISE__;
}

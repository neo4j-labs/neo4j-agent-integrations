import { MemoryClient } from "@neo4j-labs/agent-memory";

export const DEFAULT_ENDPOINT = 'https://memory.neo4jlabs.com/v1';

export interface NamsConfig {
  apiKey: string;
  endpoint?: string;
  workspaceId?: string;
}

export interface NamsScope {
  userId: string;
  conversationId?: string;
}

export type MemorySource = 'long-term' | 'conversation' | 'cross-session' | 'reasoning';
export type MemoryType = 'fact' | 'interaction' | 'pattern' | 'user_preference';

export interface MemoryHit {
  content: string;
  source: MemorySource;
  type: string;
  score?: number;
}

export interface StoreInput {
  content: string;
  type: MemoryType;
  confidence?: number;
  tags?: string[];
}

export type GraphExtractor = (client: MemoryClient, input: StoreInput) => Promise<void>;
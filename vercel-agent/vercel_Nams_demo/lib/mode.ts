import type { NamsMode } from '@neo4j-labs/nams-ai-provider';

export type ChatMode = NamsMode | 'off';

export const CHAT_MODES: readonly ChatMode[] = ['provider', 'middleware', 'tools', 'hooks', 'off'];

// The raw NAMS_MODE value; `npm run dev` sets it, unset means provider.
export function rawMode(): string {
  return (process.env.NAMS_MODE ?? 'provider').trim();
}

// The active mode, or null when NAMS_MODE is not a known mode.
export function memoryMode(): ChatMode | null {
  const raw = rawMode() as ChatMode;
  return CHAT_MODES.includes(raw) ? raw : null;
}

export function namsConfig() {
  return { apiKey: process.env.NAMS_API_KEY ?? '', workspaceId: process.env.MEMORY_WORKSPACE_ID };
}

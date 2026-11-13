import type { ChatMode } from '@/lib/mode';

export const AGENT_NAME = 'NAMS Chat';

export const DEFAULT_SUGGESTIONS = [
  "Hi! I'm Alex, a data scientist at TechCorp.",
  'What do you remember about me?',
  'I prefer concise, technical answers.',
  'What graph algorithms work best for recommendation systems?',
];

export const SESSION_STORAGE_KEY = 'nams-session-id';
export const THEME_STORAGE_KEY = 'nams-chat-theme';

export const MEMORY_MODES: Record<ChatMode, { detail: string; tone: 'success' | 'info' | 'warning' }> = {
  provider: { detail: 'createNamsProvider() · app/api/chat/route.ts', tone: 'success' },
  middleware: { detail: 'createNams().wrap() · app/api/chat/route.ts', tone: 'success' },
  tools: { detail: 'createNams().toolsWithMcp() · query_memory / store_memory', tone: 'info' },
  hooks: { detail: 'createNams().hooks() · loadSession + onFinish', tone: 'success' },
  off: { detail: 'no memory', tone: 'warning' },
};

export const MEMORY_TABS = [
  { id: 'recent', label: 'recent' },
  { id: 'observations', label: 'observations' },
  { id: 'insights', label: 'insights' },
  { id: 'entities', label: 'entities' },
  { id: 'reasoning', label: 'reasoning' },
] as const;

import type { UIMessage, DynamicToolUIPart } from 'ai';
import type { MemoryHit, QueryOutput, ParsedMemory } from '@/types';

export function getMsgText(msg: UIMessage): string {
  return msg.parts
    .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
    .map(p => p.text)
    .join('');
}

export function parseMemory(parts: UIMessage['parts']): ParsedMemory {
  const queryPart = parts.find(
    (p): p is DynamicToolUIPart =>
      p.type === 'dynamic-tool' && (p as DynamicToolUIPart).toolName === 'query_memory',
  ) as DynamicToolUIPart | undefined;

  const storeParts = parts.filter(
    (p): p is DynamicToolUIPart =>
      p.type === 'dynamic-tool' &&
      (p as DynamicToolUIPart).toolName === 'store_memory' &&
      (p as DynamicToolUIPart).state === 'output-available',
  ) as DynamicToolUIPart[];

  if (!queryPart) {
    const stored: MemoryHit[] = storeParts.map(sp => ({
      content: String((sp.input as Record<string, unknown>)?.content ?? ''),
      source: (sp.input as Record<string, unknown>)?.type === 'interaction'
        ? ('conversation' as const)
        : ('long-term' as const),
      type: String((sp.input as Record<string, unknown>)?.type ?? 'fact'),
    }));
    const recent = stored.filter(m => m.source === 'conversation');
    const obs    = stored.filter(m => m.source === 'long-term');
    return {
      counts: { recent: recent.length, observations: obs.length, reasoning: 0 },
      items:  { recent, observations: obs, reasoning: [] },
    };
  }

  const out  = queryPart.state === 'output-available' ? (queryPart.output as QueryOutput) : undefined;
  const mems = out?.memories ?? [];
  const recent       = mems.filter(m => m.source === 'conversation');
  const observations = mems.filter(m => m.source === 'long-term');
  const reasoning    = mems.filter(m => m.source === 'reasoning');
  return {
    counts: { recent: recent.length, observations: observations.length, reasoning: reasoning.length },
    items:  { recent, observations, reasoning },
  };
}

export function formatErrorMessage(error: unknown): string | null {
  if (error instanceof Error) return error.message;
  if (error) return String(error);
  return null;
}

import { getToolName, isToolUIPart } from 'ai';
import type { DynamicToolUIPart, ToolUIPart, UIMessage } from 'ai';
import type { MemorySnapshot } from '@/types';

export type ToolPart = ToolUIPart | DynamicToolUIPart;

export function getMsgText(msg: UIMessage): string {
  return msg.parts
    .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
    .map(p => p.text)
    .join('\n\n');
}

export function lastUserText(messages: readonly UIMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role === 'user') {
      const text = getMsgText(messages[i]);
      if (text) return text;
    }
  }
  return '';
}

// Static (memory) and dynamic (MCP) tool calls alike.
export function toolParts(parts: UIMessage['parts']): ToolPart[] {
  return parts.filter((p): p is ToolPart => isToolUIPart(p));
}

export function isMemoryTool(name: string): boolean {
  return name === 'query_memory' || name === 'store_memory';
}

export function stepCount(parts: UIMessage['parts']): number {
  return parts.filter(p => p.type === 'step-start').length;
}

export { getToolName };

export function toolStateLabel(part: ToolPart): string {
  switch (part.state) {
    case 'input-streaming':
    case 'input-available':
      return 'running…';
    case 'approval-requested':
      return 'waiting for approval';
    case 'approval-responded':
      return part.approval.approved ? 'approved' : 'denied';
    case 'output-available':
      return part.preliminary ? 'streaming…' : 'done';
    case 'output-error':
      return 'failed';
    case 'output-denied':
      return 'denied';
    default:
      return '';
  }
}

export function toolOutputText(part: ToolPart): string | null {
  if (part.state === 'output-error') return part.errorText;
  if (part.state !== 'output-available') return null;
  const out = part.output;
  if (out == null) return null;
  return typeof out === 'string' ? out : (JSON.stringify(out, null, 2) ?? String(out));
}

export function emptySnapshot(): MemorySnapshot {
  return {
    counts: { recent: 0, observations: 0, insights: 0, entities: 0, reasoning: 0 },
    items: { recent: [], observations: [], insights: [], entities: [], reasoning: [] },
  };
}

export function formatErrorMessage(error: unknown): string | null {
  if (error instanceof Error) return error.message;
  if (error) return String(error);
  return null;
}

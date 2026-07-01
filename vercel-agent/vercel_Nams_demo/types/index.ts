export interface MemoryHit {
  content: string;
  source: 'conversation' | 'long-term' | 'reasoning';
  type: string;
  score?: number;
}

export interface QueryOutput {
  found: boolean;
  count?: number;
  memories: MemoryHit[];
}

export interface ReasoningStep {
  id: string;
  reasoning: string;
  actionTaken: string;
  result?: string;
}

export interface ParsedMemory {
  counts: { recent: number; observations: number; reasoning: number };
  items: { recent: MemoryHit[]; observations: MemoryHit[]; reasoning: MemoryHit[] };
}

export interface ChatComponentProps {
  suggestions?: string[];
  fluid?: boolean;
}

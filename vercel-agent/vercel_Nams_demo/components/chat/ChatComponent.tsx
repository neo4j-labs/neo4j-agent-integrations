'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport, isToolUIPart } from 'ai';

import { CleanIconButton, Typography } from '@neo4j-ndl/react';
import { Prompt, Response, Suggestion, Thinking, UserBubble } from '@neo4j-ndl/react/ai';
import { ArrowPathIconOutline, Square2StackIconOutline } from '@neo4j-ndl/react/icons';

import MemoryPanel from './MemoryPanel';
import ReasoningPanel from './ReasoningPanel';
import { AGENT_NAME, DEFAULT_SUGGESTIONS, MEMORY_MODES, SESSION_STORAGE_KEY } from '@/constants';
import type { ChatMode, MemorySnapshot, MemoryTab } from '@/types';
import {
  emptySnapshot,
  formatErrorMessage,
  getMsgText,
  getToolName,
  isMemoryTool,
  lastUserText,
  stepCount,
  toolParts,
} from '@/utils/message';

// Snapshot key for what NAMS already held before the first message.
const OPENING = '@opening';

// One id per browser, kept across reloads and new chats, so memory follows the user.
function browserUserId(): string {
  if (typeof window === 'undefined') return '';
  try {
    const stored = localStorage.getItem(SESSION_STORAGE_KEY);
    if (stored) return stored;
    const id = crypto.randomUUID();
    localStorage.setItem(SESSION_STORAGE_KEY, id);
    return id;
  } catch {
    return crypto.randomUUID();
  }
}

interface ChatComponentProps {
  mode: ChatMode;
  suggestions?: readonly string[];
}

export default function ChatComponent({ mode, suggestions = DEFAULT_SUGGESTIONS }: ChatComponentProps) {
  const endRef = useRef<HTMLDivElement>(null);
  const startedAtRef = useRef<number | null>(null);
  const wasBusyRef = useRef(false);
  const userId = useRef('');
  if (!userId.current) userId.current = browserUserId();

  const [input, setInput] = useState('');
  const [copyError, setCopyError] = useState<string | null>(null);
  const [thinkingTimes, setThinkingTimes] = useState<Record<string, number>>({});
  const [memory, setMemory] = useState<Record<string, MemorySnapshot>>({});
  const [expandedMemory, setExpandedMemory] = useState<Record<string, boolean>>({});
  const [expandedReasoning, setExpandedReasoning] = useState<Record<string, boolean>>({});
  const [activeTab, setActiveTab] = useState<Record<string, MemoryTab>>({});

  const { messages, sendMessage, regenerate, stop, status, error } = useChat({
    transport: new DefaultChatTransport({
      api: '/api/chat',
      // Only the newest message goes up; memory modes load earlier turns from NAMS.
      // Memory off has no NAMS, so it gets this chat's transcript instead.
      prepareSendMessagesRequest: ({ messages, trigger }) => ({
        body: {
          message: messages[messages.length - 1],
          trigger,
          sessionId: userId.current,
          ...(mode === 'off'
            ? { transcript: messages.slice(0, -1).map(m => ({ role: m.role, content: getMsgText(m) })) }
            : {}),
        },
      }),
    }),
  });

  const isBusy = status === 'submitted' || status === 'streaming';

  const loadMemory = useCallback(async (key: string, query: string) => {
    setMemory(prev => ({
      ...prev,
      [key]: { ...(prev[key] ?? emptySnapshot()), loading: true, error: undefined },
    }));
    try {
      const params = new URLSearchParams({ userId: userId.current, q: query });
      const response = await fetch(`/api/memory?${params}`);
      const payload: unknown = await response.json();
      if (!response.ok) {
        const detail = (payload as { error?: string } | null)?.error;
        throw new Error(detail ?? `Memory service returned ${response.status}.`);
      }
      setMemory(prev => ({ ...prev, [key]: payload as MemorySnapshot }));
    } catch (err) {
      setMemory(prev => ({
        ...prev,
        [key]: { ...emptySnapshot(), error: formatErrorMessage(err) ?? 'Could not reach the memory service.' },
      }));
    }
  }, []);

  useEffect(() => {
    if (mode !== 'off') void loadMemory(OPENING, '');
  }, [loadMemory, mode]);

  // Time each answer, then read what NAMS holds once it is done.
  useEffect(() => {
    if (isBusy && !wasBusyRef.current) {
      wasBusyRef.current = true;
      startedAtRef.current = Date.now();
      return;
    }
    if (!isBusy && wasBusyRef.current) {
      wasBusyRef.current = false;
      const last = messages.at(-1);
      const startedAt = startedAtRef.current;
      startedAtRef.current = null;
      if (last?.role === 'assistant') {
        if (startedAt !== null) setThinkingTimes(prev => ({ ...prev, [last.id]: Date.now() - startedAt }));
        if (mode !== 'off') void loadMemory(last.id, lastUserText(messages));
      }
    }
  }, [isBusy, messages, loadMemory, mode]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, status]);

  const handleSend = (override?: string) => {
    const text = (override ?? input).trim();
    if (!text || isBusy) return;
    setInput('');
    sendMessage({ text });
  };

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      setCopyError('Copy failed.');
      setTimeout(() => setCopyError(null), 3000);
    }
  };

  const errorMessage = formatErrorMessage(error);
  const opening = memory[OPENING];
  const knownAlready = opening ? Object.values(opening.counts).reduce((sum, n) => sum + n, 0) : 0;
  const showConversation = messages.length > 0 || errorMessage !== null;

  return (
    <section style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0, width: '100%' }}>
      <div
        className="n-bg-neutral-bg-weak"
        style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden', minHeight: 0, width: '100%' }}
      >
        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: 16 }}>
          <div style={{ margin: '0 auto', width: '100%', maxWidth: 860 }}>
            {copyError && (
              <div className="n-bg-warning-bg-weak n-border n-border-warning-border-weak n-rounded-lg n-p-2 n-mb-2">
                <Typography variant="body-small">{copyError}</Typography>
              </div>
            )}

            {!showConversation ? (
              <div className="n-flex n-flex-col n-gap-12" style={{ paddingTop: '8vh' }}>
                <div className="n-flex n-flex-col n-gap-2">
                  <Typography variant="display">Hi, how can I help you today?</Typography>
                  {knownAlready > 0 && (
                    <Typography variant="body-medium" style={{ color: 'var(--theme-color-neutral-text-weaker)' }}>
                      {AGENT_NAME}: NAMS is already holding {knownAlready}{' '}
                      {knownAlready === 1 ? 'memory' : 'memories'} from your earlier chats.
                    </Typography>
                  )}
                </div>
                <div className="n-flex n-flex-col n-gap-4">
                  <Typography variant="body-medium">Suggestions</Typography>
                  {suggestions.map((s, i) => (
                    <Suggestion key={s} isPrimary={i === 0} onClick={() => handleSend(s)}>{s}</Suggestion>
                  ))}
                </div>
              </div>
            ) : (
              <div className="n-flex n-flex-col n-gap-4 n-pb-4">
                {messages.map((msg, idx) => {
                  const isLast = idx === messages.length - 1;
                  const isLive = isBusy && isLast;

                  if (msg.role === 'user') {
                    return (
                      <div key={msg.id} style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <UserBubble avatarProps={{ name: 'U', type: 'letters' }}>{getMsgText(msg)}</UserBubble>
                      </div>
                    );
                  }

                  const ms = thinkingTimes[msg.id];
                  const snapshot = memory[msg.id];
                  const memoryCalls = toolParts(msg.parts).filter(p => isMemoryTool(getToolName(p)));
                  const text = getMsgText(msg);
                  const hasTrace = msg.parts.some(p => p.type === 'reasoning' || isToolUIPart(p));
                  const hasPanels = isLive || hasTrace || snapshot !== undefined || mode !== 'off';

                  return (
                    <div key={msg.id} className="n-w-full n-flex n-flex-col n-gap-2">
                      {(isLive || ms !== undefined) && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                          <span
                            style={{
                              width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                              background: isLive ? 'var(--theme-color-warning-text)' : 'var(--theme-color-success-text)',
                            }}
                          />
                          <span style={{ fontSize: 12, fontStyle: 'italic', color: 'var(--palette-neutral-text-weakest)' }}>
                            {ms === undefined ? 'Thinking…' : `Thought for ${Math.max(1, Math.round(ms / 1000))}s`}
                          </span>
                        </div>
                      )}

                      {hasPanels && (
                        <div style={{ border: '1px solid var(--theme-color-primary-border-weak)', borderRadius: 10, overflow: 'hidden' }}>
                          <MemoryPanel
                            mode={mode}
                            snapshot={snapshot}
                            memoryCalls={memoryCalls}
                            steps={stepCount(msg.parts)}
                            isLive={isLive}
                            isExpanded={expandedMemory[msg.id] ?? false}
                            onToggleExpand={() => setExpandedMemory(p => ({ ...p, [msg.id]: !(p[msg.id] ?? false) }))}
                            activeTab={activeTab[msg.id] ?? 'recent'}
                            onSetTab={tab => setActiveTab(p => ({ ...p, [msg.id]: tab }))}
                          />
                          <ReasoningPanel
                            parts={msg.parts}
                            isLive={isLive}
                            isExpanded={expandedReasoning[msg.id] ?? false}
                            onToggleExpand={() => setExpandedReasoning(p => ({ ...p, [msg.id]: !(p[msg.id] ?? false) }))}
                          />
                        </div>
                      )}

                      {text && (
                        <div
                          style={{
                            width: '100%', marginTop: 3, padding: '12px 16px', borderRadius: 10,
                            background: 'var(--theme-color-neutral-bg-strong)',
                            color: 'var(--theme-color-neutral-text-default)',
                            overflowWrap: 'anywhere',
                          }}
                        >
                          <Response isAnimating={isLive}>{text}</Response>
                        </div>
                      )}

                      {!isLive && (
                        <div className="n-flex n-flex-row n-gap-1.5">
                          {isLast && (
                            <CleanIconButton size="small" description="Re-run" onClick={() => regenerate()}>
                              <ArrowPathIconOutline />
                            </CleanIconButton>
                          )}
                          <CleanIconButton size="small" description="Copy" onClick={() => void handleCopy(text)}>
                            <Square2StackIconOutline />
                          </CleanIconButton>
                        </div>
                      )}
                    </div>
                  );
                })}

                {status === 'submitted' && messages.at(-1)?.role !== 'assistant' && <Thinking isThinking />}

                {status === 'error' && (
                  <div className="n-bg-danger-bg-weak n-border n-border-danger-border-weak n-rounded-lg n-p-3 n-flex n-items-start">
                    <Typography variant="body-small">⚠ {errorMessage ?? 'Something went wrong.'}</Typography>
                    <CleanIconButton size="small" description="Retry" onClick={() => regenerate()}>
                      <ArrowPathIconOutline />
                    </CleanIconButton>
                  </div>
                )}

                <div ref={endRef} />
              </div>
            )}
          </div>
        </div>

        <div className="n-px-4 n-pt-4 n-pb-1 n-mt-auto full-width-content">
          <div style={{ margin: '0 auto', width: '100%', maxWidth: 860 }}>
            <Prompt
              value={input}
              onChange={e => setInput(e.target.value)}
              onSubmitPrompt={() => handleSend()}
              onCancelPrompt={stop}
              isRunningPrompt={isBusy}
              isSubmitDisabled={input.trim().length === 0 && !isBusy}
              disclaimer={
                <Typography variant="body-small" style={{ color: 'var(--palette-neutral-text-weakest)' }}>
                  {mode === 'off'
                    ? 'Memory is off. This chat forgets you when you start a new chat or reload the page.'
                    : `Memories are stored in Neo4j via NAMS (${mode} · ${MEMORY_MODES[mode].detail}) and persist across chats.`}
                </Typography>
              }
            />
          </div>
        </div>
      </div>
    </section>
  );
}

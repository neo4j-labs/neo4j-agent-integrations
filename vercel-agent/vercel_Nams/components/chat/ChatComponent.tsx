'use client';

import { useEffect, useRef, useState } from 'react';
import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport } from 'ai';
import type { DynamicToolUIPart } from 'ai';

import { CleanIconButton, Typography } from '@neo4j-ndl/react';
import { Prompt, Response, Suggestion, Thinking, UserBubble } from '@neo4j-ndl/react/ai';
import { ArrowPathIconOutline, Square2StackIconOutline } from '@neo4j-ndl/react/icons';

import MemoryPanel from './MemoryPanel';
import ReasoningPanel from './ReasoningPanel';
import { getMsgText, parseMemory, formatErrorMessage } from '@/utils/message';
import { DEFAULT_SUGGESTIONS, SESSION_STORAGE_KEY } from '@/constants';
import type { ReasoningStep, ChatComponentProps } from '@/types';

export default function ChatComponent({ suggestions = DEFAULT_SUGGESTIONS, fluid = false }: ChatComponentProps) {
  const messagesEndRef    = useRef<HTMLDivElement>(null);
  const submittedAtRef    = useRef<number | null>(null);
  const prevStepCountRef  = useRef<number>(0);
  const resolvedConvIdRef = useRef<string | undefined>(undefined);

  const sessionId = useRef('');
  if (!sessionId.current) {
    const stored = typeof window !== 'undefined' ? localStorage.getItem(SESSION_STORAGE_KEY) : null;
    sessionId.current = stored ?? crypto.randomUUID();
    if (!stored && typeof window !== 'undefined') localStorage.setItem(SESSION_STORAGE_KEY, sessionId.current);
  }

  const [input, setInput]                         = useState('');
  const [copyError, setCopyError]                 = useState<string | null>(null);
  const [thinkingTimes, setThinkingTimes]         = useState<Record<string, number>>({});
  const [expandedReasoning, setExpandedReasoning] = useState<Record<string, boolean>>({});
  const [expandedMemory, setExpandedMemory]       = useState<Record<string, boolean>>({});
  const [activeMemTab, setActiveMemTab]           = useState<Record<string, 'recent' | 'observations' | 'reasoning'>>({});
  const [msgReasoningSteps, setMsgReasoningSteps] = useState<Record<string, ReasoningStep[]>>({});

  const { messages, sendMessage, regenerate, stop, status, error } = useChat({
    transport: new DefaultChatTransport({
      api:  '/api/chat',
      body: () => ({ sessionId: sessionId.current, conversationId: resolvedConvIdRef.current }),
    }),
    onFinish: ({ message }) => {
      if (message.role !== 'assistant') return;
      if (submittedAtRef.current !== null) {
        const ms = Date.now() - submittedAtRef.current;
        submittedAtRef.current = null;
        setThinkingTimes(prev => ({ ...prev, [message.id]: ms }));
      }
      const msgId     = message.id;
      const prevCount = prevStepCountRef.current;
      const params    = new URLSearchParams({ userId: sessionId.current });
      if (resolvedConvIdRef.current) params.set('conversationId', resolvedConvIdRef.current);
      fetch(`/api/reasoning?${params}`)
        .then(r => r.ok ? r.json() : null)
        .then((data: { steps?: ReasoningStep[] } | null) => {
          const steps    = data?.steps ?? [];
          const newSteps = steps.slice(prevCount);
          prevStepCountRef.current = steps.length;
          if (newSteps.length > 0) setMsgReasoningSteps(prev => ({ ...prev, [msgId]: newSteps }));
        })
        .catch(() => {});
    },
    onData: (part) => {
      if ((part as { type: string }).type === 'data-conversation-id') {
        const convId = (part as { data: string }).data;
        if (convId) resolvedConvIdRef.current = convId;
      }
    },
  });

  useEffect(() => {
    if (status === 'submitted') submittedAtRef.current = Date.now();
  }, [status]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, status]);

  const isStreaming = status === 'submitted' || status === 'streaming';

  const handleSend = (override?: string) => {
    const text = (override ?? input).trim();
    if (!text) return;
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

  return (
    <section style={fluid ? { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0, width: '100%' } : undefined}>
      <div
        className="n-bg-neutral-bg-weak"
        style={fluid
          ? { display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden', minHeight: 0, width: '100%' }
          : { width: '480px', height: '100%', display: 'flex', flexDirection: 'column' }}
      >
        <div
          className="n-p-4 n-flex n-flex-col n-grow n-overflow-y-auto"
          style={fluid ? { flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px' } : undefined}
        >
          {copyError && (
            <div className="n-bg-warning-bg-weak n-border n-border-warning-border-weak n-rounded-lg n-p-2 n-mb-2">
              <Typography variant="body-small">{copyError}</Typography>
            </div>
          )}

          {messages.length === 0 ? (
            <div className="n-flex n-flex-col n-gap-4">
              {errorMessage && (
                <div className="n-bg-danger-bg-weak n-border n-border-danger-border-weak n-rounded-lg n-p-3">
                  <Typography variant="body-small">⚠ {errorMessage}</Typography>
                </div>
              )}
              <div className="n-flex n-flex-col n-gap-12">
                <Typography variant="display">Hi, how can I help you today?</Typography>
                <div className="n-flex n-flex-col n-gap-4">
                  <Typography variant="body-medium">Suggestions</Typography>
                  {suggestions.map((s, i) => (
                    <Suggestion key={s} isPrimary={i === 0} onClick={() => handleSend(s)}>{s}</Suggestion>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="n-flex n-flex-col n-gap-4 n-pb-4">
              {messages.map((msg, idx) => {
                const isLast         = idx === messages.length - 1;
                const isLive         = isStreaming && isLast;
                const secs           = thinkingTimes[msg.id] ? Math.round(thinkingTimes[msg.id] / 1000) : null;
                const { counts, items } = parseMemory(msg.parts);
                const completedSteps = msgReasoningSteps[msg.id] ?? [];
                const toolParts      = msg.parts.filter(
                  (p): p is DynamicToolUIPart =>
                    p.type === 'dynamic-tool' &&
                    (p.toolName === 'query_memory' || p.toolName === 'store_memory'),
                );
                const hasOverlay = toolParts.length > 0 || isLive || completedSteps.length > 0;

                return (
                  <div key={msg.id} className="n-w-full"
                    style={msg.role === 'user' ? { display: 'flex', justifyContent: 'flex-end' } : undefined}>
                    {msg.role === 'user' ? (
                      <UserBubble avatarProps={{ name: 'U', type: 'letters' }}>{getMsgText(msg)}</UserBubble>
                    ) : (
                      <div className="n-w-full n-flex n-flex-col n-gap-2">
                        {hasOverlay && (
                          <div style={{ marginBottom: 4 }}>
                            {/* Thinking indicator */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                              <span style={{
                                width: 7, height: 7, borderRadius: '50%', flexShrink: 0, display: 'inline-block',
                                background: isLive
                                  ? 'var(--theme-color-warning-text)'
                                  : 'var(--theme-color-success-text)',
                              }} />
                              <span style={{ fontSize: 12, color: 'var(--palette-neutral-text-weakest)', fontStyle: 'italic' }}>
                                {isLive && !secs ? 'Thinking…' : `Thought for ${secs ?? '?'}s`}
                              </span>
                            </div>

                            {/* Memory + Reasoning panels */}
                            <div style={{ border: '1px solid var(--theme-color-primary-border-weak)', borderRadius: 10, overflow: 'hidden' }}>
                              <MemoryPanel
                                isLive={isLive}
                                counts={counts}
                                items={items}
                                isExpanded={expandedMemory[msg.id] ?? false}
                                onToggleExpand={() => setExpandedMemory(p => ({ ...p, [msg.id]: !(p[msg.id] ?? false) }))}
                                activeTab={activeMemTab[msg.id] ?? 'recent'}
                                onSetTab={tab => setActiveMemTab(p => ({ ...p, [msg.id]: tab }))}
                              />
                              <ReasoningPanel
                                isLive={isLive}
                                completedSteps={completedSteps}
                                toolParts={toolParts}
                                isExpanded={expandedReasoning[msg.id] ?? false}
                                onToggleExpand={() => setExpandedReasoning(p => ({ ...p, [msg.id]: !(p[msg.id] ?? false) }))}
                              />
                            </div>
                          </div>
                        )}

                        <Response isAnimating={isLive}>{getMsgText(msg)}</Response>

                        {(!isStreaming || !isLast) && (
                          <div className="n-flex n-flex-row n-gap-1.5">
                            <CleanIconButton size="small" description="Re-run" onClick={() => regenerate()}>
                              <ArrowPathIconOutline />
                            </CleanIconButton>
                            <CleanIconButton size="small" description="Copy" onClick={() => handleCopy(getMsgText(msg))}>
                              <Square2StackIconOutline />
                            </CleanIconButton>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}

              {status === 'submitted' && <Thinking isThinking />}

              {status === 'error' && (
                <div className="n-bg-danger-bg-weak n-border n-border-danger-border-weak n-rounded-lg n-p-3 n-flex n-items-start n-justify-between n-gap-2">
                  <Typography variant="body-small">⚠ {errorMessage ?? 'Something went wrong.'}</Typography>
                  <CleanIconButton size="small" description="Retry" onClick={() => regenerate()}>
                    <ArrowPathIconOutline />
                  </CleanIconButton>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        <div className="n-px-4 n-pt-4 n-pb-1 n-mt-auto full-width-content">
          <Prompt
            value={input}
            onChange={e => setInput(e.target.value)}
            onSubmitPrompt={() => handleSend()}
            onCancelPrompt={stop}
            isRunningPrompt={isStreaming}
            isSubmitDisabled={input.trim().length === 0 && !isStreaming}
            disclaimer={
              <Typography variant="body-small" style={{ color: 'var(--palette-neutral-text-weakest)' }}>
                Memories are stored in Neo4j via NAMS and persist across sessions.
              </Typography>
            }
          />
        </div>
      </div>
    </section>
  );
}

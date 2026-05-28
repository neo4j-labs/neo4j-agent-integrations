'use client';

import { useEffect, useRef, useState } from 'react';
import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport } from 'ai';
import type { UIMessage, DynamicToolUIPart } from 'ai';

import { CleanIconButton, TextLink, Typography } from '@neo4j-ndl/react';
import {
  Prompt,
  Response,
  Suggestion,
  Thinking,
  UserBubble,
} from '@neo4j-ndl/react/ai';
import {
  ArrowPathIconOutline,
  Cog6ToothIconOutline,
  HandThumbDownIconOutline,
  Square2StackIconOutline,
  XMarkIconOutline,
} from '@neo4j-ndl/react/icons';

interface McpToolRecord {
  tool: string;
  durationMs: number;
  ok: boolean;
}

interface MemoryContextData {
  semanticMatches: number;
  reflections: number;
  observations: number;
  recentMessages: number;
  mcpTools: McpToolRecord[];
}

interface ChatComponentProps {
  sessionId: string;
  userId?: string;
  conversationId?: string;
  onConversationIdResolved?: (id: string) => void;
  userName?: string;
  suggestions?: string[];
  onClose?: () => void;
  fluid?: boolean;
  hideHeader?: boolean;
  onMessageCountChange?: (count: number) => void;
  onTitleGenerated?: (title: string) => void;
}


const DEFAULT_SUGGESTIONS = [
  'I want to import data',
  'Create an AI agent',
  'Invite project members',
  'Generate a report',
];


export default function ChatComponent({
  sessionId,
  userId,
  conversationId,
  onConversationIdResolved,
  userName = 'User',
  suggestions = DEFAULT_SUGGESTIONS,
  onClose,
  fluid = false,
  hideHeader = false,
  onMessageCountChange,
  onTitleGenerated,
}: ChatComponentProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const msgTimestampsRef = useRef<Map<string, Date>>(new Map());
  const submittedAtRef = useRef<number | null>(null);
  const [msgThinkingTimes, setMsgThinkingTimes] = useState<Record<string, number>>({});
  const onTitleGeneratedRef = useRef(onTitleGenerated);
  onTitleGeneratedRef.current = onTitleGenerated;
  const onConversationIdResolvedRef = useRef(onConversationIdResolved);
  onConversationIdResolvedRef.current = onConversationIdResolved;
  const conversationIdRef = useRef<string | undefined>(conversationId);
  const pendingMemoryContextRef = useRef<MemoryContextData | null>(null);
  const [input, setInput] = useState('');
  const [copyError, setCopyError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [msgMemoryContexts, setMsgMemoryContexts] = useState<Record<string, MemoryContextData>>({});
  const {
    messages,
    setMessages,
    sendMessage,
    regenerate,
    stop,
    status,
    error,
  } = useChat({
    transport: new DefaultChatTransport({
      api: '/api/chat',
      body: () => ({ sessionId, userId, conversationId: conversationIdRef.current }),
    }),
    onFinish: ({ message }) => {
      if (message.role === 'assistant') {
        if (submittedAtRef.current !== null) {
          const thinkingMs = Date.now() - submittedAtRef.current;
          submittedAtRef.current = null;
          setMsgThinkingTimes(prev => ({ ...prev, [message.id]: thinkingMs }));
        }
        if (pendingMemoryContextRef.current) {
          const memCtx = pendingMemoryContextRef.current;
          pendingMemoryContextRef.current = null;
          setMsgMemoryContexts(prev => ({ ...prev, [message.id]: memCtx }));
        }
      }
    },
    onData: (dataPart) => {
      if (dataPart.type === 'data-session-title') {
        onTitleGeneratedRef.current?.(dataPart.data as string);
      }
      if (dataPart.type === 'data-memory-context') {
        pendingMemoryContextRef.current = dataPart.data as MemoryContextData;
      }
    },
  });

  useEffect(() => {
    let cancelled = false;
    setMessages([]);
    setHistoryLoading(true);
    const params = new URLSearchParams({ sessionId });
    if (conversationIdRef.current) params.set('conversationId', conversationIdRef.current);
    fetch(`/api/chat?${params.toString()}`)
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled) {
          if (data.conversationId && !conversationIdRef.current) {
            conversationIdRef.current = data.conversationId;
            onConversationIdResolvedRef.current?.(data.conversationId);
          }
          if (Array.isArray(data.messages) && data.messages.length > 0) {
            setMessages(data.messages);
          }
        }
      })
      .catch((err) => { console.warn('[ChatComponent] Failed to load conversation history:', err); })
      .finally(() => { if (!cancelled) setHistoryLoading(false); });
    return () => { cancelled = true; };
  }, [sessionId]);

  const isStreaming = status === 'submitted' || status === 'streaming';


  useEffect(() => {
    if (status === 'submitted') {
      submittedAtRef.current = Date.now();
    }
  }, [status]);

  useEffect(() => {
    messages.forEach((msg) => {
      if (!msgTimestampsRef.current.has(msg.id)) {
        msgTimestampsRef.current.set(msg.id, new Date());
      }
    });
    onMessageCountChange?.(messages.length);
  }, [messages.length]);

  const formatTimestamp = (date?: Date) => {
    if (!date) return '';
    return date.toLocaleString('en-GB', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: false,
    }).replace(',', '');
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  const getMsgText = (msg: UIMessage) =>
    msg.parts
      .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
      .map((p) => p.text)
      .join('');

  const handleSend = (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text) return;
    setInput('');
    sendMessage({ text });
  };

  const handleCancel = () => stop();

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopyError(null);
    } catch {
      setCopyError('Copy failed — please copy manually.');
      setTimeout(() => setCopyError(null), 3000);
    }
  };

  const errorMessage =
    error instanceof Error ? error.message : error ? String(error) : null;

  return (
    <section
      style={
        fluid
          ? { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }
          : undefined
      }
      className={fluid ? undefined : 'n-h-screen'}
    >
      <div
        style={fluid ? { display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden', minHeight: 0, width: '100%' } : undefined}
        className={fluid ? 'n-bg-neutral-bg-weak' : 'n-w-[440px] n-h-full n-flex n-flex-col n-bg-neutral-bg-weak'}
      >
        {!hideHeader && (
          <div className="n-flex n-flex-row n-border-b n-border-neutral-border-weak n-p-3">
            <div className="n-ml-auto">
              <CleanIconButton description="settings" tooltipProps={{}}>
                <Cog6ToothIconOutline />
              </CleanIconButton>
              <CleanIconButton description="close" onClick={onClose}>
                <XMarkIconOutline />
              </CleanIconButton>
            </div>
          </div>
        )}

        <div
          className="n-p-4 n-flex n-flex-col n-grow n-overflow-y-auto"
          style={fluid ? { flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px' } : undefined}
        >
          {historyLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', paddingTop: '32px' }}>
              <Typography variant="body-small" style={{ opacity: 0.5 }}>Loading conversation…</Typography>
            </div>
          ) : (
            <>
          {copyError && (
            <div className="n-bg-warning-bg-weak n-border n-border-warning-border-weak n-rounded-lg n-p-2 n-mb-2">
              <Typography variant="body-small">{copyError}</Typography>
            </div>
          )}

          {messages.length === 0 ? (
            <div className="n-flex n-flex-col n-gap-4">
              {errorMessage && (
                <div className="n-bg-danger-bg-weak n-border n-border-danger-border-weak n-rounded-lg n-p-3 n-flex n-items-start n-justify-between n-gap-2">
                  <Typography variant="body-small">⚠ {errorMessage}</Typography>
                  <CleanIconButton size="small" description="Retry" onClick={() => regenerate()}>
                    <ArrowPathIconOutline />
                  </CleanIconButton>
                </div>
              )}
              <div className="n-flex n-flex-col n-gap-12">
                <Typography variant="display">
                  Hi {userName}, how can I help you today?
                </Typography>

                <div className="n-flex n-flex-col n-gap-4">
                  <Typography variant="body-medium">Suggestions</Typography>
                  {suggestions.map((s, i) => (
                    <Suggestion
                      key={s}
                      isPrimary={i === 0}
                      onClick={() => handleSend(s)}
                    >
                      {s}
                    </Suggestion>
                  ))}
                </div>

                <Typography variant="body-medium">
                  You can also drag and drop files here, or{' '}
                  <TextLink as="button" type="internal-underline">
                    browse
                  </TextLink>
                  . Supports CSV, MOV, PDF
                </Typography>
              </div>
            </div>
          ) : (
            <div className="n-flex n-flex-col n-gap-4 n-pb-4">
              {messages.map((msg, idx) => (
                <div
                  key={msg.id}
                  className="n-w-full"
                  style={msg.role === 'user' ? { display: 'flex', justifyContent: 'flex-end' } : undefined}
                >
                  {msg.role === 'user' ? (
                    <div>
                      <UserBubble
                        avatarProps={{
                          name: userName.slice(0, 2).toUpperCase(),
                          type: 'letters',
                        }}
                      >
                        {getMsgText(msg)}
                      </UserBubble>
                      {msgTimestampsRef.current.get(msg.id) && (
                        <Typography
                          variant="body-small"
                          style={{ display: 'block', marginTop: '4px', opacity: 0.6, textAlign: 'right' }}
                        >
                          {formatTimestamp(msgTimestampsRef.current.get(msg.id)!)}
                        </Typography>
                      )}
                    </div>
                  ) : (
                    <div className="n-w-full n-flex n-flex-col n-gap-2">
                      {/* Show completed thinking duration above the response */}
                      {msg.id in msgThinkingTimes && (
                        <Thinking
                          isThinking={false}
                          thinkingMs={msgThinkingTimes[msg.id]}
                        />
                      )}
                      <div className="n-flex n-flex-col n-gap-2">
                        {msgMemoryContexts[msg.id] &&
                          (msgMemoryContexts[msg.id].recentMessages +
                           msgMemoryContexts[msg.id].semanticMatches +
                           msgMemoryContexts[msg.id].reflections +
                           msgMemoryContexts[msg.id].observations) > 0 && (
                          <div
                            style={{
                              display: 'flex',
                              flexDirection: 'column',
                              gap: '6px',
                              padding: '6px 10px',
                              borderRadius: '8px',
                              border: '1px solid var(--theme-color-primary-border-weak)',
                              backgroundColor: 'var(--theme-color-primary-bg-weak)',
                            }}
                          >
                            {/* Memory context counts */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                              <Typography
                                variant="body-small"
                                style={{ fontWeight: 600, color: 'var(--theme-color-primary-text)', whiteSpace: 'nowrap' }}
                              >
                                🧠 Agent Memory
                              </Typography>
                              {msgMemoryContexts[msg.id].recentMessages > 0 && (
                                <span style={{ fontSize: '11px', padding: '1px 7px', borderRadius: '10px', backgroundColor: 'var(--theme-color-info-bg-weak)', color: 'var(--theme-color-info-text)' }}>
                                  {msgMemoryContexts[msg.id].recentMessages} recent
                                </span>
                              )}
                              {msgMemoryContexts[msg.id].semanticMatches > 0 && (
                                <span style={{ fontSize: '11px', padding: '1px 7px', borderRadius: '10px', backgroundColor: 'var(--theme-color-success-bg-weak)', color: 'var(--theme-color-success-text)' }}>
                                  {msgMemoryContexts[msg.id].semanticMatches} semantic
                                </span>
                              )}
                              {msgMemoryContexts[msg.id].reflections > 0 && (
                                <span style={{ fontSize: '11px', padding: '1px 7px', borderRadius: '10px', backgroundColor: 'var(--theme-color-warning-bg-weak)', color: 'var(--theme-color-warning-text)' }}>
                                  {msgMemoryContexts[msg.id].reflections} reflections
                                </span>
                              )}
                              {msgMemoryContexts[msg.id].observations > 0 && (
                                <span style={{ fontSize: '11px', padding: '1px 7px', borderRadius: '10px', backgroundColor: 'var(--theme-color-neutral-bg-weak)', color: 'var(--theme-color-neutral-text-default)' }}>
                                  {msgMemoryContexts[msg.id].observations} observations
                                </span>
                              )}
                            </div>

                            {/* MCP tool call details (only shown when MCP transport is active) */}
                            {msgMemoryContexts[msg.id].mcpTools?.length > 0 && (
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', paddingTop: '2px', borderTop: '1px solid var(--theme-color-primary-border-weak)' }}>
                                <Typography
                                  variant="body-small"
                                  style={{ width: '100%', fontSize: '10px', color: 'var(--theme-color-primary-text)', opacity: 0.7, marginBottom: '2px' }}
                                >
                                  🔧 MCP tools used
                                </Typography>
                                {msgMemoryContexts[msg.id].mcpTools.map((t, i) => (
                                  <span
                                    key={i}
                                    title={t.ok ? `${t.durationMs}ms` : `failed after ${t.durationMs}ms`}
                                    style={{
                                      fontSize: '10px',
                                      padding: '1px 6px',
                                      borderRadius: '8px',
                                      fontFamily: 'monospace',
                                      backgroundColor: t.ok
                                        ? 'var(--theme-color-success-bg-weak)'
                                        : 'var(--theme-color-danger-bg-weak)',
                                      color: t.ok
                                        ? 'var(--theme-color-success-text)'
                                        : 'var(--theme-color-danger-text)',
                                    }}
                                  >
                                    {t.tool.replace('memory_', '')} · {t.durationMs}ms
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                        {/* Tool calls made by the model for this response */}
                        {msg.parts
                          .filter((p): p is DynamicToolUIPart => p.type === 'dynamic-tool')
                          .map((part) => {
                            const isRunning = part.state === 'input-streaming' || part.state === 'input-available';
                            const isDone = part.state === 'output-available';
                            const isError = (part as any).state === 'output-error';
                            const query = (!isRunning && (part.input as any)?.query) || null;
                            const rawOutput = isDone ? (part as any).output : null;
                            const outputText =
                              rawOutput == null ? null
                              : typeof rawOutput === 'string' ? rawOutput
                              : JSON.stringify(rawOutput);
                            const displayOutput =
                              outputText === '[]' ? 'No results found.'
                              : outputText != null ? outputText.slice(0, 800)
                              : null;
                            return (
                              <div
                                key={part.toolCallId}
                                style={{
                                  fontSize: '12px',
                                  fontFamily: 'monospace',
                                  padding: '8px 10px',
                                  borderRadius: '8px',
                                  border: '1px solid var(--theme-color-neutral-border-weak)',
                                  backgroundColor: 'var(--theme-color-neutral-bg-default)',
                                  display: 'flex',
                                  flexDirection: 'column',
                                  gap: '4px',
                                }}
                              >
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                  <span style={{ fontWeight: 600, color: 'var(--theme-color-primary-text)' }}>
                                    🔧 {part.title ?? part.toolName}
                                  </span>
                                  {isRunning && <span style={{ opacity: 0.6, fontSize: '11px' }}>running…</span>}
                                  {isDone && <span style={{ color: 'var(--theme-color-success-text)', fontSize: '11px' }}>✓ done</span>}
                                  {isError && <span style={{ color: 'var(--theme-color-danger-text)', fontSize: '11px' }}>✗ error</span>}
                                </div>
                                {query && (
                                  <div style={{ color: 'var(--theme-color-neutral-text-weaker)', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                                    {query}
                                  </div>
                                )}
                                {displayOutput && (
                                  <div style={{ color: 'var(--theme-color-neutral-text-default)', whiteSpace: 'pre-wrap', wordBreak: 'break-all', borderTop: '1px solid var(--theme-color-neutral-border-weak)', paddingTop: '4px', marginTop: '2px' }}>
                                    {displayOutput}
                                  </div>
                                )}
                                {isError && (
                                  <div style={{ color: 'var(--theme-color-danger-text)' }}>
                                    {(part as any).errorText}
                                  </div>
                                )}
                              </div>
                            );
                          })
                        }
                        <Response
                          isAnimating={
                            isStreaming && idx === messages.length - 1
                          }
                        >
                          {getMsgText(msg)}
                        </Response>
                        {msgTimestampsRef.current.get(msg.id) && (
                          <Typography
                            variant="body-small"
                            style={{ opacity: 0.6, paddingLeft: '8px' }}
                          >
                            {formatTimestamp(msgTimestampsRef.current.get(msg.id)!)}
                          </Typography>
                        )}

                        {(!isStreaming || idx < messages.length - 1) && (
                          <div className="n-flex n-flex-row n-gap-1.5">
                            <CleanIconButton size="small" description="Dislike">
                              <HandThumbDownIconOutline />
                            </CleanIconButton>
                            <CleanIconButton size="small" description="Re-run">
                              <ArrowPathIconOutline />
                            </CleanIconButton>
                            <CleanIconButton
                              size="small"
                              description="Copy"
                              onClick={() => handleCopy(getMsgText(msg))}
                            >
                              <Square2StackIconOutline />
                            </CleanIconButton>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {(status === 'submitted') && (
                <>
                  <Thinking isThinking />
                  <Typography
                    variant="body-small"
                    style={{ opacity: 0.5, paddingLeft: '4px', marginTop: '-6px' }}
                  >
                    Fetching memory context…
                  </Typography>
                </>
              )}

              {status === 'error' && (
                <div className="n-bg-danger-bg-weak n-border n-border-danger-border-weak n-rounded-lg n-p-3 n-flex n-items-start n-justify-between n-gap-2">
                  <Typography variant="body-small">
                    ⚠ {errorMessage ?? 'Something went wrong. Please try again.'}
                  </Typography>
                  <CleanIconButton size="small" description="Retry" onClick={() => regenerate()}>
                    <ArrowPathIconOutline />
                  </CleanIconButton>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
            </>
          )}
        </div>

        <div className="n-px-4 n-pt-4 n-pb-1 n-mt-auto full-width-content">
          <Prompt
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onSubmitPrompt={() => handleSend()}
            onCancelPrompt={handleCancel}
            isRunningPrompt={isStreaming}
            isSubmitDisabled={input.trim().length === 0 && !isStreaming}
            disclaimer={
              <Typography
                variant="body-small"
                style={{ color: 'var(--palette-neutral-text-weakest)' }}
              >
                All information should be verified independently.
              </Typography>
            }
          />
        </div>

      </div>
    </section>
  );
}

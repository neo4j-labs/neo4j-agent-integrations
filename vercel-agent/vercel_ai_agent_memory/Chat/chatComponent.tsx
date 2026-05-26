'use client';

import { useEffect, useRef, useState } from 'react';
import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport } from 'ai';
import type { UIMessage } from 'ai';

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
  PlusIconOutline,
  Square2StackIconOutline,
  XMarkIconOutline,
} from '@neo4j-ndl/react/icons';

interface ChatComponentProps {
  sessionId: string;
  userName?: string;
  suggestions?: string[];
  onClose?: () => void;
  fluid?: boolean;
  hideHeader?: boolean;
  onMessageCountChange?: (count: number) => void;
}


const DEFAULT_SUGGESTIONS = [
  'I want to import data',
  'Create an AI agent',
  'Invite project members',
  'Generate a report',
];


export default function ChatComponent({
  sessionId,
  userName = 'User',
  suggestions = DEFAULT_SUGGESTIONS,
  onClose,
  fluid = false,
  hideHeader = false,
  onMessageCountChange,
}: ChatComponentProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const msgTimestampsRef = useRef<Map<string, Date>>(new Map());
  const thinkingTimesRef = useRef<Map<string, number>>(new Map()); // assistantMsgId → ms
  const submittedAtRef = useRef<number | null>(null);
  const [input, setInput] = useState('');
  const {
    messages,
    sendMessage,
    stop,
    status,
  } = useChat({
    transport: new DefaultChatTransport({
      api: '/api/chat',
      body: { sessionId },
    }),
  });

  const isStreaming = status === 'submitted' || status === 'streaming';
  const lastMsg = messages[messages.length - 1];

  // Record submitted timestamp so we can measure thinking duration
  useEffect(() => {
    if (status === 'submitted') {
      submittedAtRef.current = Date.now();
    }
  }, [status]);

  // Record a timestamp for each new message; capture thinking time for assistant messages
  useEffect(() => {
    messages.forEach((msg) => {
      if (!msgTimestampsRef.current.has(msg.id)) {
        msgTimestampsRef.current.set(msg.id, new Date());
        if (msg.role === 'assistant' && submittedAtRef.current !== null) {
          thinkingTimesRef.current.set(msg.id, Date.now() - submittedAtRef.current);
          submittedAtRef.current = null;
        }
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
          {messages.length === 0 ? (
            <div className="n-flex n-flex-col">
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
                      {thinkingTimesRef.current.has(msg.id) && (
                        <Thinking
                          isThinking={false}
                          thinkingMs={thinkingTimesRef.current.get(msg.id)}
                        />
                      )}
                      <div className="n-flex n-flex-col n-gap-2">
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
                              onClick={() =>
                                navigator.clipboard.writeText(getMsgText(msg))
                              }
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
                <Thinking isThinking />
              )}

              {status === 'error' && (
                <div className="n-bg-danger-bg-weak n-border n-border-danger-border-weak n-rounded-lg n-p-3">
                  <Typography variant="body-small">
                    ⚠ Something went wrong. Please try again.
                  </Typography>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
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
          // bottomContent={
          //   <CleanIconButton description="Add files" size="small">
          //     <PlusIconOutline />
          //   </CleanIconButton>
          // }
          />
        </div>

      </div>
    </section>
  );
}

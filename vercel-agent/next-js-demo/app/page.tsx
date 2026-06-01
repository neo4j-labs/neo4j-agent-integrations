'use client';

import { useChat, type UIMessage } from '@ai-sdk/react';
import { useState, useCallback, useMemo, type FormEvent } from 'react';
import { Banner, Button, Flex, LoadingSpinner, StatusIndicator, TextArea, Typography } from '@neo4j-ndl/react';

interface DemoStatus {
  modelProvider: string;
  modelName: string;
  memoryEnabled: boolean;
  memoryConfigSource: string;
  agentId: string;
}

function getMessageText(message?: UIMessage): string {
  const candidate = message as unknown as {
    content?: unknown;
    parts?: Array<{ type?: string; text?: string }>;
  };

  if (!candidate) return '';
  if (typeof candidate.content === 'string') return candidate.content;
  if (Array.isArray(candidate.parts)) {
    return candidate.parts
      .filter((part) => part?.type === 'text' && typeof part?.text === 'string')
      .map((part) => part.text || '')
      .join('\n');
  }
  return '';
}

export default function ChatPage() {
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [statusError, setStatusError] = useState('');
  const [saveMessage, setSaveMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [input, setInput] = useState('');

  const { messages, sendMessage, status: chatStatus, error: chatError } = useChat({
    api: '/api/chat',
  });

  const isBusy = chatStatus === 'submitted' || chatStatus === 'streaming';

  const lastAssistantText = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i]?.role === 'assistant') {
        return getMessageText(messages[i]);
      }
    }
    return '';
  }, [messages]);

  const loadStatus = useCallback(async () => {
    setStatusError('');
    try {
      const response = await fetch('/api/chat');
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error || 'Failed to load status');
      setStatus(data);
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : 'Failed to load status');
    }
  }, []);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!input.trim() || isBusy) return;
    setSaveMessage('');
    await sendMessage({ text: input.trim() });
    setInput('');
  };

  const saveAnswer = useCallback(async () => {
    if (!lastAssistantText || saving) return;
    const content = lastAssistantText.trim();

    try {
      setSaving(true);
      setSaveMessage('Saving to memory...');

      const title = content.length > 100 ? `${content.substring(0, 97)}...` : content;
      const response = await fetch('/api/chat', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: `Research: ${title}`,
          content,
          kind: 'semantic',
          tags: ['demo', 'research'],
        }),
      });

      const data = await response.json();
      if (!response.ok || !data?.ok) {
        throw new Error(data?.error || 'Failed to save');
      }

      setSaveMessage('✓ Saved to Neo4j Agent Memory');
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  }, [lastAssistantText, saving]);

  return (
    <div className='n-bg-palette-neutral-bg-weak min-h-screen p-6'>
      <Flex flexDirection='column' gap='6' className='mx-auto max-w-5xl'>
        <div className='n-bg-palette-neutral-bg-default rounded-2xl border n-border-palette-neutral-border-weak p-6 shadow-sm'>
          <Typography variant='label' className='n-text-palette-primary-text'>
            Neo4j Integration Demo
          </Typography>
          <Typography variant='h2' className='mt-2'>
            Vercel AI SDK + Neo4j Agent Memory
          </Typography>
          <Typography variant='body-medium' className='mt-2 max-w-3xl n-text-palette-neutral-text-weak'>
            Streaming chat with Neo4j graph search and memory-backed follow-ups.
          </Typography>

          <Flex gap='2' className='mt-4' flexWrap='wrap'>
            <Button size='medium' fill='outlined' color='neutral' onClick={loadStatus}>
              Refresh Status
            </Button>
            <Button
              size='medium'
              fill='outlined'
              color='primary'
              onClick={saveAnswer}
              isDisabled={!lastAssistantText || saving}
            >
              {saving ? (
                <Flex gap='2' alignItems='center'>
                  <LoadingSpinner size='small' />
                  Saving...
                </Flex>
              ) : (
                'Save Last Answer To Memory'
              )}
            </Button>
          </Flex>

          {status && (
            <div className='mt-4 grid grid-cols-1 gap-2 md:grid-cols-2'>
              <Flex gap='2' alignItems='center'>
                <Typography variant='label' className='n-text-palette-neutral-text-weak'>
                  Model
                </Typography>
                <Typography variant='body-medium'>
                  {status.modelProvider} / {status.modelName}
                </Typography>
              </Flex>
              <Flex gap='2' alignItems='center'>
                <Typography variant='label' className='n-text-palette-neutral-text-weak'>
                  Memory
                </Typography>
                <StatusIndicator type={status.memoryEnabled ? 'success' : 'danger'} />
                <Typography variant='body-medium'>{status.memoryEnabled ? 'Enabled' : 'Disabled'}</Typography>
              </Flex>
              <Flex gap='2' alignItems='center'>
                <Typography variant='label' className='n-text-palette-neutral-text-weak'>
                  Source
                </Typography>
                <Typography variant='body-medium'>{status.memoryConfigSource}</Typography>
              </Flex>
              <Flex gap='2' alignItems='center'>
                <Typography variant='label' className='n-text-palette-neutral-text-weak'>
                  Agent ID
                </Typography>
                <Typography variant='body-medium'>{status.agentId}</Typography>
              </Flex>
            </div>
          )}

          {statusError && (
            <div className='mt-3'>
              <Banner type='danger' description={statusError} />
            </div>
          )}

          {saveMessage && (
            <div className='mt-3'>
              <Banner
                type={
                  saveMessage.toLowerCase().includes('fail') || saveMessage.toLowerCase().includes('error')
                    ? 'danger'
                    : 'success'
                }
                description={saveMessage}
              />
            </div>
          )}

          {chatError && (
            <div className='mt-3'>
              <Banner type='danger' description={chatError.message} />
            </div>
          )}
        </div>

        <div className='n-bg-palette-neutral-bg-default rounded-2xl border n-border-palette-neutral-border-weak p-6 shadow-sm'>
          <div className='mb-4 max-h-[52vh] overflow-y-auto rounded-xl n-bg-palette-neutral-bg-weak p-4'>
            <Flex flexDirection='column' gap='3'>
              {messages.length === 0 && (
                <Typography variant='body-medium' className='n-text-palette-neutral-text-weak'>
                  Try: &quot;Show me tech companies&quot; or &quot;Which industries have the most organizations?&quot;
                </Typography>
              )}

              {messages.map((message) => {
                const text = getMessageText(message) || '[non-text content]';
                const isUser = message.role === 'user';

                return (
                  <Flex key={message.id} justifyContent={isUser ? 'flex-end' : 'flex-start'}>
                    <div
                      className={[
                        'max-w-[85%] rounded-xl px-4 py-3 shadow-sm',
                        isUser
                          ? 'n-bg-palette-primary-bg-strong n-text-palette-neutral-text-inverse'
                          : 'n-bg-palette-neutral-bg-default border n-border-palette-neutral-border-weak',
                      ].join(' ')}
                    >
                      <Typography variant='label' className='mb-1 opacity-70'>
                        {message.role}
                      </Typography>
                      <Typography variant='body-medium' className='whitespace-pre-wrap'>
                        {text}
                      </Typography>
                    </div>
                  </Flex>
                );
              })}

              {isBusy && (
                <Flex gap='2' alignItems='center'>
                  <LoadingSpinner size='small' />
                  <Typography variant='body-medium' className='n-text-palette-neutral-text-weak'>
                    Streaming response...
                  </Typography>
                </Flex>
              )}
            </Flex>
          </div>

          <form onSubmit={handleSubmit}>
            <Flex gap='3' flexDirection='column' className='md:flex-row'>
              <TextArea
                value={input}
                placeholder='Ask about organizations, industries, or locations...'
                isFluid={true}
                className='flex-1'
                style={{ minHeight: '6rem' }}
                htmlAttributes={{
                  onChange: (event) => setInput(event.target.value),
                }}
              />
              <Button type='submit' size='large' fill='filled' color='primary' isDisabled={isBusy || !input.trim()}>
                Send
              </Button>
            </Flex>
          </form>
        </div>
      </Flex>
    </div>
  );
}

'use client';

import { useChat } from '@ai-sdk/react';
import { useState, useCallback, useMemo, FormEvent } from 'react';

interface DemoStatus {
  modelProvider: string;
  modelName: string;
  memoryEnabled: boolean;
  memoryConfigSource: string;
  agentId: string;
}

function getMessageText(message: any): string {
  if (typeof message.content === 'string') return message.content;
  if (Array.isArray(message.parts)) {
    return message.parts
      .filter((p: any) => p?.type === 'text')
      .map((p: any) => p?.text || '')
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

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isBusy) return;
    setSaveMessage('');
    sendMessage({ text: input });
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
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 p-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">
            Vercel AI SDK + Neo4j Agent Memory
          </h1>
          <p className="text-slate-300">
            Chat with an AI assistant that remembers your research insights
          </p>
        </div>

        {/* Status Panel */}
        <div className="bg-slate-700 rounded-lg p-6 mb-6 border border-slate-600">
          <div className="flex gap-4 items-center mb-4">
            <button
              onClick={loadStatus}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition"
            >
              Load Status
            </button>
            {lastAssistantText && (
              <button
                onClick={saveAnswer}
                disabled={saving}
                className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white rounded-lg font-medium transition"
              >
                {saving ? 'Saving...' : 'Save to Memory'}
              </button>
            )}
          </div>

          {statusError && <div className="text-red-400 mb-2">{statusError}</div>}
          {saveMessage && <div className={`mb-2 ${saveMessage.includes('failed') || saveMessage.includes('Failed') ? 'text-red-400' : 'text-green-400'}`}>{saveMessage}</div>}

          {status && (
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-slate-400">Model:</span>
                <span className="text-white ml-2">
                  {status.modelProvider} / {status.modelName}
                </span>
              </div>
              <div>
                <span className="text-slate-400">Memory:</span>
                <span className={`ml-2 ${status.memoryEnabled ? 'text-green-400' : 'text-red-400'}`}>
                  {status.memoryEnabled ? '✓ Enabled' : '✗ Disabled'}
                </span>
              </div>
              <div>
                <span className="text-slate-400">Source:</span>
                <span className="text-white ml-2">{status.memoryConfigSource}</span>
              </div>
              <div>
                <span className="text-slate-400">Agent ID:</span>
                <span className="text-white ml-2">{status.agentId}</span>
              </div>
            </div>
          )}
        </div>

        {/* Chat Container */}
        <div className="bg-slate-700 rounded-lg overflow-hidden border border-slate-600 flex flex-col h-96">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 && (
              <div className="text-slate-400 text-center py-8">
                Try: "Show me tech companies" or "What industries have the most funding?"
              </div>
            )}
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-600 text-slate-100'
                  }`}
                >
                  <p className="whitespace-pre-wrap">{getMessageText(msg)}</p>
                </div>
              </div>
            ))}
            {isBusy && (
              <div className="flex justify-start">
                <div className="bg-slate-600 text-slate-100 px-4 py-2 rounded-lg">
                  <div className="flex gap-2">
                    <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                    <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <form onSubmit={handleSubmit} className="border-t border-slate-600 p-4">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about organizations, industries, or locations..."
                disabled={isBusy}
                className="flex-1 px-4 py-2 bg-slate-600 text-white placeholder-slate-400 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!input.trim() || isBusy}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white rounded-lg font-medium transition"
              >
                Send
              </button>
            </div>
            {chatError && <div className="text-red-400 text-sm mt-2">{chatError.message}</div>}
          </form>
        </div>
      </div>
    </div>
  );
}

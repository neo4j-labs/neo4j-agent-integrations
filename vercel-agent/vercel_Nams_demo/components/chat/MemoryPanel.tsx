'use client';

import { MEMORY_TABS } from '@/constants';
import type { ChatMode, MemorySnapshot, MemoryTab } from '@/types';
import { getToolName, toolStateLabel, type ToolPart } from '@/utils/message';
import { chip, footnote, panelHeader, panelTitle } from './styles';

// How memory happened in each mode, shown under the expanded panel.
const HOW: Record<ChatMode, string> = {
  provider:
    'createNamsProvider() built the model. Memory was added to the prompt before the model answered and the turn was saved after. The model never saw a memory tool.',
  middleware:
    'createNams().wrap() wrapped this one model. Memory was added to the prompt before the model answered and the turn was saved after. The model never saw a memory tool.',
  tools:
    'The model drove memory itself, calling query_memory and store_memory from createNams().toolsWithMcp(). The route also saves the text of each turn.',
  hooks:
    "The app's code drove memory, not the model: hooks().loadSession() restored the chat before the answer, onFinish() saved the turn after, and the route wrote one reasoning step per agent step.",
  off: 'Memory is off. Nothing was loaded from or saved to NAMS.',
};

// The badge that tells the modes apart at a glance.
function driver(mode: ChatMode, memoryCalls: number, steps: number): string | null {
  switch (mode) {
    case 'tools':
      return memoryCalls > 0
        ? `model called ${memoryCalls} memory tool${memoryCalls === 1 ? '' : 's'}`
        : 'model called no memory tool';
    case 'hooks':
      return steps > 0
        ? `app hooks · ${steps} reasoning step${steps === 1 ? '' : 's'} saved`
        : 'app hooks · loadSession + onFinish';
    case 'provider':
      return 'wrapped provider · never a tool call';
    case 'middleware':
      return 'wrapped model · never a tool call';
    default:
      return null;
  }
}

interface MemoryPanelProps {
  mode: ChatMode;
  snapshot?: MemorySnapshot;
  memoryCalls: readonly ToolPart[];
  steps: number;
  isLive: boolean;
  isExpanded: boolean;
  onToggleExpand: () => void;
  activeTab: MemoryTab;
  onSetTab: (tab: MemoryTab) => void;
}

export default function MemoryPanel({
  mode,
  snapshot,
  memoryCalls,
  steps,
  isLive,
  isExpanded,
  onToggleExpand,
  activeTab,
  onSetTab,
}: MemoryPanelProps) {
  const counts = snapshot?.counts;
  const total = counts ? MEMORY_TABS.reduce((sum, tab) => sum + counts[tab.id], 0) : 0;

  const drove = driver(mode, memoryCalls.length, steps);
  const isPending = mode !== 'off' && (isLive || Boolean(snapshot?.loading));
  const canExpand = total > 0 || Boolean(snapshot?.error);
  if (!drove && !canExpand && !isPending && memoryCalls.length === 0) return null;

  // Fall back to the first tab that has something in it.
  const shownTab = counts && counts[activeTab] === 0
    ? (MEMORY_TABS.find(tab => counts[tab.id] > 0)?.id ?? activeTab)
    : activeTab;
  const items = snapshot?.items[shownTab] ?? [];

  const handleChipClick = (event: React.MouseEvent, tab: MemoryTab) => {
    event.stopPropagation();
    onSetTab(tab);
    if (!isExpanded) onToggleExpand();
  };

  return (
    <div>
      <div
        style={{
          ...panelHeader,
          background: 'var(--theme-color-primary-bg-weak)',
          borderBottom: '1px solid var(--theme-color-primary-border-weak)',
          cursor: canExpand ? 'pointer' : 'default',
        }}
        onClick={() => canExpand && onToggleExpand()}
      >
        <span style={{ fontSize: 10, color: 'var(--theme-color-primary-text)' }}>●</span>
        <span style={{ ...panelTitle, color: 'var(--theme-color-primary-text)' }}>Agent Memory</span>

        {MEMORY_TABS.map(tab =>
          counts && counts[tab.id] > 0 ? (
            <span
              key={tab.id}
              style={{
                ...chip(tab.id === 'entities' ? 'success' : tab.id === 'reasoning' ? 'warning' : 'info'),
                cursor: 'pointer',
              }}
              onClick={event => handleChipClick(event, tab.id)}
            >
              {counts[tab.id]} {tab.label}
            </span>
          ) : null,
        )}

        {drove && <span style={{ ...chip('neutral'), marginLeft: 'auto' }}>{drove}</span>}

        {snapshot?.error && <span style={chip('warning')}>unavailable</span>}
        {isPending && total === 0 && !snapshot?.error && (
          <span style={{ fontSize: 11, opacity: 0.5 }}>reading the graph…</span>
        )}
        {canExpand && <span style={{ fontSize: 11, opacity: 0.45 }}>{isExpanded ? '▲' : '▼'}</span>}
      </div>

      {isExpanded && (
        <div
          style={{
            background: 'var(--theme-color-primary-bg-weak)',
            borderBottom: '1px solid var(--theme-color-primary-border-weak)',
          }}
        >
          {snapshot?.error ? (
            <div style={{ padding: '10px 14px', fontSize: 12 }}>{snapshot.error}</div>
          ) : (
            <>
              <div style={{ display: 'flex', gap: 6, padding: '6px 14px 0', flexWrap: 'wrap' }}>
                {MEMORY_TABS.map(tab => {
                  if (!counts || counts[tab.id] === 0) return null;
                  const isActive = tab.id === shownTab;
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => onSetTab(tab.id)}
                      style={{
                        fontSize: 11,
                        padding: '3px 10px',
                        borderRadius: '6px 6px 0 0',
                        border: '1px solid var(--theme-color-primary-border-weak)',
                        borderBottom: isActive ? 'none' : undefined,
                        background: isActive
                          ? 'var(--theme-color-primary-bg-weak)'
                          : 'var(--theme-color-neutral-bg-strong)',
                        color: isActive
                          ? 'var(--theme-color-primary-text)'
                          : 'var(--theme-color-neutral-text-weak)',
                        fontWeight: isActive ? 600 : 400,
                        cursor: 'pointer',
                      }}
                    >
                      {tab.label} ({counts[tab.id]})
                    </button>
                  );
                })}
              </div>

              <div style={{ padding: '8px 14px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                {items.length === 0 ? (
                  <div style={{ fontSize: 12, opacity: 0.45 }}>Nothing here yet.</div>
                ) : (
                  items.map((hit, index) => (
                    <div
                      key={`${shownTab}-${index}`}
                      style={{
                        padding: '7px 10px',
                        borderRadius: 7,
                        background: 'var(--theme-color-neutral-bg-default)',
                        border: '1px solid var(--theme-color-primary-border-weak)',
                      }}
                    >
                      <div
                        style={{
                          fontSize: 12,
                          color: 'var(--theme-color-neutral-text-default)',
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                        }}
                      >
                        {hit.content}
                      </div>
                      <div style={{ fontSize: 10, opacity: 0.45, marginTop: 3 }}>{hit.label}</div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}

          <div style={{ padding: '0 14px 10px', display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={footnote}>{HOW[mode]}</div>
            {memoryCalls.length > 0 && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {memoryCalls.map(call => (
                  <span key={call.toolCallId} style={chip('neutral')}>
                    {getToolName(call)} · {toolStateLabel(call)}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

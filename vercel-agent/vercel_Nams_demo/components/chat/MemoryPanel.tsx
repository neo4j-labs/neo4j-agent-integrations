'use client';

import type { ParsedMemory } from '@/types';
import { chip } from './styles';

type MemTab = 'recent' | 'observations' | 'reasoning';

interface MemoryPanelProps {
  isLive:         boolean;
  counts:         ParsedMemory['counts'];
  items:          ParsedMemory['items'];
  isExpanded:     boolean;
  onToggleExpand: () => void;
  activeTab:      MemTab;
  onSetTab:       (tab: MemTab) => void;
}

export default function MemoryPanel({
  isLive,
  counts,
  items,
  isExpanded,
  onToggleExpand,
  activeTab,
  onSetTab,
}: MemoryPanelProps) {
  const totalMem = counts.recent + counts.observations + counts.reasoning;

  if (!totalMem && !isLive) return null;

  const currentItems =
    activeTab === 'recent'       ? items.recent :
    activeTab === 'observations' ? items.observations :
    items.reasoning;

  const handleChipClick = (e: React.MouseEvent, tab: MemTab) => {
    e.stopPropagation();
    onSetTab(tab);
    if (!isExpanded) onToggleExpand();
  };

  return (
    <div>
      {/* Header bar */}
      <div
        style={{
          background: 'var(--theme-color-primary-bg-weak)',
          padding: '9px 14px',
          display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
          borderBottom: '1px solid var(--theme-color-primary-border-weak)',
          cursor: totalMem > 0 ? 'pointer' : 'default',
          userSelect: 'none',
        }}
        onClick={() => totalMem > 0 && onToggleExpand()}
      >
        <span style={{ fontSize: 10, color: 'var(--theme-color-primary-text)' }}>●</span>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--theme-color-primary-text)', flex: 1 }}>
          Agent Memory
        </span>
        {counts.recent > 0 && (
          <span style={{ ...chip('info'), cursor: 'pointer' }} onClick={e => handleChipClick(e, 'recent')}>
            {counts.recent} recent
          </span>
        )}
        {counts.observations > 0 && (
          <span style={{ ...chip('success'), cursor: 'pointer' }} onClick={e => handleChipClick(e, 'observations')}>
            {counts.observations} observations
          </span>
        )}
        {counts.reasoning > 0 && (
          <span style={{ ...chip('warning'), cursor: 'pointer' }} onClick={e => handleChipClick(e, 'reasoning')}>
            {counts.reasoning} reasoning
          </span>
        )}
        {!totalMem && isLive && <span style={{ fontSize: 11, opacity: 0.5 }}>loading…</span>}
        {totalMem > 0 && <span style={{ fontSize: 11, opacity: 0.45 }}>{isExpanded ? '▲' : '▼'}</span>}
      </div>

      {/* Expanded items panel */}
      {isExpanded && totalMem > 0 && (
        <div style={{
          background: 'var(--theme-color-primary-bg-weak)',
          borderBottom: '1px solid var(--theme-color-primary-border-weak)',
        }}>
          {/* Tab row */}
          <div style={{ display: 'flex', gap: 6, padding: '6px 14px 0' }}>
            {(['recent', 'observations', 'reasoning'] as const).map(tab => {
              if (counts[tab] === 0) return null;
              return (
                <button
                  key={tab}
                  onClick={() => onSetTab(tab)}
                  style={{
                    fontSize: 11, padding: '3px 10px', borderRadius: '6px 6px 0 0',
                    border: '1px solid var(--theme-color-primary-border-weak)',
                    borderBottom: activeTab === tab ? 'none' : undefined,
                    background: activeTab === tab
                      ? 'var(--theme-color-primary-bg-weak)'
                      : 'rgba(0,0,0,0.15)',
                    color: activeTab === tab
                      ? 'var(--theme-color-primary-text)'
                      : 'var(--theme-color-neutral-text-weak)',
                    cursor: 'pointer',
                    fontWeight: activeTab === tab ? 600 : 400,
                  }}
                >
                  {tab} ({counts[tab]})
                </button>
              );
            })}
          </div>

          {/* Memory items */}
          <div style={{ padding: '8px 14px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
            {currentItems.length === 0 ? (
              <div style={{ fontSize: 12, opacity: 0.45 }}>No {activeTab} memories.</div>
            ) : currentItems.map((m, i) => (
              <div key={i} style={{
                padding: '7px 10px', borderRadius: 7,
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid var(--theme-color-primary-border-weak)',
              }}>
                <div style={{ fontSize: 12, color: 'var(--theme-color-neutral-text-default)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {m.content}
                </div>
                <div style={{ fontSize: 10, opacity: 0.4, marginTop: 3 }}>
                  {m.source} · {m.type}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

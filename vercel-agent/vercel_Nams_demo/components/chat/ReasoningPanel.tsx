'use client';

import { isReasoningUIPart, isToolUIPart } from 'ai';
import type { ReasoningUIPart, UIMessage } from 'ai';
import { getToolName, toolOutputText, toolStateLabel, type ToolPart } from '@/utils/message';
import { bodyTxt, chip, monoTxt, panelHeader, panelTitle, sectionLbl, stepCard, stepNum } from './styles';

const OUTPUT_CHARS = 600;

type TracePart = ReasoningUIPart | ToolPart;

interface ReasoningPanelProps {
  parts: UIMessage['parts'];
  isLive: boolean;
  isExpanded: boolean;
  onToggleExpand: () => void;
}

// The agent's own steps for this answer: its thinking and every tool call, live as they stream.
export default function ReasoningPanel({ parts, isLive, isExpanded, onToggleExpand }: ReasoningPanelProps) {
  const trace = parts.filter(
    (part): part is TracePart => (isReasoningUIPart(part) && part.text.trim() !== '') || isToolUIPart(part),
  );

  if (trace.length === 0 && !isLive) return null;

  return (
    <div style={{ background: 'var(--theme-color-neutral-bg-default)' }}>
      <div
        style={{
          ...panelHeader,
          cursor: trace.length > 0 ? 'pointer' : 'default',
          borderBottom: isExpanded ? '1px solid var(--theme-color-neutral-border-weak)' : 'none',
        }}
        onClick={() => trace.length > 0 && onToggleExpand()}
      >
        <span style={{ fontSize: 10, color: 'var(--theme-color-primary-text)' }}>●</span>
        <span style={panelTitle}>Reasoning Trace</span>
        {trace.length > 0 && (
          <span style={chip('info')}>
            {trace.length} {trace.length === 1 ? 'step' : 'steps'}
          </span>
        )}
        {isLive && <span style={chip('warning')}>running…</span>}
        {trace.length > 0 && <span style={{ fontSize: 11, opacity: 0.45 }}>{isExpanded ? '▲' : '▼'}</span>}
      </div>

      {isExpanded && trace.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '8px 14px 12px' }}>
          {trace.map((part, index) => (
            <div key={isToolUIPart(part) ? part.toolCallId : `reasoning-${index}`} style={stepCard}>
              <div style={stepNum}>STEP {index + 1}</div>
              {isReasoningUIPart(part) ? (
                <div>
                  <div style={sectionLbl}>THINKING</div>
                  <div style={bodyTxt}>{part.text}</div>
                </div>
              ) : (
                <ToolStep part={part} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ToolStep({ part }: { part: ToolPart }) {
  const output = toolOutputText(part);
  const failed = part.state === 'output-error' || part.state === 'output-denied';

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 600, color: 'var(--theme-color-primary-text)', fontSize: 12 }}>
          {getToolName(part)}
        </span>
        <span
          style={{
            fontSize: 11,
            color: failed ? 'var(--theme-color-danger-text)' : 'var(--theme-color-neutral-text-weaker)',
          }}
        >
          {toolStateLabel(part)}
        </span>
      </div>

      {part.input != null && (
        <div>
          <div style={sectionLbl}>INPUT</div>
          <div style={monoTxt}>{JSON.stringify(part.input)}</div>
        </div>
      )}

      {output && (
        <div style={{ borderTop: '1px solid var(--theme-color-neutral-border-weak)', paddingTop: 4 }}>
          <div style={sectionLbl}>{failed ? 'ERROR' : 'RESULT'}</div>
          <div style={monoTxt}>{output.slice(0, OUTPUT_CHARS)}</div>
        </div>
      )}
    </>
  );
}

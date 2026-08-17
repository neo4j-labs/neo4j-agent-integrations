'use client';

import type { DynamicToolUIPart } from 'ai';
import type { ReasoningStep } from '@/types';
import { chip, stepCard, stepNum, sectionLbl, bodyTxt } from './styles';

interface ReasoningPanelProps {
  isLive:         boolean;
  completedSteps: ReasoningStep[];
  toolParts:      DynamicToolUIPart[];
  isExpanded:     boolean;
  onToggleExpand: () => void;
}

export default function ReasoningPanel({
  isLive,
  completedSteps,
  toolParts,
  isExpanded,
  onToggleExpand,
}: ReasoningPanelProps) {
  const stepCount = completedSteps.length || toolParts.length;

  if (!stepCount && !isLive) return null;

  return (
    <div style={{ background: 'var(--theme-color-neutral-bg-default)' }}>
      {/* Header bar */}
      <div
        style={{
          padding: '9px 14px',
          display: 'flex', alignItems: 'center', gap: 8,
          cursor: stepCount > 0 ? 'pointer' : 'default',
          userSelect: 'none',
          borderBottom: isExpanded ? '1px solid var(--theme-color-neutral-border-weak)' : 'none',
        }}
        onClick={() => stepCount > 0 && onToggleExpand()}
      >
        <span style={{ fontSize: 10, color: 'var(--theme-color-primary-text)' }}>●</span>
        <span style={{ fontSize: 13, fontWeight: 700, flex: 1 }}>Reasoning Trace</span>
        {stepCount > 0 && (
          <span style={chip('info')}>{stepCount} {stepCount === 1 ? 'step' : 'steps'}</span>
        )}
        {isLive && completedSteps.length === 0 && (
          <span style={chip('warning')}>running…</span>
        )}
        {stepCount > 0 && (
          <span style={{ fontSize: 11, opacity: 0.45 }}>{isExpanded ? '▲' : '▼'}</span>
        )}
      </div>

      {/* NAMS steps (shown after streaming completes) */}
      {isExpanded && completedSteps.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '8px 14px 12px' }}>
          {completedSteps.map((step, si) => (
            <div key={step.id} style={stepCard}>
              <div style={stepNum}>STEP {si + 1}</div>
              {step.reasoning && (
                <div>
                  <div style={sectionLbl}>REASONING</div>
                  <div style={bodyTxt}>{step.reasoning}</div>
                </div>
              )}
              {step.actionTaken && (
                <div>
                  <div style={sectionLbl}>ACTION</div>
                  <div style={{ ...bodyTxt, fontFamily: 'ui-monospace, monospace', fontSize: 12 }}>
                    {step.actionTaken}
                  </div>
                </div>
              )}
              {step.result && (
                <div style={{ borderTop: '1px solid var(--theme-color-neutral-border-weak)', paddingTop: 4 }}>
                  <div style={sectionLbl}>RESULT</div>
                  <div style={{ ...bodyTxt, fontSize: 12 }}>{step.result.slice(0, 600)}</div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Live tool calls (shown while streaming, before NAMS steps arrive) */}
      {isExpanded && completedSteps.length === 0 && toolParts.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '8px 14px 12px' }}>
          {toolParts.map(part => {
            const isDone = part.state === 'output-available';
            const out    = isDone ? part.output : null;
            const outTxt = out == null ? null : typeof out === 'string' ? out : JSON.stringify(out, null, 2);
            return (
              <div key={part.toolCallId} style={stepCard}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontWeight: 600, color: 'var(--theme-color-primary-text)', fontSize: 12 }}>
                    {part.toolName}
                  </span>
                  {!isDone && <span style={{ opacity: 0.5, fontSize: 11 }}>running…</span>}
                  {isDone  && <span style={{ color: 'var(--theme-color-success-text)', fontSize: 11 }}>✓</span>}
                </div>
                {outTxt && (
                  <div style={{ ...bodyTxt, fontSize: 11, fontFamily: 'ui-monospace, monospace', borderTop: '1px solid var(--theme-color-neutral-border-weak)', paddingTop: 4 }}>
                    {outTxt.slice(0, 400)}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

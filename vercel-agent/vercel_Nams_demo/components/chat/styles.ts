import type { CSSProperties } from 'react';

type ChipVariant = 'info' | 'success' | 'warning';

export function chip(v: ChipVariant): CSSProperties {
  const map = {
    info:    { bg: 'var(--theme-color-info-bg-weak)',    color: 'var(--theme-color-info-text)' },
    success: { bg: 'var(--theme-color-success-bg-weak)', color: 'var(--theme-color-success-text)' },
    warning: { bg: 'var(--theme-color-warning-bg-weak)', color: 'var(--theme-color-warning-text)' },
  };
  return {
    fontSize: 11, padding: '1px 9px', borderRadius: 10,
    whiteSpace: 'nowrap', background: map[v].bg, color: map[v].color,
  };
}

export const stepCard: CSSProperties = {
  padding: '10px 12px', borderRadius: 8,
  border: '1px solid var(--theme-color-neutral-border-weak)',
  background: 'var(--theme-color-neutral-bg-weak)',
  display: 'flex', flexDirection: 'column', gap: 6,
};

export const stepNum: CSSProperties = {
  fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
  textTransform: 'uppercase', color: 'var(--palette-neutral-text-weakest)',
};

export const sectionLbl: CSSProperties = {
  fontSize: 10, fontWeight: 700, letterSpacing: '0.05em',
  textTransform: 'uppercase', color: 'var(--theme-color-neutral-text-weaker)', marginBottom: 2,
};

export const bodyTxt: CSSProperties = {
  fontSize: 13, color: 'var(--theme-color-neutral-text-default)',
  whiteSpace: 'pre-wrap', wordBreak: 'break-word',
};

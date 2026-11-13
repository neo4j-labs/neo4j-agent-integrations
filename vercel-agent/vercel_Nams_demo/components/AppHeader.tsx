'use client';

import { CleanIconButton, Logo, Typography } from '@neo4j-ndl/react';
import { MoonIconOutline, PlusIconOutline, SunIconOutline } from '@neo4j-ndl/react/icons';

import { AGENT_NAME, MEMORY_MODES } from '@/constants';
import type { ChatMode } from '@/types';
import { chip } from './chat/styles';

interface AppHeaderProps {
  mode: ChatMode;
  isDarkMode: boolean;
  onToggleTheme: () => void;
  onNewChat: () => void;
  isMobile?: boolean;
}

export default function AppHeader({ mode, isDarkMode, onToggleTheme, onNewChat, isMobile }: AppHeaderProps) {
  return (
    <header
      className="n-bg-neutral-bg-weak"
      style={{
        height: 'var(--app-header-height)',
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 'var(--app-header-padding)',
        borderBottom: '2px solid var(--theme-color-neutral-border-weak)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <Logo type="full" style={{ height: 'var(--app-logo-height)', minWidth: 80, flexShrink: 0 }} />
        {!isMobile && (
          <Typography variant="subheading-large" style={{ marginLeft: 4, whiteSpace: 'nowrap' }}>
            {AGENT_NAME}
          </Typography>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={chip(MEMORY_MODES[mode].tone)} title={`NAMS_MODE=${mode} — ${MEMORY_MODES[mode].detail}`}>
          memory: {mode}
        </span>

        <CleanIconButton description="New chat" size="large" onClick={onNewChat}>
          <PlusIconOutline />
        </CleanIconButton>

        <CleanIconButton description="Toggle dark mode" size="large" onClick={onToggleTheme}>
          {isDarkMode ? <SunIconOutline /> : <MoonIconOutline />}
        </CleanIconButton>
      </div>
    </header>
  );
}

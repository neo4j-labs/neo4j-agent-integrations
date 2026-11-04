'use client';

import { useEffect, useState } from 'react';
import { CleanIconButton, Logo, Typography } from '@neo4j-ndl/react';
import { MoonIconOutline, SunIconOutline } from '@neo4j-ndl/react/icons';

interface AppHeaderProps {
  isDarkMode:    boolean;
  onToggleTheme: () => void;
  isMobile?:     boolean;
}

export default function AppHeader({ isDarkMode, onToggleTheme, isMobile }: AppHeaderProps) {
  const [mode, setMode] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/mode')
      .then((r) => r.json())
      .then((data: { mode?: string }) => setMode(data.mode ?? null))
      .catch(() => setMode(null));
  }, []);

  const memoryLabel = mode === 'off' ? 'Memory off' : mode ? `Memory: ${mode}` : null;

  return (
    <header
      className="n-bg-neutral-bg-weak"
      style={{
        height:         'var(--app-header-height)',
        flexShrink:     0,
        display:        'flex',
        alignItems:     'center',
        justifyContent: 'space-between',
        padding:        'var(--app-header-padding)',
        borderBottom:   '2px solid var(--theme-color-neutral-border-weak)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <Logo type="full" style={{ height: 'var(--app-logo-height)', minWidth: 80, flexShrink: 0 }} />
        {!isMobile && (
          <Typography variant="subheading-large" style={{ marginLeft: 4, whiteSpace: 'nowrap' }}>
            NAMS Chat
          </Typography>
        )}
        {!isMobile && memoryLabel && (
          <Typography
            variant="body-small"
            style={{
              marginLeft:   8,
              padding:      '2px 8px',
              borderRadius: 999,
              border:       '1px solid var(--theme-color-neutral-border-weak)',
              whiteSpace:   'nowrap',
            }}
          >
            {memoryLabel}
          </Typography>
        )}
      </div>

      <CleanIconButton description="Toggle dark mode" size="large" onClick={onToggleTheme}>
        {isDarkMode ? <SunIconOutline /> : <MoonIconOutline />}
      </CleanIconButton>
    </header>
  );
}

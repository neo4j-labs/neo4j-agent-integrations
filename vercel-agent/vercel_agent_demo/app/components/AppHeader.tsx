'use client';

import { CleanIconButton, Logo, Typography } from '@neo4j-ndl/react';
import {
  MoonIconOutline,
  QuestionMarkCircleIconOutline,
  SunIconOutline,
} from '@neo4j-ndl/react/icons';

interface AppHeaderProps {
  isDarkMode: boolean;
  onToggleTheme: () => void;
  isMobile?: boolean;
}

export default function AppHeader({ isDarkMode, onToggleTheme, isMobile }: AppHeaderProps) {
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
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
        <Logo type="full" style={{ height: 'var(--app-logo-height)', minWidth: '80px', flexShrink: 0 }} />
        {!isMobile && (
          <Typography variant="subheading-large" style={{ marginLeft: '4px', whiteSpace: 'nowrap' }}>
            AI Chat
          </Typography>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
        <CleanIconButton description="Toggle dark mode" size="large" onClick={onToggleTheme}>
          {isDarkMode ? <SunIconOutline /> : <MoonIconOutline />}
        </CleanIconButton>
        <CleanIconButton
          description="Help"
          size="large"
          onClick={() => window.open('https://neo4j.com/docs/', '_blank')}
        >
          <QuestionMarkCircleIconOutline />
        </CleanIconButton>
      </div>
    </header>
  );
}

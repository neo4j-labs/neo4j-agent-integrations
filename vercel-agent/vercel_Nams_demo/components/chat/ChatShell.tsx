'use client';

import { useEffect, useState } from 'react';

import AppHeader from '@/components/AppHeader';
import ChatComponent from '@/components/chat/ChatComponent';
import { THEME_STORAGE_KEY } from '@/constants';
import type { ChatMode } from '@/types';

export default function ChatShell({ mode }: { mode: ChatMode }) {
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  // Bumping the key remounts the chat: a new, empty chat for the same user.
  const [chatKey, setChatKey] = useState(0);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
      if (stored === 'light' || stored === 'dark') setIsDarkMode(stored === 'dark');
    } catch {}

    const query = window.matchMedia('(max-width: 640px)');
    setIsMobile(query.matches);
    const onChange = (event: MediaQueryListEvent) => setIsMobile(event.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  const toggleTheme = () => {
    setIsDarkMode(wasDark => {
      try {
        window.localStorage.setItem(THEME_STORAGE_KEY, wasDark ? 'light' : 'dark');
      } catch {}
      return !wasDark;
    });
  };

  return (
    <div
      className={`n-bg-neutral-bg-default ${isDarkMode ? 'ndl-theme-dark' : 'ndl-theme-light'}`}
      style={{ height: '100dvh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
    >
      <AppHeader
        mode={mode}
        isDarkMode={isDarkMode}
        onToggleTheme={toggleTheme}
        onNewChat={() => setChatKey(k => k + 1)}
        isMobile={isMobile}
      />
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
        <ChatComponent key={chatKey} mode={mode} />
      </div>
    </div>
  );
}

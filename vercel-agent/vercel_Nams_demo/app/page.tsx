'use client';

import { useEffect, useState } from 'react';
import AppHeader from '@/components/AppHeader';
import ChatComponent from '@/components/chat/ChatComponent';

export default function HomePage() {
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 640px)');
    setIsMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  return (
    <div
      className={`n-bg-neutral-bg-default ${isDarkMode ? 'ndl-theme-dark' : 'ndl-theme-light'}`}
      style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
    >
      <AppHeader isDarkMode={isDarkMode} onToggleTheme={() => setIsDarkMode(v => !v)} isMobile={isMobile} />
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
        <ChatComponent fluid />
      </div>
    </div>
  );
}

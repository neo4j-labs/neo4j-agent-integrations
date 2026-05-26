'use client';

import { useEffect, useState } from 'react';
import { CleanIconButton, Drawer, OutlinedButton, TextInput, Typography } from '@neo4j-ndl/react';
import {
  CheckIconOutline,
  PanelLeftCollapseIcon,
  PanelLeftIcon,
  PencilSquareIconOutline,
  TrashIconOutline,
  XMarkIconOutline,
} from '@neo4j-ndl/react/icons';
import ChatComponent from '@/Chat/chatComponent';
import AppHeader from '@/app/components/AppHeader';

interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
}

const SESSIONS_KEY = 'neo4j-chat-sessions';
const CURRENT_KEY = 'neo4j-chat-current-session';
const THEME_KEY = 'neo4j-chat-theme';

export default function HomePage() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(true);
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [messageCount, setMessageCount] = useState(0);

  useEffect(() => {
    const raw = localStorage.getItem(SESSIONS_KEY);
    let storedSessions: ChatSession[] = raw ? JSON.parse(raw) : [];

    if (storedSessions.length === 0) {
      const id = crypto.randomUUID();
      storedSessions = [{ id, title: 'New Chat', createdAt: new Date().toISOString() }];
      localStorage.setItem(SESSIONS_KEY, JSON.stringify(storedSessions));
    }

    const storedCurrentId = localStorage.getItem(CURRENT_KEY);
    const validId =
      storedSessions.find((s) => s.id === storedCurrentId)?.id ?? storedSessions[0].id;
    localStorage.setItem(CURRENT_KEY, validId);

    const savedTheme = localStorage.getItem(THEME_KEY);
    if (savedTheme !== null) setIsDarkMode(savedTheme === 'dark');

    setSessions(storedSessions);
    setCurrentSessionId(validId);
    setHydrated(true);
  }, []);

  useEffect(() => {
    const mobileMq = window.matchMedia('(max-width: 767px)');
    const tabletMq = window.matchMedia('(min-width: 768px) and (max-width: 1023px)');

    const handle = () => {
      const mobile = mobileMq.matches;
      setIsMobile(mobile);
      setIsDrawerOpen(!mobile && !tabletMq.matches);
    };

    handle();
    mobileMq.addEventListener('change', handle);
    tabletMq.addEventListener('change', handle);
    return () => {
      mobileMq.removeEventListener('change', handle);
      tabletMq.removeEventListener('change', handle);
    };
  }, []);

  const persist = (updated: ChatSession[]) => {
    setSessions(updated);
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(updated));
  };

  const switchTo = (id: string) => {
    setCurrentSessionId(id);
    localStorage.setItem(CURRENT_KEY, id);
    setMessageCount(0);
    if (isMobile) setIsDrawerOpen(false);
  };

  const createNewSession = () => {
    const id = crypto.randomUUID();
    const newSession: ChatSession = { id, title: 'New Chat', createdAt: new Date().toISOString() };
    const updated = [newSession, ...sessions];
    persist(updated);
    switchTo(id);
  };

  const deleteSession = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const updated = sessions.filter((s) => s.id !== id);
    if (updated.length === 0) {
      const newId = crypto.randomUUID();
      const newSession: ChatSession = { id: newId, title: 'New Chat', createdAt: new Date().toISOString() };
      persist([newSession]);
      switchTo(newId);
    } else {
      persist(updated);
      if (currentSessionId === id) switchTo(updated[0].id);
    }
  };

  const startEdit = (id: string, currentTitle: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(id);
    setEditTitle(currentTitle);
  };

  const saveEdit = (id: string) => {
    if (editTitle.trim()) {
      persist(sessions.map((s) => (s.id === id ? { ...s, title: editTitle.trim() } : s)));
    }
    setEditingId(null);
    setEditTitle('');
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditTitle('');
  };

  const toggleTheme = () => {
    const next = !isDarkMode;
    setIsDarkMode(next);
    localStorage.setItem(THEME_KEY, next ? 'dark' : 'light');
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const diffDays = Math.floor((Date.now() - date.getTime()) / 86_400_000);
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;
    return date.toLocaleDateString();
  };

  const currentSession = sessions.find((s) => s.id === currentSessionId);

  if (!hydrated || !currentSessionId) return null;

  return (
    <div
      className={`n-bg-neutral-bg-default ${isDarkMode ? 'ndl-theme-dark' : 'ndl-theme-light'}`}
      style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
    >
      <AppHeader isDarkMode={isDarkMode} onToggleTheme={toggleTheme} isMobile={isMobile} />
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0, position: 'relative' }}>
        {/* Mobile backdrop */}
        {isMobile && isDrawerOpen && (
          <div
            onClick={() => setIsDrawerOpen(false)}
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 98,
              backgroundColor: 'rgba(0,0,0,0.5)',
            }}
          />
        )}
        <Drawer
          isExpanded={isDrawerOpen}
          onExpandedChange={setIsDrawerOpen}
          type={isMobile ? 'overlay' : 'push'}
          isCloseable={false}
          style={{ zIndex: isMobile ? 99 : undefined }}
        >
          <Drawer.Header>
            <OutlinedButton
              size="small"
              onClick={createNewSession}
              leadingVisual={<PencilSquareIconOutline />}
            >
              New chat
            </OutlinedButton>
          </Drawer.Header>

          <Drawer.Body>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sidebar-section-gap)' }}>
              <Typography
                variant="body-medium"
                style={{
                  color: 'var(--theme-color-neutral-text-weak)',
                  padding: 'var(--sidebar-label-padding)',
                  marginBottom: '4px',
                }}
              >
                Chats
              </Typography>

              {sessions.map((session) => (
                <div
                  key={session.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => switchTo(session.id)}
                  onKeyDown={(e) => e.key === 'Enter' && switchTo(session.id)}
                  onMouseEnter={() => setHoveredId(session.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  style={{
                    padding: 'var(--sidebar-item-padding)',
                    borderRadius: 'var(--sidebar-item-radius)',
                    cursor: 'pointer',
                    backgroundColor:
                      session.id === currentSessionId
                        ? 'var(--theme-color-primary-bg-selected)'
                        : hoveredId === session.id
                          ? 'var(--theme-color-neutral-bg-weak)'
                          : 'transparent',
                    transition: 'background-color 0.15s ease',
                  }}
                >
                  {editingId === session.id ? (
                    <div
                      style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <TextInput
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        size="small"
                        htmlAttributes={{
                          onKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => {
                            if (e.key === 'Enter') saveEdit(session.id);
                            if (e.key === 'Escape') cancelEdit();
                          },
                          autoFocus: true,
                        }}
                        style={{ flex: 1 }}
                      />
                      <CleanIconButton description="Save" size="small" onClick={() => saveEdit(session.id)}>
                        <CheckIconOutline />
                      </CleanIconButton>
                      <CleanIconButton description="Cancel" size="small" onClick={cancelEdit}>
                        <XMarkIconOutline />
                      </CleanIconButton>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px' }}>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <Typography
                          variant="body-medium"
                          style={{
                            display: 'block',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            color:
                              session.id === currentSessionId
                                ? 'var(--theme-color-primary-text)'
                                : 'var(--theme-color-neutral-text-default)',
                          }}
                        >
                          {session.title}
                        </Typography>
                        <Typography
                          variant="body-small"
                          style={{ display: 'block', color: 'var(--theme-color-neutral-text-weak)', marginTop: '2px' }}
                        >
                          {formatDate(session.createdAt)}
                        </Typography>
                      </div>

                      <div
                        style={{
                          display: 'flex',
                          gap: '2px',
                          flexShrink: 0,
                          opacity: isMobile || hoveredId === session.id || session.id === currentSessionId ? 1 : 0,
                          transition: 'opacity 0.15s ease',
                        }}
                      >
                        <CleanIconButton
                          description="Rename"
                          size="small"
                          onClick={(e) => startEdit(session.id, session.title, e)}
                        >
                          <PencilSquareIconOutline />
                        </CleanIconButton>
                        <CleanIconButton
                          description="Delete"
                          size="small"
                          onClick={(e) => deleteSession(session.id, e)}
                        >
                          <TrashIconOutline />
                        </CleanIconButton>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Drawer.Body>
        </Drawer>
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            minHeight: 0,
            minWidth: 0,
          }}
        >
          <div
            style={{
              height: 'var(--toolbar-height)',
              padding: 'var(--toolbar-padding)',
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--toolbar-gap)',
              flexShrink: 0,
              borderBottom: '1px solid var(--theme-color-neutral-border-weak)',
              backgroundColor: 'var(--theme-color-neutral-bg-weak)',
            }}
          >
            <CleanIconButton
              description={isDrawerOpen ? 'Collapse sidebar' : 'Expand sidebar'}
              onClick={() => setIsDrawerOpen(!isDrawerOpen)}
            >
              {isDrawerOpen ? <PanelLeftCollapseIcon /> : <PanelLeftIcon />}
            </CleanIconButton>
            <div>
              <Typography variant="subheading-medium" style={{ color: 'var(--theme-color-neutral-text-default)' }}>
                {currentSession?.title ?? 'New Chat'}
              </Typography>
              {messageCount > 0 && (
                <Typography variant="body-small" style={{ display: 'block', color: 'var(--theme-color-neutral-text-weak)' }}>
                  {messageCount} {messageCount === 1 ? 'message' : 'messages'}
                </Typography>
              )}
            </div>
          </div>
          <ChatComponent
            key={currentSessionId}
            sessionId={currentSessionId}
            userName="User"
            fluid
            hideHeader
            onMessageCountChange={setMessageCount}
            suggestions={[
              'What companies are in the graph?',
              'Find the most connected nodes',
              'I want to import data',
              'Create an AI agent',
            ]}
          />
        </div>
      </div>
    </div>
  );
}


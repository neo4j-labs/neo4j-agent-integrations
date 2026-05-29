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
  conversationId?: string;
}

export default function HomePage() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(true);
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [messageCount, setMessageCount] = useState(0);

  // Load session store from server on mount (cookie-backed, userId stable per browser)
  useEffect(() => {
    fetch('/api/sessions')
      .then(r => r.json())
      .then((store) => {
        const list: ChatSession[] = store.sessions ?? [];
        setSessions(list);
        setCurrentSessionId(store.currentSessionId ?? (list[0]?.id ?? null));
        setIsDarkMode(store.theme !== 'light');
        setUserId(store.userId ?? null);
        setHydrated(true);
      })
      .catch(() => {
        const id = crypto.randomUUID();
        setSessions([{ id, title: 'New Chat', createdAt: new Date().toISOString() }]);
        setCurrentSessionId(id);
        setHydrated(true);
      });
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

  const apiPatch = (body: Record<string, unknown>) =>
    fetch('/api/sessions', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).catch(err => console.error('[HomePage] Session sync error:', err));

  const switchTo = (id: string) => {
    setCurrentSessionId(id);
    apiPatch({ currentSessionId: id });
    setMessageCount(0);
    if (isMobile) setIsDrawerOpen(false);
  };

  const createNewSession = async () => {
    try {
      const res = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      setSessions(data.sessions);
      setCurrentSessionId(data.currentSessionId);
      setMessageCount(0);
      if (isMobile) setIsDrawerOpen(false);
    } catch (err) {
      console.error('[HomePage] Failed to create session:', err);
    }
  };

  const deleteSession = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const session = sessions.find(s => s.id === id);
    if (session?.conversationId) {
      fetch(`/api/chat?conversationId=${encodeURIComponent(session.conversationId)}`, { method: 'DELETE' })
        .catch(err => console.error('[HomePage] Failed to delete NAMS conversation:', err));
    }
    try {
      const res = await fetch(`/api/sessions?id=${encodeURIComponent(id)}`, { method: 'DELETE' });
      const data = await res.json();
      setSessions(data.sessions);
      if (data.currentSessionId !== currentSessionId) {
        setCurrentSessionId(data.currentSessionId);
        setMessageCount(0);
      }
    } catch (err) {
      console.error('[HomePage] Failed to delete session:', err);
    }
  };

  const startEdit = (id: string, currentTitle: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(id);
    setEditTitle(currentTitle);
  };

  const saveEdit = (id: string) => {
    if (editTitle.trim()) {
      const title = editTitle.trim();
      setSessions(prev => prev.map(s => s.id === id ? { ...s, title } : s));
      apiPatch({ sessionId: id, update: { title } });
    }
    setEditingId(null);
    setEditTitle('');
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditTitle('');
  };

  const autoTitleSession = (sessionId: string, title: string) => {
    setSessions(prev => prev.map(s => s.id === sessionId && s.title === 'New Chat' ? { ...s, title } : s));
    apiPatch({ sessionId, update: { title } });
  };

  const toggleTheme = () => {
    const next = !isDarkMode;
    setIsDarkMode(next);
    apiPatch({ theme: next ? 'dark' : 'light' });
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const diffDays = Math.floor((Date.now() - date.getTime()) / 86_400_000);
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;
    return date.toLocaleDateString();
  };

  const currentSession = sessions.find(s => s.id === currentSessionId);

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
            userId={userId ?? undefined}
            conversationId={currentSession?.conversationId}
            previousConversationIds={sessions
              .filter(s => s.id !== currentSessionId && s.conversationId)
              .map(s => s.conversationId!)
              .slice(0, 5) // Limit to 5 most recent
            }
            onConversationIdResolved={(convId) => {
              setSessions(prev => prev.map(s =>
                s.id === currentSessionId ? { ...s, conversationId: convId } : s
              ));
              apiPatch({ sessionId: currentSessionId, update: { conversationId: convId } });
            }}
            userName="User"
            fluid
            hideHeader
            onMessageCountChange={setMessageCount}
            onTitleGenerated={(title) => autoTitleSession(currentSessionId, title)}
            suggestions={[
              'What organizations are in the graph?',
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

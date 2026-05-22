'use client';

import { useEffect, useState } from 'react';
import ChatComponent from '@/Chat/chatComponent';

export default function HomePage() {
  const [sessionId, setSessionId] = useState<string | null>(null);

  useEffect(() => {
    const key = 'neo4j-chat-session-id';
    let id = sessionStorage.getItem(key);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(key, id);
    }
    setSessionId(id);
  }, []);

  if (!sessionId) return null;

  return (
    <main
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
      }}
    >
      <div style={{ width: '100%', maxWidth: '800px', height: '80vh' }}>
        <ChatComponent
          sessionId={sessionId}
          userName="User"
          suggestions={[
            'What companies are in the graph?',
            'Find the most connected nodes',
            'I want to import data',
            'Create an AI agent',
          ]}
        />
      </div>
    </main>
  );
}

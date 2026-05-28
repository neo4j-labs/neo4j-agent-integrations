export const runtime = 'nodejs';

const COOKIE_NAME = 'neo4j-chat-v1';
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365; // 1 year
const MAX_SESSIONS = 30;

interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  conversationId?: string;
}

interface SessionStore {
  userId: string;
  sessions: ChatSession[];
  currentSessionId: string;
  theme: string;
}

function parseCookies(req: Request): Record<string, string> {
  const header = req.headers.get('cookie') ?? '';
  const result: Record<string, string> = {};
  for (const part of header.split(';')) {
    const [key, ...rest] = part.trim().split('=');
    if (key) result[key.trim()] = decodeURIComponent(rest.join('='));
  }
  return result;
}

function readStore(req: Request): SessionStore | null {
  const cookies = parseCookies(req);
  const raw = cookies[COOKIE_NAME];
  if (!raw) return null;
  try {
    return JSON.parse(Buffer.from(raw, 'base64url').toString('utf-8')) as SessionStore;
  } catch {
    return null;
  }
}

function buildCookieHeader(store: SessionStore): string {
  const encoded = Buffer.from(JSON.stringify(store)).toString('base64url');
  return `${COOKIE_NAME}=${encoded}; Path=/; Max-Age=${COOKIE_MAX_AGE}; SameSite=Lax`;
}

function jsonResponse(data: unknown, status = 200, store?: SessionStore): Response {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (store) headers['Set-Cookie'] = buildCookieHeader(store);
  return new Response(JSON.stringify(data), { status, headers });
}

function makeInitialStore(): SessionStore {
  const id = crypto.randomUUID();
  return {
    userId: crypto.randomUUID(),
    sessions: [{ id, title: 'New Chat', createdAt: new Date().toISOString() }],
    currentSessionId: id,
    theme: 'dark',
  };
}

// GET: Return current session store (creates initial state if no cookie)
export async function GET(req: Request) {
  let store = readStore(req);
  let created = false;
  if (!store) {
    store = makeInitialStore();
    created = true;
  }
  return jsonResponse(store, 200, created ? store : undefined);
}

// POST: Create a new session
export async function POST(req: Request) {
  let body: { title?: string } = {};
  try { body = await req.json(); } catch { /* use defaults */ }

  let store = readStore(req) ?? makeInitialStore();
  const id = crypto.randomUUID();
  const newSession: ChatSession = { id, title: body.title ?? 'New Chat', createdAt: new Date().toISOString() };
  const sessions = [newSession, ...store.sessions].slice(0, MAX_SESSIONS);
  store = { ...store, sessions, currentSessionId: id };

  return jsonResponse({ session: newSession, sessions, currentSessionId: id }, 200, store);
}

// PATCH: Update a session (title/conversationId) or top-level fields (currentSessionId, theme)
export async function PATCH(req: Request) {
  let body: {
    sessionId?: string;
    update?: Partial<ChatSession>;
    currentSessionId?: string;
    theme?: string;
  } = {};
  try { body = await req.json(); } catch { /* use defaults */ }

  let store = readStore(req);
  if (!store) return jsonResponse({ error: 'No session store found' }, 404);

  if (body.sessionId && body.update) {
    store = {
      ...store,
      sessions: store.sessions.map(s =>
        s.id === body.sessionId ? { ...s, ...body.update } : s
      ),
    };
  }
  if (body.currentSessionId !== undefined) {
    store = { ...store, currentSessionId: body.currentSessionId };
  }
  if (body.theme !== undefined) {
    store = { ...store, theme: body.theme };
  }

  return jsonResponse(store, 200, store);
}

// DELETE: Remove a session by id (auto-creates a new session if the list becomes empty)
export async function DELETE(req: Request) {
  const { searchParams } = new URL(req.url);
  const id = searchParams.get('id');
  if (!id) return jsonResponse({ error: 'Missing id query param' }, 400);

  let store = readStore(req);
  if (!store) return jsonResponse({ error: 'No session store found' }, 404);

  let sessions = store.sessions.filter(s => s.id !== id);
  let currentSessionId = store.currentSessionId;

  if (sessions.length === 0) {
    const newId = crypto.randomUUID();
    sessions = [{ id: newId, title: 'New Chat', createdAt: new Date().toISOString() }];
    currentSessionId = newId;
  } else if (currentSessionId === id) {
    currentSessionId = sessions[0].id;
  }

  store = { ...store, sessions, currentSessionId };
  return jsonResponse({ sessions, currentSessionId }, 200, store);
}

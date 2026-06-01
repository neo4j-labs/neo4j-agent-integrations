# Memory Persistence Fix — Cross-Session Memory

## Problem
Agent memory was not persisting across sessions. When a user mentioned "my favorite fruit is apple" in one session and started a new session, the agent had no memory of this context.

### Root Cause
The original implementation only searched for memories within the **current conversation**. When a user:
1. Started a chat session → new `conversationId` created
2. Said "my favorite fruit is apple" → message stored in **Conversation A**
3. Created a new session (or reopened after closing) → new `conversationId` created
4. Asked a question → searched only in **Conversation B's memory** (empty)

Messages from Conversation A were orphaned and never retrieved.

## Solution
Implemented **user-level cross-session memory search** that retrieves relevant context from **all previous conversations** when starting a new session.

### Changes Made

#### 1. **Chat/chat.ts** — Added user-level memory search function
- Added `searchUserMemoryContext(userId, query, limit)` function
- Searches across all conversations for a specific user using MCP transport
- Gracefully falls back if user-level search is unavailable

```typescript
export async function searchUserMemoryContext(
  userId: string,
  query: string,
  limit = 3,
): Promise<string[]>
```

#### 2. **app/api/chat/route.ts** — Updated memory retrieval logic
- Now performs **two searches**:
  - **Conversation-specific search**: Memories from current conversation (priority)
  - **User-level search**: Memories from all previous conversations (only for new conversations)
- Deduplicates results so recent context takes priority
- Distinguishes cross-session memories with `[cross-session memory]` label in system prompt

**Key logic**:
```typescript
// Search conversation-specific memory
const conversationMatches = await searchMemoryContext(conversationId, userText);

// Search user-level memory (cross-session) for new conversations
const isNewConversation = ctx.recentMessages.length < 3;
const userMatches = isNewConversation && userText
  ? await searchUserMemoryContext(userId, userText)
  : [];
```

#### 3. **Enhanced system prompt**
- Updated instructions to acknowledge cross-session memories
- Agent now recognizes `[cross-session memory]` entries as coming from previous conversations

## How It Works

### Flow Diagram
```
Session 1:
- User: "My favorite fruit is apple"
- Agent: Adds message to Conversation A
- Memory stored with userId

Session 2 (New conversation):
- User: "What's my favorite fruit?"
- GET /api/chat → creates Conversation B
- POST /api/chat → User query triggers:
  1. searchMemoryContext(conversationB, "favorite fruit") → empty
  2. searchUserMemoryContext(userId, "favorite fruit") → finds "apple" from Session 1!
  3. Agent includes: "[cross-session memory] My favorite fruit is apple"
  4. Agent responds: "Your favorite fruit is apple"
```

## Testing

### Basic Test
1. **Session 1**: Say "My name is Alice and I like working with data"
2. **Session 2** (new): Ask "Who am I?" or "What do I like?"
3. Expected: Agent recalls details from previous session

### Advanced Test
1. Share specific information: "I use Python, work in healthcare, live in NYC"
2. Start new session
3. Ask vague question: "Tell me about myself"
4. Expected: Agent retrieves cross-session context

### Verification in Logs
When running `npm run dev`, you should see:
```
[Memory Retrieved] 0 conversation matches, 2 cross-session matches, 0 reflections, 0 observations
```

## Configuration

No additional configuration needed! The fix automatically:
- Uses MCP transport if `MEMORY_TRANSPORT=mcp` is set
- Falls back gracefully if user-level search unavailable
- Only searches across sessions for "new" conversations (< 3 messages)

## Limitations

- **SDK Transport**: User-level search currently only works with MCP transport. SDK transport falls back to conversation-only search. (This is a limitation of the current `@neo4j-labs/agent-memory` SDK)
- **New Conversations Only**: Cross-session search is only performed when entering a new conversation (< 3 messages). This prevents redundant searches in active conversations.

## Future Improvements

1. **User-level long-term memory**: Store distilled summaries of past conversations (reflections/observations at user level)
2. **SDK Support**: Extend `@neo4j-labs/agent-memory` SDK to support user-level searches
3. **Conversation Merging**: Option to explicitly merge memories from old conversations into new ones

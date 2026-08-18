/**
 * nams-enrich.ts — guarantees persistence when the model skips `store_memory`.
 *
 * `enforceQueryMemory()` can guarantee the *read* side of the memory cycle
 * because there is always a later step to force. The write side has no such
 * hook: the tool loop ends the moment the model emits final text, so a turn
 * where the model says "I'll remember that" without calling `store_memory`
 * simply persists nothing. This is documented package behaviour, not a bug —
 * the recommended remedy is exactly what this does: inspect the turn in
 * `onFinish` and store it yourself.
 *
 * Everything else this file used to work around — entity names missing from
 * memory hits, and self-referential entities extracted from the agent's own
 * output — is now fixed in @neo4j-labs/nams-ai-provider.
 */

/**
 * Persists the turn when the model never called `store_memory`. Returns true if
 * a write was made. Failures are swallowed: memory must never break a response.
 */
export async function ensureStored(
  tools: Record<string, unknown> | undefined,
  userText: string,
): Promise<boolean> {
  const sm = tools?.store_memory as { execute?: (...a: unknown[]) => unknown } | undefined;
  if (typeof sm?.execute !== 'function' || !userText.trim()) return false;

  // The user's words only. Storing the assistant's reply as well feeds the
  // extractor answers *about* memory, which it turns into entities describing
  // the memory system rather than the user. `type: 'interaction'` also routes to
  // short-term storage, which skips entity extraction entirely.
  const content = `User said: ${userText.trim()}`;

  try {
    await sm.execute(
      { content: content.slice(0, 1200), type: 'interaction', confidence: 0.75 },
      { toolCallId: 'ensure-stored', messages: [] },
    );
    return true;
  } catch (err) {
    console.warn('[enrich] ensureStored failed:', err instanceof Error ? err.message : err);
    return false;
  }
}

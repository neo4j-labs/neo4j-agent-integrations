import { makeClient } from "@neo4j-labs/nams-ai-provider";
import { namsMemory } from "@neo4j-labs/nams-ai-provider/eve";
import type { MemoryProvider, MemoryRecallResult } from "eve/memory";
import { randomUUID } from "node:crypto";
import { join } from "node:path";

try {
  process.loadEnvFile(join(import.meta.dirname, "..", ".env"));
} catch (err) {
  if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
}
process.env.NAMS_REASONING = "off";
process.env.NAMS_TRACEBACK = "on";

const apiKey = process.env.NAMS_API_KEY?.trim();
if (!apiKey) {
  console.error("No NAMS_API_KEY. Copy .env.example to .env and fill it in.");
  process.exit(1);
}
const connection = {
  apiKey,
  endpoint: process.env.NAMS_ENDPOINT?.trim() || undefined,
  workspaceId: process.env.WORKSPACE_ID?.trim() || undefined,
};
const endpoint = connection.endpoint ?? "https://memory.neo4jlabs.com/v1";
const headers: Record<string, string> = {
  Authorization: `Bearer ${apiKey}`,
  ...(connection.workspaceId ? { "X-Workspace-Id": connection.workspaceId } : {}),
};

const { default: memory } = await import("../agent/memory/nams");
const agent: MemoryProvider = memory.provider;
const bare: MemoryProvider = namsMemory({ ...connection, maxMemories: 8 });
const nams = makeClient(connection);

const SLOT = "nams";
const run = randomUUID().slice(0, 8);
const USER = `traceback-check-${run}`;
const OTHER = `traceback-check-other-${run}`;
const COMPANY = "Zorvex Freightworks";
const INVESTOR = "Halvane Capital";
const FIRST = `I'm tracking ${COMPANY}, a rail freight company. Its investors are ${INVESTOR} and Quillmere Partners.`;
const CATALOG = "Available connections: eve__search, neo4j-graph, neo4j-investments. Use them when the user asks.";
const FILLER = [
  "Summarize this week's semiconductor export news.",
  "What are the main cloud data warehouse vendors?",
  "Give me three trends in battery storage.",
  "Which sectors had the most layoffs this quarter?",
  "Explain what a Series C round usually signals.",
  "List the big players in satellite broadband.",
  "How do analysts value a SaaS company?",
  "What happened in the vector database market lately?",
  "Compare two approaches to supply chain financing.",
  "What is driving interest in small modular reactors?",
  "Which payments companies went public this year?",
];

let failures = 0;
function check(name: string, ok: boolean, detail?: string): void {
  if (!ok) failures++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${!ok && detail ? `\n      ${detail}` : ""}`);
}

const context = (scopeKey: string, sessionId: string, input: unknown[], messages: unknown[] = []) => ({
  abortSignal: new AbortController().signal,
  operationId: randomUUID(),
  session: { id: sessionId, auth: {}, turn: {} },
  memory: { scope: { key: scopeKey, namespace: SLOT, value: scopeKey }, slot: SLOT },
  turn: { id: randomUUID(), input, sequence: 1 },
  messages,
}) as never;

async function turn(scopeKey: string, sessionId: string, user: string, reply: string, extra: unknown[] = []) {
  const input = [...extra, { role: "user", content: user }];
  await agent.capture!["turn.completed"]!(
    context(scopeKey, sessionId, input, [...input, { role: "assistant", content: reply }]),
  );
}

const recalled = (result: MemoryRecallResult, id?: string): string =>
  (result?.messages ?? []).filter((m) => id === undefined || m.id === id).map((m) => m.content).join("\n");

async function extractionDone(conversationId: string, timeoutMs: number): Promise<string> {
  const until = Date.now() + timeoutMs;
  let last = "";
  while (Date.now() < until) {
    const res = await fetch(`${endpoint}/conversations/${conversationId}/extraction-status`, { headers });
    const body = (await res.json().catch(() => ({}))) as { summary?: Record<string, number> };
    const summary = body.summary ?? {};
    last = JSON.stringify(summary);
    if (Object.keys(summary).length > 0 && !summary.pending && !summary.processing && !summary.running) return "";
    await new Promise((r) => setTimeout(r, 3000));
  }
  return last;
}

async function workerStatus(): Promise<string> {
  try {
    const res = await fetch(`${endpoint}/status`, { headers });
    const body = (await res.json()) as {
      streams?: { consumerGroups?: { lag?: number; pending?: number; lastDeliveredId?: string }[] }[];
    };
    const group = body.streams?.[0]?.consumerGroups?.[0];
    if (!group) return "unknown";
    const at = Number(group.lastDeliveredId?.split("-")[0]);
    return `lag ${group.lag}, in flight ${group.pending}, last delivered ${at ? new Date(at).toISOString() : "?"}`;
  } catch {
    return "unknown";
  }
}

async function cleanup(): Promise<void> {
  for (const userId of [USER, OTHER]) {
    const listed = await nams.shortTerm.listConversations({ userId, limit: 200 }).catch((err) => {
      console.warn(`Cleanup: could not list ${userId}'s conversations:`, err);
      return [];
    });
    for (const c of listed.filter((c) => c.userId === userId)) {
      await nams.shortTerm.deleteConversation(c.id)
        .catch((err) => console.warn(`Cleanup: could not delete ${c.id}:`, err));
    }
  }
}

let exitCode = 0;
try {
  console.log(`Run ${run}: writing session 1 for ${USER}`);
  await turn(USER, `${run}-s1`, FIRST, `Noted: you track ${COMPANY}.`, [
    { role: "user", kind: "context.instruction", content: CATALOG },
  ]);
  const own = await nams.shortTerm.listConversations({ userId: USER, limit: 200 });
  const first = own.find((c) => c.userId === USER && c.metadata?.session === `${run}-s1`);
  if (!first) throw new Error("session 1 conversation was not created");

  const sessionOne = await nams.shortTerm.getConversation(first.id, { limit: 20 });
  check(
    "eve's connection catalog was not saved as a user message",
    !(sessionOne.messages ?? []).some((m) => m.content.includes("Available connections")),
  );

  console.log("Waiting for NAMS to extract entities from session 1 ...");
  const stuck = await extractionDone(first.id, 90_000);
  if (stuck) {
    console.error(
      `\nNAMS did not extract session 1 within 90 s (${stuck}).\n` +
      `Memory worker: ${await workerStatus()}.\n` +
      "This is the hosted service, not the agent: trace-back and the long-term graph need entities. " +
      "The trace-back checks were not run. Try again once the worker catches up.",
    );
    exitCode = 2;
  } else {
    console.log(`Writing ${FILLER.length} newer sessions ...`);
    for (const [i, text] of FILLER.entries()) {
      await turn(USER, `${run}-s${i + 2}`, text, "Here is a short answer.");
    }

    const question = `What did we say about ${COMPANY}?`;
    const ask = `${run}-s${FILLER.length + 2}`;
    const baseline = recalled(await bare.recall["turn.started"](context(USER, ask, [{ role: "user", content: question }])));
    check(
      "the provider's own recall misses session 1",
      !baseline.includes(`tracking ${COMPANY}`),
      "session 1 is inside the provider's recent-session window; trace-back is not what found it",
    );

    const traced = recalled(await agent.recall["turn.started"](context(USER, ask, [{ role: "user", content: question }])), "nams-traceback");
    check(
      "trace-back brings session 1 back",
      traced.includes(INVESTOR),
      traced ? `got:\n${traced}` : "no <nams_traceback> message",
    );

    const other = recalled(await agent.recall["turn.started"](context(OTHER, `${run}-other`, [{ role: "user", content: question }])), "nams-traceback");
    check("another user asking the same question gets nothing", other === "", `got:\n${other}`);
  }
} catch (error) {
  console.error(error);
  exitCode = 1;
} finally {
  await cleanup();
  console.log("Cleaned up.");
}

if (exitCode === 0 && failures > 0) exitCode = 1;
if (exitCode === 0) console.log("\nAll checks passed.");
process.exit(exitCode);

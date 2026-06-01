// Observable Classic notebook
// Vercel AI SDK + Neo4j — interactive browser demo
//
// Open in browser:
//   https://htmlpreview.github.io/?https://raw.githubusercontent.com/karanchellani/neo4j-agent-integrations/vercel-agent/vercel-agent/vercel_agent.html
//
// This notebook covers three patterns — all running live in the browser:
//   0. Direct Neo4j query  (neo4j-driver, no AI)
//   1. Custom Tools agent  (generateText + tool() + neo4j-driver)
//   2. Memory agent        (generateText + neo4j-driver memory graph)
//
// The MCP Agent pattern requires a local Node.js process — see 1-mcp-agent.mjs.

export default function define(runtime, observer) {
  const main = runtime.module();

  // ── Title ──────────────────────────────────────────────────────────────────
  main.variable(observer()).define(["md"], function (md) {
    return md`# Vercel AI SDK + Neo4j

Three patterns for building AI agents over a Neo4j graph database, running live in the browser.

| # | Pattern | Key APIs |
|---|---------|----------|
| 0 | **Direct Query** | \`neo4j-driver\` |
| 1 | **Custom Tools Agent** | \`generateText\`, \`tool()\`, \`jsonSchema()\` |
| 2 | **Memory Agent** | \`neo4j-driver\` memory graph + \`generateText\` |
| — | **MCP Agent** *(Node.js only)* | \`@ai-sdk/mcp\` — run \`node 1-mcp-agent.mjs\` |

> **Prerequisites:** Sections 1 & 2 require an OpenAI API key. Section 2 also requires a writable Neo4j instance (e.g. [AuraDB Free](https://neo4j.com/cloud/platform/aura-graph-database/)).`;
  });

  // ── Configuration ──────────────────────────────────────────────────────────
  main.variable(observer()).define(["md"], function (md) {
    return md`---
## ⚙️ Configuration`;
  });

  main.variable(observer("viewof neo4jUri")).define(
    "viewof neo4jUri", ["Inputs"],
    (Inputs) => Inputs.text({ label: "Neo4j URI", value: "neo4j+s://demo.neo4jlabs.com:7687", width: 440 })
  );
  main.variable(observer("neo4jUri")).define(
    "neo4jUri", ["Generators", "viewof neo4jUri"], (G, _) => G.input(_)
  );

  main.variable(observer("viewof neo4jUsername")).define(
    "viewof neo4jUsername", ["Inputs"],
    (Inputs) => Inputs.text({ label: "Username", value: "companies" })
  );
  main.variable(observer("neo4jUsername")).define(
    "neo4jUsername", ["Generators", "viewof neo4jUsername"], (G, _) => G.input(_)
  );

  main.variable(observer("viewof neo4jPassword")).define(
    "viewof neo4jPassword", ["Inputs"],
    (Inputs) => Inputs.password({ label: "Password", value: "companies" })
  );
  main.variable(observer("neo4jPassword")).define(
    "neo4jPassword", ["Generators", "viewof neo4jPassword"], (G, _) => G.input(_)
  );

  main.variable(observer("viewof openaiKey")).define(
    "viewof openaiKey", ["Inputs"],
    (Inputs) => Inputs.password({ label: "OpenAI API key", placeholder: "sk-…" })
  );
  main.variable(observer("openaiKey")).define(
    "openaiKey", ["Generators", "viewof openaiKey"], (G, _) => G.input(_)
  );

  main.variable(observer("viewof aiModel")).define(
    "viewof aiModel", ["Inputs"],
    (Inputs) => Inputs.select(["gpt-4o-mini", "gpt-4o", "gpt-4.1"], {
      label: "Model",
      value: "gpt-4o-mini",
    })
  );
  main.variable(observer("aiModel")).define(
    "aiModel", ["Generators", "viewof aiModel"], (G, _) => G.input(_)
  );

  // ── Package imports ────────────────────────────────────────────────────────
  // Note: when running in a plain HTML page, load neo4j-driver via the browser
  // UMD bundle in <head> and read window.neo4j here. esm.sh serves the Node.js
  // build which fails in browsers (string_decoder not available).
  main.variable(observer("neo4j")).define("neo4j", async function () {
    if (typeof window !== "undefined" && window.neo4j) return window.neo4j;
    // Fallback: dynamically inject the browser UMD bundle
    await new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://unpkg.com/neo4j-driver@5/lib/browser/neo4j-web.js";
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
    return window.neo4j;
  });

  main.variable(observer("aiPkg")).define("aiPkg", async function () {
    // ai v4 API: maxSteps / ai v6 API: stopWhen: stepCountIs()
    // esm.sh resolves to the latest compatible version
    return import("https://esm.sh/ai@4");
  });

  main.variable(observer("openaiPkg")).define(
    "openaiPkg", ["openaiKey"],
    async function (openaiKey) {
      const { createOpenAI } = await import("https://esm.sh/@ai-sdk/openai@1");
      return createOpenAI({ apiKey: openaiKey, dangerouslyAllowBrowser: true });
    }
  );

  // ── Neo4j driver ───────────────────────────────────────────────────────────
  main.variable(observer("driver")).define(
    "driver",
    ["neo4j", "neo4jUri", "neo4jUsername", "neo4jPassword"],
    function (neo4j, uri, user, pass) {
      return neo4j.driver(uri, neo4j.auth.basic(user, pass), {
        disableLosslessIntegers: true,
      });
    }
  );

  // ── Section 0: Direct Neo4j Query ──────────────────────────────────────────
  main.variable(observer()).define(["md"], function (md) {
    return md`---
## 0. Direct Neo4j Query

No AI — uses \`neo4j-driver\` directly. Verifies connectivity and shows the top 10 organisations by news article coverage.`;
  });

  main.variable(observer("topOrgs")).define(
    "topOrgs", ["driver"],
    async function (driver) {
      const { records } = await driver.executeQuery(
        `MATCH (a:Article)-[:MENTIONS]->(o:Organization)
         RETURN o.name AS org, count(a) AS articles
         ORDER BY articles DESC LIMIT 10`
      );
      return records.map((r) => ({
        org: r.get("org"),
        articles: r.get("articles"),
      }));
    }
  );

  main.variable(observer()).define(
    ["Inputs", "topOrgs"],
    function (Inputs, topOrgs) {
      return Inputs.table(topOrgs, {
        header: { org: "Organisation", articles: "Article Count" },
      });
    }
  );

  main.variable(observer("dbLabels")).define(
    "dbLabels", ["driver"],
    async function (driver) {
      const { records } = await driver.executeQuery(
        "CALL db.labels() YIELD label RETURN label ORDER BY label"
      );
      return records.map((r) => r.get("label"));
    }
  );

  main.variable(observer()).define(
    ["md", "dbLabels"],
    function (md, labels) {
      return md`**Node labels:** ${labels.join(" · ")}`;
    }
  );

  // ── Section 1: Custom Tools Agent ──────────────────────────────────────────
  main.variable(observer()).define(["md"], function (md) {
    return md`---
## 1. Custom Tools Agent

A \`getInvestments\` tool is defined with \`tool()\` + \`inputSchema: jsonSchema()\` (no Zod in AI SDK v4+), then passed to \`generateText\`. The LLM decides when to call it.

> Enter your OpenAI API key in the configuration above before running.`;
  });

  main.variable(observer("viewof customQuery")).define(
    "viewof customQuery", ["Inputs"],
    (Inputs) =>
      Inputs.text({
        label: "Query",
        value: "Which companies did Google invest in?",
        width: 500,
      })
  );
  main.variable(observer("customQuery")).define(
    "customQuery", ["Generators", "viewof customQuery"], (G, _) => G.input(_)
  );

  main.variable(observer("viewof runCustom")).define(
    "viewof runCustom", ["Inputs"],
    (Inputs) => Inputs.button("▶ Run Custom Tools Agent")
  );
  main.variable(observer("runCustom")).define(
    "runCustom", ["Generators", "viewof runCustom"], (G, _) => G.input(_)
  );

  main.variable(observer("customResult")).define(
    "customResult",
    ["runCustom", "aiPkg", "openaiPkg", "aiModel", "customQuery", "driver"],
    async function (_, aiPkg, openai, model, query, driver) {
      if (!_) return null;
      const { generateText, tool, jsonSchema } = aiPkg;

      const getInvestments = tool({
        description: "Returns the investments made by a company.",
        inputSchema: jsonSchema({
          type: "object",
          properties: {
            company: { type: "string", description: "Company or organisation name" },
          },
          required: ["company"],
        }),
        execute: async ({ company }) => {
          const { records } = await driver.executeQuery(
            `MATCH (o:Organization)-[:HAS_INVESTOR]->(i)
             WHERE o.name = $company
             RETURN i.name AS name, labels(i) AS types LIMIT 20`,
            { company }
          );
          return records.map((r) => ({
            name: r.get("name"),
            types: r.get("types"),
          }));
        },
      });

      const result = await generateText({
        model: openai(model),
        system:
          "You are a helpful graph analyst with access to a Neo4j companies knowledge graph. Use the available tools to answer questions accurately.",
        prompt: query,
        tools: { getInvestments },
        maxSteps: 5,
      });
      return {
        text: result.text,
        toolCalls: result.steps.flatMap((s) => s.toolCalls ?? []).length,
      };
    }
  );

  main.variable(observer()).define(
    ["customResult", "html"],
    function (result, html) {
      if (!result)
        return html`<p style="color:#888"><em>Click ▶ Run to execute.</em></p>`;
      return html`<div
        style="font-family:monospace;white-space:pre-wrap;background:#f5f5f5;padding:1rem;border-radius:6px;line-height:1.5"
      ><strong style="font-family:system-ui">Tool calls made: ${result.toolCalls}</strong>\n\n${result.text}</div>`;
    }
  );

  // ── Section 2: Memory Agent ────────────────────────────────────────────────
  main.variable(observer()).define(["md"], function (md) {
    return md`---
## 2. Memory Agent

Memory is stored **directly in Neo4j** using \`neo4j-driver\` — no extra packages needed.

**Graph schema:**
\`\`\`
(:MemorySession {id})-[:HAS_MESSAGE]->(:MemoryMessage {role, content, timestamp})
\`\`\`

- **Before hook** — retrieves prior messages and injects them into the system prompt  
- **After hook** — saves each turn as \`(:MemoryMessage)\` nodes

The two-turn demo shows memory in action: Turn 2 correctly resolves *"the company we discussed"* using Turn 1's stored context.

> Set a **writable** Neo4j URI below (must be separate from the read-only demo DB).`;
  });

  main.variable(observer("viewof memUri")).define(
    "viewof memUri", ["Inputs"],
    (Inputs) =>
      Inputs.text({
        label: "Memory Neo4j URI",
        placeholder: "neo4j+s://xxxx.databases.neo4j.io",
        width: 440,
      })
  );
  main.variable(observer("memUri")).define(
    "memUri", ["Generators", "viewof memUri"], (G, _) => G.input(_)
  );

  main.variable(observer("viewof memUser")).define(
    "viewof memUser", ["Inputs"],
    (Inputs) => Inputs.text({ label: "Memory username", value: "neo4j" })
  );
  main.variable(observer("memUser")).define(
    "memUser", ["Generators", "viewof memUser"], (G, _) => G.input(_)
  );

  main.variable(observer("viewof memPass")).define(
    "viewof memPass", ["Inputs"],
    (Inputs) => Inputs.password({ label: "Memory password", placeholder: "your-aura-password" })
  );
  main.variable(observer("memPass")).define(
    "memPass", ["Generators", "viewof memPass"], (G, _) => G.input(_)
  );

  main.variable(observer("memDriver")).define(
    "memDriver",
    ["neo4j", "memUri", "memUser", "memPass"],
    function (neo4j, uri, user, pass) {
      if (!uri) return null;
      return neo4j.driver(uri, neo4j.auth.basic(user, pass), {
        disableLosslessIntegers: true,
      });
    }
  );

  main.variable(observer("sessionId")).define("sessionId", function () {
    return `obs-${Date.now()}`;
  });

  main.variable(observer("storeMessage")).define(
    "storeMessage",
    ["memDriver", "sessionId"],
    function (memDriver, sessionId) {
      return async function (role, content) {
        if (!memDriver)
          throw new Error(
            "Memory driver not initialised — set the Memory Neo4j URI above."
          );
        await memDriver.executeQuery(
          `MERGE (s:MemorySession {id: $sessionId})
           CREATE (m:MemoryMessage {role: $role, content: $content, timestamp: datetime()})
           CREATE (s)-[:HAS_MESSAGE]->(m)`,
          { sessionId, role, content }
        );
      };
    }
  );

  main.variable(observer("getRecentMessages")).define(
    "getRecentMessages",
    ["memDriver", "sessionId"],
    function (memDriver, sessionId) {
      return async function (limit = 10) {
        if (!memDriver) return [];
        const { records } = await memDriver.executeQuery(
          `MATCH (s:MemorySession {id: $sessionId})-[:HAS_MESSAGE]->(m:MemoryMessage)
           RETURN m.role AS role, m.content AS content
           ORDER BY m.timestamp ASC LIMIT $limit`,
          { sessionId, limit }
        );
        return records.map(
          (r) => `${r.get("role").toUpperCase()}: ${r.get("content")}`
        );
      };
    }
  );

  main.variable(observer("viewof memTurn1")).define(
    "viewof memTurn1", ["Inputs"],
    (Inputs) =>
      Inputs.text({
        label: "Turn 1",
        value: "Give me a competitive analysis of Google.",
        width: 500,
      })
  );
  main.variable(observer("memTurn1")).define(
    "memTurn1", ["Generators", "viewof memTurn1"], (G, _) => G.input(_)
  );

  main.variable(observer("viewof memTurn2")).define(
    "viewof memTurn2", ["Inputs"],
    (Inputs) =>
      Inputs.text({
        label: "Turn 2",
        value: "What are the subsidiaries of the company we discussed?",
        width: 500,
      })
  );
  main.variable(observer("memTurn2")).define(
    "memTurn2", ["Generators", "viewof memTurn2"], (G, _) => G.input(_)
  );

  main.variable(observer("viewof runMemory")).define(
    "viewof runMemory", ["Inputs"],
    (Inputs) => Inputs.button("▶ Run Memory Agent (2 turns)")
  );
  main.variable(observer("runMemory")).define(
    "runMemory", ["Generators", "viewof runMemory"], (G, _) => G.input(_)
  );

  main.variable(observer("memoryResult")).define(
    "memoryResult",
    [
      "runMemory",
      "aiPkg",
      "openaiPkg",
      "aiModel",
      "memTurn1",
      "memTurn2",
      "storeMessage",
      "getRecentMessages",
    ],
    async function (
      _,
      aiPkg,
      openai,
      model,
      turn1,
      turn2,
      storeMessage,
      getRecentMessages
    ) {
      if (!_) return null;
      const { generateText } = aiPkg;
      const SYSTEM =
        "You are a helpful graph analyst with access to a Neo4j companies knowledge graph.";
      const out = [];

      // Turn 1
      const r1 = await generateText({
        model: openai(model),
        system: SYSTEM,
        prompt: turn1,
        maxSteps: 1,
      });
      out.push({ turn: 1, query: turn1, response: r1.text });
      await storeMessage("user", turn1);
      await storeMessage("assistant", r1.text);

      // Turn 2 — inject Turn 1 history via before-hook
      const history = await getRecentMessages();
      const ctxWithHistory = `${SYSTEM}\n\n--- CONVERSATION HISTORY ---\n${history.join(
        "\n"
      )}\n----------------------------`;
      const r2 = await generateText({
        model: openai(model),
        system: ctxWithHistory,
        prompt: turn2,
        maxSteps: 1,
      });
      out.push({ turn: 2, query: turn2, response: r2.text });
      await storeMessage("user", turn2);
      await storeMessage("assistant", r2.text);

      return out;
    }
  );

  main.variable(observer()).define(
    ["memoryResult", "html"],
    function (result, html) {
      if (!result)
        return html`<p style="color:#888"><em>Click ▶ Run to execute the two-turn demo.</em></p>`;
      return html`<div style="font-family:system-ui;line-height:1.6">
        ${result.map(
          (t) => html`<details
            open
            style="margin:0.75rem 0;border:1px solid #ddd;border-radius:6px;padding:0.5rem 1rem"
          >
            <summary>
              <strong>Turn ${t.turn}:</strong> ${t.query}
            </summary>
            <p style="white-space:pre-wrap;margin:0.5rem 0;color:#333">
              ${t.response}
            </p>
          </details>`
        )}
      </div>`;
    }
  );

  // ── MCP Agent — reference ──────────────────────────────────────────────────
  main.variable(observer()).define(["md"], function (md) {
    return md`---
## MCP Agent *(Node.js only)*

The \`@ai-sdk/mcp\` client connects via HTTP to a locally-running \`neo4j-mcp-server\`.  
Because it targets \`localhost\`, it cannot run inside a browser-hosted notebook.

**Start the MCP server and run the agent from a terminal:**

\`\`\`bash
# Start MCP server
python -m neo4j_mcp \\
  --uri neo4j+s://demo.neo4jlabs.com:7687 \\
  --username companies --password companies \\
  --port 8443 --transport http

# In a second terminal
node 1-mcp-agent.mjs
\`\`\`

Source: [\`1-mcp-agent.mjs\`](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/vercel-agent/vercel-agent/1-mcp-agent.mjs)`;
  });

  return main;
}

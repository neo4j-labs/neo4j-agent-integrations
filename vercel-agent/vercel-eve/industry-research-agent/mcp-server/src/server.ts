// Local MCP server with one tool: get_investments.
// `npm run mcp` serves it at localhost:8100/mcp. Set MCP_TRANSPORT=stdio for desktop apps.
// Logs go to stderr, because stdio mode uses stdout for messages.
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  type Tool,
} from "@modelcontextprotocol/sdk/types.js";
import { closeDriver, describeTarget, getInvestments } from "./neo4j.js";

// eve doesn't start this, so load .env ourselves.
try {
  process.loadEnvFile?.();
} catch {
  // No .env — use the defaults in ./neo4j.ts.
}

const NAME = "neo4j-investments-mcp";
const VERSION = "0.1.0";

const PORT = Number(process.env.INVESTMENTS_MCP_PORT?.trim() || 8100);
const PATH = process.env.INVESTMENTS_MCP_PATH?.trim() || "/mcp";
const TRANSPORT = process.env.MCP_TRANSPORT?.trim().toLowerCase() === "stdio" ? "stdio" : "http";

const TOOLS: Tool[] = [
  {
    name: "get_investments",
    description:
      "Look up the investors in a company by its exact name. " +
      "Returns the id, name, and type (Person or Organization) of each investor. " +
      "Use this for who invested in a company, who its backers are, and its funding relationships.",
    inputSchema: {
      type: "object",
      properties: {
        company: {
          type: "string",
          description: "Exact company name as it appears in the graph, e.g. 'Neo4j'.",
        },
      },
      required: ["company"],
    },
  },
];

function buildServer(): Server {
  const server = new Server({ name: NAME, version: VERSION }, { capabilities: { tools: {} } });

  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    if (req.params.name !== "get_investments") {
      return {
        content: [{ type: "text", text: `Unknown tool: ${req.params.name}` }],
        isError: true,
      };
    }

    const company = (req.params.arguments ?? {}).company;
    if (typeof company !== "string" || company.trim() === "") {
      return {
        content: [{ type: "text", text: "get_investments needs a company name." }],
        isError: true,
      };
    }

    return { content: [{ type: "text", text: await getInvestments(company.trim()) }] };
  });

  return server;
}

async function main() {
  if (TRANSPORT === "stdio") {
    await buildServer().connect(new StdioServerTransport());
    console.error(`${NAME} on stdio → ${describeTarget()}`);
    return;
  }

  const http = createServer((req, res) => {
    void handleHttp(req, res).catch((error) => {
      console.error("[mcp] request failed:", error);
      if (!res.headersSent) res.writeHead(500).end();
    });
  });

  http.listen(PORT, () => {
    console.error(`${NAME} → ${describeTarget()}`);
    console.error(`Listening at http://localhost:${PORT}${PATH}`);
    console.error("Leave this running and start the agent in another terminal.");
  });

  for (const signal of ["SIGINT", "SIGTERM"] as const) {
    process.on(signal, () => {
      http.close();
      void closeDriver().finally(() => process.exit(0));
    });
  }
}

// No sessions: each request gets a fresh MCP server.
async function handleHttp(req: IncomingMessage, res: ServerResponse) {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);

  // scripts/chat.mjs sends HEAD to check the server is up.
  if (req.method === "HEAD") {
    res.writeHead(url.pathname === PATH ? 200 : 404).end();
    return;
  }

  if (url.pathname !== PATH) {
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: `Not found. MCP is served at ${PATH}.` }));
    return;
  }

  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });
  const server = buildServer();

  res.on("close", () => {
    void transport.close();
    void server.close();
  });

  await server.connect(transport);
  await transport.handleRequest(req, res);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

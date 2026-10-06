#!/usr/bin/env node
// `npm run chat`: starts the local MCP server (if it isn't running), then `eve dev`.
// Extra args go to eve, e.g. `npm run chat -- --tools full`.
import { spawn } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

try {
  process.loadEnvFile(join(root, ".env"));
} catch {
  console.warn("  No .env found — using the ambient environment.");
}

const MCP_URL = process.env.INVESTMENTS_MCP_URL?.trim() || "http://localhost:8100/mcp";

const dim = (text) => `\x1b[2m${text}\x1b[0m`;
const yellow = (text) => `\x1b[33m${text}\x1b[0m`;

/** Is the MCP server up? Any reply below 500 counts. */
async function reachable(timeoutMs = 1000) {
  try {
    const response = await fetch(MCP_URL, {
      method: "HEAD",
      signal: AbortSignal.timeout(timeoutMs),
    });
    return response.status < 500;
  } catch {
    return false;
  }
}

let mcp;

if (await reachable()) {
  console.log(dim(`  MCP server already running at ${MCP_URL}`));
} else {
  console.log(dim(`  Starting the local MCP server → ${MCP_URL}`));

  mcp = spawn(
    process.execPath,
    [join(root, "node_modules", "tsx", "dist", "cli.mjs"), join(root, "mcp-server", "src", "server.ts")],
    { cwd: root, stdio: ["ignore", "ignore", "pipe"] },
  );

  // Keep server logs out of the chat UI; show them only if it dies.
  let stderr = "";
  mcp.stderr.on("data", (chunk) => {
    stderr += chunk;
  });

  mcp.on("error", (error) => {
    console.warn(yellow(`  Could not start the MCP server: ${error.message}`));
    mcp = undefined;
  });

  mcp.on("exit", (code) => {
    if (code) console.warn(yellow(`\n  MCP server exited (${code}):\n${stderr.trim()}`));
  });

  // The agent works without it, so a timeout only warns.
  const deadline = Date.now() + 8000;
  let up = false;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 250));
    if (await reachable()) {
      up = true;
      break;
    }
    if (mcp?.exitCode !== null && mcp?.exitCode !== undefined) break;
  }

  if (up) {
    console.log(dim("  MCP server ready — get_investments is available in this chat."));
  } else {
    console.warn(
      yellow("  MCP server did not come up — chatting without get_investments."),
      dim("\n  Run `npm run mcp` in another terminal to see why."),
    );
  }
}

console.log(dim("  Opening eve chat. Ctrl+C to quit.\n"));

const eve = spawn(
  process.execPath,
  [join(root, "node_modules", "eve", "bin", "eve.js"), "dev", ...process.argv.slice(2)],
  { cwd: root, stdio: "inherit" },
);

// Let eve handle Ctrl+C; stop the MCP server once eve exits.
process.on("SIGINT", () => {});
process.on("SIGTERM", () => {});

eve.on("exit", (code, signal) => {
  mcp?.kill("SIGTERM");
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 0);
});

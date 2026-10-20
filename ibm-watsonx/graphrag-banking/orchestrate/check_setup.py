"""Check that `make wxo-setup` created every demo object in watsonx Orchestrate.

Each `orchestrate ... list` command returns every object in the tenant. This
script keeps only the banking demo's objects and checks that they are wired
together: the agent uses all six tools, and the baseline uses the knowledge base.

Usage: uv run python orchestrate/check_setup.py
Exits with status 1 if any check fails.
"""

import json
import os
import subprocess
import sys
from typing import Any

from build_agent import TOOLS

from graphrag_banking.config import load_settings

CONNECTION = "banking_creds"
AGENTS = ["banking_support", "banking_baseline"]
KNOWLEDGE_BASE = "banking_policies"
# The ADK prints through rich, which wraps output at 80 columns when it is not a
# terminal. That breaks long JSON strings and truncates table cells.
_WIDE_OUTPUT = {**os.environ, "COLUMNS": "10000"}


def _orchestrate(*args: str) -> str:
    result = subprocess.run(
        ["orchestrate", *args],
        capture_output=True,
        text=True,
        check=False,
        env=_WIDE_OUTPUT,
    )
    if result.returncode != 0:
        sys.exit(
            f"orchestrate {' '.join(args)} failed. Run `make wxo-env` to log in again.\n"
            f"{result.stderr.strip()}"
        )
    return result.stdout


def _orchestrate_json(*args: str) -> Any:
    return json.loads(_orchestrate(*args, "-v"))


def _report(ok: bool, label: str, detail: str) -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {detail}", flush=True)
    return ok


def check_environment() -> bool:
    expected = os.environ.get("WO_ENV_NAME", "")
    active = next(
        (
            line.split()[0]
            for line in _orchestrate("env", "list").splitlines()
            if "(active)" in line
        ),
        "",
    )
    return _report(
        bool(expected) and active == expected,
        "environment",
        f"active is {active or 'none'}, WO_ENV_NAME is {expected or 'not set'}",
    )


def check_connection() -> bool:
    rows = [
        c for c in _orchestrate_json("connections", "list") if c["app_id"] == CONNECTION
    ]
    entered = {c["environment"] for c in rows if c["credentials_entered"]}
    missing = sorted({"draft", "live"} - entered)
    return _report(
        not missing,
        f"connection {CONNECTION}",
        f"credentials missing for {', '.join(missing)}"
        if missing
        else "credentials set for draft and live",
    )


def check_tools() -> tuple[bool, dict[str, str]]:
    ids = {
        t["name"]: t["id"]
        for t in _orchestrate_json("tools", "list")
        if t["name"] in TOOLS
    }
    missing = [name for name in TOOLS if name not in ids]
    ok = _report(
        not missing,
        "tools",
        f"missing {', '.join(missing)}" if missing else f"all {len(TOOLS)} imported",
    )
    return ok, ids


def check_knowledge_base() -> tuple[bool, str | None]:
    kb_id = next(
        (
            kb["id"]
            for kb in _orchestrate_json("knowledge-bases", "list")
            if kb["name"] == KNOWLEDGE_BASE
        ),
        None,
    )
    if kb_id is None:
        return _report(False, f"knowledge base {KNOWLEDGE_BASE}", "not found"), None
    status = _orchestrate_json("knowledge-bases", "status", "-n", KNOWLEDGE_BASE).get(
        "built_in_index_status"
    )
    ok = _report(
        status == "ready", f"knowledge base {KNOWLEDGE_BASE}", f"status {status}"
    )
    return ok, kb_id


def check_agents(tool_ids: dict[str, str], kb_id: str | None) -> bool:
    agents = {
        a["name"]: a
        for a in _orchestrate_json("agents", "list")["native"]
        if a["name"] in AGENTS
    }
    results = []
    for name in AGENTS:
        agent = agents.get(name)
        if agent is None:
            results.append(_report(False, f"agent {name}", "not found"))
            continue
        if name == "banking_support":
            unwired = [t for t, tid in tool_ids.items() if tid not in agent["tools"]]
            results.append(
                _report(
                    len(tool_ids) == len(TOOLS) and not unwired,
                    f"agent {name}",
                    f"not wired to {', '.join(unwired)}"
                    if unwired
                    else f"uses {len(tool_ids)} of {len(TOOLS)} tools, llm {agent['llm']}",
                )
            )
        else:
            wired = kb_id is not None and kb_id in agent["knowledge_base"]
            results.append(
                _report(
                    wired,
                    f"agent {name}",
                    f"uses {KNOWLEDGE_BASE}, llm {agent['llm']}"
                    if wired
                    else f"does not use {KNOWLEDGE_BASE}",
                )
            )
    return all(results)


def main() -> None:
    load_settings()  # loads .env, for WO_ENV_NAME
    if not check_environment():
        sys.exit("Run `make wxo-env` to activate WO_ENV_NAME, then re-run this check.")
    tools_ok, tool_ids = check_tools()
    kb_ok, kb_id = check_knowledge_base()
    results = [
        check_connection(),
        tools_ok,
        kb_ok,
        check_agents(tool_ids, kb_id),
    ]
    if not all(results):
        sys.exit(
            "Some checks failed. Re-run `make wxo-setup`, or see Troubleshooting in the README."
        )
    print("All Orchestrate demo objects are in place.")


if __name__ == "__main__":
    main()

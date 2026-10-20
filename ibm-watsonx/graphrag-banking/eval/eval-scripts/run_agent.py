"""Send eval/scenarios.yaml prompts to Orchestrate agents and save each turn as JSON.

Run with the ADK's Python, which has the ibm_watsonx_orchestrate client:

    ADK_PY="$(uv tool dir)/ibm-watsonx-orchestrate/bin/python"
    "$ADK_PY" -I eval/eval-scripts/run_agent.py <out_dir> \
        [--agents banking_support,...] [--scenarios A,B,C,D] [--runs 1] \
        [--same-thread] [--persona customer]

Agents are looked up by name. By default each run of each scenario starts a new
thread. With --same-thread, each run sends the selected scenarios in order in one
thread. Every turn is saved to <out_dir>/<agent>_<run>_<turn>_<scenario>.json with
only that turn's answer and tool calls, for score.py. Each tool call records the
agent that made it, and each turn lists the collaborators it called.

"all" runs every scenario of --persona. A scenario with no persona is a
customer's. Scenario IDs given by name run whatever their persona.
"""

import argparse
import json
import time
from pathlib import Path
from typing import Any

import yaml
from ibm_watsonx_orchestrate.client.agents.agent_client import AgentClient
from ibm_watsonx_orchestrate.client.chat.run_client import RunClient
from ibm_watsonx_orchestrate.client.threads.threads_client import ThreadsClient
from ibm_watsonx_orchestrate.client.utils import instantiate_client
from ibm_watsonx_orchestrate_clients.common.base_client import ClientAPIException

SCENARIOS_PATH = Path(__file__).resolve().parents[1] / "scenarios.yaml"
COLLABORATOR_PREFIX = "chat_with_collaborator_"
POLL_SECONDS = 2
MAX_POLLS = 150  # five minutes; the first tool call after a quiet spell can take one


def text_of(content: object) -> str:
    if isinstance(content, list):
        return "\n".join(i.get("text", "") for i in content if isinstance(i, dict))
    return str(content)


def comma_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def load_scenarios(ids: list[str], persona: str) -> list[dict[str, Any]]:
    with SCENARIOS_PATH.open(encoding="utf-8") as f:
        scenarios = yaml.safe_load(f)["scenarios"]
    if ids == ["all"]:
        return [s for s in scenarios if s.get("persona", "customer") == persona]
    by_id = {s["id"]: s for s in scenarios}
    if missing := [i for i in ids if i not in by_id]:
        raise SystemExit(f"Unknown scenario IDs: {', '.join(missing)}")
    return [by_id[i] for i in ids]


def resolve_agents(client: AgentClient, names: list[str]) -> dict[str, str]:
    found = {a["name"]: a["id"] for a in client.get_drafts_by_names(names)}
    if missing := [n for n in names if n not in found]:
        raise SystemExit(f"Agents not found in the tenant: {', '.join(missing)}")
    return {name: found[name] for name in names}


def tool_calls_of(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Pair each tool response in the message's step_history with its call's args
    and the agent that made the call."""
    calls: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    for step in message.get("step_history") or []:
        for d in step.get("step_details", []):
            if d["type"] == "tool_calls":
                agent = d.get("agent_display_name")
                calls += [c | {"agent": agent} for c in d["tool_calls"]]
            elif d["type"] == "tool_response":
                responses.append(d)
    unmatched = list(calls)
    paired = []
    for r in responses:
        call = next(
            (c for c in unmatched if c.get("id") == r.get("tool_call_id")),
            next((c for c in unmatched if c.get("name") == r.get("name")), None),
        )
        if call is not None:
            unmatched.remove(call)
        paired.append(
            {
                "name": r.get("name"),
                "args": (call or {}).get("args") or {},
                "agent": (call or {}).get("agent"),
                "content": r.get("content"),
            }
        )
    return paired


def collaborators_of(tool_calls: list[dict[str, Any]], agent_name: str) -> list[str]:
    """Collaborators the agent sent the question to, or that made tool calls."""
    names = {
        c["name"].removeprefix(COLLABORATOR_PREFIX)
        for c in tool_calls
        if c["name"] and c["name"].startswith(COLLABORATOR_PREFIX)
    }
    names |= {c["agent"] for c in tool_calls if c["agent"] not in (None, agent_name)}
    return sorted(names)


def reply_to(
    threads: ThreadsClient, run: dict[str, Any], status: dict[str, Any]
) -> dict[str, Any]:
    """The assistant message that answers this run's user message, and no other."""
    msgs = threads.get_thread_messages(run["thread_id"])
    msgs = msgs["data"] if isinstance(msgs, dict) else msgs
    reply = next(
        (
            m
            for m in msgs
            if m.get("role") == "assistant"
            and m.get("parent_message_id") == run["message_id"]
        ),
        None,
    )
    if reply is None:
        reply = ((status.get("result") or {}).get("data") or {}).get("message") or {}
    return reply


def send(
    runs: RunClient,
    threads: ThreadsClient,
    agent_id: str,
    prompt: str,
    thread_id: str | None,
) -> dict[str, Any]:
    start = time.time()
    run = runs.create_run(message=prompt, agent_id=agent_id, thread_id=thread_id)
    try:
        status = runs.wait_for_run_completion(
            run["run_id"], poll_interval=POLL_SECONDS, max_retries=MAX_POLLS
        )
    except (TimeoutError, ClientAPIException) as e:
        status = {"status": "error", "error": str(e)}
    reply = reply_to(threads, run, status)
    return {
        "status": status.get("status"),
        "error": status.get("error") or status.get("last_error"),
        "seconds": round(time.time() - start, 1),
        "model": (status.get("usage") or {}).get("model_name"),
        "thread_id": run["thread_id"],
        "run_id": run["run_id"],
        "trace_id": run.get("trace_id"),
        "answer": text_of(reply.get("content", "")),
        "tool_calls": tool_calls_of(reply),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--agents", type=comma_list, default=["banking_support"])
    parser.add_argument("--scenarios", type=comma_list, default=["A", "B", "C", "D"])
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--same-thread", action="store_true")
    parser.add_argument("--persona", choices=["customer", "staff"], default="customer")
    args = parser.parse_args()

    scenarios = load_scenarios(args.scenarios, args.persona)
    agents = resolve_agents(instantiate_client(AgentClient), args.agents)
    runs = instantiate_client(RunClient)
    threads = instantiate_client(ThreadsClient)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    mode = "same_thread" if args.same_thread else "new_thread"

    for agent_name, agent_id in agents.items():
        for run_no in range(1, args.runs + 1):
            thread_id = None
            for turn, scenario in enumerate(scenarios, start=1):
                sid = scenario["id"]
                out = {
                    "agent": agent_name,
                    "agent_id": agent_id,
                    "scenario": sid,
                    "run": run_no,
                    "mode": mode,
                    "turn": turn if args.same_thread else 1,
                    "prompt": scenario["prompt"],
                    **send(runs, threads, agent_id, scenario["prompt"], thread_id),
                }
                out["collaborators"] = collaborators_of(out["tool_calls"], agent_name)
                if args.same_thread:
                    thread_id = out["thread_id"]
                name = f"{agent_name}_{run_no:02}_{turn:02}_{sid}.json"
                (args.out_dir / name).write_text(json.dumps(out, indent=1))
                print(
                    f"{agent_name} {sid} run {run_no}/{args.runs}: {out['status']} "
                    f"in {out['seconds']}s, {len(out['tool_calls'])} tool calls",
                    flush=True,
                )


if __name__ == "__main__":
    main()

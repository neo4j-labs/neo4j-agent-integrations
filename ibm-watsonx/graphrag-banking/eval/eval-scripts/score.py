"""Score run_agent.py output with the project's eval checks and save a report.

Run from the project root:

    uv run python eval/eval-scripts/score.py <out_dir>

Prints each turn's score, then a pass/fail table per agent and scenario. Writes
eval/results/wxo-eval-<UTC timestamp>.json and exits with status 1 if any run
failed. A run passes when it completed and every check passed.
"""

import ast
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from graphrag_banking.config import EVAL_DIR, load_settings
from graphrag_banking.eval_local import RESULTS_DIR, load_scenarios, score


def parse(content: object) -> object:
    """Tool results are JSON (default style) or 'Observation: <python repr>' (react)."""
    if not isinstance(content, str):
        return content
    text = content.removeprefix("Observation:").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return content


def score_run(run: dict[str, Any], scenario: dict[str, Any], year: int) -> dict:
    tool_calls = [
        {
            "name": c["name"],
            "args": c["args"],
            "agent": c.get("agent"),
            "result": parse(c["content"]),
        }
        for c in run["tool_calls"]
    ]
    result = {
        "answer": run["answer"],
        "tool_calls": tool_calls,
        "collaborators": run.get("collaborators", []),
    }
    checks = score(scenario, result, year)
    completed = run["status"] == "completed"
    passed = completed and all(c.passed for c in checks)
    tools = ",".join(c["name"] for c in tool_calls)
    print(
        f"{run['agent']:34} {run['scenario']:3} run {run['run']} turn {run['turn']}  "
        f"{sum(c.passed for c in checks):2}/{len(checks):<2} "
        f"{'PASS' if passed else 'FAIL'} {run['seconds']:6}s  [{tools}]"
    )
    if not completed:
        print(f"{'':40}run {run['status']}: {run['error']}")
    for c in checks:
        if not c.passed:
            print(f"{'':40}missed {c.kind}: {c.fact}")
    return {
        **{k: v for k, v in run.items() if k != "tool_calls"},
        "passed": passed,
        "checks": [asdict(c) for c in checks],
        "tool_calls": tool_calls,
    }


def print_summary(
    runs: list[dict[str, Any]],
    agents: list[str],
    ids: list[str],
    runs_per_scenario: int,
    mode: str,
) -> None:
    """One row per agent and scenario. A run passes only if it completed and every
    check passed, so 'Runs passed' counts whole runs and 'Checks passed' counts the
    individual facts and tool calls the checks looked for."""
    rows = []
    for agent in agents:
        for sid in ids:
            group = [r for r in runs if (r["agent"], r["scenario"]) == (agent, sid)]
            checks = [c for r in group for c in r["checks"]]
            rows.append(
                (
                    agent,
                    sid,
                    "PASS" if all(r["passed"] for r in group) else "FAIL",
                    f"{sum(r['passed'] for r in group)} of {len(group)}",
                    f"{sum(c['passed'] for c in checks)} of {len(checks)}",
                )
            )

    headers = ("Agent", "Scenario", "Result", "Runs passed", "Checks passed")
    widths = [max(len(str(row[i])) for row in [headers, *rows]) for i in range(5)]
    rule = "  ".join("-" * w for w in widths)

    def line(row: tuple[str, ...]) -> str:
        return "  ".join(str(v).ljust(w) for v, w in zip(row, widths)).rstrip()

    passed = sum(r["passed"] for r in runs)
    print(f"\nSummary ({mode}, {runs_per_scenario} run(s) per scenario)")
    print(line(headers))
    print(rule)
    for row in rows:
        print(line(row))
    print(rule)
    print(f"Overall: {passed} of {len(runs)} runs passed")
    print("A run passes only if it completed and every check passed.")


def main() -> None:
    settings = load_settings()
    year = settings.demo_as_of.year
    scenarios = {s["id"]: s for s in load_scenarios()}
    started_at = datetime.now(UTC)

    raw = [json.loads(p.read_text()) for p in sorted(Path(sys.argv[1]).glob("*.json"))]
    if not raw:
        raise SystemExit(f"No runs found in {sys.argv[1]}")
    runs = [score_run(r, scenarios[r["scenario"]], year) for r in raw]

    agents = list(dict.fromkeys(r["agent"] for r in runs))
    ids = list(dict.fromkeys(r["scenario"] for r in runs))
    runs_per_scenario = max(r["run"] for r in runs)
    summary = {
        agent: {
            sid: sum(
                r["passed"] for r in runs if (r["agent"], r["scenario"]) == (agent, sid)
            )
            for sid in ids
        }
        for agent in agents
    }

    mode = runs[0]["mode"]
    print_summary(runs, agents, ids, runs_per_scenario, mode)

    report = {
        "started_at": started_at.isoformat(),
        "target": "watsonx_orchestrate",
        "mode": mode,
        "agents": {r["agent"]: r["agent_id"] for r in runs},
        "models": {
            agent: next(
                (r["model"] for r in runs if r["agent"] == agent and r["model"]), None
            )
            for agent in agents
        },
        "demo_as_of": settings.demo_as_of.isoformat(),
        "customer_id": settings.demo_customer_id,
        "scenarios": ids,
        "runs_per_scenario": runs_per_scenario,
        "passed": all(r["passed"] for r in runs),
        "summary": summary,
        "runs": runs,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"wxo-eval-{started_at:%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Saved {path.relative_to(EVAL_DIR.parent)}")
    if not report["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

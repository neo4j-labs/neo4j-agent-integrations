"""Check that a supervisor keeps each collaborator's facts and adds none of its own.

Run from the project root, after score.py:

    ADK_PY="$(uv tool dir)/ibm-watsonx-orchestrate/bin/python" \\
        uv run python eval/eval-scripts/supervisor_check.py <results.json> <trace_dir>

Checks each run in a wxo-eval results file whose scenario lists
expected_collaborators. Each collaborator's answer is the output.message of a
"collaborator" observation in the run's trace. A trace missing from <trace_dir>
is fetched with traces.py, which needs ADK_PY. The observability API allows four
requests a minute and keeps traces for four hours.

  Kept   Each collaborator's amounts, rule codes, percentages, dates, and names
         that the supervisor's answer keeps. Names are the "name" values in that
         collaborator's own tool results.
  Added  Amounts, rule codes, and percentages in the supervisor's answer that are
         in no collaborator's answer.
  Copy   For a scenario with one expected collaborator, whether the answer is
         its answer exactly, with a difflib ratio. Reported, not scored.

A run passes when it keeps every fact, adds none, and passed its routing
checks. Exits with status 1 if any run fails.
"""

import difflib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from graphrag_banking.eval_local import contains, load_scenarios, normalize

TRACES_SCRIPT = Path(__file__).with_name("traces.py")
SCORED_KINDS = ("amount", "rule_code", "percent")

_AMOUNT = re.compile(r"\$\d+(?:\.\d+)?(?!\w|\.\d)")
_RULE_CODE = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)+\b")
_PERCENT = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(?:%|percent\b)")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


@dataclass
class RunCheck:
    calls: Counter[str]
    kept: int = 0
    total: int = 0
    missing: dict[str, list[str]] = field(default_factory=dict)
    added: list[str] = field(default_factory=list)
    copy: bool | None = None
    ratio: float | None = None


def collaborator_answers(observations: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Each collaborator's name and answer, in the order they answered."""
    answers = []
    for o in sorted(observations, key=lambda o: o["startTime"]):
        output = o.get("output")
        if o.get("name") != "collaborator" or not isinstance(output, dict):
            continue
        name = o["metadata"]["attributes"].get("collaborator.name")
        answers.append((name, output.get("message") or ""))
    return answers


def facts(text: str, year: int) -> dict[str, set[str]]:
    """Amounts, rule codes, percentages, and dates in text, normalized."""
    plain = normalize(text, year)
    return {
        "amount": set(_AMOUNT.findall(plain)),
        "rule_code": set(_RULE_CODE.findall(text)),
        "percent": {f"{number}%" for number in _PERCENT.findall(plain)},
        "date": set(_DATE.findall(plain)),
    }


def names_in(value: Any) -> set[str]:
    """Every string under a "name" key anywhere in a tool result."""
    match value:
        case dict():
            found = {value["name"]} if isinstance(value.get("name"), str) else set()
            return found.union(*(names_in(item) for item in value.values()))
        case list():
            return set().union(*(names_in(item) for item in value))
        case _:
            return set()


def check_run(
    run: dict[str, Any],
    scenario: dict[str, Any],
    observations: list[dict[str, Any]],
    year: int,
) -> RunCheck:
    answers = collaborator_answers(observations)
    final = normalize(run["answer"], year)
    final_facts = facts(run["answer"], year)
    result = RunCheck(calls=Counter(name for name, _ in answers))
    from_collaborators: dict[str, set[str]] = {kind: set() for kind in SCORED_KINDS}
    for name, answer in answers:
        found = facts(answer, year)
        for kind in SCORED_KINDS:
            from_collaborators[kind] |= found[kind]
        tool_names = set().union(
            *(
                names_in(c["result"])
                for c in run["tool_calls"]
                if c.get("agent") == name
            )
        )
        plain = normalize(answer, year)
        found["name"] = {n for n in tool_names if contains(plain, normalize(n, year))}
        for kind, values in found.items():
            kept = {
                v
                for v in values
                if (
                    contains(final, normalize(v, year))
                    if kind == "name"
                    else v in final_facts[kind]
                )
            }
            result.kept += len(kept)
            result.total += len(values)
            if values - kept:
                result.missing.setdefault(name, []).extend(sorted(values - kept))
    result.added = sorted(
        v for kind in SCORED_KINDS for v in final_facts[kind] - from_collaborators[kind]
    )
    if answers and len(scenario.get("expected_collaborators", [])) == 1:
        copied = answers[-1][1].strip()
        result.copy = copied == run["answer"].strip()
        result.ratio = difflib.SequenceMatcher(
            None, copied, run["answer"].strip()
        ).ratio()
    return result


def passed(run: dict[str, Any], result: RunCheck) -> bool:
    routing = all(c["passed"] for c in run["checks"] if c["kind"] == "routing")
    return bool(result.calls) and not result.missing and not result.added and routing


def load_trace(trace_id: str, trace_dir: Path) -> list[dict[str, Any]]:
    path = trace_dir / f"{trace_id}.json"
    if not path.exists():
        if not (adk_py := os.environ.get("ADK_PY")):
            raise SystemExit(f"No cached trace {path}. Set ADK_PY to fetch it.")
        trace_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [adk_py, "-I", str(TRACES_SCRIPT), "get", trace_id, str(path)], check=True
        )
    return json.loads(path.read_text())


def main() -> None:
    report = json.loads(Path(sys.argv[1]).read_text())
    trace_dir = Path(sys.argv[2])
    year = int(report["demo_as_of"][:4])
    scenarios = {s["id"]: s for s in load_scenarios()}
    all_passed = True
    for run in report["runs"]:
        scenario = scenarios[run["scenario"]]
        if "expected_collaborators" not in scenario:
            continue
        label = f"{run['agent']} {run['scenario']} run {run['run']} turn {run['turn']}"
        if not run.get("trace_id"):
            print(f"{label}: FAIL, no trace ID")
            all_passed = False
            continue
        result = check_run(run, scenario, load_trace(run["trace_id"], trace_dir), year)
        ok = passed(run, result)
        all_passed &= ok
        calls = ", ".join(f"{n} x{c}" for n, c in sorted(result.calls.items()))
        copy = "-" if result.copy is None else f"{result.copy} ({result.ratio:.3f})"
        print(
            f"{label}: {'PASS' if ok else 'FAIL'}  kept {result.kept}/{result.total}  "
            f"added {len(result.added)}  copy {copy}  calls {calls or 'none'}"
        )
        for name, values in result.missing.items():
            print(f"    missing from {name}: {', '.join(values)}")
        if result.added:
            print(f"    added: {', '.join(result.added)}")
    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()

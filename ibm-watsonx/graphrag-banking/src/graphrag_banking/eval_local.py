"""Run eval/scenarios.yaml through the agent and score each answer (PRD Phase 3)."""

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any

import yaml

from graphrag_banking.agent import AgentResult, run_agent
from graphrag_banking.config import EVAL_DIR, load_settings

SCENARIOS_PATH = EVAL_DIR / "scenarios.yaml"
RESULTS_DIR = EVAL_DIR / "results"

_MONTHS = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]
_MONTH_ABBREVS = [month[:3] for month in _MONTHS]
_MONTH_PATTERN = "|".join([*_MONTHS, *_MONTH_ABBREVS, "sept"])
_DATE = re.compile(
    rf"\b({_MONTH_PATTERN})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}})\b)?",
    re.IGNORECASE,
)
_AMOUNT = re.compile(r"(?:(\$)\s?)?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?")


@dataclass
class Check:
    kind: str
    fact: str
    passed: bool


def load_scenarios() -> list[dict[str, Any]]:
    with SCENARIOS_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)["scenarios"]


def persona(scenario: dict[str, Any]) -> str:
    """Who asks the scenario's prompt. A scenario with no persona is a customer's."""
    return scenario.get("persona", "customer")


def normalize(text: str, year: int) -> str:
    """Lowercase, write dates as YYYY-MM-DD, and amounts as $5000 or $1137.42."""

    def iso_date(match: re.Match[str]) -> str:
        month = _MONTH_ABBREVS.index(match[1][:3].lower()) + 1
        return date(int(match[3] or year), month, int(match[2])).isoformat()

    def plain_amount(match: re.Match[str]) -> str:
        cents = match[3] or ""
        if cents.strip(".0") == "":
            cents = ""
        return f"{match[1] or ''}{match[2].replace(',', '')}{cents}"

    text = text.replace("\u2019", "'")
    text = _DATE.sub(iso_date, text)
    text = _AMOUNT.sub(plain_amount, text)
    return " ".join(text.lower().split())


def contains(text: str, phrase: str) -> bool:
    """Whole-word match, so "$30" does not match "$300" or "$30.50"."""
    return re.search(rf"(?<![\w.]){re.escape(phrase)}(?!\w|\.\d)", text) is not None


def is_subset(expected: dict[str, Any], actual: Any) -> bool:
    if not isinstance(actual, dict):
        return False
    for key, value in expected.items():
        if key not in actual:
            return False
        if isinstance(value, dict):
            if not is_subset(value, actual[key]):
                return False
        elif actual[key] != value:
            return False
    return True


def found_in(expected: dict[str, Any], value: Any) -> bool:
    """True if any object nested anywhere in value contains expected."""
    if is_subset(expected, value):
        return True
    match value:
        case dict():
            return any(found_in(expected, item) for item in value.values())
        case list():
            return any(found_in(expected, item) for item in value)
        case _:
            return False


def leaves(value: Any) -> list[Any]:
    """Every value nested anywhere in value that is not a dict or a list."""
    match value:
        case dict():
            return [leaf for item in value.values() for leaf in leaves(item)]
        case list():
            return [leaf for item in value for leaf in leaves(item)]
        case _:
            return [value]


def describe(fact: dict[str, Any]) -> str:
    return json.dumps(fact, separators=(", ", ": "))


def routing_checks(scenario: dict[str, Any], collaborators: list[str]) -> list[Check]:
    """Check that the run called the expected collaborators and none forbidden."""
    called = set(collaborators)
    return [
        Check("routing", f"calls {name}", name in called)
        for name in scenario.get("expected_collaborators", [])
    ] + [
        Check("routing", f"does not call {name}", name not in called)
        for name in scenario.get("forbidden_collaborators", [])
    ]


def score(scenario: dict[str, Any], result: AgentResult, year: int) -> list[Check]:
    answer = normalize(result["answer"], year)
    tool_results = [call["result"] for call in result["tool_calls"]]
    checks = [
        Check(
            "answer",
            fact["fact"],
            any(contains(answer, normalize(v, year)) for v in fact["any_of"]),
        )
        for fact in scenario["answer_facts"]
    ]
    checks += [
        Check("trace", describe(fact), found_in(fact, tool_results))
        for fact in scenario["trace_facts"]
    ]
    checks += [
        Check("must_not_appear", phrase, not contains(answer, normalize(phrase, year)))
        for phrase in scenario["must_not_appear"]
    ]
    values = [normalize(str(leaf), year) for leaf in leaves(tool_results)]
    checks += [
        Check(
            "trace_must_not",
            phrase,
            not any(contains(value, normalize(phrase, year)) for value in values),
        )
        for phrase in scenario.get("trace_must_not", [])
    ]
    checks += routing_checks(scenario, result.get("collaborators", []))
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3, help="runs per scenario")
    parser.add_argument(
        "--scenario", action="append", help="scenario ID to run, repeatable"
    )
    parser.add_argument(
        "--persona",
        choices=["customer", "staff"],
        default="customer",
        help="run only this persona's scenarios",
    )
    args = parser.parse_args()

    settings = load_settings()
    year = settings.demo_as_of.year
    scenarios = [s for s in load_scenarios() if persona(s) == args.persona]
    if args.scenario:
        scenarios = [s for s in scenarios if s["id"] in args.scenario]

    started_at = datetime.now(UTC)
    runs: list[dict[str, Any]] = []
    for scenario in scenarios:
        for run in range(1, args.runs + 1):
            result = run_agent(scenario["prompt"], settings)
            checks = score(scenario, result, year)
            passed = all(check.passed for check in checks)
            print(
                f"{scenario['id']} run {run}/{args.runs}: {'PASS' if passed else 'FAIL'}"
            )
            for check in checks:
                if not check.passed:
                    print(f"    missed {check.kind}: {check.fact}")
            if not passed:
                print(f"    answer: {result['answer']}")
            runs.append(
                {
                    "scenario": scenario["id"],
                    "run": run,
                    "prompt": scenario["prompt"],
                    "passed": passed,
                    "answer": result["answer"],
                    "checks": [asdict(check) for check in checks],
                    "tool_calls": result["tool_calls"],
                }
            )

    summary = {
        s["id"]: sum(r["passed"] for r in runs if r["scenario"] == s["id"])
        for s in scenarios
    }
    print("\nScenario  Passed")
    for scenario in scenarios:
        print(
            f"{scenario['id']:<9} {summary[scenario['id']]}/{args.runs}  {scenario['title']}"
        )
    for scenario in scenarios:
        for item in scenario.get("manual_review", []):
            print(f"Manual review, {scenario['id']}: {item}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"eval-{started_at:%Y%m%dT%H%M%SZ}.json"
    report = {
        "started_at": started_at.isoformat(),
        "chat_model": settings.chat_model,
        "embedding_model": settings.embedding_model,
        "demo_as_of": settings.demo_as_of.isoformat(),
        "customer_id": settings.demo_customer_id,
        "runs_per_scenario": args.runs,
        "passed": all(r["passed"] for r in runs),
        "summary": summary,
        "runs": runs,
    }
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Saved {path.relative_to(EVAL_DIR.parent)}")
    if not report["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

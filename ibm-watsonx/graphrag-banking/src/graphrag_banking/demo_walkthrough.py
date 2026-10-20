"""Run the watsonx Orchestrate demo walkthrough from the README, step by step.

Each step prints a header with its number and title, where it runs and the exact
command. The command's output follows, then a "Captured" line for each value a
later step uses. The banking_support thread ID from step 2 finds the trace in
step 3, the trace ID dumps it in step 4, and step 5 summarises that dump.

Steps:
  1  Scenario A on the baseline agent
  2  Scenario A on banking_support
  3  Find the trace for the step 2 thread
  4  Dump the trace's observations to JSON
  5  Summarise the model calls in the trace
  6  Scenarios B to D on banking_support
  7  Run and score scenarios A to D

It needs the orchestrate CLI with an active environment, which ``make wxo-env``
sets up, and the ADK installed with ``uv tool install``. Commands run from the
project root. The trace dump and the scoring runs go to ``--out-dir``.

Usage:
  uv run demo-walkthrough
  uv run demo-walkthrough --skip-scoring
  uv run demo-walkthrough --steps 3-5 --thread-id <banking_support thread ID>
"""

import argparse
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlparse

import yaml
from dotenv import dotenv_values

from graphrag_banking.config import EVAL_DIR, PROJECT_ROOT

logger = logging.getLogger(__name__)

SCENARIOS_PATH = EVAL_DIR / "scenarios.yaml"
# Relative to the project root, which is the working directory for every command.
EVAL_SCRIPTS = "eval/eval-scripts"
ADK_TOOL_NAME = "ibm-watsonx-orchestrate"
DEFAULT_AGENT = "banking_support"
DEFAULT_BASELINE = "banking_baseline"
SCORED_SCENARIOS = "A,B,C,D"
TRACE_SEARCH_WINDOW = "30m"
TRACE_SEARCH_ATTEMPTS = 6
TRACE_SEARCH_WAIT_SECONDS = 15
# /observations allows four requests per minute, so each re-dump waits 20s.
TRACE_DUMP_ATTEMPTS = 4
TRACE_DUMP_WAIT_SECONDS = 20
MAX_WIDTH = 100
OUTPUT_INDENT = "  "

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_THREAD_ID = re.compile(rf"Thread ID:\s*({_UUID})")
_TRACE_ROW = re.compile(r"│[^│]*│\s*([0-9a-f]{32})\s*│")
_OBSERVATION_COUNT = re.compile(r"(\d+) observations ->")
_SAVED_REPORT = re.compile(r"Saved (\S+\.json)")
_RUN_LINE = re.compile(r": (\w+) in [\d.]+s, \d+ tool calls")
# ADK lines that add nothing for a viewer. The export tip points at a command
# that fails on every published ADK version.
_NOISE = (
    "is_async flag",
    "Non-async agent",
    "Searching for traces",
    "traces export --trace-id",
)
_REQUIRES_AUTH_HINT = (
    "If the error mentions authentication or a token, run `make wxo-env` to log "
    "in again. The login lasts two hours."
)


class StepError(RuntimeError):
    """A step failed or its output could not be parsed."""


class Where(Enum):
    """Where a step's work happens."""

    LOCAL = "local"
    CLOUD = "cloud"
    LOCAL_TO_CLOUD = "local_to_cloud"


@dataclass(frozen=True)
class Target:
    """The active orchestrate environment that every command talks to."""

    env_name: str
    host: str
    is_cloud: bool

    def label(self, where: Where) -> str:
        """The headline for a step's Where line."""
        if where is Where.LOCAL:
            return "LOCAL"
        if where is Where.CLOUD:
            if self.is_cloud:
                return f"WATSONX ORCHESTRATE CLOUD  {self.host}"
            return f"LOCAL ORCHESTRATE DEVELOPER EDITION  {self.host}"
        api = "Orchestrate cloud API" if self.is_cloud else "local Orchestrate API"
        return f"LOCAL → calls {api}  {self.host}"


class Console:
    """Prints the walkthrough with ANSI styling when stdout is a terminal."""

    _CODES: ClassVar[dict[str, str]] = {
        "bold": "1",
        "dim": "2",
        "red": "31",
        "green": "32",
        "yellow": "33",
        "blue": "34",
        "magenta": "35",
        "cyan": "36",
        "reverse": "7",
    }

    def __init__(self, color: bool, width: int) -> None:
        self.color = color
        self.width = width

    def paint(self, text: str, *styles: str) -> str:
        if not self.color or not styles:
            return text
        codes = ";".join(self._CODES[s] for s in styles)
        return f"\x1b[{codes}m{text}\x1b[0m"

    def banner(self, title: str, rows: list[tuple[str, str]]) -> None:
        bar = self.paint("═" * self.width, "cyan")
        print(f"\n{bar}\n  {self.paint(title, 'bold', 'cyan')}\n{bar}")
        self._rows(rows)

    def step_header(self, number: int, total: int, title: str) -> None:
        bar = self.paint("━" * self.width, "blue")
        tag = self.paint(f" STEP {number} of {total} ", "bold", "reverse", "blue")
        print(f"\n\n{bar}\n  {tag}  {self.paint(title, 'bold')}\n{bar}")

    def sub_header(self, label: str, title: str) -> None:
        text = f"── {label}  {title} "
        rule = "─" * max(self.width - len(text) - 2, 4)
        print(f"\n  {self.paint(text + rule, 'bold', 'blue')}")

    def where_and_command(
        self, target: Target, where: Where, detail: str, command: list[str]
    ) -> None:
        """Print the Where and Command lines. ``command`` holds quoted words."""
        style = "magenta" if where is Where.CLOUD and target.is_cloud else "green"
        label = self.paint(target.label(where), "bold", style)
        print(f"  {self.paint('Where  ', 'bold')}  {label}")
        self._wrapped(detail, "dim")
        for number, line in enumerate(self._command_lines(command)):
            name = "Command" if number == 0 else ""
            print(f"  {self.paint(f'{name:<7}', 'bold')}  {self.paint(line, 'yellow')}")
        self.rule("output")

    def _command_lines(self, words: list[str]) -> list[str]:
        """Break a command between words, with a backslash at each line end."""
        room = self.width - 13
        lines = [""]
        for word in words:
            if lines[-1] and len(lines[-1]) + len(word) + 3 > room:
                lines[-1] += " \\"
                lines.append("  ")
            lines[-1] += f"{' ' if lines[-1].strip() else ''}{word}"
        return lines

    def rule(self, label: str) -> None:
        text = f" {label} "
        left = "─" * 4
        right = "─" * max(self.width - len(text) - len(left) - 2, 4)
        print(f"  {self.paint(left + text + right, 'dim')}")

    def output(self, line: str) -> None:
        print(f"{OUTPUT_INDENT}{line}", flush=True)

    def captured(self, name: str, value: str) -> None:
        arrow = self.paint("➜ Captured", "bold", "green")
        print(f"\n  {arrow}  {name}: {self.paint(value, 'bold')}")

    def note(self, text: str) -> None:
        self._wrapped(text, "dim", indent="  ")

    def _rows(self, rows: list[tuple[str, str]]) -> None:
        pad = max(len(name) for name, _ in rows)
        for name, value in rows:
            print(f"  {self.paint(name.ljust(pad), 'bold')}  {value}")

    def _wrapped(self, text: str, style: str, indent: str = " " * 11) -> None:
        for line in textwrap.wrap(text, self.width - len(indent)):
            print(f"{indent}{self.paint(line, style)}")


@dataclass
class Captured:
    """Values one step hands to a later step."""

    baseline_thread_id: str | None = None
    thread_id: str | None = None
    trace_id: str | None = None
    trace_file: Path | None = None
    more_threads: dict[str, str] = field(default_factory=dict)
    runs_dir: Path | None = None
    score_report: str | None = None
    score_passed: bool | None = None


@dataclass
class Walkthrough:
    """Shared state for the steps."""

    console: Console
    target: Target
    out_dir: Path
    agent: str
    baseline_agent: str
    prompts: dict[str, str]
    captured: Captured
    total_steps: int
    _adk_python: Path | None = None

    @property
    def adk_python(self) -> Path:
        """The ADK's own Python, which the eval scripts need."""
        if self._adk_python is None:
            tool_dir = _run_quiet(["uv", "tool", "dir"]).strip()
            path = Path(tool_dir) / ADK_TOOL_NAME / "bin" / "python"
            if not path.exists():
                raise StepError(
                    f"The ADK's Python is not at {path}. Install the ADK with "
                    "`uv tool install ibm-watsonx-orchestrate --with neo4j "
                    "--with openai`."
                )
            self._adk_python = path
        return self._adk_python

    def run(
        self, cmd: list[str], *, stdin: str | None = None, check: bool = True
    ) -> tuple[int, str]:
        """Run a command from the project root and stream its cleaned output.

        Returns the exit status and the output without ANSI codes. With
        ``check``, a non-zero exit status raises StepError.
        """
        lines: list[str] = []
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=PROJECT_ROOT,
                env=self._child_env(),
                stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as e:
            raise StepError(f"Command not found: {cmd[0]}") from e
        with proc:
            if stdin is not None and proc.stdin is not None:
                proc.stdin.write(stdin)
                proc.stdin.close()
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = _clean(raw)
                if line is None:
                    continue
                lines.append(line)
                self.console.output(line)
        output = "\n".join(lines)
        if check and proc.returncode != 0:
            raise StepError(
                f"`{Path(cmd[0]).name}` exited with status {proc.returncode}. "
                f"{_REQUIRES_AUTH_HINT}"
            )
        return proc.returncode, output

    def run_captured(self, cmd: list[str]) -> tuple[int, str]:
        """Run a command from the project root without printing its output."""
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            env=self._child_env(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        lines = [
            line
            for raw in (result.stdout + result.stderr).splitlines()
            if (line := _clean(raw)) is not None
        ]
        return result.returncode, "\n".join(lines)

    def _child_env(self) -> dict[str, str]:
        # Rich in the ADK sizes its boxes from COLUMNS.
        columns = self.console.width - len(OUTPUT_INDENT)
        return {**os.environ, "COLUMNS": str(columns)}


@dataclass(frozen=True)
class Step:
    number: int
    title: str
    run: Callable[[Walkthrough], None]


def _clean(raw: str) -> str | None:
    """Strip ANSI codes and spinner frames. None means drop the line."""
    line = _ANSI.sub("", raw.rstrip("\n")).split("\r")[-1].rstrip()
    if any(noise in line for noise in _NOISE):
        return None
    return line


def _run_quiet(cmd: list[str]) -> str:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, cwd=PROJECT_ROOT
        )
    except FileNotFoundError as e:
        raise StepError(f"Command not found: {cmd[0]}") from e
    except subprocess.CalledProcessError as e:
        raise StepError(f"`{shlex.join(cmd)}` failed: {e.stderr.strip()}") from e
    return result.stdout


def _shell(cmd: list[str]) -> list[str]:
    """Quote each word for display, with prompts in double quotes as in the README."""
    parts = []
    for arg in cmd:
        if re.fullmatch(r"[\w@%+=:,./-]+", arg):
            parts.append(arg)
        elif not any(c in arg for c in '"$`\\!'):
            parts.append(f'"{arg}"')
        else:
            parts.append(shlex.quote(arg))
    return parts


def _relative(path: Path) -> str:
    """A path relative to the project root when it is inside it."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _parse_one(pattern: re.Pattern[str], output: str, what: str, source: str) -> str:
    if match := pattern.search(output):
        return match[1]
    raise StepError(f"Could not find the {what} in the output of {source}.")


# ---- Steps --------------------------------------------------------------------


def _chat_ask(wt: Walkthrough, agent: str, prompt: str) -> str:
    """Send one prompt with `orchestrate chat ask` and return the thread ID."""
    cmd = ["orchestrate", "chat", "ask", "-n", agent, "-r", prompt]
    wt.console.where_and_command(
        wt.target,
        Where.CLOUD,
        f"The {agent} agent runs in Orchestrate with its model, tools and "
        "knowledge base. The "
        "local CLI sends the prompt and prints the reasoning trace and answer. "
        "`echo q` ends the chat after the first answer.",
        ["echo", "q", "|", *_shell(cmd)],
    )
    _, output = wt.run(cmd, stdin="q\n")
    thread_id = _parse_one(_THREAD_ID, output, "thread ID", "orchestrate chat ask")
    wt.console.captured(f"{agent} thread ID", thread_id)
    return thread_id


def step_baseline_a(wt: Walkthrough) -> None:
    wt.captured.baseline_thread_id = _chat_ask(wt, wt.baseline_agent, wt.prompts["A"])
    wt.console.note(
        "The baseline only searches the policy knowledge base. It cannot see the "
        "customer's transactions, so it cannot know the wire is held."
    )


def step_support_a(wt: Walkthrough) -> None:
    wt.captured.thread_id = _chat_ask(wt, wt.agent, wt.prompts["A"])
    wt.console.note("Step 3 uses this thread ID to find the trace.")


def step_find_trace(wt: Walkthrough) -> None:
    thread_id = wt.captured.thread_id
    assert thread_id is not None
    cmd = [
        "orchestrate",
        "observability",
        "traces",
        "search",
        "--last",
        TRACE_SEARCH_WINDOW,
        "--session-id",
        thread_id,
    ]
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL_TO_CLOUD,
        "The local CLI searches Orchestrate's observability API. A trace's "
        "session ID is the chat's thread ID.",
        _shell(cmd),
    )
    for attempt in range(1, TRACE_SEARCH_ATTEMPTS + 1):
        status, output = wt.run_captured(cmd)
        trace_ids = _TRACE_ROW.findall(output)
        if trace_ids:
            break
        if status != 0 and "No traces found" not in output:
            for line in output.splitlines():
                wt.console.output(line)
            raise StepError(
                f"The trace search exited with status {status}. {_REQUIRES_AUTH_HINT}"
            )
        if attempt == TRACE_SEARCH_ATTEMPTS:
            for line in output.splitlines():
                wt.console.output(line)
            raise StepError(
                f"No trace for thread {thread_id} after {attempt} tries. Traces "
                "can take a few minutes to appear. Run this step again later "
                f"with `--steps 3-5 --thread-id {thread_id}`."
            )
        logger.info(
            "%sNo trace yet. Traces can take a minute to appear. "
            "Waiting %ds before try %d of %d.",
            OUTPUT_INDENT,
            TRACE_SEARCH_WAIT_SECONDS,
            attempt + 1,
            TRACE_SEARCH_ATTEMPTS,
        )
        time.sleep(TRACE_SEARCH_WAIT_SECONDS)
    for line in output.splitlines():
        wt.console.output(line)
    if len(trace_ids) > 1:
        wt.console.note(
            f"Found {len(trace_ids)} traces for this thread. Using the newest one."
        )
    wt.captured.trace_id = trace_ids[0]
    wt.console.captured("trace ID", wt.captured.trace_id)


def step_dump_trace(wt: Walkthrough) -> None:
    trace_id = wt.captured.trace_id
    assert trace_id is not None
    trace_file = wt.out_dir / "trace.json"
    cmd = [
        str(wt.adk_python),
        "-I",
        f"{EVAL_SCRIPTS}/traces.py",
        "get",
        trace_id,
        str(trace_file),
    ]
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL_TO_CLOUD,
        "traces.py runs locally with the ADK's Python and reads the trace's "
        "observations from Orchestrate's observability API. That API allows four "
        "requests per minute, and traces.py waits out a rate limit.",
        _shell(cmd),
    )
    for attempt in range(1, TRACE_DUMP_ATTEMPTS + 1):
        _, output = wt.run(cmd)
        count = _parse_one(_OBSERVATION_COUNT, output, "observation count", "traces.py")
        generations = _generations(_read_trace(trace_file))
        if _has_answer(generations):
            break
        if attempt == TRACE_DUMP_ATTEMPTS:
            wt.console.note(
                "The trace still has no model call that wrote the answer. Step 5 "
                "shows the model calls recorded so far."
            )
            break
        logger.info(
            "%sThe trace is still filling in: %d model calls so far and none wrote "
            "the answer yet. Waiting %ds before try %d of %d.",
            OUTPUT_INDENT,
            len(generations),
            TRACE_DUMP_WAIT_SECONDS,
            attempt + 1,
            TRACE_DUMP_ATTEMPTS,
        )
        time.sleep(TRACE_DUMP_WAIT_SECONDS)
    wt.captured.trace_file = trace_file
    wt.console.captured("trace file", f"{trace_file} · {count} observations")


def _read_trace(trace_file: Path) -> list[dict[str, Any]]:
    try:
        observations = json.loads(trace_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise StepError(f"Could not read the trace dump {trace_file}: {e}") from e
    if not isinstance(observations, list):
        raise StepError(f"{trace_file} does not hold a list of observations.")
    return observations


def _generations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The trace's model calls, in start order."""
    return [o for o in observations if o.get("type") == "GENERATION"]


def _output_of(generation: dict[str, Any]) -> dict[str, Any]:
    output = generation.get("output")
    return output if isinstance(output, dict) else {}


def _has_answer(generations: list[dict[str, Any]]) -> bool:
    """True when the last model call wrote an answer instead of calling a tool."""
    return bool(generations) and not _output_of(generations[-1]).get("tool_calls")


def _tool_calls(output: dict[str, Any]) -> list[str]:
    return [
        f"{call.get('name')} {json.dumps(call.get('args'), separators=(',', ':'))}"
        for call in output.get("tool_calls") or []
    ]


def step_summarise_trace(wt: Walkthrough) -> None:
    trace_file = wt.captured.trace_file
    assert trace_file is not None
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL,
        "This script reads the trace file and prints one row per model call, "
        "like the README's jq command.",
        [f"summarise the GENERATION observations in {trace_file}"],
    )
    generations = _generations(_read_trace(trace_file))
    if not generations:
        raise StepError(
            f"{trace_file} has no GENERATION observations. The trace may still "
            "be filling in. Wait a minute and run "
            f"`--steps 4-5 --trace-id {wt.captured.trace_id}`."
        )

    header = ("#", "Model", "In tok", "Out tok", "Latency")
    rows = [
        (
            str(number),
            str(gen.get("model") or "?"),
            f"{gen.get('inputTokens') or 0:,}",
            f"{gen.get('outputTokens') or 0:,}",
            f"{gen.get('latency') or 0:,} ms",
        )
        for number, gen in enumerate(generations, start=1)
    ]
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]

    def cells(row: tuple[str, ...]) -> str:
        return "  ".join(
            cell.ljust(width) if i < 2 else cell.rjust(width)
            for i, (cell, width) in enumerate(zip(row, widths, strict=True))
        )

    wt.console.output(wt.console.paint(cells(header), "bold"))
    for row, gen in zip(rows, generations, strict=True):
        wt.console.output(cells(row))
        calls = _tool_calls(_output_of(gen))
        for call in calls or ["writes the answer, no tool call"]:
            wt.console.output(
                f"{' ' * (widths[0] + 2)}{wt.console.paint('→', 'cyan')} {call}"
            )
    total_in = sum(g.get("inputTokens") or 0 for g in generations)
    total_out = sum(g.get("outputTokens") or 0 for g in generations)
    total_ms = sum(g.get("latency") or 0 for g in generations)
    wt.console.output(
        wt.console.paint(
            f"Total: {len(generations)} model calls, {total_in:,} input tokens, "
            f"{total_out:,} output tokens, {total_ms:,} ms of model time",
            "dim",
        )
    )

    wt.console.output("")
    wt.console.output(wt.console.paint("Reasoning behind each model call", "bold"))
    for number, gen in enumerate(generations, start=1):
        kwargs = _output_of(gen).get("additional_kwargs") or {}
        reasoning = kwargs.get("reasoning") or "no reasoning text"
        lines = textwrap.wrap(
            " ".join(str(reasoning).split()),
            wt.console.width - len(OUTPUT_INDENT) - 4,
        )
        for index, line in enumerate(lines):
            wt.console.output(f"{f'{number}.' if index == 0 else '':<4}{line}")

    tool_count = sum(len(_output_of(g).get("tool_calls") or []) for g in generations)
    wt.console.captured(
        "model calls", f"{len(generations)} model calls, {tool_count} tool calls"
    )


def step_more_scenarios(wt: Walkthrough) -> None:
    for number, scenario_id in enumerate(("B", "C", "D"), start=1):
        wt.console.sub_header(
            f"6.{number}", f"Scenario {scenario_id} on {wt.agent}, in a new chat"
        )
        thread_id = _chat_ask(wt, wt.agent, wt.prompts[scenario_id])
        wt.captured.more_threads[scenario_id] = thread_id


def step_score(wt: Walkthrough) -> None:
    runs_dir = wt.out_dir / "runs"
    wt.console.sub_header("7.1", f"Send scenarios {SCORED_SCENARIOS} to {wt.agent}")
    run_cmd = [
        str(wt.adk_python),
        "-I",
        f"{EVAL_SCRIPTS}/run_agent.py",
        str(runs_dir),
        "--agents",
        wt.agent,
        "--scenarios",
        SCORED_SCENARIOS,
    ]
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL_TO_CLOUD,
        "run_agent.py runs locally with the ADK's Python. It sends each prompt to "
        "the agent through the Orchestrate API, where the agent answers, and saves "
        "each answer and tool response as JSON.",
        _shell(run_cmd),
    )
    _, output = wt.run(run_cmd)
    statuses = _RUN_LINE.findall(output)
    saved = sorted(runs_dir.glob("*.json"))
    if not saved:
        raise StepError(f"run_agent.py saved no runs in {runs_dir}.")
    wt.captured.runs_dir = runs_dir
    completed = sum(s == "completed" for s in statuses)
    wt.console.captured(
        "runs", f"{len(saved)} saved to {runs_dir} · {completed} completed"
    )

    wt.console.sub_header("7.2", "Score the saved answers")
    score_cmd = ["uv", "run", "python", f"{EVAL_SCRIPTS}/score.py", str(runs_dir)]
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL,
        "score.py runs locally with the project's Python. It applies the same "
        "checks as `make eval` and writes a report to eval/results/.",
        _shell(score_cmd),
    )
    status, output = wt.run(score_cmd, check=False)
    report = _SAVED_REPORT.search(output)
    if report is None:
        raise StepError(f"score.py exited with status {status} and saved no report.")
    wt.captured.score_report = report[1]
    wt.captured.score_passed = status == 0
    verdict = "all checks passed" if status == 0 else "some checks failed"
    wt.console.captured("score report", f"{report[1]} · {verdict}")


STEPS = [
    Step(1, "Scenario A on the baseline agent", step_baseline_a),
    Step(2, "Scenario A on banking_support", step_support_a),
    Step(3, "Find the trace for the banking_support thread", step_find_trace),
    Step(4, "Dump the trace's observations to JSON", step_dump_trace),
    Step(5, "Summarise the model calls in the trace", step_summarise_trace),
    Step(6, "Scenarios B to D on banking_support", step_more_scenarios),
    Step(7, f"Run and score scenarios {SCORED_SCENARIOS}", step_score),
]


# ---- Setup --------------------------------------------------------------------


def parse_steps(value: str) -> list[int]:
    """Parse "1,3-5" into [1, 3, 4, 5]."""
    numbers: set[int] = set()
    valid = {s.number for s in STEPS}
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                start, end = (int(p) for p in part.split("-", 1))
                numbers.update(range(start, end + 1))
            else:
                numbers.add(int(part))
        except ValueError as e:
            raise argparse.ArgumentTypeError(f"Bad step range: {part}") from e
    if not numbers or not numbers <= valid:
        raise argparse.ArgumentTypeError(
            f"Steps must be between {min(valid)} and {max(valid)}, got {value}"
        )
    return sorted(numbers)


def load_prompts() -> dict[str, str]:
    with SCENARIOS_PATH.open(encoding="utf-8") as f:
        scenarios = yaml.safe_load(f)["scenarios"]
    return {s["id"]: s["prompt"] for s in scenarios}


def find_target() -> Target:
    """Read the active orchestrate environment and the instance host."""
    if shutil.which("orchestrate") is None:
        raise StepError(
            "The orchestrate CLI is not on PATH. Install the ADK with "
            "`uv tool install ibm-watsonx-orchestrate --with neo4j --with openai`."
        )
    active = [
        line.split()
        for line in _ANSI.sub(
            "", _run_quiet(["orchestrate", "env", "list"])
        ).splitlines()
        if "(active)" in line
    ]
    if not active or len(active[0]) < 2:
        raise StepError("No active orchestrate environment. Run `make wxo-env`.")
    env_name, env_url = active[0][0], active[0][1].rstrip("…")
    env_host = urlparse(env_url).netloc or env_url
    is_cloud = not any(h in env_host for h in ("localhost", "127.0.0.1"))

    # Only these two keys are read from .env. The API key is never touched.
    values = dotenv_values(PROJECT_ROOT / ".env")
    wo_env_name = os.environ.get("WO_ENV_NAME") or values.get("WO_ENV_NAME")
    wo_url = os.environ.get("WO_INSTANCE_URL") or values.get("WO_INSTANCE_URL")
    host = env_host
    if is_cloud and wo_url and env_name == wo_env_name:
        host = urlparse(wo_url).hostname or env_host
    elif is_cloud and wo_env_name and env_name != wo_env_name:
        logger.warning(
            "The active orchestrate environment is %s, not WO_ENV_NAME %s from "
            ".env. Commands go to the active environment. Run `make wxo-env` to "
            "switch.",
            env_name,
            wo_env_name,
        )
    return Target(env_name=env_name, host=host, is_cloud=is_cloud)


def check_inputs(selected: list[int], captured: Captured) -> None:
    """Fail before any cloud call when a step's input will be missing."""
    chosen = set(selected)
    if 3 in chosen and 2 not in chosen and captured.thread_id is None:
        raise StepError(
            "Step 3 needs the banking_support thread ID. Include step 2 or pass "
            "--thread-id."
        )
    if 4 in chosen and 3 not in chosen and captured.trace_id is None:
        raise StepError("Step 4 needs a trace ID. Include step 3 or pass --trace-id.")
    if 5 in chosen and 4 not in chosen:
        raise StepError("Step 5 reads the trace file from step 4. Include step 4.")


def print_summary(wt: Walkthrough, elapsed: float) -> None:
    c = wt.captured
    rows = [
        ("Baseline thread A", c.baseline_thread_id),
        (f"{wt.agent} thread A", c.thread_id),
        ("Trace ID", c.trace_id),
        ("Trace file", str(c.trace_file) if c.trace_file else None),
        *((f"{wt.agent} thread {k}", v) for k, v in c.more_threads.items()),
        ("Scoring runs", str(c.runs_dir) if c.runs_dir else None),
        ("Score report", c.score_report),
    ]
    shown = [(name, value) for name, value in rows if value]
    if c.score_passed is not None:
        verdict = (
            wt.console.paint("PASS", "bold", "green")
            if c.score_passed
            else wt.console.paint("FAIL, see step 7", "bold", "red")
        )
        shown.append(("Score", verdict))
    shown.append(("Elapsed", f"{elapsed:.0f}s"))
    wt.console.banner("Walkthrough complete: captured values", shown)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--steps",
        type=parse_steps,
        default=[s.number for s in STEPS],
        help='Steps to run, such as "1-5" or "2,3,4,5". Default: all.',
    )
    parser.add_argument(
        "--skip-scoring",
        action="store_true",
        help="Skip step 7, which sends four more prompts and takes a minute or two.",
    )
    parser.add_argument("--agent", default=DEFAULT_AGENT, help="Agent with tools.")
    parser.add_argument(
        "--baseline-agent", default=DEFAULT_BASELINE, help="Knowledge-base agent."
    )
    parser.add_argument(
        "--thread-id", help="banking_support thread ID for step 3 without step 2."
    )
    parser.add_argument("--trace-id", help="Trace ID for step 4 without step 3.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Where to write the trace dump and scoring runs. Default: a new "
        "temporary folder.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    width = min(shutil.get_terminal_size((MAX_WIDTH, 24)).columns, MAX_WIDTH)
    console = Console(color=sys.stdout.isatty(), width=width)
    selected = [n for n in args.steps if not (args.skip_scoring and n == 7)]
    captured = Captured(thread_id=args.thread_id, trace_id=args.trace_id)

    started = time.monotonic()
    try:
        check_inputs(selected, captured)
        target = find_target()
        if args.out_dir is None:
            out_dir = Path(tempfile.mkdtemp(prefix="demo-walkthrough-"))
        else:
            out_dir = args.out_dir.resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
        wt = Walkthrough(
            console=console,
            target=target,
            out_dir=out_dir,
            agent=args.agent,
            baseline_agent=args.baseline_agent,
            prompts=load_prompts(),
            captured=captured,
            total_steps=len(STEPS),
        )
        where = "cloud" if target.is_cloud else "local developer edition"
        console.banner(
            "watsonx Orchestrate demo walkthrough",
            [
                ("Environment", f"{target.env_name} · {where} · {target.host}"),
                ("Agents", f"{args.baseline_agent}, {args.agent}"),
                ("Steps", ", ".join(str(n) for n in selected)),
                ("Output folder", _relative(out_dir)),
            ],
        )
        for step in STEPS:
            if step.number not in selected:
                continue
            title = step.title.replace("banking_support", args.agent)
            console.step_header(step.number, wt.total_steps, title)
            step.run(wt)
    except StepError as e:
        print(f"\n  {console.paint('✖ Failed', 'bold', 'red')}  {e}", file=sys.stdout)
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n  {console.paint('Interrupted', 'bold', 'yellow')}")
        sys.exit(130)
    print_summary(wt, time.monotonic() - started)
    if wt.captured.score_passed is False:
        sys.exit(1)


if __name__ == "__main__":
    main()

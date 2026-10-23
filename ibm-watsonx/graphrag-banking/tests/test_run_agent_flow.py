"""Unit tests for run_agent.py's --referral-flow helpers. None need a tenant.

run_agent.py imports the ADK, which the project environment does not have, so
the ADK modules are stubbed before the import. The message shapes follow IBM's
async flow tutorial and the ADK's FormWidget. They are not yet checked against
a tenant.
"""

import sys
import types
from typing import Any

import pytest

from graphrag_banking.config import EVAL_DIR

ADK_MODULES = {
    "ibm_watsonx_orchestrate.client.agents.agent_client": ["AgentClient"],
    "ibm_watsonx_orchestrate.client.chat.run_client": ["RunClient"],
    "ibm_watsonx_orchestrate.client.threads.threads_client": ["ThreadsClient"],
    "ibm_watsonx_orchestrate.client.utils": ["instantiate_client"],
    "ibm_watsonx_orchestrate_clients.common.base_client": ["ClientAPIException"],
}
for module_name, names in ADK_MODULES.items():
    if module_name not in sys.modules:
        module = types.ModuleType(module_name)
        for name in names:
            setattr(module, name, type(name, (Exception,), {}))
        sys.modules[module_name] = module

sys.path.insert(0, str(EVAL_DIR / "eval-scripts"))
import run_agent

REFERRAL_TEXT = (
    "Referral REF-0001 was sent to the fraud team and assigned to Sam Price. "
    "Do not tell the client about this referral or the fraud review. "
    "Policy AML-NO-TIPOFF forbids tipping off the client."
)


def _text(message_id: str, text: str, role: str = "assistant") -> dict[str, Any]:
    return {
        "id": message_id,
        "role": role,
        "content": [{"response_type": "text", "text": text}],
    }


def _form(message_id: str, form_data: object, form_id: str = "f1") -> dict:
    return {
        "id": message_id,
        "role": "assistant",
        "content": [
            {
                "id": form_id,
                "response_type": "forms",
                "name": "confirm_form",
                "json_schema": {"properties": {"summary": {"type": "string"}}},
                "ui_schema": {"ui:submitButtonOptions": {"submitText": "Confirm"}},
                "form_data": form_data,
            }
        ],
    }


CONFIRM_DATA = {
    "application_id": "APP-1001",
    "summary": "Shared identifiers and circular deposits.",
    "red_flags": ["FRAUD-SHARED-ID", "FRAUD-CIRCULAR-FLOW"],
}


class FakeThreads:
    """Returns the next list of thread messages on each call, then the last."""

    def __init__(self, *snapshots: list[dict[str, Any]], wrap: bool = False):
        self.snapshots = list(snapshots)
        self.wrap = wrap

    def get_thread_messages(self, thread_id: str) -> object:
        msgs = self.snapshots.pop(0) if len(self.snapshots) > 1 else self.snapshots[0]
        return {"data": msgs} if self.wrap else msgs


class FakeRuns:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def create_run(self, **kwargs: Any) -> dict[str, Any]:
        self.sent.append(kwargs)
        return {"run_id": "run-confirm", "thread_id": kwargs["thread_id"]}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_agent.time, "sleep", lambda _: None)
    monkeypatch.setattr(run_agent, "MAX_POLLS", 5)


def test_form_of_finds_the_form_item() -> None:
    message = _form("m1", CONFIRM_DATA)
    assert run_agent.form_of(message)["name"] == "confirm_form"


def test_form_of_ignores_text_and_user_messages() -> None:
    assert run_agent.form_of(_text("m1", "The flow has started.")) is None
    user = _form("m2", CONFIRM_DATA) | {"role": "user"}
    assert run_agent.form_of(user) is None
    assert run_agent.form_of({"role": "assistant", "content": "plain"}) is None


def test_confirm_payload_presses_submit_with_the_form_data() -> None:
    form = run_agent.form_of(_form("m1", CONFIRM_DATA))
    assert run_agent.confirm_payload(form) == [
        {
            "response_type": "form_operation",
            "form_operation": "submit",
            "form_data": CONFIRM_DATA,
            "id": "f1",
        }
    ]


def test_confirm_payload_without_an_id_or_data() -> None:
    assert run_agent.confirm_payload({"response_type": "forms"}) == [
        {"response_type": "form_operation", "form_operation": "submit", "form_data": {}}
    ]


def test_flow_text_reads_text_items() -> None:
    assert run_agent.flow_text(_text("m1", REFERRAL_TEXT)) == REFERRAL_TEXT


@pytest.mark.parametrize("form_data", [{"sent": REFERRAL_TEXT}, '{"sent": "%s"}'])
def test_flow_text_reads_output_only_form_data(form_data: object) -> None:
    if isinstance(form_data, str):
        form_data = form_data % REFERRAL_TEXT
    assert REFERRAL_TEXT in run_agent.flow_text(_form("m1", form_data))


def test_flow_text_reads_nested_lists() -> None:
    text = run_agent.flow_text(_form("m1", CONFIRM_DATA))
    assert "FRAUD-CIRCULAR-FLOW" in text
    assert "APP-1001" in text


def test_referral_ended_on_each_end_step() -> None:
    assert run_agent.referral_ended(_text("m1", REFERRAL_TEXT))
    assert run_agent.referral_ended(
        _text("m2", "No referral was recorded. Application not found.")
    )
    assert run_agent.referral_ended(
        _text("m3", "The referral was cancelled. Nothing was recorded.")
    )
    assert not run_agent.referral_ended(_text("m4", "The flow has started."))
    assert not run_agent.referral_ended(_text("m5", "REF-0001", role="user"))


def test_wait_for_skips_seen_messages_and_polls_until_done() -> None:
    old = _text("m0", "Ortega Builders has four red flags.")
    started = _text("m1", "The flow has started.")
    form = _form("m2", CONFIRM_DATA)
    threads = FakeThreads([old], [old, started], [old, started, form], wrap=True)
    seen = {"m0"}
    found, match = run_agent.wait_for(
        threads, "t1", seen, lambda m: run_agent.form_of(m) is not None
    )
    assert match is form
    assert [m["id"] for m in found] == ["m1", "m2"]
    assert seen == {"m0", "m1", "m2"}


def test_wait_for_gives_up_after_max_polls() -> None:
    threads = FakeThreads([_text("m1", "The flow has started.")])
    found, match = run_agent.wait_for(threads, "t1", set(), run_agent.referral_ended)
    assert match is None
    assert [m["id"] for m in found] == ["m1"]


def test_run_referral_flow_confirms_once_and_leaves_the_review_form() -> None:
    reply = _text("m1", "I started the fraud referral.")
    confirm = _form("m2", CONFIRM_DATA)
    submitted = {"id": "m3", "role": "user", "content": []}
    sent = _text("m4", REFERRAL_TEXT)
    review = _form("m5", CONFIRM_DATA | {"referral_id": "REF-0001"}, form_id="f2")
    threads = FakeThreads(
        [reply],
        [reply, confirm],
        [reply, confirm, submitted],
        [reply, confirm, submitted, sent, review],
    )
    runs = FakeRuns()
    flow = run_agent.run_referral_flow(runs, threads, "agent-1", "t1", set())

    assert len(runs.sent) == 1
    assert runs.sent[0]["thread_id"] == "t1"
    assert runs.sent[0]["message"][0]["id"] == "f1"
    assert flow["end"] == "referral"
    assert flow["confirm_run_id"] == "run-confirm"
    assert [m["id"] for m in flow["messages"]] == ["m1", "m2", "m3", "m4"]


def test_run_referral_flow_without_a_form_sends_nothing() -> None:
    threads = FakeThreads([_text("m1", "I can't refer this application.")])
    runs = FakeRuns()
    flow = run_agent.run_referral_flow(runs, threads, "agent-1", "t1", set())
    assert runs.sent == []
    assert flow["end"] == "no form"


def test_with_flow_adds_new_assistant_text_to_the_answer() -> None:
    out = {"answer": "I started the fraud referral.", "tool_calls": []}
    flow = {
        "end": "referral",
        "messages": [
            _text("m1", "I started the fraud referral."),
            {"id": "m3", "role": "user", "content": "REF-9999"},
            _text("m4", REFERRAL_TEXT),
        ],
    }
    result = run_agent.with_flow(out, flow)
    assert result["answer"] == f"I started the fraud referral.\n{REFERRAL_TEXT}"
    assert result["flow"] is flow
    assert out["answer"] == "I started the fraud referral."

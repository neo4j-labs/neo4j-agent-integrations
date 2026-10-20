"""The fraud_referral workflow: Dana confirms, the referral is written, Sam reviews.

``bank_supervisor`` calls this flow as a tool with the application ID, the red
flag rule codes, and a summary from the fraud check earlier in the chat.

1. A form asks the banker who started the flow to confirm or cancel. Cancel
   ends the flow and writes nothing.
2. ``create_fraud_referral`` writes the ``FraudReferral`` with status OPEN.
3. A message gives the banker the referral ID and the AML-NO-TIPOFF reminder.
   The flow's own result arrives only after Sam acts, so this message is how
   the banker gets the ID in the same turn.
4. A script looks up the fraud reviewer by email, and a form assigned to them
   offers Accept and Close.
5. ``resolve_fraud_referral`` sets the status to ACCEPTED or CLOSED.

The flow has no connection of its own. Its two tools bring ``banker_creds``.
``build_referral_tools.sh`` imports the tools first, because the flow refers
to them by name. In preview every form goes to the person who started the
flow, so the review form reaches Sam only in a live deploy.
"""

import os

from ibm_watsonx_orchestrate.flow_builder.data_map import DataMap
from ibm_watsonx_orchestrate.flow_builder.flows import END, START, Flow, flow
from ibm_watsonx_orchestrate.flow_builder.types import Assignment, UserAssignmentPolicy
from ibm_watsonx_orchestrate_core.types.tools.types import WXOUser
from pydantic import BaseModel, Field

# Read when the flow is imported. The address must be Sam Price's tenant login.
REVIEWER_EMAIL = os.environ.get("FRAUD_REVIEWER_EMAIL", "sam.price@example.com")

AML_NO_TIPOFF = (
    "Do not tell the client about this referral or the fraud review. "
    "Policy AML-NO-TIPOFF forbids tipping off the client."
)


class ReferralInput(BaseModel):
    application_id: str = Field(description="The loan application to refer.")
    red_flags: list[str] = Field(
        description=(
            "The red flag rule codes from the fraud check, such as FRAUD-SHARED-ID."
        )
    )
    summary: str = Field(description="A short summary of why it is referred.")


class ReferralState(BaseModel):
    confirmed: bool = False
    referral_id: str = ""
    error: str = ""
    decision: str = ""
    # Typed as in IBM's user_activity_user_assignment example, so the review
    # form can be assigned to it.
    reviewer: WXOUser = Field(description="The fraud reviewer for the review form.")


class CreateInput(BaseModel):
    application_id: str
    red_flags: list[str]
    summary: str


class Referral(BaseModel):
    referral_id: str | None = None
    status: str | None = None
    error: str | None = None


class ResolveInput(BaseModel):
    referral_id: str
    status: str


def _shown(expression: str, target: str = "self.input.value") -> DataMap:
    """Map a flow variable onto a form output field."""
    return DataMap(
        maps=[Assignment(target_variable=target, value_expression=expression)]
    )


def _show_referral(form, *, with_id: bool) -> None:
    """Add the application, summary, and red flags to a form."""
    if with_id:
        form.field_output_field(
            "referral_id", "Referral", value=_shown("flow.private.referral_id")
        )
    form.field_output_field(
        "application_id", "Application", value=_shown("flow.input.application_id")
    )
    form.field_output_field("summary", "Summary", value=_shown("flow.input.summary"))
    form.list_output_field(
        "red_flags",
        "Red flags",
        choices=_shown("flow.input.red_flags", target="self.input.choices"),
    )


def _confirm_step(aflow: Flow):
    """Ask the banker to confirm. Only Confirm sets flow.private.confirmed."""
    step = aflow.userflow(
        name="confirm_referral",
        display_name="Confirm the referral",
        label="Refer {flow.input.application_id} to the fraud team",
    )
    form = step.form(
        "confirm_form",
        display_name="Confirm the referral",
        instructions=(
            "This sends the application to the fraud team for review. "
            "Confirm to send it, or cancel to send nothing."
        ),
        submit_button_label="Confirm",
    )
    _show_referral(form, with_id=False)
    cancel = step.add_button("Cancel")

    confirmed = step.script(
        name="mark_confirmed", script="flow.private.confirmed = True"
    )
    cancelled = step.field(
        "cancelled",
        display_name="Cancelled",
        text="The referral was cancelled. Nothing was recorded.",
    )
    step.edge(START, form)
    step.edge(form, confirmed, button_label="Confirm")
    step.edge(cancel, cancelled)
    step.edge(confirmed, END)
    step.edge(cancelled, END)
    return step


def _notify_step(aflow: Flow):
    """Give the banker the referral ID and the AML-NO-TIPOFF reminder."""
    step = aflow.userflow(name="referral_sent", display_name="Referral sent")
    sent = step.field(
        "sent",
        display_name="Referral sent",
        text=(
            "Referral {flow.private.referral_id} was sent to the fraud team "
            "and assigned to Sam Price. " + AML_NO_TIPOFF
        ),
    )
    step.edge(START, sent)
    step.edge(sent, END)
    return step


def _error_step(aflow: Flow):
    """Tell the banker why no referral was written."""
    step = aflow.userflow(name="referral_failed", display_name="Referral not sent")
    failed = step.field(
        "failed",
        display_name="Referral not sent",
        text="No referral was recorded. {flow.private.error}",
    )
    step.edge(START, failed)
    step.edge(failed, END)
    return step


def _review_step(aflow: Flow):
    """Ask the fraud reviewer to accept or close the referral."""
    step = aflow.userflow(
        name="review_referral",
        display_name="Review the referral",
        label="Fraud referral {flow.private.referral_id}",
    )
    step.assign_to(UserAssignmentPolicy.USER, assignees="flow.private.reviewer")
    form = step.form(
        "review_form",
        display_name="Review the referral",
        instructions=(
            "A banker referred this application to the fraud team. "
            "Accept it to open a fraud case, or close it if no case is needed."
        ),
        submit_button_label="Accept",
    )
    _show_referral(form, with_id=True)
    close = step.add_button("Close")

    accepted = step.script(
        name="mark_accepted", script="flow.private.decision = 'ACCEPTED'"
    )
    closed = step.script(name="mark_closed", script="flow.private.decision = 'CLOSED'")
    step.edge(START, form)
    step.edge(form, accepted, button_label="Accept")
    step.edge(close, closed)
    step.edge(accepted, END)
    step.edge(closed, END)
    return step


@flow(
    name="fraud_referral",
    display_name="Fraud referral",
    description=(
        "Refer a loan application to the fraud team. The banker confirms in a "
        "form, then the fraud reviewer Sam Price accepts or closes the referral. "
        "Pass the application ID, the red flag rule codes from the fraud check, "
        "and a short summary."
    ),
    input_schema=ReferralInput,
    private_schema=ReferralState,
)
def build_fraud_referral(aflow: Flow) -> Flow:
    confirm = _confirm_step(aflow)

    create = aflow.tool(
        "create_fraud_referral", input_schema=CreateInput, output_schema=Referral
    )
    for name in ("application_id", "red_flags", "summary"):
        create.map_input(input_variable=name, expression=f"flow.input.{name}")

    record = aflow.script(
        name="record_referral",
        script=(
            "result = flow.nodes['create_fraud_referral'].output\n"
            "flow.private.referral_id = result.referral_id or ''\n"
            "flow.private.error = result.error or ''"
        ),
    )
    notify = _notify_step(aflow)
    failed = _error_step(aflow)
    find_reviewer = aflow.script(
        name="find_reviewer",
        script=(
            "flow.private.reviewer = "
            f"system.user.search_by_email('{REVIEWER_EMAIL}')[0]"
        ),
    )
    review = _review_step(aflow)

    resolve = aflow.tool(
        "resolve_fraud_referral", input_schema=ResolveInput, output_schema=Referral
    )
    resolve.map_input(
        input_variable="referral_id", expression="flow.private.referral_id"
    )
    resolve.map_input(input_variable="status", expression="flow.private.decision")

    aflow.edge(START, confirm)
    if_confirmed = aflow.conditions(name="if_confirmed")
    aflow.edge(confirm, if_confirmed)
    if_confirmed.condition(
        to_node=create, expression="flow.private.confirmed == True"
    ).condition(to_node=END, default=True)

    aflow.edge(create, record)
    if_created = aflow.conditions(name="if_created")
    aflow.edge(record, if_created)
    if_created.condition(
        to_node=notify, expression="flow.private.referral_id != ''"
    ).condition(to_node=failed, default=True)

    aflow.sequence(notify, find_reviewer, review, resolve, END)
    aflow.edge(failed, END)
    return aflow

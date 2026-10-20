# Loan Fraud Demo Walkthrough

This walkthrough runs the staff demo from start to finish. A relationship manager asks whether a loan can be approved. The application looks clean. The graph shows that it is part of a fraud ring.

After you set the scene, the demo has four steps: the failure, the fix, the follow-up, and the proof. It takes about 10 minutes.

---

## The story

Dana Whitfield is a relationship manager at the bank. Ortega Builders, one of Dana's clients, has applied for a $400,000 line of credit. The deposits look strong, and the amount is under Dana's approval limit. On paper, Dana can approve it without anyone else.

Three facts sit outside the application, spread across other bankers' books:

- **Hidden owner:** Victor Hale controls Ortega Builders through a holding company. Hale ran a business that left the bank with a written-off loan.
- **Hidden ring:** Ortega and three other businesses applied for credit in the same few weeks. All four list Hale's phone number, and three applied from the same device.
- **Money loop:** Most of Ortega's strong deposits came from the other three businesses, a few days after Ortega sent them money.

A credit specialist working alone says yes. A supervisor that asks a credit specialist and a fraud specialist recommends a referral to the fraud team.

---

## Cast

| Name | ID | Role in the demo |
|---|---|---|
| Dana Whitfield | `RM-07` | The relationship manager who asks every question |
| Victor Hale | `P-1001` | The hidden owner at the center of the ring |
| Luis Ortega | `P-1002` | Ortega Builders' director, who owns 30 percent of it |
| Crestline Holdings | `B-1001` | Hale's holding company. Its only address is a registered agent service in Dover. |
| Ortega Builders | `B-1002` | Dana's client and the applicant |
| Hale Restoration LLC | `B-1003` | Hale's old business, whose loan was written off |
| Keystone Paving | `B-1004` | Ring member, managed by Tom Becker, `RM-03` |
| Summit Ridge Supply | `B-1005` | Ring member, managed by Alicia Romero, `RM-05` |
| Lakeview Interiors | `B-1006` | Ring member, managed by Grant Holloway, `RM-09` |

All scenarios use the demo date of October 8, 2026.

---

## Agents

| Agent | Model | What it does in the demo |
|---|---|---|
| `credit_analyst` | gpt-oss-120b | It checks the application against the lending and approval rules. It is the failure step when asked alone. |
| `fraud_investigator` | gpt-oss-120b | It finds the real owners, the connected group, and any money loops. |
| `banking_policy` | gpt-oss-120b | It answers general policy questions from the knowledge base. |
| `bank_supervisor` | gpt-6-luna | It sends each question to the right specialists and writes the final answer. It has no tools of its own. |

Every staff tool reads the `banker_creds` connection. The connection is fixed to Dana's banker ID, `RM-07`, so every chat runs as Dana.

---

## Before you start

Check each item before the audience arrives.

- **Graph:** `make rebuild` has run on the demo's Aura instance. The rebuild loads the fraud data and runs the connected group step. The connected group step creates an Aura Graph Analytics session, which is billed while it runs.
- **Checks:** `uv run validate-data` and `make test` both pass.
- **Orchestrate:** Run `./orchestrate/connect_env.sh` to refresh the tenant token. `orchestrate agents list` shows the four staff agents. `bank_supervisor` lists `credit_analyst`, `fraud_investigator`, and `banking_policy` as collaborators.
- **Aura console:** The proof query from [Step 5](#step-5-the-proof-in-neo4j-aura) is saved in your own Aura console. Aura saved queries belong to the user who saves them.
- **Browser tabs:** Open one tab with the Orchestrate chat and one with the Aura Query tool.

---

## Step 1: Set the scene

**Say:** "Dana is a relationship manager. Dana's client, Ortega Builders, wants a $400,000 line of credit. Let's see what an AI assistant says."

Show the application facts:

| Fact | Value |
|---|---|
| Application | `APP-1001`, a business line of credit |
| Amount | $400,000 |
| Stated annual revenue | $2,440,000 |
| Deposits in the last 90 days | $610,000 |
| Dana's approval limit | $500,000 |

The lending rule `LEND-BUSLINE-REV` allows a line of up to 25 percent of verified annual revenue. The credit check takes revenue from the last 90 days of deposits: $610,000 times four, which is $2,440,000. So the largest line is $610,000, and the request fits. It is also under Dana's limit under `AUTH-RM-LIMIT`.

---

## Step 2: The failure

**Agent:** `credit_analyst`

**Prompt:** "Ortega Builders applied for a $400,000 line of credit. Their deposits look strong. Can I approve it?"

**What happens:** The agent looks up the application in the graph. Revenue supports the request, and the amount is under Dana's limit. It recommends approval.

**Say:** "This agent has the bank's data, and it still says yes. A credit check looks at one application. It cannot see who owns the business, who else applied, or where the deposits came from. Those facts live in other bankers' books."

---

## Step 3: The fix

Start a new chat for this step. Step 4 runs in the same chat.

**Agent:** `bank_supervisor`

**Prompt:** Use the same prompt as Step 2.

**What happens:** The supervisor sends the question to `credit_analyst` and `fraud_investigator`. The credit check passes. The fraud check finds the red flags. The supervisor opens with one recommendation, then writes a "Credit check" section and a "Fraud check" section.

**What the answer contains:**

- **Recommendation:** Do not approve. Refer the application to the fraud team under `FRAUD-REFERRAL`, because it matches two or more red flags.
- **Hidden owner:** Crestline Holdings owns 70 percent of Ortega Builders. Victor Hale owns 80 percent of Crestline. Hale's effective share of Ortega is 56 percent, so Hale is a beneficial owner under `KYC-UBO-25`. Neither Hale nor Crestline appears on the application.
- **Prior loss:** Hale Restoration LLC, which Hale owns, had a $250,000 term loan. The bank wrote off $186,400 of it on February 28, 2025. That matches `FRAUD-PRIOR-LOSS`.
- **Hidden ring:** Ortega, Keystone Paving, Summit Ridge Supply, and Lakeview Interiors all applied in the last three weeks. All four list the phone number `+1-555-0610`, which is Hale's. Ortega, Keystone, and Summit applied from the same device. The four businesses sit in one connected group, and Hale is its most central member. That matches `FRAUD-SHARED-ID`.
- **Money loop:** Ortega received $610,000 in the last 90 days. Ortega sent $370,000 to Keystone, Summit, and Lakeview, and $455,000 came back from them. That matches `FRAUD-CIRCULAR-FLOW`.
- **Revenue:** The loop money does not count as revenue. Only $155,000 came from outside clients.
- **Warning:** Do not tell Ortega Builders about the referral, under `AML-NO-TIPOFF`.

Luis Ortega may appear as a 30 percent beneficial owner and Ortega's director. That is correct, and it is not a red flag.

**What to point out in Orchestrate:** Open the step history. It shows one call to `credit_analyst` and one call to `fraud_investigator`, and no call to `banking_policy`.

**Say:** "The answer says the application matches these red flags. It does not say anyone committed fraud. Dana decides. Each red flag names the policy rule it comes from."

---

## Step 4: The follow-up

Run this step in the same chat as Step 3.

**Agent:** `bank_supervisor`

**Prompt:** "Ortega's owner called asking why the line is delayed. What can I tell him?"

**What happens:** This is a policy question, so the supervisor sends it to `banking_policy` alone. It adds one sentence of context from the chat: the line is Ortega Builders' application, and the supervisor recommended a fraud referral.

**What the answer contains:**

- **Rule:** Dana must not mention the referral or the fraud review, under `AML-NO-TIPOFF`.
- **Wording:** The answer gives the suspicious activity policy's script: "Your application is still in review. Reviews can take longer when we need to verify more information. We will contact you when the review is complete."

The answer does not name Victor Hale or Crestline, and gives no phone, device, or amount from Step 3.

**What to point out in Orchestrate:** The step history shows one call to `banking_policy` and no call to the other specialists.

**Say:** "Staff can break bank policy by saying too much. The supervisor knew from the chat that a referral was recommended, so it asked the policy specialist the right question. Dana gets words that are safe to use."

---

## Step 5: The proof in Neo4j Aura

Open the Aura Query tool, run the saved query, and switch to the graph view.

```cypher
// The graph behind the Scenario E answer.
MATCH (hale:Person {person_id: 'P-1001'})
RETURN
  COLLECT {
    MATCH p = (hale)-[:OWNS*1..2]->(:Business {business_id: 'B-1002'})
    RETURN p
  } AS hidden_owner,
  COLLECT {
    MATCH p = (hale)-[:OWNS]->(:Business)-[:BORROWER_ON]->(:Loan {status: 'WRITTEN_OFF'})
    RETURN p
  } AS prior_loss,
  COLLECT {
    MATCH p = (:Business)-[:HAS_PHONE]->(:Phone {number: '+1-555-0610'})
    RETURN p
  } AS shared_phone,
  COLLECT {
    MATCH p = (:Business)-[:APPLIED_FOR]->(:LoanApplication)
              -[:SUBMITTED_FROM]->(:Device {device_id: 'DEV-1001'})
    RETURN p
  } AS shared_device,
  COLLECT {
    MATCH p = (:Business)-[:HOLDS]->(:Account)-[:HAS_TRANSACTION]->(:Transaction)
              -[:TO_ACCOUNT]->(:Account {account_id: 'A-3001'})
    RETURN p
  } AS loop_in,
  COLLECT {
    MATCH p = (hale)-[:IN_GROUP]->(:ConnectedGroup)
    RETURN p
  } AS connected_group,
  COLLECT {
    MATCH p = (r:FraudRule)-[:FROM_CHUNK]->(:Chunk)
    WHERE r.rule_code IN ['KYC-UBO-25', 'FRAUD-PRIOR-LOSS', 'FRAUD-SHARED-ID',
                          'FRAUD-CIRCULAR-FLOW']
    RETURN p
  } AS policy_text
```

**What the graph shows:**

- Hale owns Crestline, and Crestline owns Ortega.
- Hale also owns Hale Restoration, which links to the written-off loan.
- Ortega, Keystone, Summit, and Lakeview all point to one phone node.
- Three applications point to one device node.
- Eight transfers flow into Ortega's account from the other three ring accounts.
- Hale sits in the connected group. Hale's `IN_GROUP` link carries the highest centrality score.
- Each rule links to the policy chunk it comes from.

**Say:** "Each fact in the answer is a node or a link here. You can check every one of them."

---

## Reset between presentations

Start a new chat in Orchestrate for each presentation. Step 4 depends on Step 3 being in the same chat. The demo writes nothing to the graph, so the graph needs no reset.

---

## If something goes wrong

- **`credit_analyst` does not recommend approval in Step 2:** Ask again in a new chat. The agent sometimes says only that Dana may approve, without recommending approval.
- **The supervisor calls only one specialist in Step 3:** Ask again in a new chat. Note it afterwards, because the supervisor should call both specialists every time.
- **The supervisor's answer leaves out a fact:** The supervisor can shorten a specialist's answer and drop details, such as a rule name. Open that specialist's step in the step history to show its full answer.
- **Step 4 asks which line Dana means:** The supervisor did not add the context sentence, or Step 3 ran in a different chat. Run Step 3 and Step 4 again in one new chat.
- **The chat shows a token or connection error:** Run `./orchestrate/connect_env.sh` again.
- **The proof query draws no group:** The connected group step did not run. Run `uv run build-groups` to rebuild the groups without a full reset. It creates a billed Aura Graph Analytics session while it runs.

---

## Key numbers

| Fact | Value |
|---|---|
| Hale's effective share of Ortega | 56 percent, which is 80 percent of 70 percent |
| Beneficial owner threshold | 25 percent |
| Hale Restoration loan | $250,000 term loan, with $186,400 written off on February 28, 2025 |
| Ortega's deposits, last 90 days | $610,000 |
| Loop deposits from the ring | $455,000: $180,000 from Keystone, $160,000 from Summit, and $115,000 from Lakeview |
| Ortega's transfers back to the ring | $370,000 |
| Deposits from outside clients | $155,000 |
| Shared phone | `+1-555-0610`, used by all four applicants |
| Shared device | `DEV-1001`, used by Ortega, Keystone, and Summit |
| Relationship manager approval limit | $500,000 |

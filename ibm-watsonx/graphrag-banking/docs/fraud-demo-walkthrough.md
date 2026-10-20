# Loan Fraud Demo Walkthrough

This walkthrough runs the staff demo from start to finish. A relationship manager asks whether she can approve a loan. The application looks clean. The graph shows that it is part of a fraud ring.

The demo takes about 15 minutes. The optional steps add about 5 more.

---

## The story

Dana Whitfield is a relationship manager at the bank. Ortega Builders, one of her clients, has applied for a $400,000 line of credit. The deposits look strong, and the amount is under Dana's approval limit. On paper, she can approve it herself.

Three facts sit outside the application, spread across other bankers' books:

- **Hidden owner:** Victor Hale controls Ortega Builders through a holding company. Hale ran a business that left the bank with a written-off loan last year.
- **Hidden ring:** Ortega and three other businesses applied for credit in the same few weeks. All four list Hale's phone number, and three applied from the same laptop.
- **Money loop:** Most of Ortega's strong deposits came from the other three businesses, and most of that money went back to them within days.

A single agent that reads the lending policy says yes. A supervisor that asks a credit specialist and a fraud specialist says no, and refers the case to the fraud team.

---

## Cast

| Name | ID | Role in the demo |
|---|---|---|
| Dana Whitfield | `RM-07` | The relationship manager who asks every question |
| Sam Price | `FR-02` | The fraud reviewer who receives the referral |
| Victor Hale | `P-1001` | The hidden owner at the center of the ring |
| Crestline Holdings | `B-1001` | Hale's holding company. Its only address is a registered agent service in Dover. |
| Ortega Builders | `B-1002` | Dana's client and the applicant |
| Hale Restoration LLC | `B-1003` | Hale's old business, whose loan was written off |
| Keystone Paving | `B-1004` | Ring member, managed by Tom Becker, `RM-03` |
| Summit Ridge Supply | `B-1005` | Ring member, managed by Alicia Romero, `RM-05` |
| Lakeview Interiors | `B-1006` | Ring member, managed by Grant Holloway, `RM-09` |
| Brightline Dental | `B-1007` | Dana's clean client, owned by Dr. Nina Patel |
| Harbor Physical Therapy | `B-1008` | An unrelated business that shares Brightline's registered agent address |

All scenarios use the demo date of October 8, 2026.

---

## Agents

| Agent | What it does in the demo |
|---|---|
| `banking_baseline` | The failure step. It answers from the policy documents alone. |
| `credit_analyst` | It checks the application against the lending and approval rules. |
| `fraud_investigator` | It finds the real owners, the connected group, and any money loops. |
| `banking_policy` | It answers general policy questions from the knowledge base. |
| `bank_supervisor` | It sends each question to the right specialists and writes the final answer. It also starts the referral workflow. |

The referral workflow is `fraud_referral`. It is a flow tool on `bank_supervisor`.

---

## Before you start

Check each item before the audience arrives.

- **Graph:** `make rebuild` has run on the demo's Aura instance. The rebuild loads the fraud data and runs the connected group step.
- **Checks:** `uv run validate-data` and `make test` both pass.
- **Orchestrate:** The staff agents, the `fraud_referral` workflow, and the `banking_policies` knowledge base are imported. `make wxo-check` passes.
- **Clean slate:** No `FraudReferral` exists in the graph. The [Reset](#reset-between-presentations) section shows how to clear them.
- **Aura console:** The proof query from the [Proof](#step-10-the-proof-in-neo4j-aura) step is saved in your own Aura console. Aura saved queries belong to the user who saves them.
- **Browser tabs:** Open one tab with the Orchestrate chat and one with the Aura Query tool.

---

## Step 1: Set the scene

**Say:** "Dana is a relationship manager. Her client, Ortega Builders, wants a $400,000 line of credit. Let's see what an AI assistant tells her."

Show the application facts:

| Fact | Value |
|---|---|
| Application | `APP-1001`, a business line of credit |
| Amount | $400,000 |
| Stated annual revenue | $2,440,000 |
| Deposits in the last 90 days | $610,000 |
| Dana's approval limit | $500,000 |

The lending rule `LEND-BUSLINE-REV` allows a line of up to 25 percent of annual revenue. On stated revenue, that is $610,000. The request fits, and it is under Dana's limit under `AUTH-RM-LIMIT`.

---

## Step 2: The failure

**Agent:** `banking_baseline`

**Prompt:** "Ortega Builders applied for a $400,000 line of credit. Their deposits look strong. Can I approve it?"

**What happens:** The agent reads the lending policy. It sees strong revenue and an amount under the limit. It says yes.

**Say:** "The answer follows the policy, and it is wrong. The policy documents cannot see who owns Ortega, who else applied, or where the deposits came from. Those facts live in records across four bankers' books."

---

## Step 3, optional: One specialist alone

Use this step for an audience that cares most about Orchestrate.

**Agent:** `credit_analyst`

**Prompt:** The same as Step 2.

**What happens:** The agent checks the application in the graph. Revenue supports the request, and the amount is under Dana's limit. It recommends approval.

**Say:** "This agent uses the graph, and it still says yes. A credit check looks at one application. It cannot see the ring. That is why the bank needs more than one specialist."

---

## Step 4: The fix

**Agent:** `bank_supervisor`

**Prompt:** The same as Step 2.

**What happens:** The supervisor sends the question to `credit_analyst` and `fraud_investigator`. The credit check passes. The fraud check finds three red flags. The supervisor combines both answers.

**What the answer contains:**

- **Hidden owner:** Crestline Holdings owns 70 percent of Ortega Builders. Victor Hale owns 80 percent of Crestline. His effective share of Ortega is 56 percent, so he is a beneficial owner under `KYC-UBO-25`. Neither Hale nor Crestline appears on the application.
- **Prior loss:** Hale Restoration LLC, which Hale owns, had a $250,000 term loan. The bank wrote off $186,400 of it in February 2025. That matches `FRAUD-PRIOR-LOSS`.
- **Hidden ring:** Ortega, Keystone Paving, Summit Ridge Supply, and Lakeview Interiors all applied in the last 30 days. All four list the phone number `+1-555-0610`, which is Hale's. Ortega, Keystone, and Summit applied from the same device. The four businesses sit in one connected group, and Hale has the highest centrality in it. That matches `FRAUD-SHARED-ID`.
- **Money loop:** Ortega received $610,000 in the last 90 days. Of that, $455,000 came from Keystone, Summit, and Lakeview. Ortega sent $370,000 back to them. That matches `FRAUD-CIRCULAR-FLOW`.
- **Recommendation:** Do not approve. Refer the application to the fraud team under `FRAUD-REFERRAL`, because it matches two or more red flags.
- **Revenue:** The loop money does not count as revenue. Only $155,000 came from outside clients. That is about $620,000 a year, which supports a line of about $155,000.
- **Warning:** Do not tell Ortega Builders about the referral, under `AML-NO-TIPOFF`.

**What to point out in Orchestrate:** The chat shows that the supervisor called both specialists. Point to the `credit_analyst` call and the `fraud_investigator` call.

**Say:** "The answer says the application matches these red flags. It does not say anyone committed fraud. A person decides that. Each red flag comes with the policy text it is based on."

---

## Step 5: A clean application

**Agent:** `bank_supervisor`

**Prompt:** "Brightline Dental applied for a $150,000 line of credit. Can I approve it?"

**What happens:** The supervisor sends the question to both specialists again. Dr. Nina Patel owns all of Brightline. She has no past losses. Brightline shares no phone, email, device, or director with any other applicant. Its $300,000 in deposits over 90 days came from many outside payers, with no loops.

**Expected answer:** Recommend approval. Revenue supports the request. Dana can approve it herself under `AUTH-RM-LIMIT`.

**Say:** "The agent does not flag everything. A clean application gets a clean answer."

---

## Step 6: The false alarm

**Agent:** `bank_supervisor`

**Prompt:** "Brightline Dental and Harbor Physical Therapy share an address. Is that a problem?"

**What happens:** The shared address is 910 Harbor Gate Way, Suite 200, in Dover, Delaware. It belongs to a registered agent service. More than 200 businesses in the graph list it.

**Expected answer:** No. Under `FRAUD-REG-AGENT`, a shared registered agent address is not a red flag on its own. The two businesses share nothing else.

**Say:** "A simple rule would flag every business at that address. The graph shows that 200 others share it, and that these two share nothing else. The connected group step also leaves these addresses out, so they never join businesses into a group."

---

## Step 7: Tipping off

**Agent:** `bank_supervisor`

**Prompt:** "Ortega's owner called asking why the line is delayed. What can I tell him?"

**What happens:** The supervisor sends the question to `banking_policy`.

**Expected answer:** Dana must not mention the referral or the fraud review, under `AML-NO-TIPOFF`. The answer gives the neutral wording the suspicious activity policy allows.

**Say:** "This is a policy question, so it goes to the policy specialist. Staff can break the law by saying too much, so the agent gives Dana words she can use."

---

## Step 8: Limits outside the book

**Agent:** `bank_supervisor`

**Prompt:** "Show me the account balances for Keystone Paving."

**What happens:** Keystone Paving is in the ring, but Tom Becker manages it, not Dana. The tools check which bankers manage each client before they return details.

**Expected answer:** Keystone is in the same connected group as Ortega, and the answer can say how it connects. It shows no balances or transactions for Keystone.

**Say:** "Finding the ring needs the whole graph, across every banker's book. Privacy needs limits on what each banker sees. The tools do both."

---

## Step 9: The referral

Run this step in the same chat as Step 4.

**Agent:** `bank_supervisor`

**Prompt:** "Refer it to the fraud team."

**What happens:**

1. The supervisor starts the `fraud_referral` workflow with the application, the connected group, and the red flag rules.
2. The workflow shows Dana a form with the referral summary and two buttons, Confirm and Cancel.
3. Dana clicks Confirm.
4. The workflow writes a `FraudReferral` to the graph. It links the referral to the application, the connected group, each red flag rule, and Sam Price.
5. The chat shows the referral ID and reminds Dana not to tell the client.
6. The workflow assigns a review task to Sam Price.

**Expected answer:** The referral was sent. The answer gives its ID and the `AML-NO-TIPOFF` reminder.

**Say:** "The agent recommends. A person decides. Nothing was written until Dana clicked Confirm. The referral is the only thing the demo writes. It never changes the application, a loan, or an account."

### Sam's review

Sam receives the task only on the live agents. In the preview chat, every workflow task goes back to the person who started it, so the review form appears for Dana instead.

On the live agents:

1. Sign in as Sam Price.
2. Open the chat. The review task is marked with a blue dot.
3. Show the application, the red flags, and the policy text for each one.
4. Click Accept.

**Say:** "Sam sees the same evidence the agent found, without re-running the investigation."

---

## Step 10: The proof in Neo4j Aura

Open the Aura Query tool, run the saved query, and switch to the graph view.

```cypher
// The graph behind the Scenario E answer and the referral.
MATCH (hale:Person {person_id: 'P-1001'})
MATCH (app:LoanApplication {application_id: 'APP-1001'})
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
  } AS policy_text,
  COLLECT {
    MATCH p = (:FraudReferral)-[:FOR_APPLICATION]->(app)
    RETURN p
  } AS referral
```

**What the graph shows:**

- Hale owns Crestline, and Crestline owns Ortega.
- Hale also owns Hale Restoration, which links to the written-off loan.
- Ortega, Keystone, Summit, and Lakeview all point to one phone node.
- Three applications point to one device node.
- Transfers flow into Ortega's account from the other three ring accounts.
- Hale sits in the connected group. His `IN_GROUP` link carries the highest centrality score.
- Each red flag rule links to the policy chunk it comes from.
- The new referral links to the application.

**Say:** "Each fact in the answer is a node or a link here. You can check every one of them."

---

## Reset between presentations

Delete the demo referrals so the next presentation starts clean. Run this in the Aura Query tool:

```cypher
MATCH (r:FraudReferral) DETACH DELETE r
```

Start a new chat in Orchestrate for each presentation. Step 9 depends on Step 4 being in the same chat.

---

## If something goes wrong

- **The supervisor calls only one specialist in Step 4:** Ask the question again in a new chat. Note it afterwards, because the supervisor should call both specialists every time.
- **The supervisor's answer leaves out a fact:** The supervisor rewrites each specialist's answer, and it can drop details. Open the `fraud_investigator` step in the chat to show the specialist's full answer.
- **The referral form does not appear:** Check that the `fraud_referral` workflow is imported and listed in `bank_supervisor`'s tools.
- **Sam does not see the task:** Check that the agents run live, not in preview. In preview, the task goes back to Dana.
- **The proof query draws no group:** The connected group step did not run. Run `make rebuild` again.

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
| Brightline's deposits, last 90 days | $300,000 from many outside payers |
| Businesses at the registered agent address | More than 200 |
| Relationship manager approval limit | $500,000 |

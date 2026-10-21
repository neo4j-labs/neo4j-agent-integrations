# Graph Schema

This page lists the node labels, relationships, and indexes in the demo graph. The loaders in `src/graphrag_banking/` write it. [`data/README.md`](../data/README.md) documents the CSV columns and the controlled values.

The graph has four layers. The customer layer holds accounts and transactions. The rule layer holds the fee, hold, compliance, fraud, and lending rules. The document layer holds the policy text, split into chunks. The staff layer holds the business ownership and loan data, and the connected groups built from it.

## Customer layer

| Label | Key | Notes |
|---|---|---|
| `Customer` | `customer_id` | The demo customer is `C-1001`. |
| `Account` | `account_id` | Holds `ledger_balance` and `available_balance`. |
| `Transaction` | `transaction_id` | `type` gives the direction. `status` can be `HELD` or `PENDING`. |
| `Counterparty` | `counterparty_id` | A merchant, business, individual, or lender. `name` has a full-text index. |
| `ScheduledPayment` | `payment_id` | A recurring payment from an account. |
| `ComplianceAlert` | `alert_id` | Raised by a transaction under a compliance rule. |

| Relationship | Meaning |
|---|---|
| `(Customer)-[:HOLDS {role}]->(Account)` | The role is `PRIMARY` or `JOINT`. |
| `(Customer)-[:RELATED_TO {type}]->(Customer)` | Family links such as `SPOUSE`. |
| `(Account)-[:IS_PRODUCT]->(AccountProduct)` | The account's product. |
| `(Account)-[:HAS_TRANSACTION]->(Transaction)` | |
| `(Customer)-[:INITIATED]->(Transaction)` | |
| `(Transaction)-[:PAID_TO]->(Counterparty)` | A debit. |
| `(Transaction)-[:RECEIVED_FROM]->(Counterparty)` | A credit. |
| `(fee:Transaction)-[:FEE_FOR]->(Transaction)` | Links a fee to the transaction that caused it. |
| `(Transaction)-[:RAISED]->(ComplianceAlert)` | |
| `(ComplianceAlert)-[:UNDER_RULE]->(ComplianceRule)` | |
| `(Account)-[:HAS_SCHEDULED_PAYMENT]->(ScheduledPayment)` | |
| `(ScheduledPayment)-[:PAYS]->(Counterparty)` | |

## Rule layer

The rule layer loads from `data/policy_facts.yaml`, whose header comment documents every field.

| Label | Key | Notes |
|---|---|---|
| `AccountProduct` | `product_code` | `tier` is `STANDARD` or `PREMIUM`. |
| `Policy` | `policy_id` | One per policy document. |
| `FeeRule`, `HoldRule`, `ComplianceRule` | `rule_code` | Customer rules. |
| `FraudRule`, `LendingRule` | `rule_code` | Staff rules. |

| Relationship | Meaning |
|---|---|
| `(Policy)-[:DEFINES]->(rule)` | The policy that defines the rule. |
| `(FeeRule)-[:APPLIES_TO]->(AccountProduct)` | Every product that can be charged the fee, including products that waive it. |
| `(FeeRule)-[:WAIVED_FOR]->(AccountProduct)` | Always a subset of `APPLIES_TO`. A fee is charged when the product is in `APPLIES_TO` and not in `WAIVED_FOR`. |

## Document layer

`build-policy-graph` splits each policy document into one chunk per `##` section. It embeds each chunk, and it uses no entity extraction.

| Label | Notes |
|---|---|
| `Document` | One per policy. Holds `title`, `policy_id`, and `audience`. `audience` is customer or staff. |
| `Chunk` | One policy section, with its embedding and a `rule_codes` list. |
| `CustomerChunk` | An extra label on chunks of customer documents. |

| Relationship | Meaning |
|---|---|
| `(Chunk)-[:FROM_DOCUMENT]->(Document)` | |
| `(Chunk)-[:NEXT_CHUNK]->(Chunk)` | The next section in the same document. `search_policies` returns each match's neighbors. |
| `(rule)-[:FROM_CHUNK]->(Chunk)` | Links each rule to the section that states it. This link is how an answer ties a rule to its policy text. |

## Staff layer

| Label | Key | Notes |
|---|---|---|
| `Banker`, `FraudReviewer` | `banker_id`, `reviewer_id` | The staff who own books and review referrals. |
| `Person`, `Business` | `person_id`, `business_id` | Owners, directors, and the businesses they own. |
| `Phone`, `Email`, `Address`, `Device` | `number`, `address`, `address_id`, `device_id` | Identifiers that people and businesses share. |
| `Loan`, `LoanApplication` | `loan_id`, `application_id` | The lending history and the application under review. |
| `ConnectedGroup` | `group_id` | Written by `build-groups`. IDs look like `CG-0001`. |
| `FraudReferral` | `referral_id` | Written by the referral tools only. The demo does not use it. |

| Relationship | Meaning |
|---|---|
| `(Banker)-[:MANAGES]->(Customer)` and `(Banker)-[:MANAGES]->(Business)` | A banker's book. |
| `(Person)-[:OWNS]->(Business)` and `(Business)-[:OWNS]->(Business)` | Ownership, with a `percent`. |
| `(Person)-[:DIRECTOR_OF]->(Business)` | |
| `(Person or Business)-[:HAS_PHONE]->(Phone)` | The same pattern holds for `HAS_EMAIL` and `HAS_ADDRESS`. |
| `(Business)-[:HOLDS]->(Account)` | A business account. |
| `(Business)-[:APPLIED_FOR]->(LoanApplication)` | |
| `(LoanApplication)-[:SUBMITTED_FROM]->(Device)` | |
| `(Business)-[:BORROWER_ON]->(Loan)` | |
| `(Transaction)-[:TO_ACCOUNT]->(Account)` | A transfer between two bank accounts. It is one transaction row. |
| `(Customer, Person, or Business)-[:IN_GROUP {centrality}]->(ConnectedGroup)` | Written by `build-groups`. |

A connected group exists only when two or more of its members share a phone, email, device, or address. Registered agent and coworking addresses do not count. The [decision log](decision_log.md) explains the rule.

The referral tools also write `(Banker)-[:SUBMITTED]->(FraudReferral)`, `FOR_APPLICATION`, `ASSIGNED_TO`, `ABOUT_GROUP`, and `CITES` relationships.

## Constraints and indexes

- **Unique constraints:** One per label on its key property, for every label in the customer, rule, and staff layers. `ConnectedGroup.group_id` has one too.
- **Vector index:** `chunk_embedding` covers only `CustomerChunk`. Staff documents stay out of `search_policies`.
- **Full-text index:** `counterparty_name` covers `Counterparty.name`. The payee lookup uses it.

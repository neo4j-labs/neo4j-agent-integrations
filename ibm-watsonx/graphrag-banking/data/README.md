# Data

| Path | What it is | Committed |
|---|---|---|
| `policy_facts.yaml` | Canonical products, policies and rules. Schema in its header comment. | Yes |
| `hero_fixtures.yaml` | Hand-written records for the hero scenarios in PRD section 4. | Yes |
| `policy_templates/` | Policy Markdown with `${placeholders}`. | Yes |
| `policies/` | Rendered policy documents, written by `render-policies`. | Yes |
| `generated/` | CSVs written by `generate-data`. Rebuilt on every `make ingest`. | No |
| `generated/fraud/` | Loan fraud CSVs for the staff demo, also written by `generate-data`. | No |

## Conventions

- **Encoding:** UTF-8, comma-separated, one header row, written with Python's `csv` module (fields that contain commas are quoted).
- **Datetimes:** `initiated_at`, `posted_at` and `opened_at` are ISO 8601 UTC with a `Z` suffix, e.g. `2026-10-07T15:42:00Z`.
- **Dates:** `available_on`, `next_run_date`, `opened_date`, `customer_since` and `effective_date` are `YYYY-MM-DD`.
- **Amounts:** plain decimals with two places and no currency symbol or thousands separator, e.g. `5000.00`. Amounts are always positive.
- **Nulls:** an empty cell. Do not load an empty cell as an empty string.
- **Direction:** comes from `Transaction.type`.
  - Credits: `WIRE_IN`, `ACH_IN`, `CHECK_DEPOSIT`.
  - Debits: `WIRE_OUT`, `ACH_OUT`, `CARD`, `FEE`, `TRANSFER`.
- **Balances:** `ledger_balance` counts `POSTED` transactions only. `available_balance` is the ledger balance minus `HELD` or `PENDING` debits. Pending deposits are not in either balance until they post, so a pending deposit's `available_on` is the date it adds to the available balance.

## Node CSVs (`generated/`)

| File | Label | Columns |
|---|---|---|
| `customers.csv` | `Customer` | `customer_id`, `name`, `email`, `phone`, `segment`, `risk_rating`, `kyc_status`, `customer_since` |
| `accounts.csv` | `Account` | `account_id`, `nickname`, `ledger_balance`, `available_balance`, `currency`, `status`, `opened_date` |
| `transactions.csv` | `Transaction` | `transaction_id`, `type`, `amount`, `currency`, `initiated_at`, `posted_at`, `available_on`, `status`, `channel`, `description` |
| `counterparties.csv` | `Counterparty` | `counterparty_id`, `name`, `kind`, `category`, `country` |
| `scheduled_payments.csv` | `ScheduledPayment` | `payment_id`, `amount`, `frequency`, `next_run_date`, `status` |
| `compliance_alerts.csv` | `ComplianceAlert` | `alert_id`, `rule_code`, `status`, `opened_at`, `reason` |

The first column is the node key.

## Relationship CSVs (`generated/`)

| File | Relationship | Columns |
|---|---|---|
| `rel_related_to.csv` | `(Customer)-[:RELATED_TO {type}]->(Customer)` | `customer_id`, `related_customer_id`, `type` |
| `rel_holds.csv` | `(Customer)-[:HOLDS {role}]->(Account)` | `customer_id`, `account_id`, `role` |
| `rel_is_product.csv` | `(Account)-[:IS_PRODUCT]->(AccountProduct)` | `account_id`, `product_code` |
| `rel_has_transaction.csv` | `(Account)-[:HAS_TRANSACTION]->(Transaction)` | `account_id`, `transaction_id` |
| `rel_initiated.csv` | `(Customer)-[:INITIATED]->(Transaction)` | `customer_id`, `transaction_id` |
| `rel_paid_to.csv` | `(Transaction)-[:PAID_TO]->(Counterparty)` | `transaction_id`, `counterparty_id` |
| `rel_received_from.csv` | `(Transaction)-[:RECEIVED_FROM]->(Counterparty)` | `transaction_id`, `counterparty_id` |
| `rel_fee_for.csv` | `(fee:Transaction)-[:FEE_FOR]->(Transaction)` | `fee_transaction_id`, `transaction_id` |
| `rel_raised.csv` | `(Transaction)-[:RAISED]->(ComplianceAlert)` | `transaction_id`, `alert_id` |
| `rel_under_rule.csv` | `(ComplianceAlert)-[:UNDER_RULE]->(ComplianceRule)` | `alert_id`, `rule_code` |
| `rel_has_scheduled_payment.csv` | `(Account)-[:HAS_SCHEDULED_PAYMENT]->(ScheduledPayment)` | `account_id`, `payment_id` |
| `rel_pays.csv` | `(ScheduledPayment)-[:PAYS]->(Counterparty)` | `payment_id`, `counterparty_id` |

Debits link to their counterparty with `PAID_TO`, and credits link with `RECEIVED_FROM`. `FEE` transactions have no counterparty, and `rel_fee_for.csv` links them to the transaction that caused them. `rel_is_product.csv` and `rel_under_rule.csv` point at rule-layer keys, so load them after `policy_facts.yaml`.

## Controlled values

| Field | Values |
|---|---|
| `Transaction.type` | `WIRE_OUT`, `WIRE_IN`, `ACH_OUT`, `ACH_IN`, `CHECK_DEPOSIT`, `CARD`, `FEE`, `TRANSFER` |
| `Transaction.status` | `POSTED`, `PENDING`, `HELD`, `FAILED`, `RETURNED`, `REVERSED` |
| `Transaction.channel` | `ONLINE`, `MOBILE`, `BRANCH`, `ACH`, `CARD`, `SYSTEM` |
| `Transaction.currency`, `Account.currency` | `USD` |
| `Counterparty.kind` | `MERCHANT`, `BUSINESS`, `INDIVIDUAL`, `LENDER` |
| `Customer.segment` | `RETAIL`, `PREMIER` |
| `Customer.risk_rating` | `LOW`, `MEDIUM`, `HIGH` |
| `Customer.kyc_status` | `VERIFIED`, `PENDING`, `EXPIRED` |
| `Account.status` | `OPEN`, `FROZEN`, `CLOSED` |
| `HOLDS.role` | `PRIMARY`, `JOINT` |
| `RELATED_TO.type` | `SPOUSE` |
| `ScheduledPayment.frequency` | `WEEKLY`, `BIWEEKLY`, `MONTHLY` |
| `ScheduledPayment.status` | `ACTIVE`, `PAUSED` |
| `ComplianceAlert.status` | `OPEN`, `CLEARED`, `ESCALATED` |

## Rule layer (`policy_facts.yaml`)

The rule layer loads straight from `policy_facts.yaml`, not from CSVs. Read the file with `yaml.safe_load`. Note that PyYAML parses an unquoted `effective_date` such as `2026-01-01` as a `datetime.date`.

- `products[]` become `AccountProduct` nodes, keyed on `product_code`.
- `policies[]` become `Policy` nodes, keyed on `policy_id`.
  - `audience` is customer or staff. `build-policy-graph` writes it on the `Document` node. Chunks of customer documents also get the `CustomerChunk` label, and only those are in the `chunk_embedding` vector index.
- `fee_rules[]`, `hold_rules[]` and `compliance_rules[]` become `FeeRule`, `HoldRule` and `ComplianceRule` nodes, keyed on `rule_code`.
- `fraud_rules[]` and `lending_rules[]` become `FraudRule` and `LendingRule` nodes, keyed on `rule_code`. They carry `percent`, `years`, `lookback_days`, `min_red_flags` or `amount` where present.
  - Properties: `name`, `condition` and `transaction_types` (a list), plus `amount`, `hold_days` or `threshold` where present.
  - `threshold` is optional on fee and hold rules. It is set on `FEE-OVERDRAFT` (no fee when overdrawn by $50 or less) and `HOLD-CHECK-LARGE`. It is null on `SANCTIONS-SCREEN-01`.
- Each rule's `policy_id` gives `(Policy)-[:DEFINES]->(rule)`.
- For fee rules:
  - `applies_to` gives `[:APPLIES_TO]` to every product that can be charged the fee, including products that waive it.
  - `waived_for` gives `[:WAIVED_FOR]`. It is always a subset of `applies_to`.
  - A fee is charged when the account's product is in `applies_to` and not in `waived_for`.

## Hero ID ranges

Hero records come from `hero_fixtures.yaml`. Background records never use these ID ranges.

| Entity | Hero IDs | Background IDs |
|---|---|---|
| Customer | `C-1001`, `C-1002` | `C-5000` and up |
| Account | `A-1001` to `A-1003`, `A-2001` | `A-5000` and up |
| Counterparty | `CP-1001` to `CP-1016` | `CP-5000` and up |
| Transaction | `T-1001` to `T-1306` | `T-50000` and up |
| ComplianceAlert | `AL-1001` | `AL-5000` and up |
| ScheduledPayment | `SP-1001` to `SP-1004` | `SP-5000` and up |

Background transactions may use a hero counterparty such as Acme Corp, but they never touch a hero customer or account.

## Loan fraud CSVs (`generated/fraud/`)

The staff demo's data lives in its own folder. `generate-data` writes it with its own random seed, so the customer CSVs do not change. `load-structured` loads both folders. `Account`, `Transaction` and `Counterparty` rows come from both folders, and their keys never collide.

The conventions above apply, with these additions:

- **Datetimes:** `submitted_at` is ISO 8601 UTC with a `Z` suffix.
- **Dates:** `registered_on`, `first_seen` and `closed_date` are `YYYY-MM-DD`.
- **Amounts:** `principal`, `balance`, `approval_limit` and `stated_annual_revenue` follow the amount format. A loan's `balance` is the amount still owed, or the amount written off for a `WRITTEN_OFF` loan.
- **Percents:** `percent` is a plain number from 0 to 100.
- **Transfers:** A transfer between two bank accounts is one `WIRE_OUT` or `ACH_OUT` on the sender's account, with a `TO_ACCOUNT` link to the receiving account. There is no matching credit row. It counts as a debit for the sender and a credit for the receiver.
- **Balances:** Every fraud transaction is `POSTED`, so `available_balance` equals `ledger_balance`.

### Node CSVs

| File | Label | Columns |
|---|---|---|
| `bankers.csv` | `Banker` | `banker_id`, `name`, `role`, `approval_limit` |
| `fraud_reviewers.csv` | `FraudReviewer` | `reviewer_id`, `name` |
| `persons.csv` | `Person` | `person_id`, `name` |
| `businesses.csv` | `Business` | `business_id`, `name`, `industry`, `registered_on` |
| `phones.csv` | `Phone` | `number` |
| `emails.csv` | `Email` | `address` |
| `addresses.csv` | `Address` | `address_id`, `line1`, `city`, `state`, `kind` |
| `devices.csv` | `Device` | `device_id`, `first_seen` |
| `loans.csv` | `Loan` | `loan_id`, `type`, `principal`, `balance`, `status`, `opened_date`, `closed_date` |
| `loan_applications.csv` | `LoanApplication` | `application_id`, `type`, `amount`, `stated_annual_revenue`, `submitted_at`, `status` |
| `accounts.csv` | `Account` | The same columns as `generated/accounts.csv` |
| `transactions.csv` | `Transaction` | The same columns as `generated/transactions.csv` |
| `counterparties.csv` | `Counterparty` | The same columns as `generated/counterparties.csv` |

### Relationship CSVs

| File | Relationship | Columns |
|---|---|---|
| `rel_manages_customer.csv` | `(Banker)-[:MANAGES]->(Customer)` | `banker_id`, `customer_id` |
| `rel_manages_business.csv` | `(Banker)-[:MANAGES]->(Business)` | `banker_id`, `business_id` |
| `rel_person_owns.csv` | `(Person)-[:OWNS {percent}]->(Business)` | `person_id`, `business_id`, `percent` |
| `rel_business_owns.csv` | `(Business)-[:OWNS {percent}]->(Business)` | `owner_business_id`, `business_id`, `percent` |
| `rel_director_of.csv` | `(Person)-[:DIRECTOR_OF]->(Business)` | `person_id`, `business_id` |
| `rel_person_has_phone.csv` | `(Person)-[:HAS_PHONE]->(Phone)` | `person_id`, `number` |
| `rel_business_has_phone.csv` | `(Business)-[:HAS_PHONE]->(Phone)` | `business_id`, `number` |
| `rel_person_has_email.csv` | `(Person)-[:HAS_EMAIL]->(Email)` | `person_id`, `address` |
| `rel_business_has_email.csv` | `(Business)-[:HAS_EMAIL]->(Email)` | `business_id`, `address` |
| `rel_person_has_address.csv` | `(Person)-[:HAS_ADDRESS]->(Address)` | `person_id`, `address_id` |
| `rel_business_has_address.csv` | `(Business)-[:HAS_ADDRESS]->(Address)` | `business_id`, `address_id` |
| `rel_business_holds.csv` | `(Business)-[:HOLDS {role}]->(Account)` | `business_id`, `account_id`, `role` |
| `rel_applied_for.csv` | `(Business)-[:APPLIED_FOR]->(LoanApplication)` | `business_id`, `application_id` |
| `rel_submitted_from.csv` | `(LoanApplication)-[:SUBMITTED_FROM]->(Device)` | `application_id`, `device_id` |
| `rel_borrower_on.csv` | `(Business)-[:BORROWER_ON]->(Loan)` | `business_id`, `loan_id` |
| `rel_has_transaction.csv` | `(Account)-[:HAS_TRANSACTION]->(Transaction)` | `account_id`, `transaction_id` |
| `rel_paid_to.csv` | `(Transaction)-[:PAID_TO]->(Counterparty)` | `transaction_id`, `counterparty_id` |
| `rel_received_from.csv` | `(Transaction)-[:RECEIVED_FROM]->(Counterparty)` | `transaction_id`, `counterparty_id` |
| `rel_to_account.csv` | `(Transaction)-[:TO_ACCOUNT]->(Account)` | `transaction_id`, `account_id` |

`rel_manages_customer.csv` points at customers in `generated/customers.csv`. Every customer and every business has exactly one banker.

### Controlled values

| Field | Values |
|---|---|
| `Banker.role` | `RELATIONSHIP_MANAGER` |
| `Address.kind` | `HOME`, `OFFICE`, `REGISTERED_AGENT`, `COWORKING` |
| `Loan.type`, `LoanApplication.type` | `TERM_LOAN`, `BUSINESS_LINE`, `EQUIPMENT`, `COMMERCIAL_REAL_ESTATE` |
| `Loan.status` | `ACTIVE`, `PAID_OFF`, `WRITTEN_OFF` |
| `LoanApplication.status` | `SUBMITTED`, `IN_REVIEW`, `APPROVED`, `DECLINED` |
| `HOLDS.role` for a business | `PRIMARY` |

### Fraud ID ranges

| Entity | Hero IDs | Background IDs |
|---|---|---|
| Banker | `RM-03`, `RM-05`, `RM-07`, `RM-09` | `RM-11` and up |
| FraudReviewer | `FR-02` | `FR-01` |
| Person | `P-1001` to `P-1007` | `P-5001` and up |
| Business | `B-1001` to `B-1008` | `B-5001` and up |
| Phone | `+1-555-0610` to `+1-555-0620` | `+1-312-555-1000` and up |
| Address | `ADDR-1001` to `ADDR-1013`, `ADDR-1900` | `ADDR-6000` and up |
| Device | `DEV-1001` to `DEV-1003` | `DEV-5001` and up |
| Loan | `L-1001` | `L-5001` and up |
| LoanApplication | `APP-1001` to `APP-1005` | `APP-5001` and up |
| Account | `A-3001` to `A-3006` | `A-7000` and up |
| Counterparty | `CP-3001` to `CP-3013` | `CP-7000` and up |
| Transaction | `T-30001` to `T-30609` | `T-90000` and up |

`ADDR-1900` is the registered agent address in Dover. Background businesses list it too, so more than 200 businesses share it.

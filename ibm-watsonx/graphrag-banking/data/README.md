# Data

| Path | What it is | Committed |
|---|---|---|
| `policy_facts.yaml` | Canonical products, policies and rules. Schema in its header comment. | Yes |
| `hero_fixtures.yaml` | Hand-written records for the hero scenarios in PRD section 4. | Yes |
| `policy_templates/` | Policy Markdown with `${placeholders}`. | Yes |
| `policies/` | Rendered policy documents, written by `render-policies`. | Yes |
| `generated/` | CSVs written by `generate-data`. Rebuilt on every `make ingest`. | No |

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
- `fee_rules[]`, `hold_rules[]` and `compliance_rules[]` become `FeeRule`, `HoldRule` and `ComplianceRule` nodes, keyed on `rule_code`.
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

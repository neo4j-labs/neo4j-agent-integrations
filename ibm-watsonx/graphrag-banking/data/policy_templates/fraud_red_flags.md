# Fraud Red Flags in Lending

Effective ${pol_fraud_effective_date}. This policy is for bank staff. It lists the signs that a credit application may be part of a fraud scheme. A red flag is a reason to look closer. It is not proof that a client did anything wrong.

## How to describe red flags

Describe what the evidence shows, such as "this application matches two red flags." Never say that a client committed fraud. The fraud team decides what the evidence means.

## Beneficial owner with a prior loss

Rule code: FRAUD-PRIOR-LOSS

It is a red flag when a beneficial owner of the applicant also owned a business whose loan the bank wrote off in the last ${fraud_prior_loss_years} years. The owner may be applying again through a new business.

## Shared identifiers

Rule code: FRAUD-SHARED-ID

It is a red flag when applicants with no stated relationship share a phone number, an email address, a device, a home or office address, or a director. Businesses that look unrelated but share these details may be controlled by the same person.

## Circular money flows

Rule code: FRAUD-CIRCULAR-FLOW

It is a red flag when money leaves the applicant for related businesses and comes back as deposits. Look back ${fraud_circular_flow_lookback_days} days. Deposits that come from businesses in the applicant's connected group, after money went out to that group, do not count as verified revenue. Remove them before you check the size of a loan against revenue.

## Registered agent and coworking addresses

Rule code: FRAUD-REG-AGENT

A shared registered agent address or coworking address is not a red flag on its own. Hundreds of unrelated businesses can list the same registered agent or coworking space. Treat a shared address of this kind as a red flag only when the businesses also share other identifiers.

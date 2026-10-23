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

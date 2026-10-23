// Beat 3 of the demo: the graph behind the Scenario A answer.
//
// Run it in the Aura Query tool and switch to the graph view. It draws the
// path the agent followed for "Why did my wire transfer to Acme Corp fail
// yesterday, and will I be charged a penalty fee?":
//
//   Marcus -> Premium Checking account -> $5,000 wire to Acme Corp (HELD)
//          -> compliance alert -> review rule -> policy text
//   account -> Premium Checking product <- wire fee rules that waive it
//          -> policy text
//
// Save it in your own Aura console as "Scenario A proof". Aura saved queries
// belong to the user who saves them, so each presenter saves their own copy.

MATCH customer_to_wire = (c:Customer {customer_id: 'C-1001'})-[:HOLDS]->(a:Account)
      -[:HAS_TRANSACTION]->(t:Transaction {type: 'WIRE_OUT'})-[:PAID_TO]->(:Counterparty {name: 'Acme Corp'})
MATCH product = (a)-[:IS_PRODUCT]->(p:AccountProduct)
OPTIONAL MATCH alert_to_policy = (t)-[:RAISED]->(:ComplianceAlert)-[:UNDER_RULE]->(:ComplianceRule)
      -[:FROM_CHUNK]->(:Chunk)
OPTIONAL MATCH fee_waivers = (p)<-[:WAIVED_FOR]-(fee:FeeRule)-[:FROM_CHUNK]->(:Chunk)
WHERE fee.rule_code IN ['FEE-WIRE-OUT', 'FEE-WIRE-RETURN']
RETURN customer_to_wire, product, alert_to_policy, fee_waivers

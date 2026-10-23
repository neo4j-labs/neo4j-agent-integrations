// The graph behind the Scenario J referral.
//
// Run it in the Aura Query tool after the fraud_referral flow has written a
// referral for Ortega Builders, and switch to the graph view. It draws:
//
//   Dana -> referral -> APP-1001 <- Ortega Builders
//   referral -> connected group
//   referral -> each cited red flag rule -> policy text
//   referral -> Sam Price
//
// It shows the newest referral for APP-1001, whatever its status, so it also
// works after Sam accepts or closes it. `make demo-reset` deletes every
// referral, and then this query returns nothing.
//
// Save it in your own Aura console as "Scenario J proof". Aura saved queries
// belong to the user who saves them, so each presenter saves their own copy.

MATCH (r:FraudReferral)-[:FOR_APPLICATION]->(:LoanApplication {application_id: 'APP-1001'})
WITH r ORDER BY r.created_at DESC LIMIT 1
MATCH referral_to_application = (:Banker)-[:SUBMITTED]->(r)-[:FOR_APPLICATION]->(:LoanApplication)
      <-[:APPLIED_FOR]-(:Business)
MATCH reviewer = (r)-[:ASSIGNED_TO]->(:FraudReviewer)
OPTIONAL MATCH group = (r)-[:ABOUT_GROUP]->(:ConnectedGroup)
OPTIONAL MATCH rules_to_policy = (r)-[:CITES]->(:FraudRule)-[:FROM_CHUNK]->(:Chunk)
RETURN referral_to_application, reviewer, group, rules_to_policy

---
name: custom-investment
version: 1.0.0
description: Specialized enterprise skill to fetch internal portfolio investment relationships out of Neo4j.
metadata:
	dependencies:
		- neo4j>=5.0.0
---

# Custom Investments Skill

This skill allows the managed agent to interact directly with internal portfolio nodes inside the corporate graph database to perform optimized tracking evaluations.

## Expected Environment Variables
The execution sandbox requires the following runtime injections to function correctly:

`NEO4J_URI`
`NEO4J_USER`
`NEO4J_PASSWORD`
`NEO4J_DATABASE`
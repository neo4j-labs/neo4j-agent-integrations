resource "snowflake_secret_with_basic_authentication" "neo4j_credentials" {
  name     = "NEO4J_CREDENTIALS"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name
  username = var.neo4j_username
  password = var.neo4j_password
}

resource "snowflake_network_rule" "neo4j_access_rule" {
  name     = "NEO4J_ACCESS_RULE"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  mode       = "EGRESS"
  type       = "HOST_PORT"
  value_list = [var.neo4j_host]

  comment = "Network rule for Neo4j database access"
}

resource "snowflake_external_access_integration" "neo4j_access_integration" {
  name                  = "NEO4J_ACCESS_INTEGRATION"
  enabled               = true
  allowed_network_rules = [snowflake_network_rule.neo4j_access_rule.fully_qualified_name]
  allowed_authentication_secrets {
    secrets = [snowflake_secret_with_basic_authentication.neo4j_credentials.fully_qualified_name]
  }
}

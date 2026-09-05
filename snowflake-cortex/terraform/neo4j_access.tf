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

# External Access Integration has no first-class provider resource yet, so we
# drive it through snowflake_execute.
resource "snowflake_execute" "neo4j_access_integration" {
  execute = <<-SQL
    CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION ${local.access_integration_name}
      ALLOWED_NETWORK_RULES = (${snowflake_network_rule.neo4j_access_rule.fully_qualified_name})
      ALLOWED_AUTHENTICATION_SECRETS = (${snowflake_secret_with_basic_authentication.neo4j_credentials.fully_qualified_name})
      ENABLED = true;
  SQL
  revert  = "DROP INTEGRATION IF EXISTS ${local.access_integration_name};"
}

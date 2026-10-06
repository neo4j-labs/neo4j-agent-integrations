locals {
  agent_spec = templatefile("${path.module}/../../shared/agent/agent_spec.yaml.tftpl", {
    database                   = snowflake_database.database.name
    schema                     = snowflake_schema.schema.name
    get_organization_investors = snowflake_function_sql.get_organization_investors.name
    analyze_relationships      = snowflake_function_sql.analyze_relationships.name
    search_news_articles       = snowflake_function_sql.search_news_articles.name
    warehouse                  = var.warehouse
    customer_accounts          = snowflake_semantic_view.customer_accounts.name
    find_organizations         = snowflake_function_sql.find_organizations.name
    query_neo4j                = snowflake_function_python.query_neo4j.name
  })
}

resource "snowflake_cortex_agent" "neo4j_agent" {
  database      = snowflake_schema.schema.database
  schema        = snowflake_schema.schema.name
  name          = "NEO4J_RESEARCH_AGENT"
  specification = local.agent_spec

  profile {
    display_name = "Neo4j research agent"
  }
}

resource "snowflake_grant_privileges_to_account_role" "agent_grant" {
  account_role_name = snowflake_account_role.user.name
  privileges        = ["USAGE"]

  on_schema_object {
    object_type = "AGENT"
    object_name = snowflake_cortex_agent.neo4j_agent.fully_qualified_name
  }
}

locals {
  agent_spec = templatefile("${path.module}/templates/agent_spec.yaml.tftpl", {
    database                   = snowflake_database.database.name
    schema                     = snowflake_schema.schema.name
    get_organization_investors = snowflake_function_sql.get_organization_investors.name
    analyze_relationships      = snowflake_function_sql.analyze_relationships.name
    search_news_articles       = snowflake_function_sql.search_news_articles.name
  })
}

resource "snowflake_execute" "neo4j_agent" {
  execute = join("\n", [
    "CREATE OR REPLACE AGENT ${snowflake_schema.schema.fully_qualified_name}.${local.agent_name}",
    "  PROFILE = '{\"display_name\": \"Neo4j research agent\"}'",
    "  FROM SPECIFICATION $$",
    local.agent_spec,
    "$$",
  ])
  revert = "DROP AGENT IF EXISTS ${snowflake_schema.schema.fully_qualified_name}.\"${local.agent_name}\";"
}

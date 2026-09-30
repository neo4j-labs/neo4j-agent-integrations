# Customer accounts in Snowflake. The Cortex Analyst tool reads them.

resource "snowflake_view" "customer_accounts" {
  name      = "CUSTOMER_ACCOUNTS"
  database  = snowflake_schema.schema.database
  schema    = snowflake_schema.schema.name
  comment   = "Sample CRM accounts"
  statement = file("${path.module}/../../shared/sql/customer_accounts.sql")
}

# Matches shared/sql/customer_accounts_semantic_view.sql, which the Snowsight guide runs.
resource "snowflake_semantic_view" "customer_accounts" {
  name     = "CUSTOMER_ACCOUNTS_SV"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name
  comment  = "Customer accounts for Cortex Analyst"

  tables {
    table_alias = "ACCOUNTS"
    table_name  = snowflake_view.customer_accounts.fully_qualified_name
    primary_key = ["ACCOUNT_ID"]
    comment     = "Our customer accounts"
  }

  facts {
    qualified_expression_name = "\"ACCOUNTS\".\"ARR_USD\""
    sql_expression            = "ARR_USD"
    comment                   = "Annual recurring revenue in USD"
  }

  dimensions {
    qualified_expression_name = "\"ACCOUNTS\".\"ACCOUNT_ID\""
    sql_expression            = "ACCOUNT_ID"
    comment                   = "Account ID in the CRM"
  }
  dimensions {
    qualified_expression_name = "\"ACCOUNTS\".\"ORGANIZATION_ID\""
    sql_expression            = "ORGANIZATION_ID"
    comment                   = "The company's organization ID"
  }
  dimensions {
    qualified_expression_name = "\"ACCOUNTS\".\"ACCOUNT_NAME\""
    sql_expression            = "ACCOUNT_NAME"
    comment                   = "Company name"
  }
  dimensions {
    qualified_expression_name = "\"ACCOUNTS\".\"SEGMENT\""
    sql_expression            = "SEGMENT"
  }
  dimensions {
    qualified_expression_name = "\"ACCOUNTS\".\"RENEWAL_DATE\""
    sql_expression            = "RENEWAL_DATE"
    comment                   = "Next contract renewal"
  }
  dimensions {
    qualified_expression_name = "\"ACCOUNTS\".\"HEALTH\""
    sql_expression            = "HEALTH"
    comment                   = "Account health: Green, Amber or Red"
  }

  metrics {
    semantic_expression {
      qualified_expression_name = "\"ACCOUNTS\".\"TOTAL_ARR\""
      sql_expression            = "SUM(\"ACCOUNTS\".\"ARR_USD\")"
      comment                   = "Total annual recurring revenue in USD"
    }
  }
}

# SELECT on the semantic view is enough. The role needs no grant on the view.
resource "snowflake_grant_privileges_to_account_role" "semantic_view_grant" {
  account_role_name = snowflake_account_role.user.name
  privileges        = ["SELECT"]

  on_schema_object {
    object_type = "SEMANTIC VIEW"
    object_name = snowflake_semantic_view.customer_accounts.fully_qualified_name
  }
}

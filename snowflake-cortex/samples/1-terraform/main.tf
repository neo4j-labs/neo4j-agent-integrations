terraform {
  required_version = ">= 1.4"

  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 2.21"
    }
  }
}

provider "snowflake" {
  organization_name = var.snowflake_organization_name
  account_name      = var.snowflake_account_name
  user              = var.snowflake_service_user
  role              = "TERRAFORM_SVC"
  authenticator     = "SNOWFLAKE_JWT"
  private_key       = file(var.snowflake_private_key_path)
  warehouse         = var.warehouse

  preview_features_enabled = [
    "snowflake_external_access_integration_resource",
    "snowflake_function_python_resource",
    "snowflake_function_sql_resource",
    "snowflake_semantic_view_resource",
  ]
}

resource "snowflake_database" "database" {
  name    = var.database_name
  comment = "Neo4j integration test database"
}

resource "snowflake_schema" "schema" {
  database = snowflake_database.database.name
  name     = "NEO4J_AGENT_SCHEMA"
}

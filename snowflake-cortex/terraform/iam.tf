resource "snowflake_account_role" "user" {
  name = "USER"
}

resource "snowflake_grant_account_role" "user_grant" {
  role_name = snowflake_account_role.user.name
  user_name = var.snowflake_user
}

resource "snowflake_grant_privileges_to_account_role" "database_grant" {
  account_role_name = snowflake_account_role.user.name
  privileges        = ["USAGE"]

  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.database.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "schema_grant" {
  account_role_name = snowflake_account_role.user.name
  privileges        = ["USAGE"]

  on_schema {
    schema_name = snowflake_schema.schema.fully_qualified_name
  }
}

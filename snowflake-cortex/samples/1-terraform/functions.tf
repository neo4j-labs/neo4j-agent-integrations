# --- Model stage: the embedding model the UDFs import ---

resource "snowflake_stage_internal" "model_stage" {
  name     = "MODEL_STAGE"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  encryption {
    snowflake_full {}
  }

  directory {
    enable       = true
    auto_refresh = "false"
  }

  comment = "Stage for storing ML model files"
}

resource "terraform_data" "upload_model" {
  triggers_replace = {
    stage_id = snowflake_stage_internal.model_stage.id
    model_hash = sha256(join("", [
      for f in sort(fileset("${path.module}/../../shared/model/minilm", "**")) :
      filesha256("${path.module}/../../shared/model/minilm/${f}")
    ]))
  }

  provisioner "local-exec" {
    command = templatefile("${path.module}/scripts/upload_model.sh.tftpl", {
      model_dir        = abspath("${path.module}/../../shared/model")
      account          = "${var.snowflake_organization_name}-${var.snowflake_account_name}"
      service_user     = var.snowflake_service_user
      private_key_path = pathexpand(var.snowflake_private_key_path)
      stage            = snowflake_stage_internal.model_stage.fully_qualified_name
    })
  }
}

# --- Python UDFs ---

locals {
  # Identical settings (with the imports and secrets below) let both UDFs share one Python runtime.
  python_udf_common = {
    runtime_version              = "3.13"
    packages                     = ["neo4j", "sentence-transformers"]
    external_access_integrations = [snowflake_external_access_integration.neo4j_access_integration.name]
  }
}

resource "snowflake_function_python" "query_neo4j" {
  name     = "QUERY_NEO4J"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  arguments {
    arg_name      = "CYPHER"
    arg_data_type = "VARCHAR"
  }
  # Optional, because custom tools cannot pass OBJECT arguments. The query_neo4j tool passes only the Cypher.
  arguments {
    arg_name          = "PARAMS"
    arg_data_type     = "OBJECT"
    arg_default_value = "{}"
  }

  return_type                  = "VARIANT"
  runtime_version              = local.python_udf_common.runtime_version
  packages                     = local.python_udf_common.packages
  external_access_integrations = local.python_udf_common.external_access_integrations

  imports {
    path_on_stage  = "minilm/"
    stage_location = snowflake_stage_internal.model_stage.fully_qualified_name
  }
  secrets {
    secret_variable_name = "cred"
    secret_id            = snowflake_secret_with_basic_authentication.neo4j_credentials.fully_qualified_name
  }

  handler             = "query_neo4j"
  function_definition = file("${path.module}/../../shared/functions/query_neo4j.py")
  comment             = "Executes a read-only Cypher query against the Neo4j database"

  depends_on = [terraform_data.upload_model]
}

resource "snowflake_function_python" "generate_embeddings" {
  name     = "GENERATE_EMBEDDINGS"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  arguments {
    arg_name      = "INPUT_TEXT"
    arg_data_type = "VARCHAR"
  }

  return_type                  = "VARIANT"
  runtime_version              = local.python_udf_common.runtime_version
  packages                     = local.python_udf_common.packages
  external_access_integrations = local.python_udf_common.external_access_integrations

  imports {
    path_on_stage  = "minilm/"
    stage_location = snowflake_stage_internal.model_stage.fully_qualified_name
  }
  secrets {
    secret_variable_name = "cred"
    secret_id            = snowflake_secret_with_basic_authentication.neo4j_credentials.fully_qualified_name
  }

  handler             = "generate_embeddings"
  function_definition = file("${path.module}/../../shared/functions/generate_embeddings.py")
  comment             = "Embedding function using sentence transformers"

  depends_on = [terraform_data.upload_model]
}

# --- SQL functions: the agent's fixed Neo4j tools ---

locals {
  query_neo4j_fqn         = "\"${snowflake_function_python.query_neo4j.database}\".\"${snowflake_function_python.query_neo4j.schema}\".\"${snowflake_function_python.query_neo4j.name}\""
  generate_embeddings_fqn = "\"${snowflake_function_python.generate_embeddings.database}\".\"${snowflake_function_python.generate_embeddings.schema}\".\"${snowflake_function_python.generate_embeddings.name}\""
}

resource "snowflake_function_sql" "find_organizations" {
  name     = "FIND_ORGANIZATIONS"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  arguments {
    arg_name      = "NAME"
    arg_data_type = "VARCHAR"
  }

  return_type = "VARIANT"
  comment     = "Finds organizations by name; returns their ids"

  function_definition = templatefile("${path.module}/../../shared/sql/find_organizations.sql", {
    query_neo4j = local.query_neo4j_fqn
  })
}

resource "snowflake_function_sql" "get_organization_investors" {
  name     = "GET_ORGANIZATION_INVESTORS"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  arguments {
    arg_name      = "ORGANIZATION_ID"
    arg_data_type = "VARCHAR"
  }

  return_type = "VARIANT"
  comment     = "Returns investors for a given organization"

  function_definition = templatefile("${path.module}/../../shared/sql/get_organization_investors.sql", {
    query_neo4j = local.query_neo4j_fqn
  })
}

resource "snowflake_function_sql" "analyze_relationships" {
  name     = "ANALYZE_RELATIONSHIPS"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  arguments {
    arg_name      = "ORGANIZATION_ID"
    arg_data_type = "VARCHAR"
  }
  arguments {
    arg_name          = "LIMIT"
    arg_data_type     = "NUMBER"
    arg_default_value = "20"
  }
  arguments {
    arg_name          = "MAX_DEPTH"
    arg_data_type     = "INT"
    arg_default_value = "2"
  }

  return_type = "VARIANT"
  comment     = "Analyzes relationship paths between organizations"

  function_definition = templatefile("${path.module}/../../shared/sql/analyze_relationships.sql", {
    query_neo4j = local.query_neo4j_fqn
  })
}

resource "snowflake_function_sql" "search_news_articles" {
  name     = "SEARCH_NEWS_ARTICLES"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  arguments {
    arg_name      = "ORGANIZATION_ID"
    arg_data_type = "VARCHAR"
  }
  arguments {
    arg_name      = "TOPIC"
    arg_data_type = "VARCHAR"
  }
  arguments {
    arg_name          = "LIMIT"
    arg_data_type     = "NUMBER"
    arg_default_value = "20"
  }

  return_type = "VARIANT"
  comment     = "Finds news about an organization that has content about the given topic"

  function_definition = templatefile("${path.module}/../../shared/sql/search_news_articles.sql", {
    query_neo4j         = local.query_neo4j_fqn
    generate_embeddings = local.generate_embeddings_fqn
  })
}

resource "snowflake_grant_privileges_to_account_role" "grant_function_permissions" {
  for_each = {
    find_organizations         = snowflake_function_sql.find_organizations.fully_qualified_name
    get_organization_investors = snowflake_function_sql.get_organization_investors.fully_qualified_name
    analyze_relationships      = snowflake_function_sql.analyze_relationships.fully_qualified_name
    search_news_articles       = snowflake_function_sql.search_news_articles.fully_qualified_name
    # The query_neo4j tool calls this UDF directly. The embedding UDF needs no grant.
    query_neo4j = snowflake_function_python.query_neo4j.fully_qualified_name
  }
  account_role_name = snowflake_account_role.user.name
  privileges        = ["USAGE"]

  on_schema_object {
    object_type = "FUNCTION"
    object_name = each.value
  }
}

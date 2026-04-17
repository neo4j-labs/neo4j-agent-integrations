# --- Model stage: holds SentenceTransformer files for the embedding UDF ---

resource "snowflake_stage_internal" "model_stage" {
  name     = "MODEL_STAGE"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  encryption {
    snowflake_full {}
  }

  directory {
    enable       = true
    auto_refresh = false
  }

  comment = "Stage for storing ML model files"
}

resource "null_resource" "upload_model" {
  triggers = {
    stage_id = snowflake_stage_internal.model_stage.id
    model_hash = sha256(join("", [
      for f in sort(fileset("${path.module}/minilm", "**")) :
      filesha256("${path.module}/minilm/${f}")
    ]))
  }

  provisioner "local-exec" {
    command = templatefile("${path.module}/scripts/upload_model.sh.tftpl", {
      module_path      = path.module
      account_locator  = "${var.snowflake_organization_name}-${var.snowflake_account_name}"
      service_user     = var.snowflake_service_user
      private_key_path = pathexpand(var.snowflake_private_key_path)
      database         = snowflake_schema.schema.database
      schema           = snowflake_schema.schema.name
      stage_name       = snowflake_stage_internal.model_stage.name
    })
  }

  depends_on = [
    snowflake_stage_internal.model_stage
  ]
}

# --- Python UDFs ---

locals {
  # all python  UDFs share the same config (secrets, imports, runtime, packages, external access) so a runtime in the
  # warehouse can be reused for query neo4j and generate embeddings
  python_udf_common = {
    runtime_version              = "3.13"
    packages                     = ["neo4j", "sentence-transformers"]
    external_access_integrations = [local.access_integration_name]
  }
}

resource "snowflake_function_python" "query_neo4j" {
  name     = "QUERY_NEO4J"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  arguments {
    arg_name      = "cypher"
    arg_data_type = "VARCHAR"
  }
  arguments {
    arg_name      = "params"
    arg_data_type = "OBJECT"
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
  function_definition = file("${path.module}/../functions/query_neo4j.py")
  comment             = "Executes a cypher query against the Neo4j database"

  depends_on = [
    null_resource.upload_model,
    snowflake_execute.neo4j_access_integration,
  ]
}

resource "snowflake_function_python" "generate_embeddings" {
  name     = "GENERATE_EMBEDDINGS"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  arguments {
    arg_name      = "query"
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
  function_definition = file("${path.module}/../functions/generate_embeddings.py")
  comment             = "Embedding function using sentence transformers"

  depends_on = [
    null_resource.upload_model,
    snowflake_execute.neo4j_access_integration,
  ]
}

# --- SQL wrapper functions (agent tools) ---

locals {
  query_neo4j_fqn         = "\"${snowflake_function_python.query_neo4j.database}\".\"${snowflake_function_python.query_neo4j.schema}\".\"${snowflake_function_python.query_neo4j.name}\""
  generate_embeddings_fqn = "\"${snowflake_function_python.generate_embeddings.database}\".\"${snowflake_function_python.generate_embeddings.schema}\".\"${snowflake_function_python.generate_embeddings.name}\""
}

resource "snowflake_function_sql" "get_organization_investors" {
  name     = "GET_ORGANIZATION_INVESTORS"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  arguments {
    arg_name      = "COMPANY"
    arg_data_type = "VARCHAR"
  }

  return_type = "VARIANT"
  comment     = "Returns investors for a given organization"

  function_definition = templatefile("${path.module}/sql/get_organization_investors.sql", {
    query_neo4j = local.query_neo4j_fqn
  })
}

resource "snowflake_function_sql" "analyze_relationships" {
  name     = "ANALYZE_RELATIONSHIPS"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  arguments {
    arg_name      = "COMPANY"
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

  function_definition = templatefile("${path.module}/sql/analyze_relationships.sql", {
    query_neo4j = local.query_neo4j_fqn
  })
}

resource "snowflake_function_sql" "search_news_articles" {
  name     = "SEARCH_NEWS_ARTICLES"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  arguments {
    arg_name      = "COMPANY"
    arg_data_type = "VARCHAR"
  }
  arguments {
    arg_name      = "QUERY"
    arg_data_type = "VARCHAR"
  }
  arguments {
    arg_name          = "LIMIT"
    arg_data_type     = "NUMBER"
    arg_default_value = "20"
  }

  return_type = "VARIANT"
  comment     = "Find news about the given <company> that has content about the given <query>"

  function_definition = templatefile("${path.module}/sql/search_news_articles.sql", {
    query_neo4j         = local.query_neo4j_fqn
    generate_embeddings = local.generate_embeddings_fqn
  })
}

resource "snowflake_grant_privileges_to_account_role" "grant_function_permissions" {
  for_each = {
    get_organization_investors = snowflake_function_sql.get_organization_investors.fully_qualified_name
    analyze_relationships      = snowflake_function_sql.analyze_relationships.fully_qualified_name
    search_news_articles       = snowflake_function_sql.search_news_articles.fully_qualified_name
  }
  account_role_name = snowflake_account_role.user.name
  privileges        = ["USAGE"]

  on_schema_object {
    object_type = "FUNCTION"
    object_name = each.value
  }
}

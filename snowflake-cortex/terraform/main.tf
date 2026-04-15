terraform {
  required_version = ">= 1.0"

  required_providers {
    snowflake = {
      source = "snowflakedb/snowflake"
    }
  }
}

# default provider
provider "snowflake" {

  # Configure via environment variables:
  # SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD, SNOWFLAKE_REGION
  organization_name = var.snowflake_organization_name
  account_name      = var.snowflake_account_name
  user              = var.snowflake_service_user
  role              = "TERRAFORM_SVC"
  authenticator     = "SNOWFLAKE_JWT"
  private_key       = file(var.snowflake_private_key_path)

  # Warehouse required for Python UDF creation
  warehouse = var.warehouse

  # Enable preview features
  preview_features_enabled = [
    "snowflake_stage_internal_resource",
    "snowflake_function_python_resource",
    "snowflake_function_sql_resource"
  ]
}


# Database
resource "snowflake_database" "database" {
  name    = var.database_name
  comment = "Neo4j integration test database"
}

resource "snowflake_schema" "schema" {
  database = snowflake_database.database.name
  name     = "TEST_SCHEMA"
}

locals {
  # TODO rename
  access_integration_name = "NEO4J_ACCESS_INTEGRATION2"
  agent_name              = "RESEARCH_AGENT"
}

# # Roles
# resource "snowflake_account_role" "developer" {
#   name = "DEVELOPER"
# }

resource "snowflake_account_role" "user" {
  name = "USER"
}

# # Grant roles to current user
# resource "snowflake_grant_account_role" "developer_grant" {
#   role_name = snowflake_account_role.developer.name
#   user_name = var.snowflake_user
# }

resource "snowflake_grant_account_role" "user_grant" {
  role_name = snowflake_account_role.user.name
  user_name = var.snowflake_user
}

# Neo4j credentials secret
resource "snowflake_secret_with_basic_authentication" "neo4j_credentials" {
  name     = "neo4j_credentials2" // TODO
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name
  username = var.neo4j_username
  password = var.neo4j_password
}

# Network rule for Neo4j access
resource "snowflake_network_rule" "neo4j_access_rule" {
  name     = "neo4j_access_rule2" // TODO
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  mode       = "EGRESS"
  type       = "HOST_PORT"
  value_list = [var.neo4j_host]

  comment = "Network rule for Neo4j database access"
}

resource "snowflake_execute" "neo4j_access_integration" {
  execute = <<EOT
      CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION ${local.access_integration_name}
        ALLOWED_NETWORK_RULES = (${snowflake_network_rule.neo4j_access_rule.fully_qualified_name})
        ALLOWED_AUTHENTICATION_SECRETS = (${snowflake_secret_with_basic_authentication.neo4j_credentials.fully_qualified_name})
        ENABLED = true;
    EOT
  revert  = "DROP INTEGRATION IF EXISTS ${local.access_integration_name};"
  depends_on = [
    snowflake_network_rule.neo4j_access_rule,
    snowflake_secret_with_basic_authentication.neo4j_credentials,
  ]
}

# Grant database permissions to user role
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

# Stage for model files (optional - for embedding UDF)
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

  comment    = "Stage for storing ML model files"
  depends_on = [snowflake_schema.schema]
}

# Upload SentenceTransformer embedding model files to stage
resource "null_resource" "upload_model" {
  triggers = {
    stage_id = snowflake_stage_internal.model_stage.id
    model_hash = sha256(join("", [
      for f in sort(fileset("${path.module}/minilm", "**")) :
      filesha256("${path.module}/minilm/${f}")
    ]))
  }

  provisioner "local-exec" {
    command = <<-EOT
      cd ${path.module}

      # Download model if not exists
      if [ ! -d "minilm" ]; then
        echo "Downloading sentence transformer model..."
        python3 -c "from sentence_transformers import SentenceTransformer; model = SentenceTransformer('all-MiniLM-L6-v2'); model.save('./minilm')"
      fi

      # Upload to stage
      echo "Uploading model files to Snowflake stage..."
      find minilm -type f | while read -r file; do
        rel_path="$${file#./minilm/}"
        dir_path=$(dirname "$rel_path")
        ~/bin/snowsql \
          -a ${var.snowflake_organization_name}-${var.snowflake_account_name} \
          -u TERRAFORM_SVC \
          --private-key-path ${var.snowflake_private_key_path} \
          -q "USE DATABASE ${snowflake_schema.schema.database}; USE SCHEMA ${snowflake_schema.schema.name}; PUT file://$file @${snowflake_stage_internal.model_stage.name}/$dir_path AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"
      done

      echo "✅ Upload complete!"
    EOT
  }

  depends_on = [
    snowflake_stage_internal.model_stage
  ]
}

# Query Neo4j UDF
resource "snowflake_function_python" "query_neo4j" {
  name     = "QUERY_NEO4J2" // TODO
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

  return_type     = "VARIANT"
  runtime_version = "3.13"
  packages        = ["neo4j", "sentence-transformers"]
  imports {
    path_on_stage  = "minilm/"
    stage_location = snowflake_stage_internal.model_stage.fully_qualified_name
  }
  external_access_integrations = [local.access_integration_name]
  secrets {
    secret_variable_name = "cred"
    secret_id            = snowflake_secret_with_basic_authentication.neo4j_credentials.fully_qualified_name
  }

  handler             = "query_neo4j"
  function_definition = file("${path.module}/../functions/query_neo4j.py")

  comment = "Executes a cypher query against the Neo4j database"

  depends_on = [
    snowflake_schema.schema,
    snowflake_stage_internal.model_stage,
    null_resource.upload_model,
    snowflake_execute.neo4j_access_integration,
    snowflake_secret_with_basic_authentication.neo4j_credentials
  ]
}

# Embedding test UDF (optional)
resource "snowflake_function_python" "generate_embeddings" {
  name     = "GENERATE_EMBEDDINGS"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  arguments {
    arg_name      = "query"
    arg_data_type = "VARCHAR"
  }

  return_type     = "VARIANT"
  runtime_version = "3.13"
  packages        = ["neo4j", "sentence-transformers"]
  imports {
    path_on_stage  = "minilm/"
    stage_location = snowflake_stage_internal.model_stage.fully_qualified_name
  }
  external_access_integrations = [local.access_integration_name]
  secrets {
    secret_variable_name = "cred"
    secret_id            = snowflake_secret_with_basic_authentication.neo4j_credentials.fully_qualified_name
  }

  handler             = "generate_embeddings"
  function_definition = file("${path.module}/../functions/generate_embeddings.py")

  comment = "Embedding function using sentence transformers"

  depends_on = [
    snowflake_schema.schema,
    snowflake_stage_internal.model_stage,
    null_resource.upload_model,
    snowflake_execute.neo4j_access_integration,
    snowflake_secret_with_basic_authentication.neo4j_credentials
  ]
}

# Get Organization Investors UDF
resource "snowflake_function_sql" "get_organization_investors" {
  name     = "GET_ORGANIZATION_INVESTORS"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  arguments {
    arg_name      = "company"
    arg_data_type = "VARCHAR"
  }
  return_type = "VARIANT"
  comment     = "Returns investors for a given organization"

  function_definition = <<-SQL
    "${snowflake_function_python.query_neo4j.database}"."${snowflake_function_python.query_neo4j.schema}"."${snowflake_function_python.query_neo4j.name}"(
        'MATCH (o:Organization {name: $company})
        RETURN o.name as name,
        [(o)-[:HAS_INVESTOR]->(p:Person) | p.name] as investor
        LIMIT 1',
        {'company': company}
    )
  SQL
  depends_on          = [snowflake_function_python.query_neo4j]

}

# Analyze Relationships UDF
resource "snowflake_function_sql" "analyze_relationships" {
  name     = "ANALYZE_RELATIONSHIPS"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  arguments {
    arg_name      = "company"
    arg_data_type = "VARCHAR"
  }

  arguments {
    arg_name          = "limit"
    arg_data_type     = "NUMBER"
    arg_default_value = "20"
  }

  arguments {
    arg_name          = "max_depth"
    arg_data_type     = "INT"
    arg_default_value = "2"
  }

  return_type = "VARIANT"

  function_definition = <<-SQL
    "${snowflake_function_python.query_neo4j.database}"."${snowflake_function_python.query_neo4j.schema}"."${snowflake_function_python.query_neo4j.name}"(
        CONCAT('MATCH path = (o1:Organization {name: $company})
                     -[*1..', 2, ']-(o2:Organization)
        WHERE o1 <> o2
        RETURN DISTINCT o2.name as organization,
               [r in relationships(path) | type(r)] as relationships,
               length(path) as distance
        ORDER BY distance
        LIMIT $limit'),
        {'company': company, 'limit': limit}
    )
  SQL

  comment = "Analyzes relationship paths between organizations"

  depends_on = [snowflake_function_python.query_neo4j]
}

# Analyze Relationships UDF
resource "snowflake_function_sql" "search_news_articles" {
  name     = "SEARCH_NEWS_ARTICLES"
  database = snowflake_schema.schema.database
  schema   = snowflake_schema.schema.name

  arguments {
    arg_name      = "company"
    arg_data_type = "VARCHAR"
  }

  arguments {
    arg_name      = "query"
    arg_data_type = "VARCHAR"
  }

  arguments {
    arg_name          = "limit"
    arg_data_type     = "NUMBER"
    arg_default_value = "20"
  }

  return_type = "VARIANT"

  function_definition = <<-SQL
    "${snowflake_function_python.query_neo4j.database}"."${snowflake_function_python.query_neo4j.schema}"."${snowflake_function_python.query_neo4j.name}"('
        MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)
        MATCH (a)-[:HAS_CHUNK]->(c:Chunk)
        CALL db.index.vector.queryNodes(''news_sbert'', $limit, $embedding)
        YIELD node, score
        WHERE node = c
        RETURN a.title as title,
               a.date as date,
               c.text as text,
               score
        ORDER BY score DESC',
        {
          'company': company,
          'limit': limit,
          'embedding': "${snowflake_function_python.generate_embeddings.database}"."${snowflake_function_python.generate_embeddings.schema}"."${snowflake_function_python.generate_embeddings.name}"(query)
        })
  SQL

  comment = "Find news about the given <company> that has content about the given <query>"
  depends_on = [
    snowflake_function_python.query_neo4j,
    snowflake_function_python.generate_embeddings,
  ]
}


resource "snowflake_grant_privileges_to_account_role" "grant_function_permissions" {
  for_each = {
    get_organization_investors : snowflake_function_sql.get_organization_investors.fully_qualified_name,
    analyze_relationships : snowflake_function_sql.analyze_relationships.fully_qualified_name,
    search_news_articles : snowflake_function_sql.search_news_articles.fully_qualified_name,
  }
  account_role_name = snowflake_account_role.user.name
  privileges        = ["USAGE"]

  on_schema_object {
    object_type = "FUNCTION"
    object_name = each.value
  }
  depends_on = [
    snowflake_function_sql.get_organization_investors,
    snowflake_function_sql.analyze_relationships,
    snowflake_function_sql.search_news_articles,
  ]
}


resource "snowflake_execute" "neo4j_agent" {
  execute = <<EOT
      CREATE OR REPLACE AGENT ${snowflake_schema.schema.fully_qualified_name}.${local.agent_name}
        PROFILE = '{"display_name": "Neo4j research agent"}'
        FROM SPECIFICATION $$
models:
  orchestration: auto
tools:
  - tool_spec:
      type: generic
      name: get_organization_investors
      description:  |-
        PROCEDURE/FUNCTION DETAILS:
        - Type: User-Defined Function
        - Language: SQL
        - Signature: (COMPANY VARCHAR)
        - Returns: VARIANT
        - Execution: User context with null input handling
        - Volatility: Stable
        - Primary Function: Neo4j Graph Database Query
        - Target: Organization and Investor relationships
        - Error Handling: Standard SQL error propagation

        DESCRIPTION:
        This user-defined function interfaces with a Neo4j graph database to retrieve investor information for a specified company. The function accepts a company name as input and returns a structured VARIANT object containing both the company name and an array of associated investor names. It leverages Neo4j's Cypher query language to traverse the graph database, specifically looking for Organization nodes with matching company names and following HAS_INVESTOR relationships to connected Person nodes. The function is designed to return data for a single company (LIMIT 1) and provides a clean interface for accessing graph-based relationship data from within a SQL environment. Users should ensure they have appropriate read permissions on both the SQL function and the underlying Neo4j database connection.

        USAGE SCENARIOS:
        - Retrieving investor information for company profile pages or reports
        - Performing due diligence research on company ownership and investment relationships
        - Supporting automated investor relationship mapping and analysis workflows
      input_schema:
        type: object
        properties:
          company:
            description: The name of the company
            type: string
        required:
          - company
tool_resources:
  get_organization_investors:
    execution_environment:
      query_timeout: 60
      type: warehouse
    identifier: '"TEST2"."TEST_SCHEMA"."GET_ORGANIZATION_INVESTORS"'
    name: GET_ORGANIZATION_INVESTORS(VARCHAR)
    type: function

$$
EOT
  revert  = "DROP AGENT IF EXISTS ${snowflake_schema.schema.fully_qualified_name}.\"${local.agent_name}\";"
  depends_on = [
    snowflake_function_sql.get_organization_investors,
  ]
}

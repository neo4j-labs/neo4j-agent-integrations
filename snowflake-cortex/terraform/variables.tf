variable "database_name" {
  description = "Name of the Snowflake database"
  type        = string
  default     = "TEST"
}

variable "snowflake_user" {
  description = "Snowflake user to grant roles to"
  type        = string
}

variable "snowflake_organization_name" {
  description = "Snowflake organization name"
  type        = string
}

variable "snowflake_account_name" {
  description = "Snowflake account name"
  type        = string
}

variable "snowflake_private_key_path" {
  description = "Path to the Snowflake private key file"
  type        = string
}

variable "snowflake_service_user" {
  description = "Snowflake service user"
  type        = string
}

variable "neo4j_host" {
  description = "Neo4j host and port (e.g., demo.neo4jlabs.com:7687)"
  type        = string
  default     = "demo.neo4jlabs.com:7687"
}

variable "neo4j_username" {
  description = "Neo4j username"
  type        = string
  default     = "companies"
  sensitive   = true
}

variable "neo4j_password" {
  description = "Neo4j password"
  type        = string
  sensitive   = true
}

variable "warehouse" {
  description = "Snowflake warehouse for Python UDF creation"
  type        = string
  default     = "COMPUTE_WH"
}


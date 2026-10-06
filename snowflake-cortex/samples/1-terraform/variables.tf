# --- Snowflake connection ---

variable "snowflake_organization_name" {
  description = "Snowflake organization name"
  type        = string
}

variable "snowflake_account_name" {
  description = "Snowflake account name"
  type        = string
}

variable "snowflake_service_user" {
  description = "Service user that runs Terraform. It needs the TERRAFORM_SVC role"
  type        = string
  default     = "TERRAFORM_SVC"
}

variable "snowflake_private_key_path" {
  description = "Path to the PEM-encoded private key for the service user"
  type        = string
}

variable "warehouse" {
  description = "Warehouse that Terraform uses. The USER role gets it too, for the agent's tools"
  type        = string
  default     = "COMPUTE_WH"
}

# --- Snowflake resources ---

variable "database_name" {
  description = "Name of the Snowflake database to create"
  type        = string
  default     = "NEO4J_AGENT"
}

variable "snowflake_user" {
  description = "User who gets the USER role"
  type        = string
}

# --- Neo4j connection ---

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

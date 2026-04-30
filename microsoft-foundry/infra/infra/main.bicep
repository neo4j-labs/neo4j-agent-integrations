targetScope = 'subscription'

@minLength(1)
@maxLength(20)
@description('Environment suffix added to all resource names. Examples: "dev", "prod", "chris-pr". Becomes part of the resource group name and every Azure resource in this deployment.')
param environmentName string

@description('Azure region for the resource group and all resources.')
param location string

@description('Workload token used in resource names. Combined with environmentName to produce resource names like rg-foundry-neo4j-dev.')
param workloadName string = 'foundry-neo4j'

@description('Neo4j Bolt URI, for example neo4j+s://demo.neo4jlabs.com:7687.')
param neo4jUri string

@description('Neo4j database name.')
param neo4jDatabase string = 'neo4j'

@description('Container image for the Neo4j MCP server.')
param containerImage string = 'mcp/neo4j:latest'

@description('Run the Neo4j MCP server in read-only mode. Use "true" or "false".')
@allowed([
  'true'
  'false'
])
param readOnly string = 'true'

@description('Container port used by the MCP HTTP transport.')
param mcpPort string = '8000'

@description('Expose the MCP server through public Container Apps ingress. Use "false" for private/internal deployments.')
@allowed([
  'true'
  'false'
])
param mcpExternalIngress string = 'true'

@description('Minimum Container Apps replicas.')
param mcpMinReplicas string = '1'

@description('Maximum Container Apps replicas.')
param mcpMaxReplicas string = '3'

@description('Container CPU cores, for example "0.5" or "1.0".')
param mcpCpu string = '0.5'

@description('Container memory, for example "1Gi" or "2Gi".')
param mcpMemory string = '1Gi'

@description('HTTP concurrent requests per replica before scale-out.')
param mcpConcurrentRequests string = '20'

@description('Neo4j MCP log format: "json" or "text".')
param neo4jLogFormat string = 'json'

@description('Enable Neo4j MCP telemetry. Use "true" or "false".')
@allowed([
  'true'
  'false'
])
param neo4jTelemetry string = 'true'

@description('Number of nodes sampled for Neo4j schema inference.')
param neo4jSchemaSampleSize string = '100'

@description('CORS allowed origins for the MCP HTTP server. Empty disables CORS.')
param neo4jAllowedOrigins string = ''

@description('Provision a Microsoft Foundry account, project, and model deployment alongside the Neo4j MCP server. Use "true" or "false". Set to "false" if you already have a Foundry project and just want the MCP endpoint.')
@allowed([
  'true'
  'false'
])
param createFoundryProject string = 'true'

@description('Foundry model deployment name. Must match a model available in the chosen region.')
param foundryModelName string = 'gpt-4o-mini'

@description('Foundry model version. Required for Azure OpenAI model deployments.')
param foundryModelVersion string = '2024-07-18'

@description('Foundry model deployment SKU. Most modern Foundry models use GlobalStandard.')
param foundryModelSkuName string = 'GlobalStandard'

@description('Foundry model deployment capacity (thousands of tokens per minute).')
param foundryModelCapacity string = '30'

@description('Foundry embedding model deployment name. Must match a model available in the chosen region. Used by the agent-framework multi-agent example to do vector search over the public companies demo graph (which uses 1536-dim cosine embeddings).')
param foundryEmbeddingModelName string = 'text-embedding-3-small'

@description('Foundry embedding model version.')
param foundryEmbeddingModelVersion string = '1'

@description('Foundry embedding model SKU.')
param foundryEmbeddingModelSkuName string = 'GlobalStandard'

@description('Foundry embedding model capacity (thousands of tokens per minute).')
param foundryEmbeddingModelCapacity string = '30'

@description('Entra object ID granted Azure AI Developer on the Foundry account so the signed-in user can call the Foundry data plane after az login. azd auto-populates this from the signed-in user. Empty disables the role assignment.')
param principalId string = ''

@description('Type of the principal granted Azure AI Developer: "User" for interactive azd auth login, "ServicePrincipal" in CI.')
@allowed([
  'User'
  'ServicePrincipal'
])
param principalType string = 'User'

var normalizedWorkload = toLower(replace(workloadName, '_', '-'))
var normalizedEnv = toLower(replace(environmentName, '_', '-'))
var baseName = '${normalizedWorkload}-${normalizedEnv}'

var commonTags = {
  workload: normalizedWorkload
  environment: normalizedEnv
  'azd-env-name': environmentName
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${baseName}'
  location: location
  tags: commonTags
}

module app './app.bicep' = {
  name: 'app-${baseName}'
  scope: rg
  params: {
    location: location
    baseName: baseName
    commonTags: commonTags
    containerImage: containerImage
    neo4jUri: neo4jUri
    neo4jDatabase: neo4jDatabase
    readOnly: readOnly
    mcpPort: mcpPort
    mcpExternalIngress: mcpExternalIngress
    mcpMinReplicas: mcpMinReplicas
    mcpMaxReplicas: mcpMaxReplicas
    mcpCpu: mcpCpu
    mcpMemory: mcpMemory
    mcpConcurrentRequests: mcpConcurrentRequests
    neo4jLogFormat: neo4jLogFormat
    neo4jTelemetry: neo4jTelemetry
    neo4jSchemaSampleSize: neo4jSchemaSampleSize
    neo4jAllowedOrigins: neo4jAllowedOrigins
  }
}

var foundryEnabled = bool(createFoundryProject)

module foundry './foundry.bicep' = if (foundryEnabled) {
  name: 'foundry-${baseName}'
  scope: rg
  params: {
    location: location
    baseName: baseName
    commonTags: commonTags
    modelName: foundryModelName
    modelVersion: foundryModelVersion
    modelSkuName: foundryModelSkuName
    modelCapacity: int(foundryModelCapacity)
    embeddingModelName: foundryEmbeddingModelName
    embeddingModelVersion: foundryEmbeddingModelVersion
    embeddingModelSkuName: foundryEmbeddingModelSkuName
    embeddingModelCapacity: int(foundryEmbeddingModelCapacity)
    principalId: principalId
    principalType: principalType
  }
}

output mcpEndpoint string = app.outputs.mcpEndpoint
output containerAppName string = app.outputs.containerAppName
output containerAppsEnvironmentName string = app.outputs.containerAppsEnvironmentName
output logAnalyticsWorkspaceName string = app.outputs.logAnalyticsWorkspaceName
output resourceGroupName string = rg.name
output mcpExternalIngress string = mcpExternalIngress

output foundryResourceGroup string = foundryEnabled ? rg.name : ''
output foundryAccountName string = foundryEnabled ? foundry.outputs.accountName : ''
output foundryProjectName string = foundryEnabled ? foundry.outputs.projectName : ''
output foundryProjectEndpoint string = foundryEnabled ? foundry.outputs.projectEndpoint : ''
output foundryModelDeploymentName string = foundryEnabled ? foundry.outputs.modelDeploymentName : ''
output foundryEmbeddingDeploymentName string = foundryEnabled ? foundry.outputs.embeddingDeploymentName : ''

// Names the `azure.ai.agents` azd extension expects in its postdeploy hook.
// Without these, `azd up` fails with "AZURE_AI_PROJECT_ENDPOINT is not set"
// once the extension is installed locally. `AZURE_TENANT_ID` is the third
// var the hook requires; it isn't a deployment artifact, so deploy.sh
// seeds it into the azd env from `az account show` before `azd up`.
output AZURE_AI_PROJECT_ENDPOINT string = foundryEnabled ? foundry.outputs.projectEndpoint : ''
output AZURE_AI_MODEL_DEPLOYMENT_NAME string = foundryEnabled ? foundry.outputs.modelDeploymentName : ''

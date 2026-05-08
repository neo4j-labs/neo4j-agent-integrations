targetScope = 'resourceGroup'

@description('Azure region for all resources.')
param location string

@description('Base name token derived from workload + environment, used in every resource name.')
param baseName string

@description('Common tags applied to all resources.')
param commonTags object

@description('Container image for the Neo4j MCP server.')
param containerImage string

@description('Neo4j Bolt URI.')
param neo4jUri string

@description('Neo4j database name.')
param neo4jDatabase string

@description('Run the Neo4j MCP server in read-only mode. Use "true" or "false".')
@allowed([
  'true'
  'false'
])
param readOnly string

@description('Container port used by the MCP HTTP transport.')
param mcpPort string

@description('Expose the MCP server through public Container Apps ingress. Use "false" for private/internal deployments.')
@allowed([
  'true'
  'false'
])
param mcpExternalIngress string

@description('Minimum Container Apps replicas.')
param mcpMinReplicas string

@description('Maximum Container Apps replicas.')
param mcpMaxReplicas string

@description('Container CPU cores.')
param mcpCpu string

@description('Container memory.')
param mcpMemory string

@description('HTTP concurrent requests per replica before scale-out.')
param mcpConcurrentRequests string

@description('Neo4j MCP log format: "json" or "text".')
param neo4jLogFormat string

@description('Enable Neo4j MCP telemetry. Use "true" or "false".')
@allowed([
  'true'
  'false'
])
param neo4jTelemetry string

@description('Number of nodes sampled for Neo4j schema inference.')
param neo4jSchemaSampleSize string

@description('CORS allowed origins for the MCP HTTP server. Empty disables CORS.')
param neo4jAllowedOrigins string

var logAnalyticsName = 'log-${baseName}'
var containerAppsEnvironmentName = 'cae-${baseName}'
var containerAppName = 'ca-${baseName}'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  tags: commonTags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppsEnvironmentName
  location: location
  tags: commonTags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource mcpContainerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  tags: commonTags
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: bool(mcpExternalIngress)
        targetPort: int(mcpPort)
        transport: 'http'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'neo4j-mcp'
          image: containerImage
          env: [
            {
              name: 'NEO4J_URI'
              value: neo4jUri
            }
            {
              name: 'NEO4J_DATABASE'
              value: neo4jDatabase
            }
            {
              name: 'NEO4J_TRANSPORT_MODE'
              value: 'http'
            }
            {
              name: 'NEO4J_MCP_HTTP_HOST'
              value: '0.0.0.0'
            }
            {
              name: 'NEO4J_MCP_HTTP_PORT'
              value: mcpPort
            }
            {
              name: 'NEO4J_READ_ONLY'
              value: readOnly
            }
            {
              name: 'NEO4J_LOG_FORMAT'
              value: neo4jLogFormat
            }
            {
              name: 'NEO4J_TELEMETRY'
              value: neo4jTelemetry
            }
            {
              name: 'NEO4J_SCHEMA_SAMPLE_SIZE'
              value: neo4jSchemaSampleSize
            }
            {
              name: 'NEO4J_MCP_HTTP_ALLOWED_ORIGINS'
              value: neo4jAllowedOrigins
            }
          ]
          resources: {
            cpu: json(mcpCpu)
            memory: mcpMemory
          }
        }
      ]
      scale: {
        minReplicas: int(mcpMinReplicas)
        maxReplicas: int(mcpMaxReplicas)
        rules: [
          {
            name: 'http-scale'
            http: {
              metadata: {
                concurrentRequests: mcpConcurrentRequests
              }
            }
          }
        ]
      }
    }
  }
}

output mcpEndpoint string = 'https://${mcpContainerApp.properties.configuration.ingress.fqdn}/mcp'
output containerAppName string = mcpContainerApp.name
output containerAppsEnvironmentName string = containerAppsEnvironment.name
output logAnalyticsWorkspaceName string = logAnalytics.name

targetScope = 'resourceGroup'

@description('Azure region for the Foundry account, project, and model deployment.')
param location string

@description('Base name token used in resource names.')
param baseName string

@description('Common tags applied to all resources.')
param commonTags object

@description('Foundry model name (e.g. gpt-4o-mini).')
param modelName string

@description('Foundry model version. Required for Azure OpenAI model deployments.')
param modelVersion string

@description('Foundry model deployment SKU. Most modern Foundry models use GlobalStandard.')
param modelSkuName string

@description('Foundry model deployment capacity, in thousands of tokens per minute.')
param modelCapacity int

@description('Principal ID (Entra object ID) granted Azure AI Developer on the Foundry account so DefaultAzureCredential works in examples. Empty disables the role assignment.')
param principalId string

@description('Type of the principal granted Azure AI Developer. Use "User" for an interactive azd auth login, "ServicePrincipal" in CI.')
@allowed([
  'User'
  'ServicePrincipal'
])
param principalType string = 'User'

// customSubDomainName must be globally unique across Azure (it becomes part
// of https://<name>.services.ai.azure.com/...). The 4-char suffix is
// deterministic per resource group + workload, so re-deploys keep the same
// name but collisions across tenants are unlikely.
var uniqueSuffix = take(uniqueString(resourceGroup().id, baseName), 4)
var accountName = 'aif-${baseName}-${uniqueSuffix}'
var projectName = 'proj-${baseName}'

// Azure AI Developer — broad data-plane access on the Foundry account, including
// model deployments and agent operations.
// https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/ai-machine-learning
var azureAiDeveloperRoleId = '64702f94-c441-49e6-a78b-ef80e0188fee'

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
  location: location
  tags: commonTags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundryAccount
  name: modelName
  sku: {
    name: modelSkuName
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: foundryAccount
  name: projectName
  location: location
  tags: commonTags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: 'Microsoft Foundry + Neo4j integration project'
    displayName: 'Foundry + Neo4j'
  }
  dependsOn: [
    modelDeployment
  ]
}

resource deployerRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  scope: foundryAccount
  name: guid(foundryAccount.id, principalId, azureAiDeveloperRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiDeveloperRoleId)
    principalId: principalId
    principalType: principalType
  }
}

output accountName string = foundryAccount.name
output projectName string = foundryProject.name
output projectEndpoint string = foundryProject.properties.endpoints['AI Foundry API']
output modelDeploymentName string = modelDeployment.name

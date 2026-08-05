output "aks_name" {
  description = "AKS cluster name."
  value       = azurerm_kubernetes_cluster.aks.name
}

output "resource_group" {
  description = "Resource group holding the AKS cluster."
  value       = azurerm_kubernetes_cluster.aks.resource_group_name
}

output "acr_login_server" {
  description = "Registry login server for image references (e.g. inveintelligence.azurecr.io)."
  value       = data.azurerm_container_registry.acr.login_server
}

output "get_credentials_command" {
  description = "Run this to point kubectl at the new cluster."
  value       = "az aks get-credentials --resource-group ${azurerm_kubernetes_cluster.aks.resource_group_name} --name ${azurerm_kubernetes_cluster.aks.name} --overwrite-existing"
}

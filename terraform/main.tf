# -----------------------------------------------------------------------------
# Existing resources (read-only). The ACR already exists and holds invint:v1.
# We reference it instead of creating it, so `terraform destroy` never deletes
# your registry or its images.
# -----------------------------------------------------------------------------
data "azurerm_container_registry" "acr" {
  name                = var.acr_name
  resource_group_name = var.acr_resource_group_name
}

# The RG already exists (it holds the ACR). Reference it, don't recreate it.
data "azurerm_resource_group" "rg" {
  name = var.resource_group_name
}

# -----------------------------------------------------------------------------
# AKS cluster + system node pool.
# Managed identity (SystemAssigned) is what gets AcrPull on the registry below,
# so no image-pull secret is needed (Step 9 of the doc becomes unnecessary).
# -----------------------------------------------------------------------------
resource "azurerm_kubernetes_cluster" "aks" {
  name                = var.aks_name
  location            = var.aks_location
  resource_group_name = data.azurerm_resource_group.rg.name
  dns_prefix          = var.dns_prefix

  default_node_pool {
    name       = "system"
    vm_size    = var.node_vm_size
    node_count = var.node_count
  }

  identity {
    type = "SystemAssigned"
  }

  # Keep the default LoadBalancer SKU (standard) so the Service of type
  # LoadBalancer gets a public IP.
  network_profile {
    network_plugin    = "azure"
    load_balancer_sku = "standard"
  }

  tags = {
    project = "investor-intelligence"
    managed = "terraform"
  }
}

# -----------------------------------------------------------------------------
# Give the cluster's kubelet identity AcrPull on the existing registry.
# This is the Terraform equivalent of `az aks update --attach-acr`.
# -----------------------------------------------------------------------------
resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                            = data.azurerm_container_registry.acr.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_kubernetes_cluster.aks.kubelet_identity[0].object_id
  skip_service_principal_aad_check = true
}

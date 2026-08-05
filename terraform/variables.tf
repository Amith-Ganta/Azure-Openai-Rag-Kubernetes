variable "subscription_id" {
  description = "Azure subscription ID (Azure for Students)."
  type        = string
  default     = "c22c3359-4cde-44b3-87a5-f66ed84eaf3a"
}

variable "resource_group_name" {
  description = "Resource group that will hold the AKS cluster. Reuses the RG that already holds the ACR."
  type        = string
  default     = "rag-inv-intelligence"
}

variable "location" {
  description = "Region of the existing RG/ACR. Read-only reference; not used to place AKS."
  type        = string
  default     = "spaincentral"
}

variable "aks_location" {
  description = "Region for the AKS cluster. Must be in the subscription's allowed-regions policy (sys.regionrestriction) AND offer AKS. spaincentral is allowed for ACR but rejects AKS (403 RequestDisallowedByAzure), so AKS goes to polandcentral (nearest allowed region with AKS)."
  type        = string
  default     = "polandcentral"
}

variable "aks_name" {
  description = "AKS cluster name."
  type        = string
  default     = "inv-intelligence-aks"
}

variable "dns_prefix" {
  description = "DNS prefix for the AKS API server."
  type        = string
  default     = "invint"
}

variable "node_vm_size" {
  description = "VM size for the AKS node pool. Standard_B2s_v2 = 2 vCPU, burstable, cheapest AKS-capable size available in polandcentral (the older Standard_B2s is NOT offered there; the 400 error listed B2s_v2 as the allowed replacement). Fits the 6-vCPU Student cap."
  type        = string
  default     = "Standard_B2s_v2"
}

variable "node_count" {
  description = "Number of nodes. 1 node * 2 vCPU = 2 vCPU total, well under the 6-vCPU regional cap."
  type        = number
  default     = 1
}

variable "acr_name" {
  description = "Existing Azure Container Registry to attach for image pulls. NOT created by this Terraform."
  type        = string
  default     = "inveintelligence"
}

variable "acr_resource_group_name" {
  description = "Resource group of the existing ACR."
  type        = string
  default     = "rag-inv-intelligence"
}

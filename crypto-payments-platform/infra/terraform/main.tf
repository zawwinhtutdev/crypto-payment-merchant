# Terraform: Azure infrastructure for the Crypto payments platform.
#
# Provisions: resource group, AKS cluster, container registry, Key Vault
# (for secrets like the JWT signing key / DB credentials), and a Postgres
# flexible server for the durable ledger store.
#
# This is a skeleton meant to demonstrate IaC structure/patterns — not a
# deploy-ready module (no remote state backend, provider version pins would
# need finalizing, etc).

terraform {
  required_version = ">= 1.7.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }

  # Remote state — never commit state to source control for a real project.
  backend "azurerm" {
    resource_group_name  = "mesh-tfstate-rg"
    storage_account_name = "meshtfstate"
    container_name       = "tfstate"
    key                  = "payments-platform.tfstate"
  }
}

provider "azurerm" {
  features {}
}

variable "environment" {
  description = "Deployment environment (dev/staging/prod)"
  type        = string
  default     = "dev"
}

variable "location" {
  type    = string
  default = "eastus2"
}

resource "azurerm_resource_group" "main" {
  name     = "mesh-payments-${var.environment}-rg"
  location = var.location
}

resource "azurerm_kubernetes_cluster" "main" {
  name                = "mesh-payments-${var.environment}-aks"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "meshpayments${var.environment}"

  default_node_pool {
    name                = "system"
    node_count          = 3
    vm_size             = "Standard_D4s_v5"
    enable_auto_scaling = true
    min_count           = 3
    max_count           = 10
  }

  identity {
    type = "SystemAssigned"
  }

  # DevSecOps: enable Azure AD integration + RBAC rather than static
  # kubeconfig credentials, and enable the Azure Policy add-on for
  # cluster-level compliance enforcement.
  azure_active_directory_role_based_access_control {
    managed = true
    azure_rbac_enabled = true
  }

  azure_policy_enabled = true

  network_profile {
    network_plugin = "azure"
    network_policy = "azure"  # required for NetworkPolicy resources to take effect
  }
}

resource "azurerm_container_registry" "main" {
  name                = "meshpayments${var.environment}acr"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Premium"
  admin_enabled       = false  # push/pull via AKS managed identity, not admin creds

  # Vulnerability scanning on push — DevSecOps gate before images ever
  # reach a cluster.
  quarantine_policy_enabled = true
}

resource "azurerm_key_vault" "main" {
  name                       = "mesh-payments-${var.environment}-kv"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  sku_name                   = "standard"
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  purge_protection_enabled   = true
  soft_delete_retention_days = 30
}

data "azurerm_client_config" "current" {}

resource "azurerm_postgresql_flexible_server" "ledger_db" {
  name                   = "mesh-payments-${var.environment}-pg"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  sku_name               = "GP_Standard_D2s_v3"
  storage_mb             = 65536
  version                = "16"
  backup_retention_days  = 35   # payments data — long retention for audit/recovery
  geo_redundant_backup_enabled = true

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false  # AAD-only, no static DB passwords
  }
}

output "aks_cluster_name" {
  value = azurerm_kubernetes_cluster.main.name
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "key_vault_uri" {
  value = azurerm_key_vault.main.vault_uri
}

# Azure Cognitive Search Backup: tenaliaiaz-jlens-user-workspace

This directory contains the complete backup of the Azure Cognitive Search configuration for the index `tenaliaiaz-jlens-user-workspace`.

## Backup Contents:
- `index.json` - Index definition (with filterable workspace_id, workspace_name, user_id)
- `indexer.json` - Indexer configuration
- `skillset.json` - Skillset definition
- `datasource.json` - Data source configuration
- `restore.sh` - Restoration script

## Service Details:
- Service: cog-search-tenaliaiaz-prod-uksouth
- Resource Group: rg-tenaliaiaz-prod-uksouth-01
- Backup Date: 2025-11-29T12:34:29.456+05:30

## Key Changes:
- workspace_id: filterable=true
- workspace_name: filterable=true
- user_id: filterable=true

## Usage:
Run `./restore.sh` to restore all components to the search service.

#!/bin/bash

# Azure Cognitive Search Restore Script
# Service: cog-search-tenaliaiaz-prod-uksouth
# Resource Group: rg-tenaliaiaz-prod-uksouth-01

SERVICE_NAME="cog-search-tenaliaiaz-prod-uksouth"
RESOURCE_GROUP="rg-tenaliaiaz-prod-uksouth-01"
API_VERSION="2023-11-01"

# Get admin key
echo "Getting admin key..."
ADMIN_KEY=$(az search admin-key show --service-name $SERVICE_NAME --resource-group $RESOURCE_GROUP --query "primaryKey" -o tsv)

if [ -z "$ADMIN_KEY" ]; then
    echo "Error: Could not retrieve admin key"
    exit 1
fi

BASE_URL="https://$SERVICE_NAME.search.windows.net"

echo "Starting restore process..."

# 1. Create/Update Datasource
echo "Creating datasource..."
curl -X PUT "$BASE_URL/datasources/tenaliaiaz-jlens-user-workspace-datasource?api-version=$API_VERSION" \
  -H "api-key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d @datasource.json

# 2. Create/Update Skillset
echo "Creating skillset..."
curl -X PUT "$BASE_URL/skillsets/tenaliaiaz-jlens-user-workspace-skillset?api-version=$API_VERSION" \
  -H "api-key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d @skillset.json

# 3. Create/Update Index
echo "Creating index..."
curl -X PUT "$BASE_URL/indexes/tenaliaiaz-jlens-user-workspace?api-version=$API_VERSION" \
  -H "api-key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d @index.json

# 4. Create/Update Indexer
echo "Creating indexer..."
curl -X PUT "$BASE_URL/indexers/tenaliaiaz-jlens-user-workspace-indexer?api-version=$API_VERSION" \
  -H "api-key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d @indexer.json

echo "Restore completed!"
echo "Note: You may need to run the indexer manually to populate the index with data."

#!/bin/bash

SERVICE_NAME="cog-search-tenaliaiaz-prod-uksouth"
RESOURCE_GROUP="rg-tenaliaiaz-prod-uksouth-01"
API_VERSION="2023-11-01"

ADMIN_KEY=$(az search admin-key show --service-name $SERVICE_NAME --resource-group $RESOURCE_GROUP --query "primaryKey" -o tsv)
BASE_URL="https://$SERVICE_NAME.search.windows.net"

echo "Restoring generated-proposals-index..."

curl -X PUT "$BASE_URL/datasources/generated-proposals-datasource?api-version=$API_VERSION" \
  -H "api-key: $ADMIN_KEY" -H "Content-Type: application/json" -d @datasource.json

curl -X PUT "$BASE_URL/skillsets/generated-proposals-skillset?api-version=$API_VERSION" \
  -H "api-key: $ADMIN_KEY" -H "Content-Type: application/json" -d @skillset.json

curl -X PUT "$BASE_URL/indexes/generated-proposals-index?api-version=$API_VERSION" \
  -H "api-key: $ADMIN_KEY" -H "Content-Type: application/json" -d @index.json

curl -X PUT "$BASE_URL/indexers/generated-proposals-indexer?api-version=$API_VERSION" \
  -H "api-key: $ADMIN_KEY" -H "Content-Type: application/json" -d @indexer.json

echo "Restore completed!"

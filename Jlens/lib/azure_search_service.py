import os
import json
from typing import List, Dict, Any, Optional
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    CorsOptions,
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticField,
    SemanticSearch
)
from dotenv import load_dotenv
import uuid
from datetime import datetime

load_dotenv()

class AzureSearchService:
    def __init__(self):
        self.search_service = os.getenv("AZURE_SEARCH_SERVICE")
        self.search_key = os.getenv("AZURE_SEARCH_KEY")
        self.endpoint = f"https://{self.search_service}.search.windows.net"
        self.credential = AzureKeyCredential(self.search_key)
        
        self.index_client = SearchIndexClient(
            endpoint=self.endpoint,
            credential=self.credential
        )
        
        # User workspace index Name
        self.user_workspace_index = "tenaliai-jlens-user-workspace-index"
        
    def create_user_workspace_index(self) -> bool:
        """Create the user workspace search index with required fields and semantic search"""
        try:
            fields = [
                SimpleField(name="id", type=SearchFieldDataType.String, key=True),
                SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="standard.lucene"),
                SimpleField(name="index_name", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="group_name", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="file_name", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="file_link", type=SearchFieldDataType.String),
                SimpleField(name="user_id", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="user_name", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="uploaded_datetime", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
                SimpleField(name="workspace_id", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="workspace_name", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="conversation_id", type=SearchFieldDataType.String, filterable=True, facetable=True)
            ]
            
            cors_options = CorsOptions(allowed_origins=["*"], max_age_in_seconds=300)
            
            # Create semantic configuration similar to sales index
            semantic_config = SemanticConfiguration(
                name="semanticConfig",
                prioritized_fields=SemanticPrioritizedFields(
                    content_fields=[SemanticField(field_name="content")],
                    keywords_fields=[SemanticField(field_name="file_name")],
                    title_field=SemanticField(field_name="file_name")
                )
            )
            
            semantic_search = SemanticSearch(configurations=[semantic_config])
            
            index = SearchIndex(
                name=self.user_workspace_index,
                fields=fields,
                cors_options=cors_options,
                semantic_search=semantic_search
            )
            
            result = self.index_client.create_or_update_index(index)
            print(f"Created/Updated index with semantic search: {result.name}")
            return True
            
        except Exception as e:
            print(f"Error creating user workspace index: {str(e)}")
            return False
    
    def get_search_client(self, index_name: str = None) -> SearchClient:
        """Get search client for specific index"""
        index = index_name or self.user_workspace_index
        return SearchClient(
            endpoint=self.endpoint,
            index_name=index,
            credential=self.credential
        )
    
    def upload_document(self, document: Dict[str, Any], index_name: str = None) -> bool:
        """Upload a single document to the search index"""
        try:
            search_client = self.get_search_client(index_name)
            result = search_client.upload_documents([document])
            return len(result) > 0 and result[0].succeeded
        except Exception as e:
            print(f"Error uploading document: {str(e)}")
            return False
    
    def upload_documents(self, documents: List[Dict[str, Any]], index_name: str = None) -> bool:
        """Upload multiple documents to the search index"""
        try:
            search_client = self.get_search_client(index_name)
            result = search_client.upload_documents(documents)
            return all(doc.succeeded for doc in result)
        except Exception as e:
            print(f"Error uploading documents: {str(e)}")
            return False
    
    def search_documents_hybrid(self, query: str, workspace_name: str = None, workspace_type: str = None,
                               top: int = 3, index_name: str = None) -> List[Dict[str, Any]]:
        """Hybrid search with vector + semantic for optimized indexes"""
        try:
            search_client = self.get_search_client(index_name)
            
            # Check if this uses hybrid search (Jman Sales or user workspaces)
            use_hybrid = (
                (workspace_name == "Jman Sales" and index_name == "tenaliaiaz-sharepoint-sales-index") or
                (workspace_name == "Nexus" and index_name == "nexus-ms") or
                (workspace_name == "AISOW" and index_name == "tenaliaz-aisow-index") or
                (workspace_type in ["own", "shared"] and index_name == "tenaliaiaz-jlens-user-workspace")
            )
            
            if use_hybrid:
                # Get embedding for query
                embedding = self.get_embedding(query)
                
                # Create vector query
                from azure.search.documents.models import VectorizedQuery
                vector_query = VectorizedQuery(
                    vector=embedding,
                    k_nearest_neighbors=10,
                    fields="text_vector"
                )
                
                # Select fields based on workspace type
                if workspace_name == "Jman Sales":
                    select_fields = ["title", "chunk", "sharepoint_name", "sharepoint_url", "created_by_name", "last_modified_by_name"]
                    results = search_client.search(
                    search_text=query,
                    query_type="semantic",
                    semantic_configuration_name="tenaliaiaz-sharepoint-sales-index-semantic-configuration",
                    scoring_profile="hybridBoost",
                    vector_queries=[vector_query],
                    top=top,
                    select=select_fields
                )
                elif workspace_name == "Nexus":
                    select_fields = ["title", "chunk"]
                    results = search_client.search(
                    search_text=query,
                    query_type="semantic",
                    semantic_configuration_name="nexus-ms-semantic-configuration",
                    scoring_profile="hybridBoost",
                    vector_queries=[vector_query],
                    top=top,
                    select=select_fields
                )
                elif workspace_name == "AISOW":
                    # select_fields = ["title", "chunk", "sharepoint_name", "sharepoint_url", "created_by_name", "last_modified_by_name"]
                    select_fields = ["title", "chunk", "sharepoint_name", "sharepoint_url", "domains", "subdomains", "client", "project_type", "platform", "summary"]
                    results = search_client.search(
                    search_text=query,
                    query_type="semantic",
                    semantic_configuration_name="semantic-config",
                    scoring_profile="hybridBoost",
                    vector_queries=[vector_query],
                    top=top,
                    select=select_fields
                )
                else:
                    select_fields = ["title", "chunk", "file_name", "file_link", "user_name", "workspace_name"]
                    results = search_client.search(
                    search_text=query,
                    query_type="semantic",
                    semantic_configuration_name="tenaliaiaz-jlens-user-workspace-semantic-configuration",
                    scoring_profile="hybridBoost",
                    vector_queries=[vector_query],
                    top=top,
                    select=select_fields
                )
                
                # results = search_client.search(
                #     search_text=query,
                #     query_type="semantic",
                #     semantic_configuration_name="tenaliaiaz-sharepoint-sales-index-semantic-configuration",
                #     scoring_profile="hybridBoost",
                #     vector_queries=[vector_query],
                #     top=top,
                #     select=select_fields
                # )
                
                # Filter results to prevent hallucination - only return results with text relevance
                # Skip filter for AISOW — structured metadata makes results reliable
                if workspace_name == "AISOW":
                    return [dict(r) for r in results]

                filtered_results = []
                query_lower = query.lower()
                
                for result in results:
                    result_dict = dict(result)
                    
                    # Check if query terms appear in title or content
                    title = result_dict.get('title', '').lower()
                    chunk = result_dict.get('chunk', '').lower()
                    
                    # For single word queries, check exact match
                    if len(query.split()) == 1:
                        if query_lower in title or query_lower in chunk:
                            filtered_results.append(result_dict)
                    else:
                        # For multi-word queries, check if any word appears
                        query_words = query_lower.split()
                        if any(word in title or word in chunk for word in query_words):
                            filtered_results.append(result_dict)
                
                return filtered_results
            else:
                # Fallback to regular search
                return self.search_documents(query, top=top, index_name=index_name)
                
        except Exception as e:
            print(f"Error in hybrid search: {str(e)}")
            return []
    
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for text using Azure OpenAI"""
        try:
            import requests
            import os
            
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            api_key = os.getenv("AZURE_OPENAI_KEY")
            
            response = requests.post(
                f"{endpoint}/openai/deployments/text-embedding-3-small/embeddings?api-version=2024-02-15-preview",
                headers={"api-key": api_key, "Content-Type": "application/json"},
                json={"input": text}
            )
            
            if response.status_code == 200:
                return response.json()["data"][0]["embedding"]
            else:
                print(f"Error getting embedding: {response.text}")
                return []
                
        except Exception as e:
            print(f"Error getting embedding: {str(e)}")
            return []

    def search_documents(self, query: str, workspace_id: str = None, user_id: str = None, 
                        top: int = 5, index_name: str = None) -> List[Dict[str, Any]]:
        """Search documents with workspace and user filtering"""
        try:
            search_client = self.get_search_client(index_name)
            
            # Build filter
            filters = []
            if workspace_id:
                filters.append(f"workspace_id eq '{workspace_id}'")
            if user_id:
                filters.append(f"user_id eq '{user_id}'")
            
            filter_expression = " and ".join(filters) if filters else None
            
            results = search_client.search(
                search_text=query,
                filter=filter_expression,
                top=top,
                include_total_count=True
            )
            
            return [dict(result) for result in results]
            
        except Exception as e:
            print(f"Error searching documents: {str(e)}")
            return []
    
    def delete_document(self, document_id: str, index_name: str = None) -> bool:
        """Delete a document from the search index"""
        try:
            search_client = self.get_search_client(index_name)
            result = search_client.delete_documents([{"id": document_id}])
            return len(result) > 0 and result[0].succeeded
        except Exception as e:
            print(f"Error deleting document: {str(e)}")
            return False
    
    def delete_workspace_documents(self, workspace_id: str, index_name: str = None) -> bool:
        """Delete all documents for a specific workspace"""
        try:
            search_client = self.get_search_client(index_name)
            
            # First, search for all documents in the workspace
            results = search_client.search(
                search_text="*",
                filter=f"workspace_id eq '{workspace_id}'",
                select=["id"]
            )
            
            # Delete all found documents
            documents_to_delete = [{"id": result["id"]} for result in results]
            if documents_to_delete:
                result = search_client.delete_documents(documents_to_delete)
                return all(doc.succeeded for doc in result)
            return True
            
        except Exception as e:
            print(f"Error deleting workspace documents: {str(e)}")
            return False
    
    def create_document_from_file_metadata(self, file_metadata: Dict[str, Any], 
                                         content: str, workspace_info: Dict[str, Any],
                                         user_info: Dict[str, Any], conversation_id: str = "") -> Dict[str, Any]:
        """Create a search document from file metadata"""
        return {
            "id": str(uuid.uuid4()),
            "content": content,
            "index_name": self.user_workspace_index,
            "group_name": workspace_info.get("name", ""),
            "file_name": file_metadata.get("name", ""),
            "file_link": file_metadata.get("link", ""),
            "user_id": str(user_info.get("id", "")),
            "user_name": user_info.get("name", ""),
            "uploaded_datetime": datetime.utcnow().isoformat() + "Z",
            "workspace_id": str(workspace_info.get("id", "")),
            "workspace_name": workspace_info.get("name", ""),
            "conversation_id": conversation_id
        }
    
    def index_exists(self, index_name: str = None) -> bool:
        """Check if an index exists"""
        try:
            index = index_name or self.user_workspace_index
            self.index_client.get_index(index)
            return True
        except Exception:
            return False

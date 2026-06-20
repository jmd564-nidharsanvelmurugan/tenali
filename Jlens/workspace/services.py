import mimetypes
from sqlalchemy.orm import Session
from uuid import UUID
from db.models import Workspace, FileMetadata, FileMetadataType, McpDbConfig, User, WorkspaceType
from .schemas import WorkspaceCreate, FileMetadataOut, AddMcp, UpdateMcp, McpResponse
from azure.storage.blob.aio import BlobServiceClient
from fastapi import UploadFile
import os
from starlette.responses import StreamingResponse
from typing import Optional, List, Dict, Any
from azure.storage.blob import generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import quote
from fastapi.exceptions import HTTPException
from fastapi import status
import uuid
from Jlens.lib.azure_search_service import AzureSearchService
from Jlens.workspace.indexing_logger import logger as indexing_logger
import PyPDF2
import docx
import asyncio
import io


AZURE_BLOB_STORAGE_CONNECTION_STRING = os.getenv(
    "AZURE_BLOB_STORAGE_CONNECTION_STRING")
AZURE_BLOB_STORAGE_CONTAINER_NAME = os.getenv(
    "AZURE_BLOB_STORAGE_CONTAINER_NAME")

# New container for user workspaces
USER_WORKSPACE_CONTAINER = "tenaliai-jlens-user-workspace"
USER_WORKSPACE_SAS_URL = os.getenv("USER_WORKSPACE_SAS_URL")

blob_service_client = BlobServiceClient.from_connection_string(
    AZURE_BLOB_STORAGE_CONNECTION_STRING)

# Initialize Azure Search Service
search_service = AzureSearchService()


def create_workspace(db: Session, user_id: UUID, data: WorkspaceCreate) -> Workspace:

    existing_workspace = (
        db.query(Workspace)
        .filter(Workspace.name.ilike(data.name) & (Workspace.user_id == user_id))
        .first()
    )

    if existing_workspace:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace already exists",
        )

    # Determine workspace type based on data
    workspace_type = WorkspaceType.shared if not data.is_private else WorkspaceType.own

    workspace = Workspace(
        name=data.name,
        description=data.description,
        pre_prompt=data.preprompt,
        is_private=data.is_private,
        is_system_workspace=False,
        workspace_type=workspace_type,
        user_id=user_id
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace


def create_system_workspace(db: Session, data: WorkspaceCreate) -> Workspace:
    """Create a system workspace (admin only)"""
    existing_workspace = (
        db.query(Workspace)
        .filter(Workspace.name.ilike(data.name) & (Workspace.is_system_workspace == True))
        .first()
    )

    if existing_workspace:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System workspace already exists",
        )

    workspace = Workspace(
        name=data.name,
        description=data.description,
        pre_prompt=data.preprompt,
        is_private=False,
        is_system_workspace=True,
        workspace_type=WorkspaceType.system,
        user_id=None
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace


def get_user_workspaces(db: Session, user_id: UUID):
    from db.models import UserComponentAccess, SystemWorkspaceTemplate, WorkspaceShare
    
    # Get system template names
    system_template_names = [t.name for t in db.query(SystemWorkspaceTemplate).filter(
        SystemWorkspaceTemplate.is_active == True
    ).all()]
    
    # Get user's owned workspaces (includes copies of system workspaces)
    owned_workspaces = db.query(Workspace).filter(
        Workspace.user_id == user_id
    ).all()
    
    # Get shared workspaces via workspace_shares table
    shared_workspace_ids = [
        str(share.workspace_id) for share in db.query(WorkspaceShare).filter(
            WorkspaceShare.shared_with_id == user_id
        ).all()
    ]
    shared_workspaces = db.query(Workspace).filter(
        Workspace.id.in_(shared_workspace_ids)
    ).all() if shared_workspace_ids else []
    
    # Combine and deduplicate
    all_ws = owned_workspaces + shared_workspaces
    all_workspaces = {str(ws.id): ws for ws in all_ws}
    
    # Convert to dicts with correct is_system_workspace flag and shared status
    result = []
    for ws in all_workspaces.values():
        is_shared = str(ws.id) in shared_workspace_ids
        result.append({
            "id": ws.id,
            "name": ws.name,
            "description": ws.description,
            "pre_prompt": ws.pre_prompt,
            "is_private": ws.is_private,
            "is_system_workspace": ws.name in system_template_names,
            "is_shared": is_shared,
            "user_id": ws.user_id,
            "owner_email": ws.owner.email if ws.owner else None,
            "created_at": ws.created_at,
            "updated_at": ws.updated_at
        })
    
    return result


def check_workspace_access(db: Session, user_id: UUID, workspace_id: UUID) -> bool:
    """Check if user has access to a workspace"""
    from db.models import UserComponentAccess, WorkspaceShare
    
    # Check if user owns the workspace
    owned = db.query(Workspace).filter(
        Workspace.id == workspace_id,
        Workspace.user_id == user_id
    ).first()
    
    if owned:
        return True
    
    # Check if workspace is shared with user
    shared = db.query(WorkspaceShare).filter(
        WorkspaceShare.workspace_id == workspace_id,
        WorkspaceShare.shared_with_id == user_id
    ).first()
    
    if shared:
        return True
    
    # Check if user has access via UserComponentAccess
    access = db.query(UserComponentAccess).filter(
        UserComponentAccess.user_id == user_id,
        UserComponentAccess.component_id == workspace_id,
        UserComponentAccess.component_type == "workspace"
    ).first()
    
    return access is not None


def get_accessible_workspaces(db: Session, user_id: UUID):
    # Returns workspaces user owns + has access to (for sidebar navigation)
    from db.models import UserComponentAccess, SystemWorkspaceTemplate, WorkspaceShare
    
    result = []
    
    # 1. Get workspace access records (new approach)
    workspace_access = db.query(UserComponentAccess).filter(
        UserComponentAccess.user_id == user_id,
        UserComponentAccess.component_type == "workspace"
    ).all()
    
    for access in workspace_access:
        workspace = db.query(Workspace).filter(Workspace.id == access.component_id).first()
        if workspace:
            result.append({
                "id": str(workspace.id),
                "name": workspace.name,
                "description": workspace.description,
                "pre_prompt": workspace.pre_prompt,
                "is_private": workspace.is_private,
                "is_system_workspace": workspace.is_system_workspace,
                "workspace_type": "system" if workspace.is_system_workspace else "shared",
                "user_id": str(workspace.user_id) if workspace.user_id else None,
                "owner_email": workspace.owner.email if workspace.owner else "system",
                "created_at": workspace.created_at,
                "updated_at": workspace.updated_at
            })
    
    # 2. Get system workspace templates user has access to (old approach for backward compatibility)
    system_template_access = db.query(UserComponentAccess).filter(
        UserComponentAccess.user_id == user_id,
        UserComponentAccess.component_type == "system_workspace_template"
    ).all()
    
    for access in system_template_access:
        template = db.query(SystemWorkspaceTemplate).filter(
            SystemWorkspaceTemplate.id == access.component_id
        ).first()
        if template:
            result.append({
                "id": str(template.id),
                "name": template.name,
                "description": template.description,
                "pre_prompt": template.pre_prompt,
                "is_private": False,
                "is_system_workspace": True,
                "workspace_type": "system",
                "user_id": None,
                "owner_email": "system",
                "created_at": template.created_at,
                "updated_at": template.updated_at
            })
    
    # 3. Get user's own workspaces (non-system)
    owned = db.query(Workspace).filter(
        Workspace.user_id == user_id,
        Workspace.is_system_workspace != True  # Exclude system workspaces to avoid duplicates
    ).all()
    
    for ws in owned:
        result.append({
            "id": str(ws.id),
            "name": ws.name,
            "description": ws.description,
            "pre_prompt": ws.pre_prompt,
            "is_private": ws.is_private,
            "is_system_workspace": False,
            "workspace_type": "own",
            "user_id": str(ws.user_id),
            "owner_email": ws.owner.email if ws.owner else None,
            "created_at": ws.created_at,
            "updated_at": ws.updated_at
        })
    
    # 4. Get shared workspaces
    shared_workspace_ids = [
        str(share.workspace_id) for share in db.query(WorkspaceShare).filter(
            WorkspaceShare.shared_with_id == user_id
        ).all()
    ]
    
    if shared_workspace_ids:
        shared_workspaces = db.query(Workspace).filter(
            Workspace.id.in_(shared_workspace_ids)
        ).all()
        
        for ws in shared_workspaces:
            result.append({
                "id": str(ws.id),
                "name": ws.name,
                "description": ws.description,
                "pre_prompt": ws.pre_prompt,
                "is_private": ws.is_private,
                "is_system_workspace": False,
                "workspace_type": "shared",
                "user_id": str(ws.user_id),
                "owner_email": ws.owner.email if ws.owner else None,
                "created_at": ws.created_at,
                "updated_at": ws.updated_at
            })
    
    return result


def get_all_workspaces(db: Session):
    # Get all user workspaces
    from db.models import SystemWorkspaceTemplate
    
    workspaces = db.query(Workspace).join(
        User, Workspace.user_id == User.id, isouter=True
    ).all()
    
    result = []
    
    # Add system workspace templates as "system workspaces"
    templates = db.query(SystemWorkspaceTemplate).filter(
        SystemWorkspaceTemplate.is_active == True
    ).all()
    
    for template in templates:
        result.append({
            "id": str(template.id),
            "name": template.name,
            "description": template.description,
            "pre_prompt": template.pre_prompt,
            "is_private": False,
            "is_system_workspace": True,
            "user_id": None,
            "owner_email": "System",
            "created_at": template.created_at,
            "updated_at": template.updated_at
        })
    
    # Add user workspaces
    for ws in workspaces:
        result.append({
            "id": ws.id,
            "name": ws.name,
            "description": ws.description,
            "pre_prompt": ws.pre_prompt,
            "is_private": ws.is_private,
            "is_system_workspace": False,
            "user_id": ws.user_id,
            "owner_email": ws.owner.email if ws.owner else "Unknown",
            "created_at": ws.created_at,
            "updated_at": ws.updated_at
        })
    
    return result


def get_shared_workspaces(db: Session, workspace_id: UUID):

    return db.query(Workspace).filter(Workspace.id == workspace_id).all()


def delete_workspace(db: Session, workspace_id: UUID, user_id: UUID) -> bool:
    # Check if user owns the workspace
    workspace = db.query(Workspace).filter(
        Workspace.id == workspace_id, Workspace.user_id == user_id).first()
    
    if workspace:
        # User owns the workspace - delete it
        if workspace.is_system_workspace:
            return False
        db.delete(workspace)
        db.commit()
        return True
    
    # Check if user has shared access - unlink instead of delete
    from db.models import WorkspaceShare
    share = db.query(WorkspaceShare).filter(
        WorkspaceShare.workspace_id == workspace_id,
        WorkspaceShare.shared_with_id == user_id
    ).first()
    
    if share:
        # User has shared access - remove the share
        db.delete(share)
        db.commit()
        return True
    
    return False


def get_all_system_workspaces(db: Session):
    """Get all system workspaces (admin only)"""
    return db.query(Workspace).filter(Workspace.is_system_workspace == True).all()


def update_system_workspace(db: Session, workspace_id: UUID, data: WorkspaceCreate):
    """Update system workspace (admin only)"""
    workspace = db.query(Workspace).filter(
        Workspace.id == workspace_id,
        Workspace.is_system_workspace == True
    ).first()
    
    if not workspace:
        raise HTTPException(status_code=404, detail="System workspace not found")
    
    workspace.name = data.name
    workspace.description = data.description
    workspace.pre_prompt = data.preprompt
    db.commit()
    db.refresh(workspace)
    return workspace


def delete_system_workspace(db: Session, workspace_id: UUID) -> bool:
    """Delete system workspace (admin only)"""
    workspace = db.query(Workspace).filter(
        Workspace.id == workspace_id,
        Workspace.is_system_workspace == True
    ).first()
    
    if workspace:
        db.delete(workspace)
        db.commit()
        return True
    return False


def update_pre_prompt(db: Session, workspace_id: UUID, new_pre_prompt: str) -> Workspace | None:
    workspace = db.query(Workspace).filter(
        Workspace.id == workspace_id,
    ).first()

    if not workspace:
        return None

    workspace.pre_prompt = new_pre_prompt
    db.commit()
    db.refresh(workspace)
    return workspace


async def upload_file_to_azure_blob(file: bytes, blob_path: str):
    """Legacy function for backward compatibility"""
    async with BlobServiceClient.from_connection_string(AZURE_BLOB_STORAGE_CONNECTION_STRING) as client:
        container_client = client.get_container_client(AZURE_BLOB_STORAGE_CONTAINER_NAME)
        blob_client = container_client.get_blob_client(blob_path)
        await blob_client.upload_blob(file, overwrite=True)

def extract_text_from_file(file_content: bytes, filename: str) -> str:
    """Extract text content from different file types"""
    try:
        file_extension = filename.lower().split('.')[-1] if '.' in filename else ''
        
        if file_extension == 'pdf':
            return extract_text_from_pdf(file_content)
        elif file_extension in ['docx', 'doc']:
            return extract_text_from_docx(file_content)
        elif file_extension == 'txt':
            return file_content.decode('utf-8', errors='ignore')
        else:
            # Try to decode as text for other formats
            return file_content.decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error extracting text from {filename}: {str(e)}")
        return ""

def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text from PDF file"""
    try:
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"Error extracting PDF text: {str(e)}")
        return ""

def extract_text_from_docx(file_content: bytes) -> str:
    """Extract text from DOCX file"""
    try:
        docx_file = io.BytesIO(file_content)
        doc = docx.Document(docx_file)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text
    except Exception as e:
        print(f"Error extracting DOCX text: {str(e)}")
        return ""

async def delete_blob_file(blob_path: str):
    """Delete a file from the user workspace blob container"""
    blob = blob_service_client.get_blob_client(container=USER_WORKSPACE_CONTAINER, blob=blob_path)
    await blob.delete_blob()
    await blob.delete_blob()


async def delete_file_from_search_index(workspace_id: str, file_name: str):
    """Delete file chunks from the search index"""
    try:
        import requests
        import os
        azure_search_service = os.getenv("AZURE_SEARCH_SERVICE")
        azure_search_key = os.getenv("AZURE_SEARCH_KEY")
        index_name = "tenaliaiaz-jlens-user-workspace"
        
        # Search for all chunks of this file
        search_url = f"https://{azure_search_service}.search.windows.net/indexes/{index_name}/docs"
        headers = {"api-key": azure_search_key, "Content-Type": "application/json"}
        params = {
            "api-version": "2024-07-01",
            "search": "*",
            "$filter": f"workspace_id eq '{workspace_id}' and file_name eq '{file_name}'",
            "$select": "chunk_id",
            "$top": 1000
        }
        response = requests.get(search_url, headers=headers, params=params)
        if response.status_code != 200:
            return
        
        docs = response.json().get("value", [])
        if not docs:
            return
        
        # Delete all chunks
        delete_url = f"https://{azure_search_service}.search.windows.net/indexes/{index_name}/docs/index?api-version=2024-07-01"
        batch = {"value": [{"@search.action": "delete", "chunk_id": doc["chunk_id"]} for doc in docs]}
        requests.post(delete_url, json=batch, headers=headers)
        indexing_logger.info(f"Deleted {len(docs)} chunks from search index for: {file_name}")
    except Exception as e:
        indexing_logger.error(f"Failed to delete from search index: {str(e)}")


async def upload_file_to_user_workspace_container(file: bytes, blob_path: str, metadata: dict = None):
    """Upload file to the user workspace container with metadata"""
    container_client = blob_service_client.get_container_client(USER_WORKSPACE_CONTAINER)
    
    # Create container if it doesn't exist
    try:
        await container_client.create_container()
    except Exception:
        pass  # Container already exists
    
    blob_client = container_client.get_blob_client(blob_path)
    import mimetypes
    from azure.storage.blob import ContentSettings
    content_type, _ = mimetypes.guess_type(blob_path)
    await blob_client.upload_blob(
        file, overwrite=True, metadata=metadata or {},
        content_settings=ContentSettings(content_type=content_type or "application/octet-stream")
    )

async def get_blob_metadata(blob_path: str) -> dict:
    """Get metadata from blob storage"""
    try:
        container_client = blob_service_client.get_container_client(USER_WORKSPACE_CONTAINER)
        blob_client = container_client.get_blob_client(blob_path)
        properties = await blob_client.get_blob_properties()
        return properties.metadata or {}
    except Exception as e:
        print(f"Error getting blob metadata: {str(e)}")
        return {}

def check_file_indexed(workspace_id: str, file_name: str) -> bool:
    """Check if a file exists in the Azure Search index"""
    import requests as req
    search_service = os.getenv("AZURE_SEARCH_SERVICE")
    search_key = os.getenv("AZURE_SEARCH_KEY")
    if not search_service or not search_key:
        return False
    url = f"https://{search_service}.search.windows.net/indexes/tenaliaiaz-jlens-user-workspace/docs/search?api-version=2023-11-01"
    headers = {"api-key": search_key, "Content-Type": "application/json"}
    body = {"search": file_name, "searchFields": "file_name", "filter": f"workspace_id eq '{workspace_id}'", "top": 1, "select": "file_name"}
    try:
        r = req.post(url, headers=headers, json=body, timeout=5)
        if r.status_code == 200:
            return len(r.json().get("value", [])) > 0
    except Exception:
        pass
    return False


def generate_user_workspace_sas_url(blob_path: str) -> str:
    """Generate SAS URL for user workspace files with download permissions"""
    try:
        from azure.storage.blob import generate_blob_sas, BlobSasPermissions
        from datetime import datetime, timedelta
        import os
        
        # Get storage account details from connection string
        connection_string = os.getenv("AZURE_BLOB_STORAGE_CONNECTION_STRING")
        if not connection_string:
            return ""
        
        # Parse account name from connection string
        account_name = None
        account_key = None
        for part in connection_string.split(';'):
            if part.startswith('AccountName='):
                account_name = part.split('=', 1)[1]
            elif part.startswith('AccountKey='):
                account_key = part.split('=', 1)[1]
        
        if not account_name or not account_key:
            return ""
        
        # Generate SAS token with download permissions
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=USER_WORKSPACE_CONTAINER,
            blob_name=blob_path,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=24)  # 24 hour expiry
        )
        
        # Return full URL with SAS token
        return f"https://{account_name}.blob.core.windows.net/{USER_WORKSPACE_CONTAINER}/{blob_path}?{sas_token}"
        
    except Exception as e:
        print(f"Error generating SAS URL: {e}")
        return ""

async def process_user_workspace_file_upload(db: Session, user: User, workspace: Workspace, 
                                           file_content: bytes, filename: str, conversation_id: str = None) -> Dict[str, Any]:
    """Process file upload for own/shared workspaces with blob metadata storage"""
    try:
        # Generate blob path for user workspace container
        blob_path = f"{workspace.id}/{user.id}/{filename}"
        
        # Generate SAS download URL for the file
        file_link = generate_user_workspace_sas_url(blob_path)
        
        # Prepare metadata for blob storage (only essential fields)
        blob_metadata = {
            "file_name": filename,
            "file_link": file_link,
            "file_size": str(len(file_content)),
            "user_id": str(user.id),
            "user_name": user.name,
            "uploaded_datetime": datetime.utcnow().isoformat(),
            "workspace_id": str(workspace.id),
            "workspace_name": workspace.name,
        }
        
        # Extract text BEFORE uploading — reject if no extractable text
        text_content = extract_text_from_file(file_content, filename)
        has_extractable_text = bool(text_content and text_content.strip() and len(text_content.strip()) > 10)
        if not has_extractable_text:
            indexing_logger.warning(f"Rejecting upload for {filename} — no extractable text (scanned/image PDF)")
            return {
                "filename": filename,
                "error": "This file has no extractable text (scanned/image PDF). Please upload a text-based PDF or DOCX.",
                "uploaded": False
            }
        
        # Upload to user workspace container with metadata
        await upload_file_to_user_workspace_container(file_content, blob_path, blob_metadata)
        
        # Create search document for indexing
        search_document = {
            "id": str(uuid.uuid4()),
            "title": filename,
            "chunk": text_content,
            "file_name": filename,
            "file_link": file_link,
            "user_id": str(user.id),
            "user_name": user.name,
            "workspace_id": str(workspace.id),
            "workspace_name": workspace.name,
            "uploaded_datetime": datetime.utcnow().isoformat() + "Z",
            "conversation_id": conversation_id or ""
        }
        
        # Note: We don't upload directly to search index
        # The indexer will automatically index files from blob storage
        indexing_logger.info(f"File uploaded to blob, indexer will process it automatically: {filename}")
        
        # Create file metadata in database first
        metadata = FileMetadata(
            type=FileMetadataType.workspace,
            workspace_id=workspace.id,
            name=filename,
            full_path=blob_path,
            link=file_link,
            uploaded_by_name=user.name,
            uploaded_by_email=user.email,
            created_at=datetime.utcnow(),
        )
        
        db.add(metadata)
        db.commit()
        db.refresh(metadata)
        
        # Trigger user workspace indexer (fire-and-forget, don't wait for completion)
        indexer_result = False
        
        try:
            indexing_logger.info(f"Triggering user workspace indexer for file: {filename}")
            indexer_result = await trigger_user_workspace_indexer()
            indexing_logger.info(f"Indexer trigger result: {indexer_result}")
        except Exception as e:
            indexing_logger.error(f"Failed to trigger user workspace indexer: {str(e)}")
        
        return {
            "filename": filename,
            "link": file_link,
            "blob_path": blob_path,
            "metadata_id": str(metadata.id),
            "uploaded": True,
            "indexed": False,
            "indexer_triggered": indexer_result
        }
        
    except Exception as e:
        indexing_logger.error(f"Error processing file upload for {filename}: {str(e)}")
        return {
            "filename": filename,
            "error": str(e)
        }

# --- Azure Blob client (async) ---

_AZURE_CONN_STR = os.getenv("AZURE_BLOB_STORAGE_CONNECTION_STRING")
if not _AZURE_CONN_STR:
    raise RuntimeError(
        "AZURE_BLOB_STORAGE_CONNECTION_STRING is not set. "
        "Please set it in your environment."
    )


# -----------------------
# Workspace/File helpers
# -----------------------

def ensure_workspace_owned_by_user(db: Session, workspace_id: UUID, user_id: UUID) -> Optional[Workspace]:
    return (
        db.query(Workspace)
        .filter(Workspace.id == workspace_id, Workspace.user_id == user_id)
        .first()
    )

def ensure_workspace_accessible_by_user(db: Session, workspace_id: UUID, user_id: UUID) -> Optional[Workspace]:
    """Check if user owns workspace or has shared access or is system workspace"""
    from db.models import WorkspaceShare
    
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        return None
    
    # System workspaces are accessible to all authenticated users
    if workspace.is_system_workspace:
        return workspace
    
    # Check if user owns it
    if workspace.user_id == user_id:
        return workspace
    
    # Check if shared with user
    is_shared = db.query(WorkspaceShare).filter(
        WorkspaceShare.workspace_id == workspace_id,
        WorkspaceShare.shared_with_id == user_id
    ).first()
    
    return workspace if is_shared else None


def list_user_workspace_files(db: Session, workspace_id: UUID, user_id: UUID) -> List[FileMetadataOut]:
    """List files from user workspace using search index"""
    import requests
    import os
    
    try:
        # Get Azure Search credentials
        search_service = os.getenv("AZURE_SEARCH_SERVICE")
        search_key = os.getenv("AZURE_SEARCH_KEY")
        index_name = "tenaliaiaz-jlens-user-workspace"
        
        if not search_service or not search_key:
            return []
        
        # Search Azure index for documents in this specific workspace only
        search_url = f"https://{search_service}.search.windows.net/indexes/{index_name}/docs"
        headers = {
            "api-key": search_key,
            "Content-Type": "application/json"
        }
        
        params = {
            "api-version": "2023-11-01",
            "search": "*",
            "$filter": f"workspace_id eq '{workspace_id}'",
            "$top": 50,
            "$select": "file_name,file_link,user_name,workspace_name,uploaded_datetime,chunk,workspace_id"
        }
        
        response = requests.get(search_url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"Search API error: {response.status_code} - {response.text}")
            return []
        
        results = response.json()
        documents = results.get("value", [])
        
        files = []
        seen_files = set()
        
        for doc in documents:
            # Double-check workspace_id matches (extra safety)
            doc_workspace_id = doc.get("workspace_id")
            if doc_workspace_id != str(workspace_id):
                continue
                
            file_name = doc.get("file_name", "Unknown File")
            
            # Skip duplicates (same file name)
            if file_name in seen_files:
                continue
            seen_files.add(file_name)
            
            # Extract blob path from file_link
            file_link = doc.get("file_link", "")
            blob_path = ""
            if file_link and USER_WORKSPACE_CONTAINER in file_link:
                blob_path = file_link.split(f"{USER_WORKSPACE_CONTAINER}/")[-1]
            
            # Generate SAS URL for secure access
            sas_url = generate_user_workspace_sas_url(blob_path) if blob_path else file_link
            
            # Parse upload datetime
            uploaded_datetime = None
            if doc.get("uploaded_datetime"):
                try:
                    uploaded_datetime = datetime.fromisoformat(doc["uploaded_datetime"].replace("Z", "+00:00"))
                except:
                    uploaded_datetime = datetime.utcnow()
            
            file_meta = FileMetadataOut(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                name=file_name,
                full_path=blob_path,
                link=sas_url,
                content_type="application/pdf",
                size=len(doc.get("chunk", "")),
                created_at=uploaded_datetime or datetime.utcnow(),
                type=FileMetadataType.workspace,
                # User workspace specific fields
                last_modified_by_name=doc.get("user_name"),
                last_modified_datetime=uploaded_datetime
            )
            files.append(file_meta)
        
        return files
        
    except Exception as e:
        print(f"Error listing user workspace files: {str(e)}")
        # Fallback to database
        db_files = db.query(FileMetadata).filter(FileMetadata.workspace_id == workspace_id).all()
        return db_files

def list_workspace_files(db: Session, workspace_id: UUID, user_id: UUID = None) -> List[FileMetadata]:
    """Return files in workspace - updated to handle different workspace types"""
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    
    if not workspace:
        return []
    
    # For Jman Sales workspace, use SharePoint index (sync version)
    if workspace.name == "Jman Sales":
        return list_jman_sales_files_sync(db, workspace_id)
    
    if workspace.name == "Nexus":
        return list_nexus_files_sync(db, workspace_id)
    
    if workspace.name == "AISOW":
        return list_aisow_files_sync(db, workspace_id)
    
    if workspace.name == "Demo":
        return list_demo_files_sync(db, workspace_id)
    
    # For user workspaces (own/shared), use database (files available immediately after upload)
    if workspace.workspace_type in [WorkspaceType.own, WorkspaceType.shared]:
        return (
            db.query(FileMetadata)
            .filter(FileMetadata.workspace_id == workspace_id)
            .order_by(FileMetadata.created_at.desc())
            .all()
        )
    
    # For other system workspaces, use database
    return (
        db.query(FileMetadata)
        .filter(FileMetadata.workspace_id == workspace_id)
        .all()
    )


# -----------------------
# Inline streaming (no Range support)
# -----------------------

async def stream_blob_file(
    container_name: str,
    blob_path: str,
    filename: str,
    disposition: str = "inline",
) -> StreamingResponse:
    """
    Stream a blob with configurable Content-Disposition.
    disposition='inline' for preview, 'attachment' for download.
    """
    client = BlobServiceClient.from_connection_string(AZURE_BLOB_STORAGE_CONNECTION_STRING)
    blob = client.get_blob_client(
        container=container_name, blob=blob_path)
    props = await blob.get_blob_properties()

    content_type = (
        props.content_settings and props.content_settings.content_type) or "application/octet-stream"
    if content_type == "application/octet-stream":
        import mimetypes
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            content_type = guessed
    file_size = props.size

    downloader = await blob.download_blob()

    async def iter_all():
        async for chunk in downloader.chunks():
            yield chunk
        await client.close()

    disp = "attachment" if disposition == "attachment" else "inline"
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'{disp}; filename="{filename}"',
        "Content-Length": str(file_size),
    }
    return StreamingResponse(iter_all(), media_type=content_type, headers=headers)


async def stream_blob_inline(
    container_name: str,
    blob_path: str,
    filename: str,
) -> StreamingResponse:
    """
    Stream a blob with Content-Disposition:inline so the browser renders it
    (PDF/image/video/audio/text). No Range/seek support.
    """
    client = BlobServiceClient.from_connection_string(AZURE_BLOB_STORAGE_CONNECTION_STRING)
    blob = client.get_blob_client(
        container=container_name, blob=blob_path)
    props = await blob.get_blob_properties()

    content_type = (
        props.content_settings and props.content_settings.content_type) or "application/octet-stream"
    file_size = props.size

    downloader = await blob.download_blob()

    async def iter_all():
        async for chunk in downloader.chunks():
            yield chunk
        await client.close()

    headers = {
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'inline; filename="{filename}"',
        "Content-Length": str(file_size),
    }
    return StreamingResponse(iter_all(), media_type=content_type, headers=headers)


async def list_jman_sales_files(db: Session, current_user) -> List[FileMetadataOut]:
    """Get JMAN Sales files from Azure Search index instead of blob storage"""
    import requests
    import os
    from datetime import datetime
    
    # Get Azure Search credentials
    search_service = os.getenv("AZURE_SEARCH_SERVICE")
    search_key = os.getenv("AZURE_SEARCH_KEY")
    index_name = "tenaliaiaz-sharepoint-sales-index"
    
    if not search_service or not search_key:
        return []
    
    # Get workspace
    workspace = db.query(Workspace).filter(Workspace.name == "Jman Sales").first()
    if not workspace:
        return []
    
    # Search Azure index for all documents
    search_url = f"https://{search_service}.search.windows.net/indexes/{index_name}/docs"
    headers = {
        "api-key": search_key,
        "Content-Type": "application/json"
    }
    
    # Get the actual documents
    params = {
        "api-version": "2023-11-01",
        "search": "*",
        "top": 50,
        "count": "true",
        "orderby": "last_modified_datetime desc",
        "select": "sharepoint_name,sharepoint_url,last_modified_by_email,last_modified_by_name,last_modified_datetime,chunk"
    }
    
    try:
        response = requests.get(search_url, headers=headers, params=params)
        if response.status_code != 200:
            return []
        
        results = response.json()
        documents = results.get("value", [])
        
        files = []
        seen_files = set()  # Track unique files by name to avoid duplicates
        
        for doc in documents:
            file_name = doc.get("sharepoint_name", "Unknown File")
            
            # Skip duplicates (same file name)
            if file_name in seen_files:
                continue
            seen_files.add(file_name)
            
            # Parse datetime if available
            modified_datetime = None
            if doc.get("last_modified_datetime"):
                try:
                    modified_datetime = datetime.fromisoformat(doc["last_modified_datetime"].replace("Z", "+00:00"))
                except:
                    modified_datetime = None
            
            file_meta = FileMetadataOut(
                id=uuid.uuid4(),
                workspace_id=workspace.id,
                name=file_name,
                full_path=doc.get("sharepoint_url", ""),
                link=doc.get("sharepoint_url", ""),
                content_type="application/pdf",
                size=len(doc.get("chunk", "")),
                created_at=modified_datetime or datetime.utcnow(),
                type=FileMetadataType.sharepoint,
                # SharePoint specific fields
                sharepoint_link=doc.get("sharepoint_url"),
                last_modified_by_email=doc.get("last_modified_by_email"),
                last_modified_by_name=doc.get("last_modified_by_name"),
                last_modified_datetime=modified_datetime,
                sharepoint_name=file_name
            )
            files.append(file_meta)
        
        return files
        
    except Exception as e:
        print(f"Error fetching JMAN Sales files from search index: {e}")
        return []
    

def list_jman_sales_files_sync(db: Session, workspace_id: UUID) -> List[FileMetadataOut]:
    """Synchronous version for Jman Sales files"""
    import requests
    import os
    from datetime import datetime
    
    # Get Azure Search credentials
    search_service = os.getenv("AZURE_SEARCH_SERVICE")
    search_key = os.getenv("AZURE_SEARCH_KEY")
    index_name = "tenaliaiaz-sharepoint-sales-index"
    
    if not search_service or not search_key:
        return []
    
    # Search Azure index for all documents
    search_url = f"https://{search_service}.search.windows.net/indexes/{index_name}/docs"
    headers = {
        "api-key": search_key,
        "Content-Type": "application/json"
    }
    
    params = {
        "api-version": "2023-11-01",
        "search": "*",
        "top": 50,
        "orderby": "last_modified_datetime desc",
        "select": "sharepoint_name,sharepoint_url,last_modified_by_email,last_modified_by_name,last_modified_datetime,chunk"
    }
    
    try:
        response = requests.get(search_url, headers=headers, params=params)
        if response.status_code != 200:
            return []
        
        results = response.json()
        documents = results.get("value", [])
        
        files = []
        seen_files = set()
        
        for doc in documents:
            file_name = doc.get("sharepoint_name", "Unknown File")
            
            if file_name in seen_files:
                continue
            seen_files.add(file_name)
            
            modified_datetime = None
            if doc.get("last_modified_datetime"):
                try:
                    modified_datetime = datetime.fromisoformat(doc["last_modified_datetime"].replace("Z", "+00:00"))
                except:
                    modified_datetime = None
            
            file_meta = FileMetadataOut(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                name=file_name,
                full_path=doc.get("sharepoint_url", ""),
                link=doc.get("sharepoint_url", ""),
                content_type="application/pdf",
                size=len(doc.get("chunk", "")),
                created_at=modified_datetime or datetime.utcnow(),
                type=FileMetadataType.sharepoint,
                sharepoint_link=doc.get("sharepoint_url"),
                last_modified_by_email=doc.get("last_modified_by_email"),
                last_modified_by_name=doc.get("last_modified_by_name"),
                last_modified_datetime=modified_datetime,
                sharepoint_name=file_name
            )
            files.append(file_meta)
        
        return files
        
    except Exception as e:
        print(f"Error fetching JMAN Sales files: {e}")
        return []
    

def list_nexus_files_sync(db: Session, workspace_id: UUID) -> List[FileMetadataOut]:
    """Synchronous version for Nexus files"""
    import requests
    import os
    from datetime import datetime
    
    # Get Azure Search credentials
    search_service = os.getenv("AZURE_SEARCH_SERVICE")
    search_key = os.getenv("AZURE_SEARCH_KEY")
    index_name = "nexus-ms"
    
    if not search_service or not search_key:
        return []
    
    # Search Azure index for all documents
    search_url = f"https://{search_service}.search.windows.net/indexes/{index_name}/docs"
    headers = {
        "api-key": search_key,
        "Content-Type": "application/json"
    }
    
    params = {
        "api-version": "2023-11-01",
        "search": "*",
        "top": 50,
        "orderby": "title desc",
        "select": "title,chunk"
    }
    
    try:
        response = requests.get(search_url, headers=headers, params=params)
        if response.status_code != 200:
            return []
        
        results = response.json()
        documents = results.get("value", [])
        
        files = []
        seen_files = set()
        
        for doc in documents:
            file_name = doc.get("title", "Unknown File")
            
            if file_name in seen_files:
                continue
            seen_files.add(file_name)
            
            modified_datetime = None
            # if doc.get("last_modified_datetime"):
            #     try:
            #         modified_datetime = datetime.fromisoformat(doc["last_modified_datetime"].replace("Z", "+00:00"))
            #     except:
            #         modified_datetime = None
            
            file_meta = FileMetadataOut(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                name=file_name,
                full_path="",
                size=len(doc.get("chunk", "")),
                created_at=modified_datetime or datetime.utcnow(),
                last_modified_datetime=modified_datetime,
            )
            files.append(file_meta)
        
        return files
        
    except Exception as e:
        print(f"Error fetching Nexus files: {e}")
        return []

def list_aisow_files_sync(db: Session, workspace_id: UUID) -> List[FileMetadataOut]:
    """Synchronous version for AISOW files"""
    import requests
    import os
    from datetime import datetime
    
    # Get Azure Search credentials
    search_service = os.getenv("AZURE_SEARCH_SERVICE")
    search_key = os.getenv("AZURE_SEARCH_KEY")
    index_name = "tenaliaz-aisow-index"
    
    if not search_service or not search_key:
        return []
    
    # Search Azure index for all documents
    search_url = f"https://{search_service}.search.windows.net/indexes/{index_name}/docs"
    headers = {
        "api-key": search_key,
        "Content-Type": "application/json"
    }
    
    params = {
        "api-version": "2023-11-01",
        "search": "*",
        "top": 50,
        "orderby": "last_modified_datetime desc",
        "select": "sharepoint_name,sharepoint_url,last_modified_by_email,last_modified_by_name,last_modified_datetime,chunk"
    }
    
    try:
        response = requests.get(search_url, headers=headers, params=params)
        if response.status_code != 200:
            return []
        
        results = response.json()
        documents = results.get("value", [])
        
        files = []
        seen_files = set()
        
        for doc in documents:
            file_name = doc.get("sharepoint_name", "Unknown File")
            
            if file_name in seen_files:
                continue
            seen_files.add(file_name)
            
            modified_datetime = None
            if doc.get("last_modified_datetime"):
                try:
                    modified_datetime = datetime.fromisoformat(doc["last_modified_datetime"].replace("Z", "+00:00"))
                except:
                    modified_datetime = None
            
            file_meta = FileMetadataOut(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                name=file_name,
                full_path=doc.get("sharepoint_url", ""),
                link=doc.get("sharepoint_url", ""),
                content_type="application/pdf",
                size=len(doc.get("chunk", "")),
                created_at=modified_datetime or datetime.utcnow(),
                type=FileMetadataType.sharepoint,
                sharepoint_link=doc.get("sharepoint_url"),
                last_modified_by_email=doc.get("last_modified_by_email"),
                last_modified_by_name=doc.get("last_modified_by_name"),
                last_modified_datetime=modified_datetime,
                sharepoint_name=file_name
            )
            files.append(file_meta)
        
        return files
        
    except Exception as e:
        print(f"Error fetching AISOW files: {e}")
        return []


def list_demo_files_sync(db: Session, workspace_id: UUID) -> List[FileMetadataOut]:
    """List files from Demo workspace search index"""
    import requests
    import os
    from datetime import datetime

    search_service = os.getenv("AZURE_SEARCH_SERVICE")
    search_key = os.getenv("AZURE_SEARCH_KEY")
    index_name = "tenaliaz-demo-index"

    if not search_service or not search_key:
        return []

    search_url = f"https://{search_service}.search.windows.net/indexes/{index_name}/docs"
    headers = {"api-key": search_key, "Content-Type": "application/json"}
    params = {
        "api-version": "2023-11-01",
        "search": "*",
        "top": 50,
        "select": "title,sharepoint_url,last_modified_datetime,domains,client,chunk"
    }

    try:
        response = requests.get(search_url, headers=headers, params=params)
        if response.status_code != 200:
            return []

        documents = response.json().get("value", [])
        files = []
        seen_files = set()

        for doc in documents:
            file_name = doc.get("title", "Unknown File")
            if file_name in seen_files:
                continue
            seen_files.add(file_name)

            modified_datetime = None
            if doc.get("last_modified_datetime"):
                try:
                    modified_datetime = datetime.fromisoformat(doc["last_modified_datetime"].replace("Z", "+00:00"))
                except:
                    modified_datetime = None

            file_meta = FileMetadataOut(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                name=file_name,
                full_path=doc.get("sharepoint_url", ""),
                link=doc.get("sharepoint_url", ""),
                content_type="application/pdf",
                size=len(doc.get("chunk", "")),
                created_at=modified_datetime or datetime.utcnow(),
                type=FileMetadataType.sharepoint,
                sharepoint_link=doc.get("sharepoint_url"),
                last_modified_datetime=modified_datetime,
                sharepoint_name=file_name
            )
            files.append(file_meta)

        return files

    except Exception as e:
        print(f"Error fetching Demo files: {e}")
        return []


async def generate_sas_url(container_name: str, blob_name: str):
    """
    Generate a time-limited SAS URL for a blob in Azure Blob Storage.
    """
    from azure.storage.blob import BlobServiceClient
    blob_service_client = BlobServiceClient.from_connection_string(
        AZURE_BLOB_STORAGE_CONNECTION_STRING)

    # Extract account details
    account_name = blob_service_client.account_name
    account_key = blob_service_client.credential.account_key
    sas_expiry = datetime.utcnow() + timedelta(minutes=15)
    # Extract file extension from blob_name (handles multiple dots)
    content_type, _ = mimetypes.guess_type(blob_name)
    if not content_type:
        content_type = "application/octet-stream"

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container_name,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=sas_expiry,
        content_disposition="inline",
        content_type=content_type
    )

    # URL-encode blob name to handle spaces and special characters
    encoded_blob_name = quote(blob_name, safe="/")

    blob_url = (
        f"https://{account_name}.blob.core.windows.net/"
        f"{container_name}/{encoded_blob_name}?{sas_token}"
    )

    return {
        "sas_url": blob_url,
        "expires_at": sas_expiry.isoformat() + "Z"
    }


async def test_mcp_db(data):
    db_uri = data.db_uri
    db_type = data.db_type

    if db_type.lower() == "postgres":
        # Test Postgres connection
        import asyncpg
        try:
            conn = await asyncpg.connect(dsn=db_uri)
            await conn.close()
            return True
        except Exception as e:
            return False
    elif db_type.lower() == "mongo" or db_type.lower() == "mongodb":
        # Test MongoDB connection
        try:
            client = AsyncIOMotorClient(db_uri, serverSelectionTimeoutMS=3000)
            await client.admin.command('ping')
            client.close()
            return True
        except Exception:
            return False
    else:
        # Unsupported DB type
        return False


async def add_mcp_controller(data: AddMcp, db: Session, current_user: UUID) -> McpDbConfig:
    mcp_db_config = McpDbConfig(
        name=data.name,
        type=data.db_type,
        db_uri=data.db_uri,
        workspace_id=data.workspace_id,
        description=data.description,
        read_only=data.read_only,

        # SSH tunnel metadata
        ssh_tunnel=data.ssh_tunnel,
        ssh_host=data.ssh_host,
        ssh_port=data.ssh_port,
        ssh_username=data.ssh_username,
        ssh_local_port=data.ssh_local_port,
        ssh_remote_host=data.ssh_remote_host,
        ssh_remote_port=data.ssh_remote_port,
    )

    # Handle secrets securely
    if data.ssh_password:
        mcp_db_config.set_ssh_password(data.ssh_password)

    if data.ssh_private_key:
        mcp_db_config.set_ssh_private_key(data.ssh_private_key)

    db.add(mcp_db_config)
    db.commit()
    db.refresh(mcp_db_config)
    return mcp_db_config


async def get_mcp_by_workspace(db: Session, workspace_id: UUID, current_user: User):
    rows = db.query(
        McpDbConfig.description,
        McpDbConfig.name,
        McpDbConfig.type,
        McpDbConfig.workspace_id
    ).join(Workspace).filter(
        McpDbConfig.workspace_id == workspace_id,
        Workspace.user_id == current_user.id
    ).all()

    result = [
        {
            "description": row[0],
            "name": row[1],
            "type": row[2],
            "workspace_id": row[3]
        } for row in rows
    ]

    return result


async def get_mcp_by_id(mcp_id: UUID, db: Session, current_user: UUID):
    mcp = db.query(McpDbConfig).filter(McpDbConfig.id == mcp_id).first()
    if not mcp:
        raise HTTPException(status_code=404, detail="MCP not found")
    
    # Verify user has access to the workspace
    if not check_workspace_access(db, current_user, mcp.workspace_id):
        raise HTTPException(status_code=403, detail="Access denied to this MCP configuration")
    
    return mcp


async def update_mcp_controller(mcp_id: UUID, data: UpdateMcp, db: Session, current_user: UUID):
    mcp = db.query(McpDbConfig).filter(McpDbConfig.id == mcp_id).first()
    if not mcp:
        raise HTTPException(status_code=404, detail="MCP not found")
    
    # Verify user has access to the workspace
    if not check_workspace_access(db, current_user, mcp.workspace_id):
        raise HTTPException(status_code=403, detail="Access denied to this MCP configuration")

    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        if key == "ssh_password" and value:
            mcp.set_ssh_password(value)
        elif key == "ssh_private_key" and value:
            mcp.set_ssh_private_key(value)
        else:
            setattr(mcp, key, value)

    db.commit()
    db.refresh(mcp)
    return mcp


async def delete_mcp_controller(mcp_id: UUID, db: Session, current_user: UUID):
    mcp = db.query(McpDbConfig).filter(McpDbConfig.id == mcp_id).first()
    if not mcp:
        raise HTTPException(status_code=404, detail="MCP not found")
    
    # Verify user has access to the workspace
    if not check_workspace_access(db, current_user, mcp.workspace_id):
        raise HTTPException(status_code=403, detail="Access denied to this MCP configuration")
    
    db.delete(mcp)
    db.commit()
    return {"message": "MCP deleted successfully"}


def share_workspace(db: Session, current_user: User, data):
    from db.models import WorkspaceShare
    
    # Verify workspace exists and user owns it
    workspace = db.query(Workspace).filter(
        Workspace.id == data.workspace_id,
        Workspace.user_id == current_user.id
    ).first()
    
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found or you don't own it")
    
    # Find user to share with
    shared_user = db.query(User).filter(User.email == data.shared_with_email).first()
    if not shared_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if already shared
    existing_share = db.query(WorkspaceShare).filter(
        WorkspaceShare.workspace_id == data.workspace_id,
        WorkspaceShare.shared_with_id == shared_user.id
    ).first()
    
    if existing_share:
        raise HTTPException(status_code=400, detail="Workspace already shared with this user")
    
    # Create share
    share = WorkspaceShare(
        workspace_id=data.workspace_id,
        owner_id=current_user.id,
        shared_with_id=shared_user.id
    )
    db.add(share)
    db.commit()
    
    return {"message": "Workspace shared successfully"}


def unshare_workspace(db: Session, current_user: User, data):
    from db.models import WorkspaceShare
    
    # User can unshare if they are the shared_with user
    share = db.query(WorkspaceShare).filter(
        WorkspaceShare.workspace_id == data.workspace_id,
        WorkspaceShare.shared_with_id == current_user.id
    ).first()
    
    if not share:
        raise HTTPException(status_code=404, detail="Shared workspace not found")
    
    db.delete(share)
    db.commit()
    
    return {"message": "Workspace unshared successfully"}

async def wait_for_indexer_completion(indexer_name: str, timeout: int = 60):
    """Wait for a NEW indexer run to complete (compares timestamps to avoid stale status)"""
    try:
        import requests
        import time
        import os
        from datetime import datetime as dt
        
        azure_search_service = os.getenv("AZURE_SEARCH_SERVICE")
        azure_search_key = os.getenv("AZURE_SEARCH_KEY")
        
        status_url = f'https://{azure_search_service}.search.windows.net/indexers/{indexer_name}/status?api-version=2024-07-01'
        headers = {
            'api-key': azure_search_key,
            'Content-Type': 'application/json'
        }
        
        # Get the current lastResult.endTime BEFORE waiting
        response = requests.get(status_url, headers=headers)
        if response.status_code != 200:
            return False
        
        before_data = response.json()
        before_end_time = before_data.get('lastResult', {}).get('endTime', '')
        
        indexing_logger.info(f"Waiting for new indexer run (previous endTime: {before_end_time})")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            await asyncio.sleep(3)
            
            response = requests.get(status_url, headers=headers)
            if response.status_code != 200:
                continue
            
            status_data = response.json()
            last_result = status_data.get('lastResult', {})
            current_end_time = last_result.get('endTime', '')
            status = last_result.get('status', 'unknown')
            
            # Check if this is a NEW run (endTime changed)
            if current_end_time and current_end_time != before_end_time:
                indexing_logger.info(f"New indexer run completed: status={status}, endTime={current_end_time}")
                return status == 'success'
        
        indexing_logger.warning(f"Indexer timeout after {timeout} seconds — no new run detected")
        return False
        
    except Exception as e:
        indexing_logger.error(f"Error waiting for indexer: {str(e)}")
        return False
async def trigger_user_workspace_indexer():
    """Trigger user workspace indexer after file upload"""
    try:
        import requests
        import os
        
        # Get environment variables
        azure_search_service = os.getenv("AZURE_SEARCH_SERVICE")
        azure_search_key = os.getenv("AZURE_SEARCH_KEY")
        
        indexer_name = "tenaliaiaz-jlens-user-workspace-indexer"
        indexing_logger.info(f"Triggering indexer: {indexer_name}")
        
        indexer_url = f'https://{azure_search_service}.search.windows.net/indexers/{indexer_name}/run?api-version=2020-06-30'
        
        headers = {
            'api-key': azure_search_key,
            'Content-Type': 'application/json'
        }
        
        response = requests.post(indexer_url, headers=headers)
        indexing_logger.info(f"Indexer response status: {response.status_code}")
        
        if response.status_code == 202:
            indexing_logger.info("User workspace indexer triggered successfully")
            return True
        else:
            indexing_logger.warning(f"Indexer trigger failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        indexing_logger.error(f"Error triggering user workspace indexer: {str(e)}")
        return False


async def get_workspace_storage(db: Session, workspace_id: UUID) -> Dict[str, Any]:
    """Calculate total storage used by a workspace from DB file count"""
    QUOTA_BYTES = 500 * 1024 * 1024  # 500MB
    MAX_FILES = 50

    # Use DB count (instant) instead of listing blobs (slow)
    file_count = db.query(FileMetadata).filter(FileMetadata.workspace_id == workspace_id).count()
    # Estimate size: average file ~2MB
    estimated_size = file_count * 2 * 1024 * 1024

    return {
        "used_bytes": estimated_size,
        "quota_bytes": QUOTA_BYTES,
        "used_mb": round(estimated_size / (1024 * 1024), 2),
        "quota_mb": 500,
        "file_count": file_count,
        "max_files": MAX_FILES,
        "percentage": round((file_count / MAX_FILES) * 100, 1) if MAX_FILES > 0 else 0,
    }


# TODO: Uncomment after running migration (see DATA_MODEL_CHANGES.md)
# async def reindex_file(db, file_meta): ...
# async def retry_failed_indexing(db): ...

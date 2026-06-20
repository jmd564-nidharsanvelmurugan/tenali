from sqlalchemy.orm import Session
from uuid import UUID
from . import services, schemas
from typing import List
from fastapi import UploadFile, HTTPException, Request
from sqlalchemy.orm import Session
from db.models import FileMetadata, FileMetadataType, User, Workspace, WorkspaceType
from datetime import datetime
import os
import requests
from dotenv import load_dotenv
load_dotenv()

AZURE_BLOB_STORAGE_CONTAINER_NAME= os.environ.get("AZURE_BLOB_STORAGE_CONTAINER_NAME")
AZURE_BLOB_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_BLOB_STORAGE_CONNECTION_STRING")

AZURE_SEARCH_SERVICE = os.getenv("AZURE_SEARCH_SERVICE")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_SERVICE_INDEXER_WORKSPACE_NAME = os.getenv("AZURE_SEARCH_SERVICE_INDEXER_WORKSPACE_NAME")

def create_workspace_controller(db: Session, current_user: User, data: schemas.WorkspaceCreate):
    return services.create_workspace(db, current_user.id, data)

def create_system_workspace_controller(db: Session, data: schemas.WorkspaceCreate):
    return services.create_system_workspace(db, data)

def get_all_system_workspaces_controller(db: Session):
    return services.get_all_system_workspaces(db)

def update_system_workspace_controller(db: Session, workspace_id: UUID, data: schemas.WorkspaceCreate):
    return services.update_system_workspace(db, workspace_id, data)

def delete_system_workspace_controller(db: Session, workspace_id: UUID):
    return services.delete_system_workspace(db, workspace_id)

def create_sales_workspace_controller(db: Session):
    return services.create_system_workspace(db, schemas.WorkspaceCreate(
        name="Jman Sales", 
        description="Sales related workspace", 
        preprompt="You are a sales assistant with access to company sales materials and documents.",
        is_private=False
    ))

def create_nexus_workspace_controller(db: Session):
    return services.create_system_workspace(db, schemas.WorkspaceCreate(
        name="Nexus", 
        description="Nexus related workspace", 
        preprompt="You are a Nexus assistant with access to company SOP materials and documents.",
        is_private=False
    ))

def create_aisow_workspace_controller(db: Session):
    return services.create_system_workspace(db, schemas.WorkspaceCreate(
        name="AISOW", 
        description="AISOW related workspace", 
        preprompt="You are an AISOW assistant with access to company AISOW materials and documents.",
        is_private=False
    ))

def create_marketing_workspace_controller(db: Session):
    return services.create_system_workspace(db, schemas.WorkspaceCreate(
        name="Marketing Hub",
        description="Marketing materials and campaign resources",
        preprompt="You are a marketing assistant with access to marketing materials, brand guidelines, and campaign resources.",
        is_private=False
    ))

def create_hr_workspace_controller(db: Session):
    return services.create_system_workspace(db, schemas.WorkspaceCreate(
        name="HR Portal",
        description="Human resources policies and employee information",
        preprompt="You are an HR assistant with access to company policies, employee handbooks, and HR procedures.",
        is_private=False
    ))

def create_knowledge_base_controller(db: Session):
    return services.create_system_workspace(db, schemas.WorkspaceCreate(
        name="Company Knowledge Base",
        description="General company information and policies",
        preprompt="You are a company assistant with access to company policies, procedures, and general information.",
        is_private=False
    ))

def get_user_workspaces_controller(db: Session, current_user: User):
    return services.get_user_workspaces(db, current_user.id)

def get_accessible_workspaces_controller(db: Session, current_user: User):
    return services.get_accessible_workspaces(db, current_user.id)

def get_all_workspaces_controller(db: Session):
    return services.get_all_workspaces(db)

def get_user_shared_workspaces_controller(db: Session, workspace_id: UUID):
    return services.get_shared_workspaces(db, workspace_id)

def delete_workspace_controller(db: Session, current_user: User, workspace_id: UUID):
    return services.delete_workspace(db, workspace_id, current_user.id)

def add_mcp_controller(data: schemas.AddMcp, db: Session, current_user: User):
    return services.add_mcp_controller(data, db, current_user.id)

async def test_mcp_db_controller(data: schemas.TestMcpDb):
    return await services.test_mcp_db(data)

async def get_mcp_controller(workspace_id: UUID, db: Session, current_user: User):
    return await services.get_mcp_by_workspace(db, workspace_id, current_user)

async def get_mcp_by_id(mcp_id: UUID, db: Session, current_user: UUID):
    return await services.get_mcp_by_id(mcp_id, db, current_user)

async def update_mcp_controller(mcp_id: UUID, data: schemas.UpdateMcp, db: Session, current_user: UUID):
    return await services.update_mcp_controller(mcp_id, data, db, current_user)

async def delete_mcp_controller(mcp_id: UUID, db: Session, current_user: UUID):
    return await services.delete_mcp_controller(mcp_id, db, current_user)

def update_pre_prompt_controller(
    workspace_id: UUID,
    data: schemas.UpdatePrePrompt,
    db: Session 
):
    updated = services.update_pre_prompt(db, workspace_id, data.pre_prompt)

    if not updated:
        raise HTTPException(status_code=404, detail="Workspace not found or not authorized to update")

    return updated


async def upload_files_progressive_controller(db: Session, user: User, workspaceId: UUID, conversationId: UUID = None, files: List[UploadFile] = None):
    """Upload files with detailed progress tracking"""
    from azure.storage.blob import BlobServiceClient
    from db.models import WorkspaceShare, WorkspaceType
    
    storage_account_name = BlobServiceClient.from_connection_string(AZURE_BLOB_STORAGE_CONNECTION_STRING).account_name
    MAX_FILES = 20
    MAX_FILE_SIZE = 16 * 1024 * 1024

    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail="Cannot upload more than 20 files at once.")

    workspace = db.query(Workspace).filter(Workspace.id == workspaceId).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    is_owner = workspace.user_id == user.id
    is_shared = db.query(WorkspaceShare).filter(
        WorkspaceShare.workspace_id == workspaceId,
        WorkspaceShare.shared_with_id == user.id
    ).first()
    
    if not is_owner and not is_shared:
        raise HTTPException(status_code=403, detail="Access denied to this workspace")

    if workspace.workspace_type == WorkspaceType.system:
        raise HTTPException(status_code=400, detail="Cannot upload files to system workspaces")

    # Check storage quota (DB-based, instant)
    MAX_FILES_PER_WORKSPACE = 50
    file_count = db.query(FileMetadata).filter(FileMetadata.workspace_id == workspaceId).count()
    if file_count + len(files) > MAX_FILES_PER_WORKSPACE:
        raise HTTPException(status_code=413, detail=f"File limit exceeded. {file_count}/{MAX_FILES_PER_WORKSPACE} files used.")

    results = []
    for file in files:
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            results.append({"filename": file.filename, "error": "file greater than 16MB", "stage": "validation"})
            continue

        result = await services.process_user_workspace_file_upload(
            db, user, workspace, contents, file.filename, conversation_id=str(conversationId) if conversationId else None
        )
        results.append(result)

    db.commit()
    
    return {
        "files": results,
        "total": len(files),
        "successful": len([r for r in results if r.get("uploaded")]),
        "failed": len([r for r in results if r.get("error")])
    }

async def upload_files_controller(db: Session, user: User, workspaceId: UUID, conversationId: UUID = None, files: List[UploadFile] = None):
    from azure.storage.blob import BlobServiceClient
    from db.models import WorkspaceShare, WorkspaceType
    
    storage_account_name = BlobServiceClient.from_connection_string(AZURE_BLOB_STORAGE_CONNECTION_STRING).account_name
    MAX_FILES = 20
    MAX_FILE_SIZE = 16 * 1024 * 1024  # 16 MB in bytes

    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail="Cannot upload more than 20 files at once.")

    # Lookup workspace
    workspace = db.query(Workspace).filter(Workspace.id == workspaceId).first()
    
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    # Check access permissions
    is_owner = workspace.user_id == user.id
    is_shared = db.query(WorkspaceShare).filter(
        WorkspaceShare.workspace_id == workspaceId,
        WorkspaceShare.shared_with_id == user.id
    ).first()
    
    if not is_owner and not is_shared:
        raise HTTPException(status_code=403, detail="Access denied to this workspace")

    # System workspaces cannot have file uploads
    if workspace.workspace_type == WorkspaceType.system:
        raise HTTPException(status_code=400, detail="Cannot upload files to system workspaces")

    uploaded_metadata = []

    for file in files:
        contents = await file.read()

        # Check file size
        if len(contents) > MAX_FILE_SIZE:
            uploaded_metadata.append({
                "filename": file.filename,
                "error": "file greater than 16MB"
            })
            continue

        # Handle different workspace types
        if workspace.workspace_type in [WorkspaceType.own, WorkspaceType.shared]:
            # Use new user workspace container and search indexing
            result = await services.process_user_workspace_file_upload(
                db, user, workspace, contents, file.filename, conversation_id=str(conversationId) if conversationId else None
            )
            uploaded_metadata.append(result)
        else:
            # Legacy system for existing workspaces (fallback)
            blob_path = f"{workspace.name}-{user.email}/workspaces----{workspace.name}-{user.email}----{file.filename}"
            await services.upload_file_to_azure_blob(contents, blob_path)
            
            metadata = FileMetadata(
                type=FileMetadataType.workspace,
                workspace_id=workspace.id,
                name=file.filename,
                full_path=blob_path,
                link=f"https://{storage_account_name}.blob.core.windows.net/{AZURE_BLOB_STORAGE_CONTAINER_NAME}/{blob_path}",
                uploaded_by_name=user.name,
                uploaded_by_email=user.email,
                created_at=datetime.now()
            )
            
            db.add(metadata)
            uploaded_metadata.append({
                "filename": file.filename,
                "link": metadata.link
            })

    db.commit()

    # For own/shared workspaces, no need to trigger legacy indexer
    if workspace.workspace_type not in [WorkspaceType.own, WorkspaceType.shared]:
        # Trigger legacy indexer for old system
        try:
            indexer_url = f'https://{AZURE_SEARCH_SERVICE}.search.windows.net/indexers/{AZURE_SEARCH_SERVICE_INDEXER_WORKSPACE_NAME}/run?api-version=2020-06-30'
            headers = {
                'api-key': AZURE_SEARCH_KEY,
                'Content-Type': 'application/json'
            }
            response = requests.post(indexer_url, headers=headers)
            response.raise_for_status()
        except Exception as e:
            print(f"Error triggering legacy indexer: {str(e)}")

    return {"uploaded_files": uploaded_metadata}


def list_workspace_files_controller(
    db: Session,
    current_user: User,
    workspace_id: UUID,
):
    ws = services.ensure_workspace_accessible_by_user(db, workspace_id, current_user.id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    files = services.list_workspace_files(db, workspace_id, current_user.id)
    return files 

async def delete_workspace_file_controller(db: Session, current_user: User, workspace_id: UUID, file_id: UUID):
    ws = services.ensure_workspace_accessible_by_user(db, workspace_id, current_user.id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    file_meta = db.query(FileMetadata).filter(FileMetadata.id == file_id, FileMetadata.workspace_id == workspace_id).first()
    if not file_meta:
        raise HTTPException(status_code=404, detail="File not found")

    # Delete from blob storage
    try:
        await services.delete_blob_file(file_meta.full_path)
    except Exception:
        pass

    # Delete from search index
    try:
        await services.delete_file_from_search_index(str(workspace_id), file_meta.name)
    except Exception:
        pass

    # Delete from DB
    db.delete(file_meta)
    db.commit()
    return None


async def view_workspace_file_controller(
    db: Session,
    current_user: User,
    workspace_id: UUID,
    file_id: UUID,
    request: Request,
    disposition: str = "inline",
):
    # Verify ownership or shared access before serving bytes
    ws = services.ensure_workspace_accessible_by_user(db, workspace_id, current_user.id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    file_meta = (
        db.query(FileMetadata)
        .filter(FileMetadata.id == file_id, FileMetadata.workspace_id == workspace_id)
        .first()
    )
    if not file_meta:
        raise HTTPException(status_code=404, detail="File not found")

    # Use correct container based on workspace type
    container = (
        services.USER_WORKSPACE_CONTAINER
        if ws.workspace_type in (WorkspaceType.own, WorkspaceType.shared)
        else AZURE_BLOB_STORAGE_CONTAINER_NAME
    )

    return await services.stream_blob_file(
        container_name=container,
        blob_path=file_meta.full_path,
        filename=file_meta.name,
        disposition=disposition,
    )

async def list_jman_sales_files_controller(
    db: Session,
    current_user: User,
):
    files = await services.list_jman_sales_files(db, current_user)
    return {
        "files": files,
        "total_count": len(files)
    }

async def generate_sas_url_controller(container_name: str, blob_name: str):
    return await services.generate_sas_url(container_name, blob_name)

def share_workspace_controller(db: Session, current_user: User, data: schemas.ShareWorkspace):
    return services.share_workspace(db, current_user, data)

def unshare_workspace_controller(db: Session, current_user: User, data: schemas.UnshareWorkspace):
    return services.unshare_workspace(db, current_user, data)
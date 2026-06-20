from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Request
from sqlalchemy.orm import Session
from uuid import UUID
from auth.deps import get_db
from auth.services import get_current_user
from db.models import User, FileMetadata
from . import schemas, controllers, services
from typing import List, Optional
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])

@router.post("/", response_model=schemas.WorkspaceOut)
def create_workspace(data: schemas.WorkspaceCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return controllers.create_workspace_controller(db, current_user, data)

@router.post("/system", response_model=schemas.WorkspaceOut)
def create_system_workspace(data: schemas.WorkspaceCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Check if user has settings access (admin privilege)
    from db.models import Feature, UserComponentAccess
    settings_feature = db.query(Feature).filter(Feature.feature_id == "settings").first()
    if settings_feature:
        has_settings = db.query(UserComponentAccess).filter(
            UserComponentAccess.user_id == current_user.id,
            UserComponentAccess.component_id == settings_feature.id,
            UserComponentAccess.component_type == "feature"
        ).first()
        
        if not has_settings:
            raise HTTPException(status_code=403, detail="Admin access required")
    
    return controllers.create_system_workspace_controller(db, data)

@router.get("/system", response_model=list[schemas.WorkspaceOut])
def get_system_workspaces(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Check admin privilege
    from db.models import UserRole
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return controllers.get_all_system_workspaces_controller(db)

@router.patch("/system/{workspace_id}", response_model=schemas.WorkspaceOut)
def update_system_workspace(workspace_id: UUID, data: schemas.WorkspaceCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Check admin privilege
    from db.models import Feature, UserComponentAccess
    settings_feature = db.query(Feature).filter(Feature.feature_id == "settings").first()
    if settings_feature:
        has_settings = db.query(UserComponentAccess).filter(
            UserComponentAccess.user_id == current_user.id,
            UserComponentAccess.component_id == settings_feature.id,
            UserComponentAccess.component_type == "feature"
        ).first()
        
        if not has_settings:
            raise HTTPException(status_code=403, detail="Admin access required")
    
    return controllers.update_system_workspace_controller(db, workspace_id, data)

@router.delete("/system/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_system_workspace(workspace_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Check admin privilege
    from db.models import Feature, UserComponentAccess
    settings_feature = db.query(Feature).filter(Feature.feature_id == "settings").first()
    if settings_feature:
        has_settings = db.query(UserComponentAccess).filter(
            UserComponentAccess.user_id == current_user.id,
            UserComponentAccess.component_id == settings_feature.id,
            UserComponentAccess.component_type == "feature"
        ).first()
        
        if not has_settings:
            raise HTTPException(status_code=403, detail="Admin access required")
    
    success = controllers.delete_system_workspace_controller(db, workspace_id)
    if not success:
        raise HTTPException(status_code=404, detail="System workspace not found")

@router.post("/sales", response_model=schemas.WorkspaceOut)
def create_sales_workspace(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return controllers.create_sales_workspace_controller(db)

@router.post("/nexus", response_model=schemas.WorkspaceOut)
def create_nexus_workspace(db: Session = Depends(get_db)):
    return controllers.create_nexus_workspace_controller(db)


@router.post("/aisow", response_model=schemas.WorkspaceOut)
def create_aisow_workspace(db: Session = Depends(get_db)):
    return controllers.create_aisow_workspace_controller(db)

@router.post("/marketing", response_model=schemas.WorkspaceOut)
def create_marketing_workspace(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return controllers.create_marketing_workspace_controller(db)

@router.post("/hr", response_model=schemas.WorkspaceOut)
def create_hr_workspace(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return controllers.create_hr_workspace_controller(db)

@router.post("/knowledge-base", response_model=schemas.WorkspaceOut)
def create_knowledge_base_workspace(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return controllers.create_knowledge_base_controller(db)

@router.get("/", response_model=list[schemas.WorkspaceOut])
def get_workspaces(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return controllers.get_user_workspaces_controller(db, current_user)

@router.get("/accessible", response_model=list[schemas.WorkspaceOut])
def get_accessible_workspaces(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return controllers.get_accessible_workspaces_controller(db, current_user)

@router.get("/all", response_model=list[schemas.WorkspaceOut])
def get_all_workspaces(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return controllers.get_all_workspaces_controller(db)

@router.get("/jman-sales/files/", response_model=schemas.FileListResponse)
async def list_jman_sales_files_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await controllers.list_jman_sales_files_controller(
        db=db,
        current_user=current_user,
    )

@router.get("/generate-sas-url/")
async def generate_sas_url(
    container_name: str, blob_name: str,
    current_user: User = Depends(get_current_user)
):
    return await controllers.generate_sas_url_controller(container_name, blob_name)


@router.get("/{workspace_id}/", response_model=list[schemas.WorkspaceOut])
def get_shared_workspaces(workspace_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from .services import check_workspace_access
    
    # Verify user has access to this workspace
    if not check_workspace_access(db, current_user.id, workspace_id):
        raise HTTPException(status_code=403, detail="Access denied to this workspace")
    
    return controllers.get_user_shared_workspaces_controller(db, workspace_id)

@router.delete("/{workspace_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(workspace_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    success = controllers.delete_workspace_controller(db, current_user, workspace_id)
    if not success:
        raise HTTPException(status_code=404, detail="Workspace not found or not owned by user")
    
@router.put("/{workspace_id}/pre-prompt/")
def update_workspace_pre_prompt(
    workspace_id: UUID,
    data: schemas.UpdatePrePrompt,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from .services import check_workspace_access
    
    # Verify user has access to this workspace
    if not check_workspace_access(db, current_user.id, workspace_id):
        raise HTTPException(status_code=403, detail="Access denied to this workspace")
    
    return controllers.update_pre_prompt_controller(workspace_id, data, db)

@router.post("/upload-image/")
async def upload_image(
    file: UploadFile = File(...),
    workspaceId: UUID = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from Jlens.lib.image_service import validate_image, resize_image, upload_image_to_blob
    file_bytes = await file.read()
    if not validate_image(file_bytes, file.filename):
        raise HTTPException(status_code=400, detail="Invalid image file")
    file_bytes = resize_image(file_bytes)
    url = await upload_image_to_blob(file_bytes, file.filename, str(current_user.id), str(workspaceId))
    return {"url": url}


@router.post("/upload-file/")
async def upload_files_to_workspace(
    workspaceId: UUID = Form(...),
    conversationId: Optional[UUID] = Form(None),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await controllers.upload_files_controller(
        db=db,
        user=current_user,
        workspaceId=workspaceId,
        conversationId=conversationId,
        files=files
    )

@router.post("/{workspace_id}/conversations/{conversation_id}/upload-file/")
async def upload_files_to_conversation(
    workspace_id: UUID,
    conversation_id: UUID,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await controllers.upload_files_controller(
        db=db,
        user=current_user,
        workspaceId=workspace_id,
        conversationId=conversation_id,
        files=files
    )

@router.post("/upload-file-progressive/")
async def upload_files_progressive(
    workspaceId: UUID = Form(...),
    conversationId: Optional[UUID] = Form(None),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Progressive file upload with real-time status updates"""
    return await controllers.upload_files_progressive_controller(
        db=db,
        user=current_user,
        workspaceId=workspaceId,
        conversationId=conversationId,
        files=files
    )

@router.get("/{workspace_id}/files/", response_model=List[schemas.FileMetadataOut])
def list_workspace_files_endpoint(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return controllers.list_workspace_files_controller(
        db=db,
        current_user=current_user,
        workspace_id=workspace_id,
    )


@router.delete("/{workspace_id}/files/{file_id}/", status_code=204)
async def delete_file_endpoint(
    workspace_id: UUID,
    file_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await controllers.delete_workspace_file_controller(db, current_user, workspace_id, file_id)


@router.get("/{workspace_id}/files/{file_id}/view/", response_class=StreamingResponse)
async def view_file_inline_endpoint(
    workspace_id: UUID,
    file_id: UUID,
    request: Request,
    disposition: str = "inline",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await controllers.view_workspace_file_controller(
        db=db,
        current_user=current_user,
        workspace_id=workspace_id,
        file_id=file_id,
        request=request,
        disposition=disposition,
    )


@router.get("/{workspace_id}/files/{file_id}/sas-url/")
async def get_file_sas_url_endpoint(
    workspace_id: UUID,
    file_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return a temporary SAS URL for direct file access (preview/download)"""
    ws = services.ensure_workspace_accessible_by_user(db, workspace_id, current_user.id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    file_meta = db.query(FileMetadata).filter(
        FileMetadata.id == file_id, FileMetadata.workspace_id == workspace_id
    ).first()
    if not file_meta:
        raise HTTPException(status_code=404, detail="File not found")
    sas_url = services.generate_user_workspace_sas_url(file_meta.full_path)
    if not sas_url:
        raise HTTPException(status_code=500, detail="Could not generate file URL")
    return {"url": sas_url, "filename": file_meta.name}


@router.get("/{workspace_id}/files/{file_id}/indexing-status/")
async def get_file_indexing_status(
    workspace_id: UUID,
    file_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check if a file has been indexed in Azure Search"""
    file_meta = db.query(FileMetadata).filter(
        FileMetadata.id == file_id, FileMetadata.workspace_id == workspace_id
    ).first()
    if not file_meta:
        raise HTTPException(status_code=404, detail="File not found")
    
    is_indexed = services.check_file_indexed(str(workspace_id), file_meta.name)
    return {"file_id": str(file_id), "filename": file_meta.name, "status": "indexed" if is_indexed else "pending"}


@router.get("/{workspace_id}/storage/")
async def get_workspace_storage_endpoint(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from .services import check_workspace_access, get_workspace_storage
    if not check_workspace_access(db, current_user.id, workspace_id):
        raise HTTPException(status_code=403, detail="Access denied")
    return await get_workspace_storage(db, workspace_id)


@router.post("/test-mcp-db")
async def test_mcp_db(
    data: schemas.TestMcpDb,
    current_user: User = Depends(get_current_user)
):
    return await controllers.test_mcp_db_controller(data)

@router.post("/add-mcp")
async def add_mcp(
    data: schemas.AddMcp,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await controllers.add_mcp_controller(data, db, current_user)

@router.get("/get-mcp/{workspace_id}")
async def get_mcp(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await controllers.get_mcp_controller(workspace_id, db, current_user)

@router.get("/get-mcp-by-id/{mcp_id}", response_model=schemas.McpResponse)
async def get_mcp_by_id_route(
    mcp_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await controllers.get_mcp_by_id(mcp_id, db, current_user.id)

@router.put("/update-mcp/{mcp_id}", response_model=schemas.McpResponse)
async def update_mcp(
    mcp_id: UUID,
    data: schemas.UpdateMcp,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await controllers.update_mcp_controller(mcp_id, data, db, current_user.id)


# DELETE
@router.delete("/delete-mcp/{mcp_id}")
async def delete_mcp(
    mcp_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await controllers.delete_mcp_controller(mcp_id, db, current_user.id)

# Workspace Sharing
@router.post("/share")
def share_workspace(
    data: schemas.ShareWorkspace,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return controllers.share_workspace_controller(db, current_user, data)

@router.delete("/unshare")
def unshare_workspace(
    data: schemas.UnshareWorkspace,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return controllers.unshare_workspace_controller(db, current_user, data)


# TODO: Uncomment after running migration (see DATA_MODEL_CHANGES.md)
# @router.post("/retry-failed") — retry failed indexing
# @router.post("/{workspace_id}/reindex") — reindex all files in workspace
# @router.post("/files/{file_id}/reindex") — reindex single file
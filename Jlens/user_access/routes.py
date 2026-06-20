
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List
from . import controllers, schemas
from auth.deps   import get_db
from auth.services import get_current_user
from db.models import User, UserComponentAccess, UserRole
 
router = APIRouter(prefix="/user-access", tags=["User Access"])

def check_admin_access(user: User):
    """Check if user has admin role"""
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
 
@router.post("/", response_model=schemas.UserComponentAccessOut)
def create_user_access(access: schemas.UserComponentAccessCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Check if user is admin
    from db.models import UserRole
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return controllers.create_access_controller(db, access)

@router.post("/bulk-update")
def bulk_update_access(
    updates: schemas.BulkAccessUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return controllers.bulk_update_access_controller(db, current_user.id, updates)

@router.get("/available-components")
def get_available_components(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return controllers.get_available_components(db, current_user.id)
 
@router.patch("/{access_id}", response_model=schemas.UserComponentAccessOut)
def update_user_access(access_id: UUID, access_update: schemas.UserComponentAccessUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Check if user is admin
    from db.models import UserRole
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return controllers.update_access_controller(db, access_id, access_update)
 
@router.delete("/{access_id}")
def delete_user_access(access_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Check if user is admin
    from db.models import UserRole
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return controllers.delete_access_controller(db, access_id)
 
@router.get("/me", response_model=list[schemas.UserComponentAccessOut])
def get_my_access(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return controllers.get_access_by_user_controller(db, current_user.id)

@router.get("/settings-data")
def get_settings_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get complete settings data when settings button is clicked"""
    # Get system workspaces
    system_workspaces = controllers.get_system_workspaces_for_admin(db)
    
    # Get user's own and shared workspaces
    user_workspaces = controllers.get_all_accessible_workspaces(db, current_user.id)
    
    # Combine all workspaces for the all_workspaces field
    all_workspaces = system_workspaces + user_workspaces
    
    return {
        "models": controllers.get_all_models_for_admin(db),
        "system_workspaces": system_workspaces,
        "all_workspaces": all_workspaces,
        "current_user": {
            "email": current_user.email,
            "name": current_user.name,
            "access": controllers.get_user_access_summary(db, current_user.id)
        }
    }

@router.get("/models-workspaces")
def get_models_and_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get only accessible models and workspaces for current user"""
    # Get user access summary (system workspaces)
    user_access_summary = controllers.get_user_access_summary(db, current_user.id)
    
    # Get all models and filter by user access
    all_models = controllers.get_all_models_for_admin(db)
    accessible_models = [
        model for model in all_models 
        if model["id"] in user_access_summary.get("models", [])
    ]
    
    # Start with system workspaces from user access
    accessible_workspaces = []
    for workspace in user_access_summary.get("workspaces", []):
        workspace_type = "system" if workspace.get("is_system_workspace", False) else "user"
        
        transformed_workspace = {
            "id": workspace["id"],
            "name": workspace["name"],
            "description": workspace.get("description", ""),
            "pre_prompt": workspace.get("pre_prompt", ""),
            "is_private": workspace.get("is_private", False),
            "is_system_workspace": workspace.get("is_system_workspace", False),
            "workspace_type": workspace_type,
            "user_id": workspace.get("user_id"),
            "owner_email": workspace.get("owner_email", "system"),
            "created_at": workspace.get("created_at"),
            "updated_at": workspace.get("updated_at")
        }
        accessible_workspaces.append(transformed_workspace)
    
    # Add user's own workspaces
    from db.models import Workspace, WorkspaceShare
    own_workspaces = db.query(Workspace).filter(
        Workspace.user_id == current_user.id,
        Workspace.is_system_workspace != True
    ).all()
    
    for ws in own_workspaces:
        accessible_workspaces.append({
            "id": str(ws.id),
            "name": ws.name,
            "description": ws.description or "",
            "pre_prompt": ws.pre_prompt or "",
            "is_private": ws.is_private,
            "is_system_workspace": False,
            "workspace_type": "user",
            "user_id": str(ws.user_id),
            "owner_email": ws.owner.email if ws.owner else current_user.email,
            "created_at": ws.created_at,
            "updated_at": ws.updated_at
        })
    
    # Add shared workspaces
    shared_workspace_ids = [
        share.workspace_id for share in db.query(WorkspaceShare).filter(
            WorkspaceShare.shared_with_id == current_user.id
        ).all()
    ]
    
    if shared_workspace_ids:
        shared_workspaces = db.query(Workspace).filter(
            Workspace.id.in_(shared_workspace_ids)
        ).all()
        
        for ws in shared_workspaces:
            accessible_workspaces.append({
                "id": str(ws.id),
                "name": ws.name,
                "description": ws.description or "",
                "pre_prompt": ws.pre_prompt or "",
                "is_private": ws.is_private,
                "is_system_workspace": False,
                "workspace_type": "shared",
                "user_id": str(ws.user_id),
                "owner_email": ws.owner.email if ws.owner else "unknown",
                "created_at": ws.created_at,
                "updated_at": ws.updated_at
            })
    
    # Remove duplicates using dictionary (keeps last occurrence)
    workspace_dict = {}
    for workspace in accessible_workspaces:
        workspace_dict[workspace["id"]] = workspace
    
    return {
        "models": accessible_models,
        "workspaces": list(workspace_dict.values())
    }

@router.get("/admin/settings-data")
def get_admin_settings_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all data needed for admin settings page in one API call"""
    check_admin_access(current_user)
    
    return {
        "models": controllers.get_all_models_for_admin(db),
        "system_workspaces": controllers.get_system_workspaces_for_admin(db),
        "all_workspaces": controllers.get_all_accessible_workspaces(db, current_user.id),
        "current_user": {
            "email": current_user.email,
            "name": current_user.name,
            "access": controllers.get_user_access_summary(db, current_user.id)
        }
    }

@router.get("/admin/user-search")
def search_user_with_access(
    email: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search for a user and return their access data"""
    check_admin_access(current_user)
    
    user = controllers.search_user_by_email_with_access(db, email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user

@router.get("/admin/search-user")
def search_user_by_email(
    email: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check if user has admin access
    check_admin_access(current_user)
    
    return controllers.search_user_by_email_with_access(db, email)

@router.get("/admin/suggest-users")
def suggest_users(
    query: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check if user has admin access
    check_admin_access(current_user)
    
    return controllers.suggest_users_controller(db, query)

@router.get("/suggest-users")
def suggest_users_non_admin(
    query: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Non-admin users can also search for users to share workspaces
    return controllers.suggest_users_controller(db, query)

@router.post("/admin/update-user-access")
def admin_update_user_access(
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin_access(current_user)
    
    user_email = request.get("user_email")
    updates = schemas.BulkAccessUpdate(**{"access_changes": request.get("access_changes", [])})
    return controllers.admin_update_user_access_controller(db, user_email, updates)

@router.post("/admin/create-user")
def admin_create_user(
    user_data: schemas.CreateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check admin privilege
    check_admin_access(current_user)
    
    return controllers.create_user_controller(db, user_data)

@router.get("/admin/all-users")
def get_all_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all users with their roles (admin only)"""
    check_admin_access(current_user)
    
    users = db.query(User).all()
    return [
        {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "client_name": user.client_name,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
        for user in users
    ]

@router.put("/admin/update-user-role/{user_id}")
def update_user_role(
    user_id: UUID,
    role: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user role (admin only)"""
    check_admin_access(current_user)
    
    # Validate role
    if role not in ["admin", "user"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin' or 'user'")
    
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update role
    user.role = UserRole.admin if role == "admin" else UserRole.user
    db.commit()
    
    return {"message": f"User role updated to {role}", "user_id": str(user_id), "new_role": role}

@router.post("/admin/create-feature")
def admin_create_feature(
    feature_data: schemas.CreateFeatureRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check admin privilege
    check_admin_access(current_user)
    
    return controllers.create_feature_controller(db, feature_data)

@router.post("/admin/create-model")
def admin_create_model(
    model_data: schemas.CreateModelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check admin privilege
    check_admin_access(current_user)
    
    return controllers.create_model_controller(db, model_data)
 
 
from sqlalchemy.orm import Session
from uuid import UUID
from passlib.context import CryptContext
from . import schemas
from db.models import UserComponentAccess, User, AIModel, Workspace, SystemWorkspaceTemplate, WorkspaceShare, WorkspaceType
from config.client_config import CLIENT_WORKSPACE_MAP, DEFAULT_MODELS

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_available_components(db: Session, user_id: UUID = None):
    """Return all available components from master tables"""
    components = []
    
    # Models
    models = db.query(AIModel).all()
    for m in models:
        components.append({
            "component": m.model_id,
            "component_type": "model",
            "description": m.description
        })
    
    # Workspaces - exclude user's own workspaces
    workspaces_query = db.query(Workspace).join(User, Workspace.user_id == User.id)
    if user_id:
        workspaces_query = workspaces_query.filter(Workspace.user_id != user_id)
    
    workspaces = workspaces_query.all()
    for w in workspaces:
        components.append({
            "component": str(w.id),
            "component_type": "workspace",
            "description": f"{w.name} (by {w.owner.name})",
            "name": w.name,
            "owner": w.owner.name
        })
    
    return components

def bulk_update_user_access(db: Session, user_id: UUID, updates: schemas.BulkAccessUpdate):
    """Bulk update user access permissions"""
    results = []
    
    for change in updates.access_changes:
        # Normalize component_type to lowercase
        component_type = change.component_type.lower()
        
        if component_type in ["workspace", "system_workspace_template"]:
            # Handle workspace access - ensure workspace exists first
            try:
                workspace_uuid = UUID(change.component)
                
                # Check if workspace exists in workspaces table
                workspace = db.query(Workspace).filter(Workspace.id == workspace_uuid).first()
                
                if change.enabled:
                    # If workspace doesn't exist, create it first from system template
                    if not workspace:
                        template = db.query(SystemWorkspaceTemplate).filter(SystemWorkspaceTemplate.id == workspace_uuid).first()
                        if template:
                            # Create workspace from template
                            workspace = Workspace(
                                id=workspace_uuid,
                                name=template.name,
                                description=template.description,
                                pre_prompt=template.pre_prompt,
                                is_private=False,
                                is_system_workspace=True,
                                workspace_type=WorkspaceType.system,
                                user_id=None
                            )
                            db.add(workspace)
                            db.flush()  # Ensure workspace is created before adding access
                            results.append(f"Created workspace: {template.name}")
                    
                    # Now add access to user-component-access
                    existing = db.query(UserComponentAccess).filter_by(
                        user_id=user_id,
                        component_id=workspace_uuid,
                        component_type="workspace"
                    ).first()
                    
                    if not existing:
                        new_access = UserComponentAccess(
                            user_id=user_id,
                            component_id=workspace_uuid,
                            component_type="workspace"
                        )
                        db.add(new_access)
                        results.append(f"Granted workspace access")
                    else:
                        results.append(f"User already has workspace access")
                else:
                    # Revoke access
                    existing = db.query(UserComponentAccess).filter_by(
                        user_id=user_id,
                        component_id=workspace_uuid,
                        component_type="workspace"
                    ).first()
                    
                    if existing:
                        db.delete(existing)
                        results.append(f"Revoked workspace access")
                    else:
                        results.append(f"User didn't have workspace access")
                        
            except ValueError:
                # If not a valid UUID, skip
                results.append(f"Invalid workspace ID: {change.component}")
                continue
        else:
            # Handle models - direct update to user-component-access
            if component_type == "model":
                model = db.query(AIModel).filter(AIModel.model_id == change.component).first()
                if not model:
                    results.append(f"Model not found: {change.component}")
                    continue
                
                existing = db.query(UserComponentAccess).filter_by(
                    user_id=user_id,
                    component_id=model.id,
                    component_type="model"
                ).first()
                
                if change.enabled and not existing:
                    new_access = UserComponentAccess(
                        user_id=user_id,
                        component_id=model.id,
                        component_type="model"
                    )
                    db.add(new_access)
                    results.append(f"Granted model: {change.component}")
                elif not change.enabled and existing:
                    db.delete(existing)
                    results.append(f"Revoked model: {change.component}")
                elif change.enabled and existing:
                    results.append(f"User already has model access: {change.component}")
                elif not change.enabled and not existing:
                    results.append(f"User didn't have model access: {change.component}")
    
    db.commit()
    return {"updated": results}

def get_all_users_access(db: Session):
    """Get all users and their access permissions"""
    users = db.query(User).all()
    result = []
    
    for user in users:
        # Get component access (features and models)
        access_records = db.query(UserComponentAccess).filter(UserComponentAccess.user_id == user.id).all()
        
        # Get workspace shares
        workspace_access = db.query(UserComponentAccess).filter(
        UserComponentAccess.user_id == user.id,
        UserComponentAccess.component_type == "workspace"
    ).all()
        
        # Get owned workspaces
        owned_workspaces = db.query(Workspace).filter(Workspace.user_id == user.id).all()
        
        grouped_access = {"models": [], "datasources": [], "workspaces": []}
        
        for access in access_records:
            if access.component_type == "model":
                model = db.query(AIModel).filter(AIModel.id == access.component_id).first()
                if model:
                    grouped_access["models"].append(model.model_id)
        
        # Add shared workspaces
        workspace_ids = set()
        for access in workspace_access:
            workspace = db.query(Workspace).filter(Workspace.id == access.component_id).first()
            if workspace and workspace.id not in workspace_ids:
                grouped_access["workspaces"].append({
                    "id": str(access.component_id),
                    "name": workspace.name,
                    "owner": workspace.owner.name if workspace.owner else "System",
                    "is_system_workspace": workspace.is_system_workspace
                })
                workspace_ids.add(access.component_id)
        
        # Add owned workspaces
        for workspace in owned_workspaces:
            if workspace.id not in workspace_ids:
                grouped_access["workspaces"].append({
                    "id": str(workspace.id),
                    "name": workspace.name,
                    "owner": user.name,
                    "is_system_workspace": workspace.is_system_workspace
                })
                workspace_ids.add(workspace.id)
        
        result.append({
            "user_id": str(user.id),
            "name": user.name,
            "email": user.email,
            "access": grouped_access,
            "total_access": len(access_records) + len(owned_workspaces)
        })
    
    return result

def get_limited_users_access(db: Session, current_user_id: UUID):
    """Get current user + 5 other users for security"""
    # Get current user first
    current_user = db.query(User).filter(User.id == current_user_id).first()
    
    # Get 5 other users (excluding current user)
    other_users = db.query(User).filter(User.id != current_user_id).limit(5).all()
    
    # Combine current user + 5 others
    users = [current_user] + other_users if current_user else other_users
    
    result = []
    for user in users:
        if not user:
            continue
            
        # Get component access (features and models)
        access_records = db.query(UserComponentAccess).filter(UserComponentAccess.user_id == user.id).all()
        
        # Get workspace shares
        workspace_access = db.query(UserComponentAccess).filter(
        UserComponentAccess.user_id == user.id,
        UserComponentAccess.component_type == "workspace"
    ).all()
        
        # Get system workspace template access
        template_access = db.query(UserComponentAccess).filter(
            UserComponentAccess.user_id == user.id,
            UserComponentAccess.component_type == "system_workspace_template"
        ).all()
        
        # Get owned workspaces
        owned_workspaces = db.query(Workspace).filter(Workspace.user_id == user.id).all()
        
        grouped_access = {"models": [], "datasources": [], "workspaces": []}
        
        for access in access_records:
            if access.component_type == "model":
                model = db.query(AIModel).filter(AIModel.id == access.component_id).first()
                if model:
                    grouped_access["models"].append(model.model_id)
        
        # Add shared workspaces
        workspace_ids = set()
        for access in workspace_access:
            workspace = db.query(Workspace).filter(Workspace.id == access.component_id).first()
            if workspace and workspace.id not in workspace_ids:
                grouped_access["workspaces"].append({
                    "id": str(access.component_id),
                    "name": workspace.name,
                    "owner": workspace.owner.name if workspace.owner else "System",
                    "is_system_workspace": workspace.is_system_workspace
                })
                workspace_ids.add(access.component_id)
        
        # Add system workspace templates
        for access in template_access:
            template = db.query(SystemWorkspaceTemplate).filter(SystemWorkspaceTemplate.id == access.component_id).first()
            if template and access.component_id not in workspace_ids:
                grouped_access["workspaces"].append({
                    "id": str(access.component_id),
                    "name": template.name,
                    "owner": "System",
                    "is_system_workspace": True
                })
                workspace_ids.add(access.component_id)
        
        # Add owned workspaces
        for workspace in owned_workspaces:
            if workspace.id not in workspace_ids:
                grouped_access["workspaces"].append({
                    "id": str(workspace.id),
                    "name": workspace.name,
                    "owner": user.name,
                    "is_system_workspace": workspace.is_system_workspace
                })
                workspace_ids.add(workspace.id)
        
        result.append({
            "user_id": str(user.id),
            "name": user.name,
            "email": user.email,
            "access": grouped_access,
            "total_access": len(access_records) + len(owned_workspaces)
        })
    
    return result

def search_user_by_email(db: Session, email: str):
    """Search for a specific user by exact email match"""
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        return None
    
    # Get component access (features and models)
    access_records = db.query(UserComponentAccess).filter(UserComponentAccess.user_id == user.id).all()
    
    # Get workspace shares
    workspace_access = db.query(UserComponentAccess).filter(
        UserComponentAccess.user_id == user.id,
        UserComponentAccess.component_type == "workspace"
    ).all()
    
    # Get system workspace template access
    template_access = db.query(UserComponentAccess).filter(
        UserComponentAccess.user_id == user.id,
        UserComponentAccess.component_type == "system_workspace_template"
    ).all()
    
    # Get owned workspaces
    owned_workspaces = db.query(Workspace).filter(Workspace.user_id == user.id).all()
    
    grouped_access = {"models": [], "datasources": [], "workspaces": []}
    
    for access in access_records:
        if access.component_type == "model":
            model = db.query(AIModel).filter(AIModel.id == access.component_id).first()
            if model:
                grouped_access["models"].append(model.model_id)
    
    # Add shared workspaces
    workspace_ids = set()
    for access in workspace_access:
        workspace = db.query(Workspace).filter(Workspace.id == access.component_id).first()
        if workspace and workspace.id not in workspace_ids:
            grouped_access["workspaces"].append({
                "id": str(access.component_id),
                "name": workspace.name,
                "owner": workspace.owner.name if workspace.owner else "System",
                "is_system_workspace": workspace.is_system_workspace
            })
            workspace_ids.add(access.component_id)
    
    # Add system workspace templates
    from db.models import SystemWorkspaceTemplate
    for access in template_access:
        template = db.query(SystemWorkspaceTemplate).filter(SystemWorkspaceTemplate.id == access.component_id).first()
        if template and access.component_id not in workspace_ids:
            grouped_access["workspaces"].append({
                "id": str(access.component_id),
                "name": template.name,
                "owner": "System",
                "is_system_workspace": True
            })
            workspace_ids.add(access.component_id)
    
    # Add owned workspaces
    for workspace in owned_workspaces:
        if workspace.id not in workspace_ids:
            grouped_access["workspaces"].append({
                "id": str(workspace.id),
                "name": workspace.name,
                "owner": user.name,
                "is_system_workspace": workspace.is_system_workspace
            })
            workspace_ids.add(workspace.id)
    
    return {
        "user_id": str(user.id),
        "name": user.name,
        "email": user.email,
        "access": grouped_access,
        "total_access": len(access_records) + len(workspace_access) + len(owned_workspaces)
    }

def suggest_users(db: Session, query: str):
    """Get up to 3 user suggestions based on partial email or name match"""
    if not query or len(query) < 2:
        return []
    
    # Search by email or name (case-insensitive partial match)
    users = db.query(User).filter(
        (User.email.ilike(f"%{query}%")) | (User.name.ilike(f"%{query}%"))
    ).limit(3).all()
    
    return [{"email": u.email, "name": u.name} for u in users]

def admin_update_user_access(db: Session, user_email: str, updates: schemas.BulkAccessUpdate):
    """Admin function to update any user's access"""
    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        raise ValueError("User not found")
    
    return bulk_update_user_access(db, user.id, updates)

def get_user_access_by_user(db: Session, user_id: UUID):
    # Get component access (features and models)
    access_records = db.query(UserComponentAccess).filter_by(user_id=user_id).all()
    
    # Get workspace shares
    workspace_access = db.query(UserComponentAccess).filter(
        UserComponentAccess.user_id == user_id,
        UserComponentAccess.component_type == "workspace"
    ).all()
    
    # Get owned workspaces
    owned_workspaces = db.query(Workspace).filter(Workspace.user_id == user_id).all()
    
    result = []
    
    for access in access_records:
        component_name = None
        
        if access.component_type.upper() == "FEATURE":
            feature = db.query(Feature).filter(Feature.id == access.component_id).first()
            component_name = feature.feature_id if feature else None
        elif access.component_type.upper() == "MODEL":
            model = db.query(AIModel).filter(AIModel.id == access.component_id).first()
            component_name = model.model_id if model else None
        
        if component_name:
            access_obj = UserComponentAccess(
                id=access.id,
                user_id=access.user_id,
                component_id=access.component_id,
                component_type=access.component_type
            )
            access_obj.component = component_name
            result.append(access_obj)
    
    # Add shared workspaces
    workspace_ids = set()
    for access in workspace_access:
        if access.component_id not in workspace_ids:
            access_obj = UserComponentAccess(
                id=access.id,
                user_id=access.user_id,
                component_id=access.component_id,
                component_type="workspace"
            )
            access_obj.component = str(access.component_id)
            result.append(access_obj)
            workspace_ids.add(access.component_id)
    
    # Add owned workspaces
    for workspace in owned_workspaces:
        if workspace.id not in workspace_ids:
            access_obj = UserComponentAccess(
                id=workspace.id,
                user_id=user_id,
                component_id=workspace.id,
                component_type="workspace"
            )
            access_obj.component = str(workspace.id)
            result.append(access_obj)
            workspace_ids.add(workspace.id)
    
    return result

def create_user(db: Session, user_data: schemas.CreateUserRequest):
    """Create a new user"""
    # Check if user already exists
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise ValueError("User with this email already exists")
    
    # Hash the password
    password_hash = pwd_context.hash(user_data.password)
    
    new_user = User(
        email=user_data.email,
        name=user_data.name,
        password_hash=password_hash,
        designation=user_data.designation,
        client_name=getattr(user_data, 'client_name', 'jlens') or 'jlens'
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Grant default access based on client
    from db.models import SystemWorkspaceTemplate, AIModel, WorkspaceType
    template_keys = CLIENT_WORKSPACE_MAP.get(new_user.client_name, [])
    default_templates = db.query(SystemWorkspaceTemplate).filter(
        SystemWorkspaceTemplate.template_key.in_(template_keys),
        SystemWorkspaceTemplate.is_active == True
    ).all()
    
    for template in default_templates:
        # First, create system workspace from template (if not exists)
        existing_workspace = db.query(Workspace).filter(
            Workspace.name == template.name,
            Workspace.is_system_workspace == True
        ).first()
        
        if not existing_workspace:
            system_workspace = Workspace(
                id=template.id,  # Use template ID as workspace ID
                name=template.name,
                description=template.description,
                pre_prompt=template.pre_prompt,
                is_private=False,
                is_system_workspace=True,
                workspace_type=WorkspaceType.system,
                user_id=None
            )
            db.add(system_workspace)
            db.flush()  # Ensure workspace is created
        
        # Then, grant access to the workspace
        workspace_access = UserComponentAccess(
            user_id=new_user.id,
            component_id=template.id,
            component_type="workspace"
        )
        db.add(workspace_access)
    
    # Grant default model access
    default_models = db.query(AIModel).filter(
        AIModel.model_id.in_(DEFAULT_MODELS)
    ).all()
    
    for model in default_models:
        model_access = UserComponentAccess(
            user_id=new_user.id,
            component_id=model.id,
            component_type="model"
        )
        db.add(model_access)
    
    # Create default sandbox workspace with user's name
    # Handle potential duplicate names by checking if workspace exists
    workspace_name = new_user.name
    existing_sandbox = db.query(Workspace).filter(
        Workspace.name == workspace_name,
        Workspace.user_id == new_user.id
    ).first()
    
    if not existing_sandbox:
        sandbox_workspace = Workspace(
            name=workspace_name,
            description=f"Personal sandbox workspace for {new_user.name}",
            pre_prompt="You are a helpful AI assistant.",
            is_private=True,
            is_system_workspace=False,
            workspace_type=WorkspaceType.own,
            user_id=new_user.id
        )
        db.add(sandbox_workspace)
        db.flush()
        
        # Grant user access to their sandbox workspace
        sandbox_access = UserComponentAccess(
            user_id=new_user.id,
            component_id=sandbox_workspace.id,
            component_type="workspace"
        )
        db.add(sandbox_access)
    
    db.commit()
    
    return {"id": str(new_user.id), "email": new_user.email, "name": new_user.name}

def create_model(db: Session, model_data: schemas.CreateModelRequest):
    """Create a new AI model"""
    # Generate model_id from name (lowercase, replace spaces with hyphens)
    model_id = model_data.name.lower().replace(' ', '-')
    
    # Check if model already exists
    existing = db.query(AIModel).filter(AIModel.model_id == model_id).first()
    if existing:
        raise ValueError("Model with this name already exists")
    
    new_model = AIModel(
        model_id=model_id,
        name=model_data.name,
        description=model_data.description
    )
    db.add(new_model)
    db.commit()
    db.refresh(new_model)
    
    return {"id": str(new_model.id), "model_id": new_model.model_id, "name": new_model.name}

def get_all_models_for_admin(db: Session):
    """Get all AI models for admin settings"""
    models = db.query(AIModel).filter(AIModel.status == 'active').all()
    return [{"id": model.model_id, "name": model.name, "description": model.description} for model in models]

def get_models_with_access(db: Session, user_id: UUID):
    """Get all models with access info for specific user"""
    models = db.query(AIModel).filter(AIModel.status == 'active').all()
    user_access = db.query(UserComponentAccess).filter(
        UserComponentAccess.user_id == user_id,
        UserComponentAccess.component_type == 'model'
    ).all()
    
    access_set = {access.component_id for access in user_access}
    
    return [{
        "id": model.model_id,
        "name": model.name, 
        "description": model.description,
        "is_access": model.id in access_set
    } for model in models]

def get_workspaces_with_access(db: Session, user_id: UUID):
    """Get system workspaces with access info for specific user"""
    templates = db.query(SystemWorkspaceTemplate).filter(SystemWorkspaceTemplate.is_active == True).all()
    user_access = db.query(UserComponentAccess).filter(
        UserComponentAccess.user_id == user_id,
        UserComponentAccess.component_type == 'system_workspace_template'
    ).all()
    
    access_set = {str(access.component_id) for access in user_access}
    
    return [{
        "id": str(template.id),
        "name": template.name,
        "description": template.description,
        "pre_prompt": template.pre_prompt,
        "is_private": False,
        "is_system_workspace": True,
        "workspace_type": "system",
        "user_id": None,
        "owner_email": "system",
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
        "is_access": str(template.id) in access_set
    } for template in templates]

def get_all_accessible_workspaces(db: Session, user_id: UUID):
    """Get own and shared workspaces for specific user (system workspaces are separate)"""
    result = []
    
    # Get system workspace template names to exclude duplicates
    system_template_names = [t.name for t in db.query(SystemWorkspaceTemplate).filter(
        SystemWorkspaceTemplate.is_active == True
    ).all()]
    
    # 1. Get user's own workspaces (non-system and not duplicates of system templates)
    owned = db.query(Workspace).filter(
        Workspace.user_id == user_id,
        Workspace.is_system_workspace != True,
        ~Workspace.name.in_(system_template_names)  # Exclude workspaces with system template names
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
            "created_at": ws.created_at.isoformat() if ws.created_at else None,
            "updated_at": ws.updated_at.isoformat() if ws.updated_at else None
        })
    
    # 2. Get shared workspaces
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
                "created_at": ws.created_at.isoformat() if ws.created_at else None,
                "updated_at": ws.updated_at.isoformat() if ws.updated_at else None
            })
    
    return result

def get_system_workspaces_for_admin(db: Session):
    """Get ALL system workspaces for admin settings (not just user's accessible ones)"""
    # Get ALL system workspaces for admin to manage access
    system_workspaces = db.query(Workspace).filter(
        Workspace.is_system_workspace == True,
        Workspace.workspace_type == WorkspaceType.system
    ).all()
    
    # Also get system workspace templates that don't have workspace instances yet
    existing_names = [ws.name for ws in system_workspaces]
    templates_without_workspaces = db.query(SystemWorkspaceTemplate).filter(
        SystemWorkspaceTemplate.is_active == True,
        ~SystemWorkspaceTemplate.name.in_(existing_names)
    ).all()
    
    result = []
    
    # Add existing system workspaces
    for workspace in system_workspaces:
        result.append({
            "id": str(workspace.id), 
            "name": workspace.name, 
            "description": workspace.description,
            "pre_prompt": workspace.pre_prompt,
            "is_private": workspace.is_private,
            "is_system_workspace": workspace.is_system_workspace,
            "workspace_type": "system",
            "user_id": str(workspace.user_id) if workspace.user_id else None,
            "owner_email": workspace.owner.email if workspace.owner else "system",
            "created_at": workspace.created_at,
            "updated_at": workspace.updated_at
        })
    
    # Add templates that don't have workspace instances (for completeness)
    for template in templates_without_workspaces:
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
    
    return result

def get_user_access_summary(db: Session, user_id: UUID):
    """Get user's access summary"""
    access_records = db.query(UserComponentAccess).filter(UserComponentAccess.user_id == user_id).all()
    
    grouped = {"models": [], "workspaces": []}
    
    for access in access_records:
        if access.component_type == "model":
            model = db.query(AIModel).filter(AIModel.id == access.component_id).first()
            if model:
                grouped["models"].append(model.model_id)
        elif access.component_type == "workspace":
            # Handle actual workspace records (new approach)
            workspace = db.query(Workspace).filter(Workspace.id == access.component_id).first()
            if workspace:
                workspace_data = {
                    "id": str(workspace.id),
                    "name": workspace.name,
                    "description": workspace.description,
                    "pre_prompt": workspace.pre_prompt,
                    "is_private": workspace.is_private,
                    "is_system_workspace": workspace.is_system_workspace,
                    "user_id": str(workspace.user_id) if workspace.user_id else None,
                    "owner_email": workspace.owner.email if workspace.owner else "system",
                    "created_at": workspace.created_at,
                    "updated_at": workspace.updated_at
                }
                grouped["workspaces"].append(workspace_data)
            else:
                # If workspace not found, it might be a system workspace template ID
                # Try to find the corresponding workspace by name
                template = db.query(SystemWorkspaceTemplate).filter(SystemWorkspaceTemplate.id == access.component_id).first()
                if template:
                    # Find workspace with same name
                    workspace_by_name = db.query(Workspace).filter(
                        Workspace.name == template.name,
                        Workspace.is_system_workspace == True
                    ).first()
                    if workspace_by_name:
                        workspace_data = {
                            "id": str(workspace_by_name.id),
                            "name": workspace_by_name.name,
                            "description": workspace_by_name.description,
                            "pre_prompt": workspace_by_name.pre_prompt,
                            "is_private": workspace_by_name.is_private,
                            "is_system_workspace": workspace_by_name.is_system_workspace,
                            "user_id": str(workspace_by_name.user_id) if workspace_by_name.user_id else None,
                            "owner_email": workspace_by_name.owner.email if workspace_by_name.owner else "system",
                            "created_at": workspace_by_name.created_at,
                            "updated_at": workspace_by_name.updated_at
                        }
                        grouped["workspaces"].append(workspace_data)
        elif access.component_type == "system_workspace_template":
            # Handle system workspace template records (old approach for backward compatibility)
            template = db.query(SystemWorkspaceTemplate).filter(SystemWorkspaceTemplate.id == access.component_id).first()
            if template:
                # Find corresponding workspace
                workspace = db.query(Workspace).filter(
                    Workspace.name == template.name,
                    Workspace.is_system_workspace == True
                ).first()
                if workspace:
                    workspace_data = {
                        "id": str(workspace.id),
                        "name": workspace.name,
                        "description": workspace.description,
                        "pre_prompt": workspace.pre_prompt,
                        "is_private": workspace.is_private,
                        "is_system_workspace": workspace.is_system_workspace,
                        "user_id": str(workspace.user_id) if workspace.user_id else None,
                        "owner_email": workspace.owner.email if workspace.owner else "system",
                        "created_at": workspace.created_at,
                        "updated_at": workspace.updated_at
                    }
                    grouped["workspaces"].append(workspace_data)
    
    return grouped

def search_user_by_email_with_access(db: Session, email: str):
    """Search user by email and return with access data"""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    
    access_summary = get_user_access_summary(db, user.id)
    
    return {
        "email": user.email,
        "name": user.name,
        "access": access_summary
    }

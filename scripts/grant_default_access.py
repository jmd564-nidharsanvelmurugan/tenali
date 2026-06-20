#!/usr/bin/env python3
"""Grant default access to existing users who don't have it"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL'))
Session = sessionmaker(bind=engine)
db = Session()

from db.models import User, UserComponentAccess, SystemWorkspaceTemplate, Workspace, AIModel, WorkspaceType
from config.client_config import CLIENT_WORKSPACE_MAP, DEFAULT_MODELS

# Get all users
users = db.query(User).all()
print(f"Found {len(users)} users")

for user in users:
    print(f"\n=== Processing {user.email} ===")
    
    # Check existing access
    existing_access = db.query(UserComponentAccess).filter(UserComponentAccess.user_id == user.id).all()
    existing_workspace_ids = {a.component_id for a in existing_access if a.component_type == 'workspace'}
    existing_model_ids = {a.component_id for a in existing_access if a.component_type == 'model'}
    
    print(f"Existing: {len(existing_workspace_ids)} workspaces, {len(existing_model_ids)} models")
    
    # Grant default workspaces based on user's client_name
    template_keys = CLIENT_WORKSPACE_MAP.get(user.client_name, [])
    default_templates = db.query(SystemWorkspaceTemplate).filter(
        SystemWorkspaceTemplate.template_key.in_(template_keys),
        SystemWorkspaceTemplate.is_active == True
    ).all()
    
    for template in default_templates:
        # Find or create workspace
        workspace = db.query(Workspace).filter(
            Workspace.name == template.name,
            Workspace.is_system_workspace == True,
            Workspace.workspace_type == WorkspaceType.system
        ).first()
        
        if not workspace:
            workspace = Workspace(
                name=template.name,
                description=template.description,
                pre_prompt=template.pre_prompt,
                is_private=False,
                is_system_workspace=True,
                workspace_type=WorkspaceType.system,
                user_id=None
            )
            db.add(workspace)
            db.flush()
            print(f"  Created workspace: {workspace.name}")
        
        # Grant access if not already granted
        if workspace.id not in existing_workspace_ids:
            access = UserComponentAccess(
                user_id=user.id,
                component_id=workspace.id,
                component_type="workspace"
            )
            db.add(access)
            print(f"  Granted: {workspace.name}")
    
    # Grant default models
    default_models = db.query(AIModel).filter(
        AIModel.model_id.in_(DEFAULT_MODELS)
    ).all()
    
    for model in default_models:
        if model.id not in existing_model_ids:
            access = UserComponentAccess(
                user_id=user.id,
                component_id=model.id,
                component_type="model"
            )
            db.add(access)
            print(f"  Granted: {model.model_id}")
    
    db.commit()

print("\n✅ Default access granted to all users")
db.close()

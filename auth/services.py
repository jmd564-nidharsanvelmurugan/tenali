from fastapi import Depends, HTTPException, status, Header, Cookie
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from db.models import User, UserComponentAccess, Workspace
from auth.jwt_utils import create_access_token
from auth.schemas import UserCreate, UserComponentAccessCreate, WorkspaceCreate, UserCreateMicrosoft
from passlib.context import CryptContext
import uuid
from auth.deps import get_db
from jose import JWTError, jwt
from auth.jwt_utils import SECRET_KEY, ALGORITHM
from uuid import UUID
from config.client_config import CLIENT_WORKSPACE_MAP, DEFAULT_MODELS

pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__default_rounds=12)

def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()
    if not user or not pwd_context.verify(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    return user

def authenticate_user_microsoft(db: Session, name: str, email: str, id: str):
    user = db.query(User).filter(User.email == email).first()
    
    

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    return user

def login_user(db: Session, email: str, password: str):
    user = authenticate_user(db, email, password)
    token = create_access_token(data={"sub": user.email,"user_id": str(user.id),"user_name": str(user.name)})
    return {"access_token": token, "token_type": "bearer"}

def login_user_microsoft(db: Session, name: str, email: str, id : str):
    user = authenticate_user_microsoft(db, name, email, id)
    token = create_access_token(data={"sub": user.email,"user_id": str(user.id),"user_name": str(user.name)})
    return {"access_token": token, "token_type": "bearer"}

def check_user_exists(db: Session, email: str) -> bool:
    return db.query(User).filter_by(email=email).first() is not None

def create_user(db: Session, user_data: UserCreate, client_name: str) -> User:
    # Check if user already exists
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists."
        )


    # Admin emails list
    admin_emails = [

        "sathishkumar@jmangroup.com",
        "vendeeshwaranchandran@jmangroup.com",
        "bharani.r@jmangroup.com",
        "vasantha.j@jmangroup.com",
        "prasad.d@jmangroup.com",
        "nidharsanvelmurugan@jmangroup.com"
        
    ]



    hashed_password = pwd_context.hash(user_data.password)

    from db.models import UserRole, SystemWorkspaceTemplate, Workspace, AIModel
    user = User(
        email=user_data.email,
        password_hash=hashed_password,
        name=user_data.name,
        designation=user_data.designation,
        client_name=client_name,  # Required parameter from API
        role=UserRole.admin if user_data.email in admin_emails else UserRole.user
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Import required models
    from db.models import WorkspaceType
    
    # Determine which workspaces to grant based on client
    template_keys = CLIENT_WORKSPACE_MAP.get(client_name, [])
    
    if template_keys:
        # Create default workspaces from templates
        default_templates = db.query(SystemWorkspaceTemplate).filter(
            SystemWorkspaceTemplate.template_key.in_(template_keys),
            SystemWorkspaceTemplate.is_active == True
        ).all()
        
        for template in default_templates:
            # Check if system workspace already exists
            existing_workspace = db.query(Workspace).filter(
                Workspace.name == template.name,
                Workspace.is_system_workspace == True,
                Workspace.workspace_type == WorkspaceType.system
            ).first()
            
            if not existing_workspace:
                # Create system workspace if it doesn't exist
                user_workspace = Workspace(
                    name=template.name,
                    description=template.description,
                    pre_prompt=template.pre_prompt,
                    is_private=False,
                    is_system_workspace=True,
                    workspace_type=WorkspaceType.system,
                    user_id=None
                )
                db.add(user_workspace)
                db.flush()  # Get the ID
                workspace_id = user_workspace.id
            else:
                workspace_id = existing_workspace.id
            
            # Grant user access to the system workspace
            template_access = UserComponentAccess(
                user_id=user.id,
                component_id=workspace_id,
                component_type="workspace"
            )
            db.add(template_access)
        
        # Grant default model access
        default_models = db.query(AIModel).filter(
            AIModel.model_id.in_(DEFAULT_MODELS)
        ).all()
        
        for model in default_models:
            model_access = UserComponentAccess(
                user_id=user.id,
                component_id=model.id,
                component_type="model"
            )
            db.add(model_access)
        
    
    # Create default sandbox workspace for ALL users (regardless of client)
    workspace_name = user.name
    existing_sandbox = db.query(Workspace).filter(
        Workspace.name == workspace_name,
        Workspace.user_id == user.id
    ).first()
    
    if not existing_sandbox:
        sandbox_workspace = Workspace(
            name=workspace_name,
            description=f"Personal sandbox workspace for {user.name}",
            pre_prompt="You are a helpful AI assistant.",
            is_private=True,
            is_system_workspace=False,
            workspace_type=WorkspaceType.own,
            user_id=user.id
        )
        db.add(sandbox_workspace)
        db.flush()
        
        # Grant user access to their sandbox workspace
        sandbox_access = UserComponentAccess(
            user_id=user.id,
            component_id=sandbox_workspace.id,
            component_type="workspace"
        )
        db.add(sandbox_access)
    
    db.commit()
    return user



def create_user_microsoft(db: Session, user_data: UserCreateMicrosoft) -> User:
    # Check if user already exists
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists."
        )

    # Admin emails list
    admin_emails = [
        "sathishkumar@jmangroup.com",
        "vendeeshwaranchandran@jmangroup.com",
        "bharani.r@jmangroup.com",
        "vasantha.j@jmangroup.com",
        "prasad.d@jmangroup.com",
        "nidharsanvelmurugan@jmangroup.com", 
    ]
    
    from db.models import UserRole
    user = User(
        email=user_data.email,
        microsoft_id=user_data.id,
        name=user_data.name,
        designation=user_data.designation,
        client_name=user_data.client_name,  # Required parameter from API
        role=UserRole.admin if user_data.email in admin_emails else UserRole.user
    )
    db.add(user)
    db.commit()
    db.refresh(user)





    # $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$



    
    
    # Import required models
    from db.models import SystemWorkspaceTemplate, Workspace, AIModel, WorkspaceType
    
    # Determine which workspaces to grant based on client
    template_keys = CLIENT_WORKSPACE_MAP.get(user_data.client_name, [])
    
    if template_keys:
        # Create default workspaces from templates (JLens, AI Proposal, Jman Sales, and Marketplace)
        default_templates = db.query(SystemWorkspaceTemplate).filter(
            SystemWorkspaceTemplate.template_key.in_(template_keys),
            SystemWorkspaceTemplate.is_active == True
        ).all()
        
        for template in default_templates:
            # Check if system workspace already exists
            existing_workspace = db.query(Workspace).filter(
                Workspace.name == template.name,
                Workspace.is_system_workspace == True,
                Workspace.workspace_type == WorkspaceType.system
            ).first()
            
            if not existing_workspace:
                # Create system workspace if it doesn't exist
                user_workspace = Workspace(
                    name=template.name,
                    description=template.description,
                    pre_prompt=template.pre_prompt,
                    is_private=False,
                    is_system_workspace=True,
                    workspace_type=WorkspaceType.system,
                    user_id=None
                )
                db.add(user_workspace)
                db.flush()  # Get the ID
                workspace_id = user_workspace.id
            else:
                workspace_id = existing_workspace.id
            
            # Grant access to the workspace
            template_access = UserComponentAccess(
                user_id=user.id,
                component_id=workspace_id,
                component_type="workspace"
            )
            db.add(template_access)
        
        # Grant default model access
        default_models = db.query(AIModel).filter(
            AIModel.model_id.in_(DEFAULT_MODELS)
        ).all()
        
        for model in default_models:
            model_access = UserComponentAccess(
                user_id=user.id,
                component_id=model.id,
                component_type="model"
            )
            db.add(model_access)
        
    
    # Create default sandbox workspace for ALL users (regardless of client)
    workspace_name = user.name
    existing_sandbox = db.query(Workspace).filter(
        Workspace.name == workspace_name,
        Workspace.user_id == user.id
    ).first()
    
    if not existing_sandbox:
        sandbox_workspace = Workspace(
            name=workspace_name,
            description=f"Personal sandbox workspace for {user.name}",
            pre_prompt="You are a helpful AI assistant.",
            is_private=True,
            is_system_workspace=False,
            workspace_type=WorkspaceType.own,
            user_id=user.id
        )
        db.add(sandbox_workspace)
        db.flush()
        
        # Grant user access to their sandbox workspace
        sandbox_access = UserComponentAccess(
            user_id=user.id,
            component_id=sandbox_workspace.id,
            component_type="workspace"
        )
        db.add(sandbox_access)
    
    db.commit()
    return user


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(
    db: Session = Depends(get_db),
    authorization: str = Header(None),
    access_token: str = Cookie(None)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Get token from cookie or header
    token = None
    if access_token:
        token = access_token
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    
    if not token:
        raise credentials_exception
    
    try:
        # Use enhanced JWT validation
        from auth.jwt_utils import verify_token
        payload = verify_token(token)
        
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
            
        # Additional security checks
        if payload.get("aud") != "jlens-frontend":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token audience"
            )
            
        if payload.get("iss") != "jlens-api":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token issuer"
            )
            
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    
    # Refresh the user object to get latest data from database
    db.refresh(user)
    return user

def create_user_access(db: Session, access: UserComponentAccessCreate):
    # Map component to component_id for the model
    from db.models import AIModel
    
    component_id = None
    if access.component_type == "model":
        model = db.query(AIModel).filter(AIModel.model_id == access.component).first()
        component_id = model.id if model else None
    
    if not component_id:
        return None
    
    db_access = UserComponentAccess(
        user_id=access.user_id,
        component_id=component_id,
        component_type=access.component_type
    )
    db.add(db_access)
    db.commit()
    db.refresh(db_access)
    return db_access

def create_workspace(db: Session, data: WorkspaceCreate) -> Workspace:
    workspace = Workspace(
        name=data.name,
        description=data.description,
        is_private=data.is_private,
        is_system_workspace=data.is_system_workspace,
        user_id=data.user_id
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace

def get_sales_workspace(db: Session) -> Workspace:
    sales_workspace = db.query(Workspace).filter(Workspace.name == "Jman Sales").first()
    return sales_workspace


def get_nexus_workspace(db: Session) -> Workspace:
    get_nexus_workspace = db.query(Workspace).filter(Workspace.name == "Nexus").first()
    return get_nexus_workspace

def get_aisow_workspace(db: Session) -> Workspace:
    get_aisow_workspace = db.query(Workspace).filter(Workspace.name == "AISOW").first()
    return get_aisow_workspace



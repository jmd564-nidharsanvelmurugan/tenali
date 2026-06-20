from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from auth.schemas import UserLogin, TokenResponse, UserResponse, UserCreate, UserLoginMicrosoft, UserCreateMicrosoft
from auth.services import create_user, create_user_access, login_user, create_workspace, get_sales_workspace, login_user_microsoft, create_user_microsoft, check_user_exists, get_current_user
from auth.jwt_utils import create_access_token
from auth.deps import get_db
from .schemas import UserComponentAccessCreate, WorkspaceCreate
from db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(credentials: UserLogin, response: Response, db: Session = Depends(get_db)):
    result = login_user(db, credentials.email, credentials.password)
    
    # Check if running on HTTPS (production)
    import os
    environment = os.getenv("ENVIRONMENT", "development")
    is_https = environment == "production"
    
    
    # Set HttpOnly cookie (48 hours to match JWT expiration)
    response.set_cookie(
        key="access_token",
        value=result["access_token"],
        httponly=True,
        secure=is_https,  # True in production (HTTPS), False in local (HTTP)
        samesite="none" if is_https else "lax",  # none for cross-origin HTTPS, lax for local
        max_age=172800,  # 48 hours
        path="/",
        domain=None
    )
    
    
    return result


@router.post("/microsoft-login", response_model=TokenResponse)
def microsoft_login(credentials: UserLoginMicrosoft, response: Response, db: Session = Depends(get_db)):
    result = login_user_microsoft(db, credentials.name, credentials.email, credentials.id)
    
    # Check if running on HTTPS (production)
    import os
    environment = os.getenv("ENVIRONMENT", "development")
    is_https = environment == "production"
    
    
    # Set HttpOnly cookie (48 hours to match JWT expiration)
    response.set_cookie(
        key="access_token",
        value=result["access_token"],
        httponly=True,
        secure=is_https,  # True in production (HTTPS), False in local (HTTP)
        samesite="none" if is_https else "lax",  # none for cross-origin HTTPS, lax for local
        max_age=172800,  # 48 hours
        path="/",
        domain=None
    )
    
    
    return result
@router.get("/user-exists")
def user_exists(email: str, db: Session = Depends(get_db)):
    return {"exists": check_user_exists(db, email)}


@router.get("/me")
def get_user_info(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role.value
    }


@router.post("/logout")
def logout(response: Response, current_user: User = Depends(get_current_user)):
    response.delete_cookie(key="access_token", path="/")
    return {"message": "Logged out successfully"}


@router.post("/signup", response_model=UserResponse)
def signup(user_data: UserCreate, db: Session = Depends(get_db)):
    user = create_user(db, user_data, client_name="jlens")  # JLens UI always passes "jlens"
    access_token = create_access_token(data={"sub": user.email})
    return user


@router.post("/signup-microsoft", response_model=UserResponse)
def signup_microsoft(user_data: UserCreateMicrosoft, db: Session = Depends(get_db)):
    user = create_user_microsoft(db, user_data)  # JLens UI passes "jlens"
    access_token = create_access_token(data={"sub": user.email})
    return user


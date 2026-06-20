from core.database import SessionLocal
from fastapi import Cookie, HTTPException, status
from typing import Optional

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_token_from_cookie_or_header(
    authorization: Optional[str] = None,
    access_token: Optional[str] = Cookie(None)
) -> str:
    """Get token from cookie (preferred) or Authorization header (fallback)"""
    
    # Try cookie first (more secure)
    if access_token:
        return access_token
    
    # Fallback to Authorization header for backward compatibility
    if authorization and authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "")
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

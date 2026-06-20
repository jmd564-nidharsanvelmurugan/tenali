from datetime import datetime, timedelta
from jose import JWTError, jwt
import os
import secrets
from dotenv import load_dotenv
load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Validate JWT configuration
if not SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY environment variable is required")

# Warning for short keys but allow them for backward compatibility
if len(SECRET_KEY) < 32:
    print(f"WARNING: JWT_SECRET_KEY is only {len(SECRET_KEY)} characters. Consider using a longer key for better security.")

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    
    # Add security claims
    now = datetime.utcnow()
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    
    to_encode.update({
        "exp": expire,
        "iat": now,  # Issued at
        "nbf": now,  # Not before
        "jti": secrets.token_urlsafe(16),  # JWT ID for token revocation
        "iss": "jlens-api",  # Issuer
        "aud": "jlens-frontend"  # Audience
    })
    
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> dict:
    """Verify and decode JWT token with enhanced validation"""
    try:
        payload = jwt.decode(
            token, 
            SECRET_KEY, 
            algorithms=[ALGORITHM],
            audience="jlens-frontend",
            issuer="jlens-api"
        )
        
        # Additional validation
        if not payload.get("sub"):
            raise JWTError("Token missing subject")
            
        if not payload.get("user_id"):
            raise JWTError("Token missing user_id")
            
        return payload
        
    except JWTError as e:
        raise JWTError(f"Token validation failed: {str(e)}")

def generate_secure_key() -> str:
    """Generate a cryptographically secure key for JWT signing"""
    return secrets.token_urlsafe(64)

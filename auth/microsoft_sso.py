from fastapi import APIRouter, HTTPException, Depends, Response, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from auth.deps import get_db
from auth.services import create_user_microsoft, check_user_exists
from auth.jwt_utils import create_access_token
from auth.schemas import UserCreateMicrosoft
from config.client_config import DOMAIN_TO_CLIENT
import httpx
import secrets
import os
import hashlib
import base64
from datetime import datetime, timedelta

router = APIRouter(prefix="/auth/microsoft", tags=["microsoft-sso"])

# In-memory state storage (use Redis in production)
sso_states = {}

MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID")
MICROSOFT_REDIRECT_URI = os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:8000/api/auth/microsoft/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

def generate_pkce_pair():
    """Generate PKCE code verifier and challenge"""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).decode('utf-8').rstrip('=')
    return code_verifier, code_challenge

@router.get("/login")
async def microsoft_login():
    """Initiate Microsoft SSO login with PKCE and state validation"""
    
    # Generate secure state, nonce, and PKCE
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier, code_challenge = generate_pkce_pair()
    
    # Store state with PKCE verifier and expiration (5 minutes)
    sso_states[state] = {
        "nonce": nonce,
        "code_verifier": code_verifier,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(minutes=5)
    }
    
    # Clean expired states
    _clean_expired_states()
    
    # Build Microsoft authorization URL with PKCE
    auth_url = (
        f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/oauth2/v2.0/authorize?"
        f"client_id={MICROSOFT_CLIENT_ID}&"
        f"response_type=code&"
        f"redirect_uri={MICROSOFT_REDIRECT_URI}&"
        f"response_mode=query&"
        f"scope=openid%20profile%20email%20User.Read&"
        f"state={state}&"
        f"nonce={nonce}&"
        f"code_challenge={code_challenge}&"
        f"code_challenge_method=S256"
    )
    
    return RedirectResponse(url=auth_url)

@router.get("/callback")
async def microsoft_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
    db: Session = Depends(get_db)
):
    """Handle Microsoft SSO callback with PKCE validation"""
    
    # Handle OAuth errors
    if error:
        raise HTTPException(
            status_code=400, 
            detail=f"Microsoft authentication failed: {error_description or error}"
        )
    
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")
    
    # Validate state parameter (CSRF protection)
    if state not in sso_states:
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter")
    
    state_data = sso_states[state]
    
    # Check state expiration
    if datetime.utcnow() > state_data["expires_at"]:
        del sso_states[state]
        raise HTTPException(status_code=400, detail="State parameter expired")
    
    nonce = state_data["nonce"]
    code_verifier = state_data["code_verifier"]
    del sso_states[state]  # Use state only once
    
    try:
        # Exchange authorization code for tokens with PKCE
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/oauth2/v2.0/token",
                data={
                    "client_id": MICROSOFT_CLIENT_ID,
                    "client_secret": MICROSOFT_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": MICROSOFT_REDIRECT_URI,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if token_response.status_code != 200:
                print(f"Token exchange failed: {token_response.status_code}")
                print(f"Response: {token_response.text}")
                raise HTTPException(
                    status_code=400, 
                    detail=f"Failed to exchange authorization code: {token_response.text}"
                )
            
            tokens = token_response.json()
            id_token = tokens.get("id_token")
            
            if not id_token:
                print(f"No id_token in response: {tokens}")
                raise HTTPException(status_code=400, detail="No ID token received")
            
            # Decode and validate ID token
            import jwt
            from jwt import PyJWKClient
            
            jwks_url = f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/discovery/v2.0/keys"
            jwks_client = PyJWKClient(jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)
            
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=MICROSOFT_CLIENT_ID,
                options={"verify_exp": True}
            )
            
            
            # Validate nonce (replay protection)
            if claims.get("nonce") != nonce:
                raise HTTPException(status_code=400, detail="Invalid nonce")
            
            # Validate required claims
            if not all(k in claims for k in ["oid", "name"]):
                raise HTTPException(status_code=400, detail="Missing required claims")
            
            # Extract user info
            user_id = claims["oid"]
            email = claims.get("email") or claims.get("preferred_username")
            name = claims["name"]
            
            if not email:
                raise HTTPException(status_code=400, detail="Email not provided by Microsoft")
            
            
            # Check if user exists, create if not
            if not check_user_exists(db, email):
                # Detect client_name from redirect URI domain
                from urllib.parse import urlparse
                _redirect_domain = urlparse(MICROSOFT_REDIRECT_URI).hostname or ""
                _detected_client = DOMAIN_TO_CLIENT.get(_redirect_domain, "jlens")
                user_data = UserCreateMicrosoft(
                    name=name,
                    email=email,
                    id=user_id,
                    client_name=_detected_client
                )
                create_user_microsoft(db, user_data)
            
            # Get user from database
            from db.models import User
            user = db.query(User).filter(User.email == email).first()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Create JWT token
            access_token = create_access_token(
                data={
                    "sub": user.email,
                    "user_id": str(user.id),
                    "user_name": user.name
                }
            )
            
            # Create response with cookie and redirect with user info (no token in URL)
            import urllib.parse
            user_info = urllib.parse.urlencode({
                'sso': 'success',
                'email': user.email,
                'name': user.name,
            })
            
            _environment = os.getenv("ENVIRONMENT", "development")
            _is_https = _environment == "production"
            
            redirect_response = RedirectResponse(
                url=f"{FRONTEND_URL}/app/chat?{user_info}",
                status_code=302
            )
            redirect_response.set_cookie(
                key="access_token",
                value=access_token,
                httponly=True,
                secure=_is_https,
                samesite="none" if _is_https else "lax",
                max_age=172800,  # 48 hours to match JWT expiration
                path="/",
                domain=None
            )
            
            
            return redirect_response
            
    except jwt.InvalidTokenError as e:
        print(f"JWT validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        print(f"Authentication error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")

@router.post("/logout")
async def microsoft_logout(response: Response):
    """Logout and clear authentication cookie"""
    response.delete_cookie(key="access_token", path="/")
    return {"message": "Logged out successfully"}

def _clean_expired_states():
    """Remove expired state entries"""
    now = datetime.utcnow()
    expired = [k for k, v in sso_states.items() if v["expires_at"] < now]
    for key in expired:
        del sso_states[key]

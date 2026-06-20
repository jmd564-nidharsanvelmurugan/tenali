import os
from fastapi import FastAPI, APIRouter, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from security_middleware import SecurityLoggingMiddleware, RateLimitingMiddleware, InputValidationMiddleware
from auth.routes import router as auth_router
from auth.microsoft_sso import router as microsoft_sso_router
from Jlens.workspace.routes import router as workspace_router
from Jlens.user_access.routes import router as user_access_router
from Jlens.conversations.routes import router as conversation_router
from Jlens.messages.routes import router as messages_router
from Jlens.mcp_server.routes import router as mcp_router
from Jlens.models.routes import router as models_router
from Jlens.analytics.routes import router as analytics_router
from Jlens.feedback.routes import router as feedback_router
from AiProposal.routes import router as ai_proposal_router




class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
        except RuntimeError as e:
            if "No response returned" in str(e):
                from fastapi.responses import Response
                return Response(status_code=503)
            raise
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Allow same-origin iframes for file preview
        if "/files/" in str(request.url) and "/view/" in str(request.url):
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
        else:
            response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response

# Check if we're in production environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
ENABLE_DOCS = os.getenv("ENABLE_DOCS", "true").lower() == "true"

# Configure FastAPI with conditional docs
if ENVIRONMENT == "production" and not ENABLE_DOCS:
    app = FastAPI(
        title="Jlens API",
        description="AI-powered chatbot platform - Secure Version",
        version="1.0.0",
        docs_url=None,  # Disable Swagger UI
        redoc_url=None  # Disable ReDoc
    )
else:
    app = FastAPI(
        title="Jlens API",
        description="AI-powered chatbot platform - Secure Version",
        version="1.0.0"
    )







    

# Add security middleware in order of priority
app.add_middleware(SecurityLoggingMiddleware)
app.add_middleware(RateLimitingMiddleware, calls_per_minute=100)  # 100 requests per minute
app.add_middleware(InputValidationMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# Security middleware
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["localhost", "127.0.0.1", "tenaliai-az-dev.jmangroup.tech", "tenaliai-az.jmangroup.tech", "jlens4o.jmangroup.tech", "marketplace-uat.jmangroup.tech", "marketplace.jmangroup.tech","nexus-ms.jmangroup.tech"]
)

# Allow CORS for frontend (React) with stricter configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "https://jlens4o.jmangroup.tech", "https://marketplace-uat.jmangroup.tech", "https://marketplace.jmangroup.tech", "https://jlens.jmangroup.tech", "https://nexus-ms.jmangroup.tech"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Restrict methods
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With", "request-id", "traceparent"],  # Added request-id and traceparent
    max_age=3600,  # Cache preflight requests
)

api_router = APIRouter()



app.include_router(auth_router, prefix="/api")
app.include_router(microsoft_sso_router, prefix="/api")
app.include_router(workspace_router, prefix="/api")
app.include_router(user_access_router, prefix="/api")
app.include_router(conversation_router, prefix="/api")
app.include_router(messages_router, prefix="/api")
app.include_router(models_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(feedback_router, prefix="/api")
app.include_router(ai_proposal_router, prefix="/api")
app.include_router(mcp_router, prefix="/api")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "security": "enabled"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

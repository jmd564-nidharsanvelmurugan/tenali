import logging
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import json

# Configure security logger
security_logger = logging.getLogger("security")
security_logger.setLevel(logging.INFO)

# Create file handler for security logs
security_handler = logging.FileHandler("security.log")
security_handler.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
security_handler.setFormatter(formatter)
security_logger.addHandler(security_handler)

class SecurityLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log security-relevant events"""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Log request details
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Check for suspicious patterns
        suspicious_patterns = [
            "<script", "javascript:", "data:", "vbscript:",
            "onload=", "onerror=", "onclick=", "eval(",
            "document.cookie", "window.location"
        ]
        
        # Check URL and headers for suspicious content
        url_path = str(request.url.path)
        query_params = str(request.url.query) if request.url.query else ""
        
        is_suspicious = any(
            pattern.lower() in url_path.lower() or 
            pattern.lower() in query_params.lower()
            for pattern in suspicious_patterns
        )
        
        if is_suspicious:
            security_logger.warning(
                f"Suspicious request detected - IP: {client_ip}, "
                f"Path: {url_path}, Query: {query_params}, "
                f"User-Agent: {user_agent}"
            )
        
        # Process request
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # Log authentication events
            if "/auth/" in url_path:
                security_logger.info(
                    f"Auth request - IP: {client_ip}, "
                    f"Path: {url_path}, Status: {response.status_code}, "
                    f"Time: {process_time:.3f}s"
                )
            
            # Log failed requests
            if response.status_code >= 400:
                security_logger.warning(
                    f"Failed request - IP: {client_ip}, "
                    f"Path: {url_path}, Status: {response.status_code}, "
                    f"Time: {process_time:.3f}s"
                )
            
            return response
            
        except Exception as e:
            security_logger.error(
                f"Request error - IP: {client_ip}, "
                f"Path: {url_path}, Error: {str(e)}"
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            )

class RateLimitingMiddleware(BaseHTTPMiddleware):
    """Simple rate limiting middleware"""
    
    def __init__(self, app, calls_per_minute: int = 60):
        super().__init__(app)
        self.calls_per_minute = calls_per_minute
        self.requests = {}  # In production, use Redis or similar
    
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        current_time = time.time()
        
        # Clean old entries (older than 1 minute)
        cutoff_time = current_time - 60
        self.requests = {
            ip: timestamps for ip, timestamps in self.requests.items()
            if any(t > cutoff_time for t in timestamps)
        }
        
        # Update timestamps for current IP
        if client_ip not in self.requests:
            self.requests[client_ip] = []
        
        # Remove old timestamps for this IP
        self.requests[client_ip] = [
            t for t in self.requests[client_ip] if t > cutoff_time
        ]
        
        # Check rate limit
        if len(self.requests[client_ip]) >= self.calls_per_minute:
            security_logger.warning(
                f"Rate limit exceeded - IP: {client_ip}, "
                f"Requests: {len(self.requests[client_ip])}"
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"}
            )
        
        # Add current request timestamp
        self.requests[client_ip].append(current_time)
        
        return await call_next(request)

class InputValidationMiddleware(BaseHTTPMiddleware):
    """Middleware to validate and sanitize input"""
    
    async def dispatch(self, request: Request, call_next):
        # Check content length
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > 10 * 1024 * 1024:  # 10MB limit
                    security_logger.warning(
                        f"Large request blocked - IP: {request.client.host}, "
                        f"Size: {content_length} bytes"
                    )
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request too large"}
                    )
            except (ValueError, TypeError):
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header"}
                )
        
        # Validate content type for POST/PUT requests
        if request.method in ["POST", "PUT", "PATCH"]:
            content_type = request.headers.get("content-type", "")
            allowed_types = [
                "application/json",
                "application/x-www-form-urlencoded",
                "multipart/form-data"
            ]
            
            if not any(allowed_type in content_type for allowed_type in allowed_types):
                security_logger.warning(
                    f"Invalid content type - IP: {request.client.host}, "
                    f"Type: {content_type}"
                )
                return JSONResponse(
                    status_code=415,
                    content={"detail": "Unsupported media type"}
                )
        
        return await call_next(request)

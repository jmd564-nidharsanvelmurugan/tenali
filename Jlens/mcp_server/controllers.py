from fastapi import Depends
from sqlalchemy.orm import Session
from .schemas import McpWorkspaceRequest
from .services import create_mcp_workspace_service
from auth.deps import get_db
from db.models import User

def create_mcp_workspace_controller(request: McpWorkspaceRequest, db):
    return create_mcp_workspace_service(request, db)

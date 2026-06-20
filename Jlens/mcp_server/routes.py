from fastapi import APIRouter
from sqlalchemy.orm import Session
from fastapi import Depends
from . import controllers, schemas
from auth.deps import get_db
from db.models import User
from auth.services import get_current_user

router = APIRouter(prefix="/mcp", tags=["MCP"])

@router.post("/")
def create_mcp_workspace(request: schemas.McpWorkspaceRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return controllers.create_mcp_workspace_controller(request, db)

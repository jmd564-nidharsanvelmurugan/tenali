from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from auth.deps import get_db
from auth.services import get_current_user
from db.models import User, UserRole
from . import services
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get("/my-stats")
def get_my_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed analytics for current user"""
    return services.get_user_detailed_analytics(db, current_user.id)

@router.get("/admin/stats")
def get_admin_analytics(
    client_name: Optional[str] = Query(None, description="Filter by client platform (jlens, marketplace, etc.)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed system-wide analytics (admin only) with optional client filtering"""
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return services.get_admin_detailed_analytics(db, client_name)


# TODO: Uncomment after running migration (see DATA_MODEL_CHANGES.md)
# @router.post("/admin/infra-costs") — add infra cost entry
# @router.get("/admin/infra-costs") — query infra costs
# @router.get("/admin/total-costs") — combined LLM + infra summary

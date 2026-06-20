from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from auth.deps import get_db
from auth.services import get_current_user
from db.models import User, UserComponentAccess, AIModel
from . import controllers, services

router = APIRouter(prefix="/models", tags=["Models"])

@router.get("/available")
def get_available_models(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get available AI models for the current user based on their access"""
    # Get user's model access
    user_access = db.query(UserComponentAccess).filter(
        UserComponentAccess.user_id == current_user.id,
        UserComponentAccess.component_type == "model"
    ).all()
    
    # Get accessible model IDs
    accessible_model_ids = {access.component_id for access in user_access}
    
    # Get all models from Azure
    all_models = controllers.get_available_models()
    
    # Filter models based on user access
    if not accessible_model_ids:
        # No access granted, return empty list
        return []
    
    # Get model details from DB to match IDs
    db_models = db.query(AIModel).filter(AIModel.id.in_(accessible_model_ids)).all()
    model_ids_map = {m.id: m.model_id for m in db_models}
    
    # Filter Azure models by accessible model_ids
    accessible_models = [
        model for model in all_models 
        if model["id"] in model_ids_map.values()
    ]
    
    return accessible_models

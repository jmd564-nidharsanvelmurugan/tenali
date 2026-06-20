from fastapi import HTTPException
from sqlalchemy.orm import Session
from . import services, schemas
from uuid import UUID
 
def create_access_controller(db: Session, access: schemas.UserComponentAccessCreate):
    return services.create_user_access(db, access)

def bulk_update_access_controller(db: Session, user_id: UUID, updates: schemas.BulkAccessUpdate):
    return services.bulk_update_user_access(db, user_id, updates)

def get_available_components(db: Session, user_id: UUID):
    return services.get_available_components(db, user_id)

def get_access_by_user_controller(db: Session, user_id: UUID):
    return services.get_user_access_by_user(db, user_id)
 
def update_access_controller(db: Session, access_id: UUID, access_update: schemas.UserComponentAccessUpdate):
    result = services.update_user_access(db, access_id, access_update)
    if not result:
        raise HTTPException(status_code=404, detail="Access record not found")
    return result
 
def delete_access_controller(db: Session, access_id: UUID):
    if not services.delete_user_access(db, access_id):
        raise HTTPException(status_code=404, detail="Access record not found")
    return {"detail": "Access deleted"}
 
def get_all_users_access_controller(db: Session):
    return services.get_all_users_access(db)

def get_limited_users_access_controller(db: Session, current_user_id: UUID):
    return services.get_limited_users_access(db, current_user_id)

def search_user_by_email_controller(db: Session, email: str):
    return services.search_user_by_email(db, email)

def suggest_users_controller(db: Session, query: str):
    return services.suggest_users(db, query)

def admin_update_user_access_controller(db: Session, user_email: str, updates: schemas.BulkAccessUpdate):
    return services.admin_update_user_access(db, user_email, updates)

def get_all_models_for_admin(db: Session):
    """Get all models for admin settings"""
    return services.get_all_models_for_admin(db)

def get_models_with_access(db: Session, user_id: UUID):
    """Get all models with access info for specific user"""
    return services.get_models_with_access(db, user_id)

def get_workspaces_with_access(db: Session, user_id: UUID):
    """Get system workspaces with access info for specific user"""
    return services.get_workspaces_with_access(db, user_id)

def get_all_accessible_workspaces(db: Session, user_id: UUID):
    """Get all accessible workspaces (system, own, shared) for specific user"""
    return services.get_all_accessible_workspaces(db, user_id)

def get_system_workspaces_for_admin(db: Session):
    """Get system workspaces for admin settings"""
    return services.get_system_workspaces_for_admin(db)

def get_user_access_summary(db: Session, user_id: UUID):
    """Get user's access summary"""
    return services.get_user_access_summary(db, user_id)

def search_user_by_email_with_access(db: Session, email: str):
    """Search user by email and return with access data"""
    return services.search_user_by_email_with_access(db, email)

def create_user_controller(db: Session, user_data: schemas.CreateUserRequest):
    try:
        return services.create_user(db, user_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

def create_feature_controller(db: Session, feature_data: schemas.CreateFeatureRequest):
    try:
        return services.create_feature(db, feature_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

def create_model_controller(db: Session, model_data: schemas.CreateModelRequest):
    try:
        return services.create_model(db, model_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
 
 
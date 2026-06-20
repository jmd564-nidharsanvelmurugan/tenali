from sqlalchemy.orm import Session
from db.models import AIModel
from . import controllers

def sync_models_to_db(db: Session):
    """Sync available models from Azure AI Foundry to database"""
    available_models = controllers.get_available_models()
    
    for model_data in available_models:
        existing = db.query(AIModel).filter(AIModel.model_id == model_data["id"]).first()
        
        if existing:
            existing.name = model_data["name"]
            existing.description = model_data["description"]
            existing.status = model_data["status"]
        else:
            new_model = AIModel(
                model_id=model_data["id"],
                name=model_data["name"],
                description=model_data["description"],
                status=model_data["status"]
            )
            db.add(new_model)
    
    db.commit()
    return db.query(AIModel).all()

def get_all_models(db: Session):
    """Get all AI models from database"""
    return db.query(AIModel).all()

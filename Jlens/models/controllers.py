import os
import requests
import subprocess
import json
from typing import List, Dict
from sqlalchemy.orm import Session
from auth.deps import get_db
from db.models import AIModel

def get_available_models() -> List[Dict]:
    """Fetch models from database"""
    
    try:
        # Get models from database
        db = next(get_db())
        db_models = db.query(AIModel).filter(AIModel.status == 'active').all()
        
        # Convert to API format
        models = []
        for model in db_models:
            # Determine logo based on model name
            logo = "/logos/openai.svg"  # default
            if "claude" in model.model_id.lower():
                logo = "/logos/claude.svg"
            elif "llama" in model.model_id.lower():
                logo = "/logos/llama.svg"
            elif "deepseek" in model.model_id.lower():
                logo = "/logos/deepseek.svg"
            elif "grok" in model.model_id.lower():
                logo = "/logos/grok.svg"
            
            models.append({
                "id": model.model_id,
                "name": model.name,
                "model": model.model_id,
                "status": "succeeded",
                "description": model.description,
                "logo": logo
            })
        
        db.close()
        return models
        
    except Exception as e:
        print(f"Error loading models from database: {e}")
        # Fallback to hardcoded list if database fails
        return get_fallback_models()

def get_fallback_models() -> List[Dict]:
    """Fallback hardcoded models if database fails"""
    return [
        {
            "id": "claude-sonnet-4-5",
            "name": "claude-sonnet-4-5",
            "model": "claude-sonnet-4-5",
            "status": "succeeded",
            "description": "Claude Sonnet 4.5",
            "logo": "/logos/claude.svg"
        },
        {
            "id": "model-router",
            "name": "model-router",
            "model": "model-router", 
            "status": "succeeded",
            "description": "Azure AI Model Router",
            "logo": "/logos/openai.svg"
        },
        {
            "id": "gpt-5.1-chat",
            "name": "gpt-5.1-chat", 
            "model": "gpt-5.1-chat",
            "status": "succeeded",
            "description": "GPT-5.1 Chat model",
            "logo": "/logos/openai.svg"
        },
        {
            "id": "gpt-5-chat",
            "name": "gpt-5-chat",
            "model": "gpt-5-chat",
            "status": "succeeded",
            "description": "GPT-5 Chat model",
            "logo": "/logos/openai.svg"
        },
        {
            "id": "gpt-4.1-mini",
            "name": "gpt-4.1-mini",
            "model": "gpt-4.1-mini", 
            "status": "succeeded",
            "description": "GPT-4.1 Mini model",
            "logo": "/logos/openai.svg"
        },
        {
            "id": "DeepSeek-R1",
            "name": "DeepSeek-R1",
            "model": "DeepSeek-R1",
            "status": "succeeded", 
            "description": "DeepSeek R1 reasoning model",
            "logo": "/logos/deepseek.svg"
        },
        {
            "id": "grok-3-mini",
            "name": "grok-3-mini",
            "model": "grok-3-mini",
            "status": "succeeded",
            "description": "Grok 3 Mini model",
            "logo": "/logos/grok.svg"
        },
        {
            "id": "llama-3.3-70b-instruct",
            "name": "Llama 3.3 70B", 
            "model": "llama-3.3-70b-instruct",
            "status": "succeeded",
            "description": "Llama 3.3 70B Instruct model",
            "logo": "/logos/llama.svg"
        },
        {
            "id": "llama-3.1-405b-instruct",
            "name": "Llama 3.1 405B",
            "model": "llama-3.1-405b-instruct", 
            "status": "succeeded",
            "description": "Llama 3.1 405B Instruct model",
            "logo": "/logos/llama.svg"
        }
    ]

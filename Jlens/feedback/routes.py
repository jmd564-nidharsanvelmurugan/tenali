from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from auth.deps import get_db
from auth.services import get_current_user
from db.models import User
from . import services
from .schemas import FeedbackCreate, FeedbackResponse, FeedbackListResponse

router = APIRouter(prefix="/feedback", tags=["feedback"])

@router.post("/")
async def submit_feedback(
    feedback_data: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Submit user feedback"""
    try:
        feedback = services.create_feedback(db, str(current_user.id), feedback_data)
        
        # Return a simple response instead of using the response model
        return {
            "id": str(feedback.id),
            "rating": feedback.rating,
            "comment": feedback.comment,
            "message": "Feedback submitted successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"DEBUG: Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to create feedback: {str(e)}")

@router.get("/status")
async def get_feedback_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check if current user has given feedback"""
    has_feedback = services.user_has_feedback(db, current_user.id)
    return {"has_feedback": has_feedback}

@router.get("/all", response_model=List[FeedbackListResponse])
async def get_all_feedbacks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all user feedbacks (admin only)"""
    if current_user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return services.get_all_feedbacks(db)

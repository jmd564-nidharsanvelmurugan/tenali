from sqlalchemy.orm import Session
from sqlalchemy import and_
from db.models import UserFeedback, User
from .schemas import FeedbackCreate
from typing import List

def create_feedback(db: Session, user_id: str, feedback_data: FeedbackCreate) -> UserFeedback:
    """Create new user feedback and update user status"""
    
    # First, verify the user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User with id {user_id} not found")
    
    # Create feedback record
    feedback = UserFeedback(
        user_id=user_id,
        rating=feedback_data.rating,
        comment=feedback_data.comment
    )
    db.add(feedback)
    
    # Update user feedback status
    user.has_given_feedback = True
    
    # Commit the transaction
    db.commit()
    
    # Return the feedback object (don't refresh, it causes issues)
    return feedback

def user_has_feedback(db: Session, user_id: str) -> bool:
    """Check if user has given feedback"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        return user.has_given_feedback if user else False
    except Exception:
        return False

def get_all_feedbacks(db: Session) -> List[dict]:
    """Get all user feedbacks with user details"""
    feedbacks = db.query(UserFeedback, User).join(
        User, UserFeedback.user_id == User.id
    ).order_by(UserFeedback.created_at.desc()).all()
    
    result = []
    for feedback, user in feedbacks:
        result.append({
            "id": str(feedback.id),
            "rating": feedback.rating,
            "comment": feedback.comment,
            "created_at": feedback.created_at,
            "user_name": user.name,
            "user_email": user.email
        })
    
    return result

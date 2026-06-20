from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class FeedbackCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5 stars")
    comment: Optional[str] = Field(None, max_length=1000, description="Optional feedback comment")

class FeedbackResponse(BaseModel):
    id: str
    rating: int
    comment: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

class FeedbackListResponse(BaseModel):
    id: str
    rating: int
    comment: Optional[str]
    created_at: datetime
    user_name: str
    user_email: str
    
    class Config:
        from_attributes = True

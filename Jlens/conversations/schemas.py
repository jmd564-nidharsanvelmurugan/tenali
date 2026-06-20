from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional
from db.models import ComponentType, ChatType

class ConversationCreate(BaseModel):
    title: str
    workspace_id: UUID
    component_type: Optional[ComponentType] = None

class ConversationOut(BaseModel):
    id: UUID
    title: str
    workspace_id: UUID
    user_id: UUID
    component_type: Optional[ComponentType]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class MessageOut(BaseModel):
    id: UUID
    workspace_id: UUID
    conversation_id: UUID
    user_id: UUID
    content: str
    role: str
    model_type: str
    chat_type: ChatType
    input_tokens: int
    output_tokens: int
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            ChatType: lambda v: v.value,
        }

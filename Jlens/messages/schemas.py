from pydantic import BaseModel, UUID4, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
from uuid import UUID
from db.models import ChatType, ComponentType

class RoleEnum(str, Enum):
    user = "user"
    assistant = "assistant"
    tool = "tool"

class MessageCreate(BaseModel):
    conversation_id: Optional[UUID] = None
    workspace_id: UUID4
    content: str
    role: RoleEnum
    model_type: Optional[str] = None
    chat_type: Optional[ChatType] = None
    component_type: Optional[ComponentType] = None
    filter_group: Optional[str] = None
    input_tokens: int
    output_tokens: int
    pre_prompt: Optional[str] = None

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
    pre_prompt: Optional[str] = None

    class Config:
        from_attributes = True
        json_encoders = {
            ChatType: lambda v: v.value,
        }
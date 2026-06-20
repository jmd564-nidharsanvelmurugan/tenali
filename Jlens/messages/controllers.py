from fastapi import HTTPException, Depends, File, UploadFile, Form
from sqlalchemy.orm import Session
from .schemas import MessageCreate
from .services import create_message, get_last_user_message, conversation_with_data, conversation_without_data, store_answer
from uuid import UUID
from fastapi.responses import StreamingResponse
from openai.types.chat import ChatCompletionMessageParam
from db.models import ChatType, ComponentType
from auth.services import get_current_user
from typing import List, Optional


async def create_message_controller(db: Session, user_id: UUID, message: MessageCreate, files: List[UploadFile] = None):
    # Check workspace access
    from Jlens.workspace.services import check_workspace_access
    from db.models import Conversation
    
    # Get conversation to find workspace
    conversation = db.query(Conversation).filter(Conversation.id == message.conversation_id).first()
    if conversation:
        has_access = check_workspace_access(db, user_id, conversation.workspace_id)
        if not has_access:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Please contact admin to grant access to this workspace."
            )
    
    if (message.component_type == ComponentType.proposal):
        return store_answer(db, user_id, message)
    
    user_msg = create_message(db, user_id, message)
    
    if ChatType(user_msg.chat_type) != ChatType("standalone"):
        return await conversation_with_data(db, user_msg, user_id, message)  
    else:
        return await conversation_without_data(db, user_msg, user_id, message, files)  

# def stream_llm_response_controller(db: Session, user_id: UUID, conversation_id: UUID):
#     user_msg = get_last_user_message(db, conversation_id)

#     if ChatType(user_msg.chat_type) != ChatType("standalone"):
#         return conversation_with_data(db, user_msg, user_id, user_msg)
#     else:
#         return conversation_without_data(db, user_msg, user_id, user_msg)
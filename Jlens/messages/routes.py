from fastapi import APIRouter, Depends, status, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from auth.deps import get_db
from auth.services import get_current_user
from .schemas import MessageCreate, MessageOut
from .controllers import create_message_controller
from typing import List, Optional
from uuid import UUID
import json

router = APIRouter(prefix="/messages", tags=["Messages"])

@router.post("/", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def create_message_endpoint(
    message: MessageCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return await create_message_controller(db, current_user.id, message)

@router.post("/with-files", response_class=StreamingResponse)
async def create_message_with_files(
    content: str = Form(...),
    conversation_id: str = Form(...),
    workspace_id: str = Form(...),
    model_type: str = Form("gpt-4.1-mini"),
    chat_type: str = Form("standalone"),
    files: List[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Create message with optional file uploads for JLens workspace"""
    message_data = MessageCreate(
        content=content,
        conversation_id=UUID(conversation_id),
        workspace_id=UUID(workspace_id),
        role="user",
        model_type=model_type,
        chat_type=chat_type,
        input_tokens=0,
        output_tokens=0
    )
    
    return await create_message_controller(db, current_user.id, message_data, files)

# @router.post("/stream/{conversation_id}", response_class=StreamingResponse)
# def stream_llm_response(
#     conversation_id: UUID,
#     db: Session = Depends(get_db),
#     current_user=Depends(get_current_user)
# ):
#     return stream_llm_response_controller(db, current_user.id, conversation_id)
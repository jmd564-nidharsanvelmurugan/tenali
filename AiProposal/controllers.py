from .schemas import UpdateMessageRequest
from typing import List
from fastapi import UploadFile
from Jlens.conversations.controllers import list_messages_by_conversation_controller
from db.models import User
from .services import *
from sqlalchemy.orm import Session
from uuid import UUID

async def update_message_controller(request: UpdateMessageRequest, db):
    return await update_message_service(request, db)

async def generate_proposal_controller(conversation_id: str, db: Session, uid: UUID , user_prompt: str = None):
    # Convert string conversation_id to UUID (essential fix)
    conv_id = UUID(conversation_id)
    return await generate_proposal(conv_id, db, uid, user_prompt)

async def follow_up_proposal_controller(conversation_id: "UUID", new_message: str, db: Session, current_user):
   
    messages = list_messages_by_conversation_controller(db, conversation_id , current_user.id) 

    if not messages:
        raise ValueError("No messages found for this conversation")
    recent_message = messages[-2].content if messages else None
    if recent_message is None:
        raise ValueError("No recent message found")
    result = await follow_up_proposal_service(conversation_id, str(recent_message), new_message, db, current_user)
    return result

def edit_answers_controller(request, db):
    return edit_answers(request, db)

def proposal_docx_controller(conversation_id: UUID, db: Session):
    return proposal_docx(conversation_id, db)

async def upload_files_controller(conversation_id: UUID, files: List[UploadFile], db: Session, current_user: User):
    return await upload_files(conversation_id, files, db, current_user)

async def edit_proposal_llm_controller(conversation_id: UUID, user_message: str, db: Session, current_user: User, message_id: UUID = None):
    return await edit_proposal_llm_service(conversation_id, user_message, db, current_user, message_id)

async def read_sales_call_questions_docx_controller():
    return await read_sales_call_questions_docx()

async def upload_sales_call_questions_docx_controller(user_id: UUID, conversation_id: UUID, file: UploadFile):
    return await upload_sales_call_questions_docx(user_id, conversation_id, file)
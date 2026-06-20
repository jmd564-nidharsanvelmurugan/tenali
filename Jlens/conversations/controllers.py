from sqlalchemy.orm import Session
from uuid import UUID
from db.models import User
from . import schemas
from fastapi import HTTPException
from .services import create_conversation_db, get_conversations_by_user_db, delete_conversation_db, get_messages_by_conversation, get_conversations_by_sharedworkspace_db


def create_conversation_controller(
    db: Session, current_user: User, conversation_in: schemas.ConversationCreate
):
    return create_conversation_db(db, current_user, conversation_in)


def get_user_conversations_controller(
    db: Session, current_user: User
):
    return get_conversations_by_user_db(db, current_user.id)

def get_user_sharedworkspace_conversations_controller(
    db: Session, workspace_id: UUID, current_user: User
):
    return get_conversations_by_sharedworkspace_db(db, workspace_id, current_user.id)


def delete_conversation_controller(
    db: Session, conversation_id: UUID, current_user: User
):
    return delete_conversation_db(db, conversation_id, current_user.id)

def list_messages_by_conversation_controller(
    db: Session, conversation_id: UUID, user_id: UUID
):
    # Get conversation and verify access
    from db.models import Conversation
    from Jlens.workspace.services import check_workspace_access
    
    print("@" * 100)
    print(f"Listing messages for conversation_id: {conversation_id} and user_id: {user_id}")
    print("@" * 100)


    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Check if user has access to the workspace (handles ownership + sharing)
    if not check_workspace_access(db, user_id, conversation.workspace_id):
        raise HTTPException(status_code=403, detail="Access denied to this conversation")
    
    messages = get_messages_by_conversation(db, conversation_id)
    if not messages:
        raise HTTPException(status_code=404, detail="No messages found")
    return messages

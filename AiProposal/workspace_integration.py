"""
AI Proposal Workspace Integration Module
Connects AI Proposal functionality with the main workspace system
"""

from sqlalchemy.orm import Session
from sqlalchemy import text
from uuid import UUID
from db.models import Workspace, Conversation, Message, User, ComponentType
from typing import Optional
import uuid

def get_ai_proposal_workspace(db: Session) -> Optional[Workspace]:
    """Get the AI Proposal system workspace"""
    return db.query(Workspace).filter(
        Workspace.name == "AI Proposal",
        Workspace.is_system_workspace == True
    ).first()

def create_ai_proposal_conversation(
    db: Session, 
    user_id: UUID, 
    title: str = "New AI Proposal"
) -> Conversation:
    """Create a new conversation in the AI Proposal workspace"""
    
    # Get AI Proposal workspace
    ai_workspace = get_ai_proposal_workspace(db)
    if not ai_workspace:
        raise ValueError("AI Proposal workspace not found")
    
    # Create conversation
    conversation = Conversation(
        id=uuid.uuid4(),
        title=title,
        workspace_id=ai_workspace.id,
        user_id=user_id,
        component_type=ComponentType.proposal
    )
    
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    
    return conversation

def ensure_ai_proposal_workspace_exists(db: Session) -> Workspace:
    """Ensure AI Proposal workspace exists, create if not (system workspace only)"""
    
    # Check for existing system workspace first
    workspace = db.query(Workspace).filter(
        Workspace.name == "AI Proposal",
        Workspace.is_system_workspace == True,
        Workspace.user_id.is_(None)  # System workspaces have no user_id
    ).first()
    
    if workspace:
        return workspace
    
    # Remove any duplicate user workspaces with same name
    db.query(Workspace).filter(
        Workspace.name == "AI Proposal",
        Workspace.is_system_workspace == False
    ).delete()
    
    # Create AI Proposal system workspace
    workspace = Workspace(
        id=uuid.uuid4(),
        name="AI Proposal",
        description="Specialized workspace for creating and managing AI-powered proposals",
        user_id=None,  # System workspace - no user ownership
        pre_prompt="You are an AI assistant specialized in proposal creation and management. Help users create, analyze, and refine professional consulting proposals.",
        is_private=False,
        is_system_workspace=True,
        workspace_type="system"
    )
    
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    
    return workspace

def get_ai_proposal_conversations(db: Session, user_id: UUID):
    """Get all AI Proposal conversations for a user"""
    
    ai_workspace = get_ai_proposal_workspace(db)
    if not ai_workspace:
        return []
    
    return db.query(Conversation).filter(
        Conversation.workspace_id == ai_workspace.id,
        Conversation.user_id == user_id,
        Conversation.component_type == ComponentType.proposal
    ).order_by(Conversation.created_at.desc()).all()

def is_ai_proposal_conversation(db: Session, conversation_id: UUID) -> bool:
    """Check if a conversation belongs to AI Proposal workspace"""
    
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id
    ).first()
    
    if not conversation:
        return False
    
    ai_workspace = get_ai_proposal_workspace(db)
    if not ai_workspace:
        return False
    
    return (conversation.workspace_id == ai_workspace.id and 
            conversation.component_type == ComponentType.proposal)

def get_ai_proposal_workspace_stats(db: Session):
    """Get statistics for AI Proposal workspace"""
    
    ai_workspace = get_ai_proposal_workspace(db)
    if not ai_workspace:
        return {
            "workspace_exists": False,
            "conversations": 0,
            "messages": 0,
            "users": 0
        }
    
    # Count conversations
    conv_count = db.query(Conversation).filter(
        Conversation.workspace_id == ai_workspace.id,
        Conversation.component_type == ComponentType.proposal
    ).count()
    
    # Count messages
    msg_count = db.query(Message).filter(
        Message.workspace_id == ai_workspace.id
    ).count()
    
    # Count unique users
    user_count = db.query(Conversation.user_id).filter(
        Conversation.workspace_id == ai_workspace.id,
        Conversation.component_type == ComponentType.proposal
    ).distinct().count()
    
    return {
        "workspace_exists": True,
        "workspace_id": str(ai_workspace.id),
        "conversations": conv_count,
        "messages": msg_count,
        "users": user_count
    }

def migrate_existing_conversations_to_ai_proposal(db: Session):
    """Migrate any existing proposal-related conversations to AI Proposal workspace"""
    
    ai_workspace = ensure_ai_proposal_workspace_exists(db)
    
    # Find conversations that might be proposal-related but not in AI Proposal workspace
    result = db.execute(text("""
        UPDATE conversation 
        SET workspace_id = :ai_workspace_id, component_type = 'proposal'
        WHERE component_type = 'proposal' AND workspace_id != :ai_workspace_id
    """), {"ai_workspace_id": ai_workspace.id})
    
    # Update messages as well
    db.execute(text("""
        UPDATE messages 
        SET workspace_id = :ai_workspace_id
        WHERE conversation_id IN (
            SELECT id FROM conversation 
            WHERE component_type = 'proposal' AND workspace_id = :ai_workspace_id
        )
    """), {"ai_workspace_id": ai_workspace.id})
    
    db.commit()
    
    return result.rowcount

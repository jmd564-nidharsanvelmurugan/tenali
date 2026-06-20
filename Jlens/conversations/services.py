from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from uuid import UUID

from db.models import Conversation, User, Message, Workspace, SystemWorkspaceTemplate
from . import schemas as convo_schemas

def create_conversation_db(db: Session, user: User, convo_in: convo_schemas.ConversationCreate):
    # Check if workspace exists, if not create it from system template
    workspace = db.query(Workspace).filter(Workspace.id == convo_in.workspace_id).first()
    
    if not workspace:
        # Check if it's a system workspace template
        template = db.query(SystemWorkspaceTemplate).filter(SystemWorkspaceTemplate.id == convo_in.workspace_id).first()
        if template:
            # Create workspace from template
            workspace = Workspace(
                id=template.id,  # Use same ID as template
                name=template.name,
                description=template.description,
                pre_prompt=template.pre_prompt,
                is_private=False,
                is_system_workspace=True,
                workspace_type="system",
                user_id=user.id,
                created_at=template.created_at,
                updated_at=template.updated_at
            )
            db.add(workspace)
            db.commit()
            db.refresh(workspace)
    
    new_convo = Conversation(
        title=convo_in.title,
        workspace_id=convo_in.workspace_id,
        user_id=user.id,
        component_type=convo_in.component_type
    )
    db.add(new_convo)
    db.commit()
    db.refresh(new_convo)
    return new_convo

def get_conversations_by_user_db(db: Session, user_id: UUID):
    res= db.query(Conversation).filter(
        Conversation.user_id == user_id
    ).order_by(Conversation.created_at.desc()).all()
    return res 

def get_conversations_by_sharedworkspace_db(db: Session, workspace_id: UUID, user_id: UUID):
    from db.models import WorkspaceShare, Workspace
    
    # Check if user owns the workspace
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    is_owner = workspace and workspace.user_id == user_id
    
    # Check if workspace is shared with this user
    is_shared = db.query(WorkspaceShare).filter(
        WorkspaceShare.workspace_id == workspace_id,
        WorkspaceShare.shared_with_id == user_id
    ).first()
    
    # If user owns workspace OR workspace is shared with them, show ALL conversations
    # Otherwise, only show user's own conversations
    if is_owner or is_shared:
        return db.query(Conversation).filter(
            Conversation.workspace_id == workspace_id
        ).order_by(Conversation.created_at.desc()).all()
    else:
        return db.query(Conversation).filter(
            Conversation.user_id == user_id,
            Conversation.workspace_id == workspace_id
        ).order_by(Conversation.created_at.desc()).all()

def delete_conversation_db(db: Session, conversation_id: UUID, user_id: UUID):
    convo = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id
    ).first()
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found or not owned by user")
    db.delete(convo)
    db.commit()

def get_messages_by_conversation(db: Session, conversation_id: UUID):
    return (
        db.query(Message)
        .filter_by(conversation_id=conversation_id)
        .order_by(Message.created_at)
        .all()
    )

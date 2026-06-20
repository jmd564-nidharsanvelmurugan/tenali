from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from auth.deps import get_db
from auth.services import get_current_user
from . import schemas, controllers
from db.models import User

router = APIRouter(prefix="/conversations", tags=["Conversations"])

@router.post("/", response_model=schemas.ConversationOut)
def create_conversation(
    conversation_in: schemas.ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return controllers.create_conversation_controller(db, current_user, conversation_in)

@router.get("/", response_model=List[schemas.ConversationOut])
def get_user_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    
    res= controllers.get_user_conversations_controller(db, current_user)
    return res

@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    controllers.delete_conversation_controller(db, conversation_id, current_user)

@router.get("/workspaces/{workspace_id}", response_model=List[schemas.ConversationOut])
def get_user_shared_conversations(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from Jlens.workspace.services import check_workspace_access
    
    # Verify user has access to this workspace
    if not check_workspace_access(db, current_user.id, workspace_id):
        raise HTTPException(status_code=403, detail="Access denied to this workspace")
    
    return controllers.get_user_sharedworkspace_conversations_controller(db, workspace_id, current_user)

@router.get("/{conversation_id}", response_model=List[schemas.MessageOut])
def get_messages_by_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return controllers.list_messages_by_conversation_controller(db, conversation_id, current_user.id)
from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from auth.deps import get_db
from auth.services import get_current_user
from typing import List
from .schemas import *
from db.models import ProposalQuestions, User
from .workspace_integration import (
    get_ai_proposal_workspace_stats,
    create_ai_proposal_conversation,
    get_ai_proposal_conversations,
    ensure_ai_proposal_workspace_exists
)

from fastapi import APIRouter, Depends, HTTPException, status, Form
from pydantic import BaseModel
from .controllers import *
from uuid import UUID
from fastapi import File, UploadFile


router = APIRouter(prefix="/proposal", tags=["AI Proposal"])

# Workspace Integration Routes
@router.get("/workspace/stats")
def get_ai_proposal_workspace_stats_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get AI Proposal workspace statistics"""
    return get_ai_proposal_workspace_stats(db)

@router.post("/workspace/conversation")
def create_ai_proposal_conversation_endpoint(
    title: str = "New AI Proposal",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new AI Proposal conversation"""
    try:
        conversation = create_ai_proposal_conversation(db, current_user.id, title)
        return {
            "id": str(conversation.id),
            "title": conversation.title,
            "workspace_id": str(conversation.workspace_id),
            "component_type": conversation.component_type
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/workspace/conversations")
def get_ai_proposal_conversations_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all AI Proposal conversations for current user"""
    conversations = get_ai_proposal_conversations(db, current_user.id)
    return [
        {
            "id": str(conv.id),
            "title": conv.title,
            "workspace_id": str(conv.workspace_id),
            "component_type": conv.component_type,
            "created_at": conv.created_at
        }
        for conv in conversations
    ]

@router.post("/workspace/ensure")
def ensure_ai_proposal_workspace_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Ensure AI Proposal workspace exists"""
    workspace = ensure_ai_proposal_workspace_exists(db)
    return {
        "id": str(workspace.id),
        "name": workspace.name,
        "description": workspace.description,
        "workspace_type": workspace.workspace_type
    }

# Original AI Proposal Routes
@router.get("/get-questions", response_model=List[ProposalQuestionResponse])
def get_all_questions(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    questions = db.query(ProposalQuestions).all()
    return questions

class ProposalRequest(BaseModel):
    conversation_id: str
    user_prompt: str = None

@router.post("/generate-proposal", response_model=GenerateProposalResponse)
async def create_message_endpoint(
    request: ProposalRequest,
    db: Session = Depends(get_db),
    current_user: User =Depends(get_current_user)
):
    try:
        print("Hit in Router")
        print(request.user_prompt)
        res = await generate_proposal_controller(request.conversation_id, db, current_user.id , request.user_prompt)
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.put("/edit-answers")
def edit_answers(
    request: EditAnswersRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return edit_answers_controller(request, db)

@router.put("/update")
async def update_message(request: UpdateMessageRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return await update_message_controller(request, db)












@router.get("/follow-up-proposal")
async def follow_up_proposal(
    conversation_id: UUID,
    message: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        
        res = await follow_up_proposal_controller(conversation_id, message, db, current_user)
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
@router.get("/proposal-docx",
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {}
            },
            "description": "DOCX file download",
        },
        400: {"description": "Bad Request"},
    },
    response_class=StreamingResponse,
    summary="Download a generated proposal DOCX",
)
def proposal_docx(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        res = proposal_docx_controller(conversation_id, db)
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    









@router.post("/upload-files")
async def upload_files(
    conversation_id: UUID = Form(...),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await upload_files_controller(conversation_id, files, db, current_user)

@router.post("/edit-proposal-llm")
async def edit_proposal_llm(
    request: EditProposalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        res = await edit_proposal_llm_controller(request.conversation_id, request.user_message, db, current_user, request.message_id, )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
@router.get("/read-sales-call-questions-docx")
async def read_sales_call_questions_docx(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await read_sales_call_questions_docx_controller()

@router.post("/upload-sales-call-qas")
async def upload_sales_call_qas(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    conversation_id: UUID = Form(...),
    file: UploadFile = File(...),
):
    return await upload_sales_call_questions_docx_controller(current_user.id, conversation_id, file)

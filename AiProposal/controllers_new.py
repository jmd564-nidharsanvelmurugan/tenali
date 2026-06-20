from uuid import UUID
from sqlalchemy.orm import Session
from .services import generate_proposal

async def generate_proposal_controller(conversation_id: str, db: Session, uid: UUID):
    conv_id = UUID(conversation_id)
    return await generate_proposal(conv_id, db, uid)

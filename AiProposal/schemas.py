from typing import List, Optional, Dict
from uuid import UUID
from pydantic import BaseModel

class UpdateMessageRequest(BaseModel):
    conversation_id: UUID
    msg_id: UUID
    content: str
class ProposalQuestionResponse(BaseModel):
    id: int
    question: str
    type: str
    options: List[str] | None
    category: str

    class Config:
        from_attributes = True

class PropertiesSchema(BaseModel):
    business_offering: Optional[List[str]] = None
    solution: Optional[List[str]] = None
    region: Optional[List[str]] = None
    project_type: Optional[List[str]] = None
    commercial_use_case: Optional[List[str]] = None
    technical_use_case: Optional[List[str]] = None
    business_model: Optional[List[str]] = None
    existing_infra: Optional[List[str]] = None
    PE_relationship: Optional[List[str]] = None

class ProposalMetadataSchema(BaseModel):
    class Config:
        from_attributes = True
        
    name: str
    link: str
    properties: Optional[PropertiesSchema]

class EditAnswersRequest(BaseModel):
    class ToEdit(BaseModel):
        qid: str
        content: str

    conversation_id: str
    to_edit: List[ToEdit]


class ChatResult(BaseModel):
    prompt: str
    response: Optional[str] = None
    error: Optional[str] = None



class Citation(BaseModel):
    filepath: str
    url: str

class CitationsSchema(BaseModel):
    citations: list[Citation]

class GenerateProposalResponse(BaseModel):
    msg_id: UUID
    proposal: List[ChatResult]
    citations: CitationsSchema

class ScoredProposals(BaseModel):
    proposal: ProposalMetadataSchema
    score: float

class EditProposalRequest(BaseModel):
    conversation_id: UUID
    user_message: str
    message_id: UUID = None  # Optional message ID for context

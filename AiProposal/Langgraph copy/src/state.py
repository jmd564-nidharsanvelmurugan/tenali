from typing import TypedDict, List, Dict, Any, Optional
from datetime import datetime

class ProposalMetadata(TypedDict):
    business_offering: str
    solution: str
    region: str
    project_type: str
    commercial_use_case: str
    technical_use_case: str
    business_model: str
    existing_infra: str
    pe_relationship: str

class SectionContent(TypedDict):
    content: str
    timestamp: str
    retrieval_query: str
    chunks_used: int
    document_ids_used: Optional[List[str]]

class GraphState(TypedDict):
    # Input
    questionnaire: Dict[str, Any]
    questionnaire_text: str
    
    # Metadata
    metadata: Optional[ProposalMetadata]
    metadata_dict: Optional[Dict[str, Any]]
    
    # Retrieval
    top_proposals: List[Dict[str, Any]]
    document_ids: List[str]
    
    # Section-specific storage
    section_chunks: Dict[str, Dict[str, List[Dict[str, Any]]]]
    section_queries: Dict[str, str]
    
    # Generated content
    business_context: Optional[SectionContent]
    overview: Optional[SectionContent]
    understanding: Optional[SectionContent]
    objectives: Optional[SectionContent]
    deliverables: Optional[SectionContent]
    approach: Optional[SectionContent]
    outcomes: Optional[SectionContent]
    business_impact: Optional[SectionContent]
    
    # Flow control
    current_section_index: int
    sections_completed: List[str]
    error: Optional[str]
    
    # ✅ ADD THIS: Sections list for production format
    sections: List[Dict[str, Any]]
    
    # Proposal assembly
    proposal: Optional[Dict[str, Any]]
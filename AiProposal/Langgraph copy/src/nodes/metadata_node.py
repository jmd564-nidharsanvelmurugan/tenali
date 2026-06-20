import json
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from ..state import GraphState
from ..tools.llm_setup import get_llm

class ProposalMetadataSchema(BaseModel):
    business_offering: str
    solution: str
    region: str
    project_type: str
    commercial_use_case: str
    technical_use_case: str
    business_model: str
    existing_infra: str
    pe_relationship: str

def extract_metadata_node(state: GraphState) -> GraphState:
    """Extract metadata from questionnaire."""
    
    print("\n" + "=" * 60)
    print("🔍 EXTRACTING: Proposal Metadata")
    print("=" * 60)
    
    llm = get_llm(temperature=0)
    structured_llm = llm.with_structured_output(ProposalMetadataSchema)
    
    prompt = ChatPromptTemplate.from_template("""
                                    You are an expert Proposal Discovery Analyst.

Analyze the questionnaire responses and classify the engagement.

Return ONLY values from the allowed lists below.

Business Offering:
- SaaS
- Financial Services
- Field Services
- Professional Services

Solution:
- Core Reporting
- Due Diligence
- Data Advisory
- Value Creation
- Exit Prep

Region:
- US
- UK
- Europe

Project Type:
- Design and Discovery
- Build
- Both

Commercial Use Case:
- Revenue Bridge
- Pipeline
- Churn
- Upsell/Cross Sell
- Operational Reporting

Technical Use Case:
- Data Platform
- Gen AI
- Data Science
- Full-Stack Development

Business Model:
- B2B
- B2C
- D2C
- C2C

Existing Infra:
- Yes
- No

PE Relationship:
- PE Firm
- PE Portco

Rules:
- Select the closest matching value.
- Never invent values outside the lists.
- Infer values from the questionnaire.
- Return structured output only.

Questionnaire:
{questionnaire}
""")
    
    chain = prompt | structured_llm
    metadata = chain.invoke({"questionnaire": state["questionnaire_text"]})
    
    # Store metadata
    state["metadata"] = metadata
    state["metadata_dict"] = metadata.model_dump()
    
    print("\n✅ Metadata extracted:")
    print(json.dumps(state["metadata_dict"], indent=2))
    
    return state
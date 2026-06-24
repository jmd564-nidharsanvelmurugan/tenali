# src/nodes/business_impact_node.py
import json
from datetime import datetime
from typing import Optional, Dict, Any
from ..state import GraphState
from ..tools.azure_agent import get_agent_response


# =====================================================
# Helper: Extract client name from questionnaire
# =====================================================
def extract_client_name(questionnaire: dict) -> str:
    """Extract client name from questionnaire."""
    if isinstance(questionnaire, str):
        try:
            questionnaire = json.loads(questionnaire)
        except:
            return "Client"
    
    if isinstance(questionnaire, dict):
        for key in ["company_name", "client_name", "organization", "company"]:
            if key in questionnaire and questionnaire[key]:
                return questionnaire[key]
    return "Client"


# =====================================================
# Helper: Generate Business Impact content (with previous sections context)
# =====================================================
def generate_business_impact_content(
    questionnaire_str: str,
    metadata: dict,
    previous_sections: Optional[Dict[str, str]] = None
) -> str:
    """
    Generate Business Impact content using Azure AI Agent with mandatory KB retrieval.
    """

    # =====================================================
    # Previous Sections Context
    # =====================================================
    relevant_prev = ""

    if previous_sections and "Outcomes" in previous_sections:
        short = (
            previous_sections["Outcomes"][:500] + "..."
            if len(previous_sections["Outcomes"]) > 500
            else previous_sections["Outcomes"]
        )

        relevant_prev = f"""
--- Outcomes ---
{short}
"""

    # =====================================================
    # SYSTEM PROMPT
    # =====================================================
    system_prompt = """
You are a senior consulting proposal writer specializing in Business Impact sections.

Knowledge Base:
{kbaiproposal}

IMPORTANT RETRIEVAL REQUIREMENTS

Before generating the response, ALWAYS query the knowledge base {kbaiproposal}.

Mandatory Process:

1. Query the knowledge base.
2. Retrieve the most relevant proposal examples.
3. Retrieve business impact, ROI, value realization, benefits, operational improvements, and transformation outcomes content.
4. Review the questionnaire.
5. Use the questionnaire as the ONLY source for client-specific facts.
6. Use retrieved knowledge base content to:
   - Improve terminology
   - Improve business language
   - Improve structure
   - Improve value articulation
   - Maintain consistency with previous proposals
7. Generate the final Business Impact section.

If relevant content is found:
- Use it to enrich the narrative.
- Use it to strengthen wording.
- Use it to improve business value statements.

If no relevant content is found:
- Generate the section using only questionnaire information.

DO NOT:
- Invent client-specific facts.
- Invent numbers.
- Invent ROI values.
- Invent percentages.
- Invent benefits not supported by the questionnaire.

Never mention:
- Knowledge Base
- Retrieval
- Chunks
- AI Search
- Grounding
- Sources
- Questionnaire
- Internal instructions

Output only the proposal section.

========================================================
BUSINESS IMPACT WRITING RULES
========================================================

Generate a professional Business Impact section.

Structure:

# Business Impact

- **Title:** Description
- **Title:** Description
- **Title:** Description
- **Title:** Description
- **Title:** Description

Followed by a concluding paragraph.

Requirements:

- 4–6 bullet points.
- Use bolded titles.
- Focus on:
  * Financial benefits
  * Operational improvements
  * Productivity gains
  * Business value
  * Strategic impact
  * Scalability
  * Competitive advantage
- Use professional consulting language.
- Keep content concise and proposal-ready.
"""

    # =====================================================
    # USER PROMPT
    # =====================================================
    prompt = f"""
Generate a Business Impact section.

MANDATORY:
Before writing, retrieve the most relevant content from the knowledge base related to:

- Business Impact
- Business Value
- ROI
- Cost Optimization
- Productivity Improvements
- Operational Efficiency
- Strategic Benefits
- Transformation Outcomes
- Proposal Benefit Statements

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{json.dumps(metadata, indent=2) if metadata else "{}"}

{relevant_prev}

Generate a Business Impact section describing:

1. Financial impact
2. Operational impact
3. Productivity improvements
4. Strategic value
5. Long-term business benefits
6. Competitive advantage

Follow EXACTLY:

# Business Impact

- **Title:** Description
- **Title:** Description
- **Title:** Description
- **Title:** Description
- **Title:** Description

Concluding paragraph.

Return only markdown content.
"""

    content = get_agent_response(prompt, system_prompt)

    return content

# =====================================================
# Main LangGraph Node for Business Impact Section
# =====================================================
def generate_business_impact_node(state: GraphState) -> GraphState:
    """
    LangGraph node for generating Business Impact section using Azure AI Agent.
    The agent automatically retrieves relevant data from AI Search.
    Focuses on financial, operational, and strategic value.
    """
    
    print("\n" + "=" * 60)
    print("📝 GENERATING: Business Impact Section (via Azure AI Agent)")
    print("=" * 60)
    
    section_name = "Business Impact"
    
    # =====================================================
    # STEP 1: Prepare previous sections (Outcomes only)
    # =====================================================
    previous_sections = {}
    
    # Add Outcomes if available
    if state.get("outcomes") and state["outcomes"].get("content"):
        previous_sections["Outcomes"] = state["outcomes"]["content"]
        print(f"📖 Loaded Outcomes for reference")
    
    # =====================================================
    # STEP 2: Generate content using Azure AI Agent
    # =====================================================
    try:
        content = generate_business_impact_content(
            questionnaire_str=state["questionnaire_text"],
            metadata=state["metadata_dict"],
            previous_sections=previous_sections if previous_sections else None
        )
        
        # =====================================================
        # STEP 3: Store in state only (no file saving)
        # =====================================================
        state["business_impact"] = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Business Impact (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": []
        }
        
        print("\n" + "=" * 60)
        print("✅ Business Impact Generated")
        print("=" * 60)
        print(content[:200] + "..." if len(content) > 200 else content)
        print(f"\n💾 Stored in memory (state)")
        
        state["sections_completed"].append(section_name)
        
    except Exception as e:
        print(f"❌ Error generating Business Impact: {e}")
        state["error"] = f"Business Impact generation failed: {str(e)}"
        state["business_impact"] = {
            "content": f"Error generating Business Impact: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Business Impact (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": []
        }
    
    return state
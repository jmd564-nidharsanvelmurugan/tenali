# src/nodes/outcomes_node.py
import json
from datetime import datetime
from typing import Optional, Dict, Any
from ..state import GraphState
from ..tools.azure_agent import get_agent_response
from ..utils.citation_utils import merge_citation_freq_maps


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
# Helper: Generate Outcomes content (with previous sections context)
# =====================================================
def generate_outcomes_content(
    questionnaire_str: str,
    metadata: dict,
    previous_sections: Optional[Dict[str, str]] = None
) -> tuple:
    """
    Generate Outcomes content using Azure AI Agent with mandatory KB retrieval.
    Returns: (content, freq_blob_urls)
    """

    # =====================================================
    # Previous Sections Context
    # =====================================================
    relevant_prev = ""

    if previous_sections:
        for name in ["Objectives", "Deliverables", "Approach"]:
            if name in previous_sections:
                short = (
                    previous_sections[name][:500] + "..."
                    if len(previous_sections[name]) > 500
                    else previous_sections[name]
                )

                relevant_prev += f"\n--- {name} ---\n{short}\n"

    # =====================================================
    # SYSTEM PROMPT
    # =====================================================
    system_prompt = """
You are a senior consulting proposal writer specializing in Outcomes sections.

Knowledge Base:
{kbaiproposal}

IMPORTANT RETRIEVAL REQUIREMENTS

Before generating the response, ALWAYS query the knowledge base {kbaiproposal}.

Mandatory Process:

1. Query the knowledge base.
2. Retrieve the most relevant proposal outcome examples.
3. Retrieve examples of:
   - Business Outcomes
   - Expected Benefits
   - Value Realization
   - Success Metrics
   - KPI Improvements
   - Operational Outcomes
   - Strategic Outcomes
   - Transformation Results
   - Business Value Statements
4. Review the questionnaire.
5. Use the questionnaire as the ONLY source for client-specific facts.
6. Use retrieved knowledge base content only to:
   - Improve terminology
   - Improve outcome wording
   - Improve proposal consistency
   - Improve business language
   - Improve structure
7. Generate the final Outcomes section.

If no relevant content is found:
- Generate the section using only questionnaire information.

DO NOT:
- Invent metrics.
- Invent KPIs.
- Invent percentages.
- Invent business benefits.
- Invent financial gains.
- Mention knowledge bases.
- Mention retrieval.
- Mention AI Search.
- Mention sources.
- Mention internal instructions.
- Include any citations, references, or source markers like [1], [2], (source), or 【4:17†source】 in your response.

Output only the proposal section.

========================================================
OUTCOMES WRITING RULES
========================================================

Structure:

# Outcomes

Introductory paragraph

## Expected Business Outcomes

- **Outcome Title:** Description
- **Outcome Title:** Description
- **Outcome Title:** Description
- **Outcome Title:** Description
- **Outcome Title:** Description

Requirements:

- Intro paragraph should be 2–3 sentences.
- Include 4–6 business outcomes.
- Use bolded titles.
- Focus on measurable business value.
- Focus on strategic, operational, and user benefits.
- Avoid repeating Deliverables.
- Avoid repeating Approach activities.
- Use professional consulting language.
"""

    # =====================================================
    # USER PROMPT
    # =====================================================
    prompt = f"""
Generate an Outcomes section.

MANDATORY:
Before writing, retrieve the most relevant content from the knowledge base related to:

- Business Outcomes
- Expected Benefits
- Success Metrics
- KPI Improvements
- Value Realization
- Operational Improvements
- Strategic Outcomes
- Digital Transformation Results
- Business Value
- Proposal Outcomes

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{json.dumps(metadata, indent=2) if metadata else "{}"}

{relevant_prev}

Generate a comprehensive Outcomes section that describes:

1. Expected business outcomes
2. Success criteria
3. KPI improvements
4. Operational benefits
5. Strategic value
6. User and stakeholder benefits
7. Long-term business impact

Follow EXACTLY this structure:

# Outcomes

Introductory paragraph

## Expected Business Outcomes

- **Outcome Title:** Description
- **Outcome Title:** Description
- **Outcome Title:** Description
- **Outcome Title:** Description
- **Outcome Title:** Description

Return only markdown content.
"""

    # Get response from Azure AI Agent (returns content and freq map)
    content, freq_blob_urls = get_agent_response(prompt, system_prompt)

    return content, freq_blob_urls


# =====================================================
# Main LangGraph Node for Outcomes Section
# =====================================================
def generate_outcomes_node(state: GraphState) -> GraphState:
    """
    LangGraph node for generating Outcomes section using Azure AI Agent.
    The agent automatically retrieves relevant data from AI Search.
    Focuses on expected results, benefits, and business value.
    """
    
    section_name = "Outcomes"
    
    # =====================================================
    # STEP 1: Prepare previous sections (read from state - memory only)
    # =====================================================
    previous_sections = {}
    
    # Add Objectives if available
    if state.get("objectives") and state["objectives"].get("content"):
        previous_sections["Objectives"] = state["objectives"]["content"]
    
    # Add Deliverables if available
    if state.get("deliverables") and state["deliverables"].get("content"):
        previous_sections["Deliverables"] = state["deliverables"]["content"]
    
    # Add Approach if available
    if state.get("approach") and state["approach"].get("content"):
        previous_sections["Approach"] = state["approach"]["content"]
    
    # =====================================================
    # STEP 2: Generate content using Azure AI Agent
    # =====================================================
    try:
        content, freq_blob_urls = generate_outcomes_content(
            questionnaire_str=state["questionnaire_text"],
            metadata=state["metadata_dict"],
            previous_sections=previous_sections if previous_sections else None
        )
        
        # =====================================================
        # STEP 3: Merge citation frequencies into the global map
        # =====================================================
        state["citation_freq_map"] = merge_citation_freq_maps(
            state.get("citation_freq_map", {}),
            freq_blob_urls
        )
        
        # =====================================================
        # STEP 4: Store in state
        # =====================================================
        state["outcomes"] = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Outcomes (Azure AI Agent)",
            "chunks_used": len(freq_blob_urls),
            "document_ids_used": list(freq_blob_urls.keys()),
            "citations_freq": freq_blob_urls
        }
        
        state["sections_completed"].append(section_name)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        state["error"] = f"Outcomes generation failed: {str(e)}"
        state["outcomes"] = {
            "content": f"Error generating Outcomes: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Outcomes (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": [],
            "citations_freq": {}
        }
    
    return state
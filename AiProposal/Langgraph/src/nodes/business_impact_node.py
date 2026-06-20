# src/nodes/business_impact_node.py
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any
from ..state import GraphState
from ..tools.azure_agent import get_agent_response
from ..tools.filtering import ensure_results_folder, save_to_json


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
    """Generate Business Impact content using Azure AI Agent with previous sections context."""
    
    # Only Outcomes as context
    relevant_prev = ""
    if previous_sections and "Outcomes" in previous_sections:
        short = previous_sections["Outcomes"][:500] + "..." if len(previous_sections["Outcomes"]) > 500 else previous_sections["Outcomes"]
        relevant_prev = f"\n--- Outcomes ---\n{short}\n"

    system_prompt = """You are a senior consulting proposal writer specializing in **Business Impact** sections.

Your task is to generate a professional Business Impact section for a proposal.

Rules:
- Start with "# Business Impact" as a level‑1 heading (Markdown).
- List 4-6 bullet points with bolded titles.
- Each bullet must follow: "- **Bolded Title:** Description sentence(s)."
- Focus on financial, operational, and strategic value.
- Quantify benefits where possible (e.g., "reduces manual effort by 50%").
- Use the questionnaire as the ONLY source for metrics and impacts.
- End with a concluding paragraph reinforcing overall value.
- The agent will automatically fetch relevant supporting data from AI Search.
"""

    prompt = f"""
Generate a Business Impact section for a proposal based on the following information:

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{json.dumps(metadata, indent=2) if metadata else "{}"}

{relevant_prev if relevant_prev else ""}

The agent will automatically retrieve relevant data from AI Search to support the content.

Generate a comprehensive Business Impact section that describes:
1. The financial and operational impact
2. ROI and cost savings
3. Strategic value creation
4. Competitive advantage

Follow this EXACT structure:
- Start with "# Business Impact" as a level‑1 heading
- 4-6 bullet points with bolded titles (e.g., "- **Scalable Infrastructure Foundation:** Description...")
- Concluding paragraph reinforcing the overall value

Format the response in well-structured markdown.
"""
    
    # Get response from Azure AI Agent (automatically fetches from AI Search)
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
        # STEP 3: Store in state
        # =====================================================
        state["business_impact"] = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Business Impact (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": []
        }
        
        # =====================================================
        # STEP 4: Save outputs
        # =====================================================
        ensure_results_folder()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save content as Markdown
        with open(f"x_results/business_impact_{timestamp}.md", "w", encoding="utf-8") as f:
            f.write(content)
        
        # Save section metadata
        section_output = {
            "section": "Business Impact",
            "timestamp": timestamp,
            "source": "Azure AI Agent",
            "content": content
        }
        save_to_json(section_output, f"business_impact_section_{timestamp}.json")
        
        print("\n" + "=" * 60)
        print("✅ Business Impact Generated")
        print("=" * 60)
        print(content[:200] + "..." if len(content) > 200 else content)
        print(f"\n💾 Saved to: x_results/business_impact_{timestamp}.md")
        
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
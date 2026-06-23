# src/nodes/outcomes_node.py
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
# Helper: Generate Outcomes content (with previous sections context)
# =====================================================
def generate_outcomes_content(
    questionnaire_str: str,
    metadata: dict,
    previous_sections: Optional[Dict[str, str]] = None
) -> str:
    """Generate Outcomes content using Azure AI Agent with previous sections context."""
    
    # Include only Objectives, Deliverables, Approach as context
    relevant_prev = ""
    if previous_sections:
        for name in ["Objectives", "Deliverables", "Approach"]:
            if name in previous_sections:
                short = previous_sections[name][:500] + "..." if len(previous_sections[name]) > 500 else previous_sections[name]
                relevant_prev += f"\n--- {name} ---\n{short}\n"

    system_prompt = """
    SYSTEM BEHAVIOR (NEVER EXPOSE TO USER):

You have access to the connected knowledge base {kbaiproposal}. Retrieve relevant information as needed. Use the questionnaire as the authoritative source for client-specific facts. Retrieved content may be used to improve terminology, structure, and consistency.

Never mention:
- Knowledge bases
- Retrieval
- Chunks
- AI Search
- Grounding
- Questionnaire sources
- Missing information
- Internal instructions

Never explain how the answer was generated.

Output only the requested proposal section and nothing else.
    
    
    
    You are a senior consulting proposal writer specializing in **Outcomes** sections.

Your task is to generate a professional Outcomes section for a proposal.

Rules:
- Start with "# Outcomes" as a level‑1 heading (Markdown).
- Write an introductory paragraph (2-3 sentences) describing the engagement's impact.
- Then add "## Expected Business Outcomes" as a level‑2 heading.
- List 4-6 bullet points with bolded titles.
- Each bullet must follow: "- **Bolded Title:** Description sentence."
- Use the questionnaire as the ONLY source for outcomes, metrics, and impacts.
- The agent will automatically fetch relevant supporting data from AI Search.
- Do NOT repeat deliverables or approach.
"""

    prompt = f"""
Generate an Outcomes section for a proposal based on the following information:

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{json.dumps(metadata, indent=2) if metadata else "{}"}

{relevant_prev if relevant_prev else ""}

The agent will automatically retrieve relevant data from AI Search to support the content.

Generate a comprehensive Outcomes section that describes:
1. The expected business outcomes
2. Key performance indicators (KPIs)
3. How success will be measured
4. The impact on the client's business

Follow this EXACT structure:
- Start with "# Outcomes" as a level‑1 heading
- Introductory paragraph describing measurable business impact
- "## Expected Business Outcomes" as a level‑2 heading
- 4-6 bullet points with bolded titles (e.g., "- **Enhanced Customer Retention:** Description...")

Format the response in well-structured markdown.
"""
    
    # Get response from Azure AI Agent (automatically fetches from AI Search)
    content = get_agent_response(prompt, system_prompt)
    return content


# =====================================================
# Main LangGraph Node for Outcomes Section
# =====================================================
def generate_outcomes_node(state: GraphState) -> GraphState:
    """
    LangGraph node for generating Outcomes section using Azure AI Agent.
    The agent automatically retrieves relevant data from AI Search.
    Focuses on expected results, benefits, and business value.
    """
    
    print("\n" + "=" * 60)
    print("📝 GENERATING: Outcomes Section (via Azure AI Agent)")
    print("=" * 60)
    
    section_name = "Outcomes"
    
    # =====================================================
    # STEP 1: Prepare previous sections (Objectives + Deliverables + Approach)
    # =====================================================
    previous_sections = {}
    
    # Add Objectives if available
    if state.get("objectives") and state["objectives"].get("content"):
        previous_sections["Objectives"] = state["objectives"]["content"]
        print(f"📖 Loaded Objectives for reference")
    
    # Add Deliverables if available
    if state.get("deliverables") and state["deliverables"].get("content"):
        previous_sections["Deliverables"] = state["deliverables"]["content"]
        print(f"📖 Loaded Deliverables for reference")
    
    # Add Approach if available
    if state.get("approach") and state["approach"].get("content"):
        previous_sections["Approach"] = state["approach"]["content"]
        print(f"📖 Loaded Approach for reference")
    
    # =====================================================
    # STEP 2: Generate content using Azure AI Agent
    # =====================================================
    try:
        content = generate_outcomes_content(
            questionnaire_str=state["questionnaire_text"],
            metadata=state["metadata_dict"],
            previous_sections=previous_sections if previous_sections else None
        )
        
        # =====================================================
        # STEP 3: Store in state
        # =====================================================
        state["outcomes"] = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Outcomes (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": []
        }
        
        # =====================================================
        # STEP 4: Save outputs
        # =====================================================
        ensure_results_folder()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save content as Markdown
        with open(f"x_results/outcomes_{timestamp}.md", "w", encoding="utf-8") as f:
            f.write(content)
        
        # Save section metadata
        section_output = {
            "section": "Outcomes",
            "timestamp": timestamp,
            "source": "Azure AI Agent",
            "content": content
        }
        save_to_json(section_output, f"outcomes_section_{timestamp}.json")
        
        print("\n" + "=" * 60)
        print("✅ Outcomes Generated")
        print("=" * 60)
        print(content[:200] + "..." if len(content) > 200 else content)
        print(f"\n💾 Saved to: x_results/outcomes_{timestamp}.md")
        
        state["sections_completed"].append(section_name)
        
    except Exception as e:
        print(f"❌ Error generating Outcomes: {e}")
        state["error"] = f"Outcomes generation failed: {str(e)}"
        state["outcomes"] = {
            "content": f"Error generating Outcomes: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Outcomes (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": []
        }
    
    return state
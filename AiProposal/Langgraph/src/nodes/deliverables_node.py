# src/nodes/deliverables_node.py
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
        # Try to parse if it's a string
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
# Helper: Generate Deliverables content (with previous sections context)
# =====================================================
def generate_deliverables_content(
    questionnaire_str: str,
    metadata: dict,
    previous_sections: Optional[Dict[str, str]] = None
) -> str:
    """Generate Deliverables content using Azure AI Agent with previous sections context."""
    
    # Format previous sections to avoid repetition
    prev_context = ""
    if previous_sections:
        prev_context = "\nPreviously written sections (do NOT repeat facts already stated):\n"
        for name, content in previous_sections.items():
            short = content[:600] + "..." if len(content) > 600 else content
            prev_context += f"\n--- {name} ---\n{short}\n"

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


    You are a senior consulting proposal writer specializing in **Deliverables** sections.

Your task is to generate a professional Deliverables section for a proposal.

Rules:
- Start with "# Deliverables" as a level‑1 heading (Markdown).
- Then write the opening paragraph customizing the client name.
- Then list the deliverables as **numbered items** (1., 2., 3., etc.).
- For each deliverable, write the name on a new line followed by bullet points.
- Each deliverable should have 2–4 bullet points.
- End with the concluding paragraph.
- Use the questionnaire as the ONLY source for deliverable names and descriptions.
- Do NOT repeat objectives or approach.
- The agent will automatically fetch relevant supporting data from AI Search.
"""

    prompt = f"""
Generate a Deliverables section for a proposal based on the following information:

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{json.dumps(metadata, indent=2) if metadata else "{}"}

{prev_context if prev_context else ""}

The agent will automatically retrieve relevant data from AI Search to support the content.

Generate a comprehensive Deliverables section that lists:
1. All deliverables to be provided
2. A description of each deliverable
3. The format and content of each deliverable
4. When each deliverable will be delivered

Follow this EXACT structure:
- Start with "# Deliverables" as a level‑1 heading
- Opening paragraph: "Throughout the engagement with [Client Name], the following key deliverables and artifacts will be provided to ensure a comprehensive and actionable outcome aligned with the project objectives:"
- Numbered deliverables (1., 2., 3., etc.) with bullet points under each
- Concluding paragraph: "Each deliverable will be iteratively reviewed with [Client Name]'s leadership and technical teams to ensure alignment with business goals and to incorporate feedback promptly. This structured approach guarantees transparency, accountability, and measurable value throughout the engagement lifecycle."

Format the response in well-structured markdown.
"""
    
    # Get response from Azure AI Agent (automatically fetches from AI Search)
    content = get_agent_response(prompt, system_prompt)
    return content


# =====================================================
# Main LangGraph Node for Deliverables Section
# =====================================================
def generate_deliverables_node(state: GraphState) -> GraphState:
    """
    LangGraph node for generating Deliverables section using Azure AI Agent.
    The agent automatically retrieves relevant data from AI Search.
    Focuses on tangible outputs, artifacts, and deliverables.
    """
    
    print("\n" + "=" * 60)
    print("📝 GENERATING: Deliverables Section (via Azure AI Agent)")
    print("=" * 60)
    
    section_name = "Deliverables"
    
    # =====================================================
    # STEP 1: Prepare previous sections (read from state - memory only)
    # =====================================================
    previous_sections = {}
    
    # Add all previous sections if available
    if state.get("business_context") and state["business_context"].get("content"):
        previous_sections["Business Context"] = state["business_context"]["content"]
        print(f"📖 Loaded Business Context for reference")
    
    if state.get("overview") and state["overview"].get("content"):
        previous_sections["Overview"] = state["overview"]["content"]
        print(f"📖 Loaded Overview for reference")
    
    if state.get("understanding") and state["understanding"].get("content"):
        previous_sections["Understanding"] = state["understanding"]["content"]
        print(f"📖 Loaded Understanding for reference")
    
    if state.get("objectives") and state["objectives"].get("content"):
        previous_sections["Objectives"] = state["objectives"]["content"]
        print(f"📖 Loaded Objectives for reference")
    
    # =====================================================
    # STEP 2: Generate content using Azure AI Agent
    # =====================================================
    try:
        content = generate_deliverables_content(
            questionnaire_str=state["questionnaire_text"],
            metadata=state["metadata_dict"],
            previous_sections=previous_sections if previous_sections else None
        )
        
        # =====================================================
        # STEP 3: Store in state only (no file saving)
        # =====================================================
        state["deliverables"] = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Deliverables (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": []
        }
        
        print("\n" + "=" * 60)
        print("✅ Deliverables Generated")
        print("=" * 60)
        print(content[:200] + "..." if len(content) > 200 else content)
        print(f"\n💾 Stored in memory (state)")
        
        state["sections_completed"].append(section_name)
        
    except Exception as e:
        print(f"❌ Error generating Deliverables: {e}")
        state["error"] = f"Deliverables generation failed: {str(e)}"
        state["deliverables"] = {
            "content": f"Error generating Deliverables: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Deliverables (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": []
        }
    
    return state
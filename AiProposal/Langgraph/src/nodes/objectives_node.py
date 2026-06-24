# src/nodes/objectives_node.py
import json
from datetime import datetime
from typing import Optional, Dict, Any
from ..state import GraphState
from ..tools.azure_agent import get_agent_response


# =====================================================
# Helper: Generate Objectives content (with previous sections context)
# =====================================================
def generate_objectives_content(
    questionnaire_str: str,
    metadata: dict,
    previous_sections: Optional[Dict[str, str]] = None
) -> str:
    """Generate Objectives content using Azure AI Agent with previous sections context."""
    
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
    
    
    
    You are a senior consulting proposal writer specializing in **Objectives** sections.

Your task is to generate a professional Objectives section for a proposal.

Rules:
- Start with "# Objectives" as a level‑1 heading (Markdown).
- Then list the objectives as **bullet points** (one bullet per objective).
- Each bullet should be a short, clear statement of a specific goal.
- Use the questionnaire as the ONLY source of client‑specific goals.
- Focus on the **desired future state** – what the client wants to achieve.
- Do NOT repeat problems or context already covered in previous sections.
- Keep language factual, direct, and solution‑oriented but not technical.
- Aim for 4–6 bullet points covering strategic, technical, and operational objectives.
- If the questionnaire does not mention a goal, leave it out.
- The agent will automatically fetch relevant supporting data from AI Search.

CRITICAL: Do NOT mention deliverables, approach, or implementation details.
"""

    prompt = f"""
Generate an Objectives section for a proposal based on the following information:

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{json.dumps(metadata, indent=2) if metadata else "{}"}

{prev_context if prev_context else ""}

The agent will automatically retrieve relevant data from AI Search to support the content.

Generate a comprehensive Objectives section that describes the **desired future state and goals**, including:
- What should the future-state solution achieve?
- What processes should become automated?
- What insights should leadership gain?
- What user experience improvements are expected?
- What business processes need improvement?
- What is the long-term vision for this solution?
- What scalability requirements exist?
- What systems should the future platform integrate with?

Format the response as bullet points in well-structured markdown.
"""
    
    # Get response from Azure AI Agent (automatically fetches from AI Search)
    content = get_agent_response(prompt, system_prompt)
    return content


# =====================================================
# Main LangGraph Node for Objectives Section
# =====================================================
def generate_objectives_node(state: GraphState) -> GraphState:
    """
    LangGraph node for generating Objectives section using Azure AI Agent.
    The agent automatically retrieves relevant data from AI Search.
    Focuses on desired future state, goals, and outcomes.
    """
    
    print("\n" + "=" * 60)
    print("📝 GENERATING: Objectives Section (via Azure AI Agent)")
    print("=" * 60)
    
    section_name = "Objectives"
    
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
    
    # =====================================================
    # STEP 2: Generate content using Azure AI Agent
    # =====================================================
    try:
        content = generate_objectives_content(
            questionnaire_str=state["questionnaire_text"],
            metadata=state["metadata_dict"],
            previous_sections=previous_sections if previous_sections else None
        )
        
        # =====================================================
        # STEP 3: Store in state only (no file saving)
        # =====================================================
        state["objectives"] = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Objectives (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": []
        }
        
        print("\n" + "=" * 60)
        print("✅ Objectives Generated")
        print("=" * 60)
        print(content[:200] + "..." if len(content) > 200 else content)
        print(f"\n💾 Stored in memory (state)")
        
        state["sections_completed"].append(section_name)
        
    except Exception as e:
        print(f"❌ Error generating Objectives: {e}")
        state["error"] = f"Objectives generation failed: {str(e)}"
        state["objectives"] = {
            "content": f"Error generating Objectives: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Objectives (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": []
        }
    
    return state
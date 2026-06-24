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
    """
    Generate Objectives content using Azure AI Agent with mandatory KB retrieval.
    """

    # =====================================================
    # Previous Sections Context
    # =====================================================
    prev_context = ""

    if previous_sections:
        prev_context = "\nPREVIOUS SECTIONS (REFERENCE ONLY)\n"

        for name, content in previous_sections.items():
            short = (
                content[:600] + "..."
                if len(content) > 600
                else content
            )

            prev_context += f"\n--- {name} ---\n{short}\n"

    # =====================================================
    # SYSTEM PROMPT
    # =====================================================
    system_prompt = """
You are a senior consulting proposal writer specializing in Objectives sections.

Knowledge Base:
{kbaiproposal}

IMPORTANT RETRIEVAL REQUIREMENTS

Before generating the response, ALWAYS query the knowledge base {kbaiproposal}.

Mandatory Process:

1. Query the knowledge base.
2. Retrieve the most relevant proposal objectives.
3. Retrieve examples of:
   - Business objectives
   - Strategic objectives
   - Operational objectives
   - Transformation goals
   - Future-state goals
   - Modernization objectives
   - Automation objectives
   - Digital transformation outcomes
4. Review the questionnaire.
5. Use the questionnaire as the ONLY source of client-specific facts.
6. Use retrieved knowledge base content only to:
   - Improve terminology
   - Improve wording
   - Improve proposal consistency
   - Improve business language
   - Improve structure
7. Generate the final Objectives section.

If no relevant content is found:
- Generate the section using only questionnaire information.

DO NOT:
- Invent objectives.
- Invent client requirements.
- Invent integrations.
- Invent future-state goals.
- Mention knowledge bases.
- Mention retrieval.
- Mention AI Search.
- Mention sources.
- Mention internal instructions.

Output only the proposal section.

========================================================
OBJECTIVES WRITING RULES
========================================================

Structure:

# Objectives

- Objective statement
- Objective statement
- Objective statement
- Objective statement
- Objective statement

Requirements:

- 4–6 bullet points.
- One objective per bullet.
- Focus on desired future state.
- Focus on business outcomes.
- Focus on strategic and operational goals.
- Keep statements concise and professional.
- Avoid implementation details.
- Avoid deliverables.
- Avoid technical solution descriptions.
"""

    # =====================================================
    # USER PROMPT
    # =====================================================
    prompt = f"""
Generate an Objectives section.

MANDATORY:
Before writing, retrieve the most relevant content from the knowledge base related to:

- Business Objectives
- Strategic Goals
- Operational Goals
- Transformation Objectives
- Future-State Vision
- Automation Objectives
- Modernization Goals
- Platform Objectives
- Business Outcomes
- Proposal Objectives

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{json.dumps(metadata, indent=2) if metadata else "{}"}

{prev_context}

Generate an Objectives section describing:

1. Desired future state
2. Business goals
3. Operational improvements
4. Leadership objectives
5. User experience goals
6. Automation goals
7. Scalability goals
8. Integration objectives

Follow EXACTLY this structure:

# Objectives

- Objective statement
- Objective statement
- Objective statement
- Objective statement
- Objective statement

Return only markdown content.
"""

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
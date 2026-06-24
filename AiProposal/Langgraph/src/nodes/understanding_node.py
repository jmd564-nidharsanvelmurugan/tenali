# src/nodes/understanding_node.py
import json
from datetime import datetime
from typing import Optional, Dict, Any
from ..state import GraphState
from ..tools.azure_agent import get_agent_response


# =====================================================
# Helper: Generate Understanding content (with previous context)
# =====================================================
def generate_understanding_content(
    questionnaire_str: str,
    metadata: dict,
    previous_sections: Optional[Dict[str, str]] = None
) -> str:
    """
    Generate Understanding content using Azure AI Agent with mandatory KB retrieval.
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
You are a senior consulting proposal writer specializing in Understanding sections.

Knowledge Base:
{kbaiproposal}

IMPORTANT RETRIEVAL REQUIREMENTS

Before generating the response, ALWAYS query the knowledge base {kbaiproposal}.

Mandatory Process:

1. Query the knowledge base.
2. Retrieve the most relevant proposal understanding sections.
3. Retrieve examples of:
   - Business challenges
   - Pain points
   - Operational inefficiencies
   - Current process limitations
   - User requirements
   - Functional requirements
   - Non-functional requirements
   - Security requirements
   - Compliance requirements
   - Integration requirements
4. Review the questionnaire.
5. Use the questionnaire as the ONLY source of client-specific facts.
6. Use retrieved knowledge base content only to:
   - Improve terminology
   - Improve requirement wording
   - Improve proposal consistency
   - Improve business language
   - Improve structure
7. Generate the final Understanding section.

If no relevant content is found:
- Generate the section using only questionnaire information.

DO NOT:
- Invent requirements.
- Invent integrations.
- Invent compliance requirements.
- Invent business challenges.
- Invent user personas.
- Mention knowledge bases.
- Mention retrieval.
- Mention AI Search.
- Mention sources.
- Mention internal instructions.

Output only the proposal section.

========================================================
UNDERSTANDING WRITING RULES
========================================================

Structure:

# Understanding

- Point 1
- Point 2
- Point 3
- Point 4
- Point 5

Requirements:

- 4–8 bullet points.
- One key point per bullet.
- Focus on business problems.
- Focus on pain points.
- Focus on requirements.
- Focus on process inefficiencies.
- Focus on operational challenges.
- Keep statements concise and factual.
- Do NOT describe solutions.
- Do NOT describe deliverables.
- Do NOT describe implementation activities.
- Do NOT describe future state.
"""

    # =====================================================
    # USER PROMPT
    # =====================================================
    prompt = f"""
Generate an Understanding section.

MANDATORY:
Before writing, retrieve the most relevant content from the knowledge base related to:

- Business Challenges
- Business Pain Points
- Operational Inefficiencies
- Current State Limitations
- User Requirements
- Functional Requirements
- Non-Functional Requirements
- Security Requirements
- Compliance Requirements
- Integration Requirements
- Proposal Understanding Sections

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{json.dumps(metadata, indent=2) if metadata else "{}"}

{prev_context}

Generate a comprehensive Understanding section describing:

1. Business problems being addressed
2. Current pain points
3. Operational inefficiencies
4. Process bottlenecks
5. User requirements
6. Functional requirements
7. Security and compliance requirements
8. Required integrations
9. Reporting and visibility challenges

Follow EXACTLY this structure:

# Understanding

- Key point
- Key point
- Key point
- Key point
- Key point

Return only markdown content.
"""

    content = get_agent_response(prompt, system_prompt)

    return content

# =====================================================
# Main LangGraph Node for Understanding Section
# =====================================================
def generate_understanding_node(state: GraphState) -> GraphState:
    """
    LangGraph node for generating Understanding section using Azure AI Agent.
    The agent automatically retrieves relevant data from AI Search.
    Focuses on business problems, pain points, and requirements.
    """
    
    print("\n" + "=" * 60)
    print("📝 GENERATING: Understanding Section (via Azure AI Agent)")
    print("=" * 60)
    
    section_name = "Understanding"
    
    # =====================================================
    # STEP 1: Prepare previous sections (read from state - memory only)
    # =====================================================
    previous_sections = {}
    
    # Add Business Context if available
    if state.get("business_context") and state["business_context"].get("content"):
        previous_sections["Business Context"] = state["business_context"]["content"]
        print(f"📖 Loaded Business Context for reference")
    
    # Add Overview if available
    if state.get("overview") and state["overview"].get("content"):
        previous_sections["Overview"] = state["overview"]["content"]
        print(f"📖 Loaded Overview for reference")
    
    # =====================================================
    # STEP 2: Generate content using Azure AI Agent
    # =====================================================
    try:
        content = generate_understanding_content(
            questionnaire_str=state["questionnaire_text"],
            metadata=state["metadata_dict"],
            previous_sections=previous_sections if previous_sections else None
        )
        
        # =====================================================
        # STEP 3: Store in state only (no file saving)
        # =====================================================
        state["understanding"] = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Understanding (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": []
        }
        
        print("\n" + "=" * 60)
        print("✅ Understanding Generated")
        print("=" * 60)
        print(content[:200] + "..." if len(content) > 200 else content)
        print(f"\n💾 Stored in memory (state)")
        
        state["sections_completed"].append(section_name)
        
    except Exception as e:
        print(f"❌ Error generating Understanding: {e}")
        state["error"] = f"Understanding generation failed: {str(e)}"
        state["understanding"] = {
            "content": f"Error generating Understanding: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Understanding (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": []
        }
    
    return state
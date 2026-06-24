# src/nodes/overview_node.py
import json
from datetime import datetime
from typing import Optional, Dict, Any
from ..state import GraphState
from ..tools.azure_agent import get_agent_response


# =====================================================
# Helper: Generate Overview content (with previous context)
def generate_overview_content(
    questionnaire_str: str,
    metadata: dict,
    previous_sections: Optional[Dict[str, str]] = None
) -> str:
    """
    Generate Overview content using Azure AI Agent with mandatory KB retrieval.
    """

    # =====================================================
    # Previous Sections Context
    # =====================================================
    prev_context = ""

    if previous_sections:
        prev_context = "\nPREVIOUS SECTIONS (REFERENCE ONLY)\n"

        for name, content in previous_sections.items():
            preview = (
                content[:500] + "..."
                if len(content) > 500
                else content
            )

            prev_context += f"\n--- {name} ---\n{preview}\n"

    # =====================================================
    # SYSTEM PROMPT
    # =====================================================
    system_prompt = """
You are a senior consulting proposal writer specializing in Overview sections.

Knowledge Base:
{kbaiproposal}

IMPORTANT RETRIEVAL REQUIREMENTS

Before generating the response, ALWAYS query the knowledge base {kbaiproposal}.

Mandatory Process:

1. Query the knowledge base.
2. Retrieve the most relevant proposal overview examples.
3. Retrieve examples of:
   - Current-state assessments
   - Existing operating environments
   - Existing business processes
   - Current platforms and systems
   - Current reporting environments
   - Existing cloud infrastructure
   - Existing application landscapes
   - Data sources and integrations
4. Review the questionnaire.
5. Use the questionnaire as the ONLY source of client-specific facts.
6. Use retrieved knowledge base content only to:
   - Improve terminology
   - Improve structure
   - Improve proposal consistency
   - Improve business language
   - Improve current-state descriptions
7. Generate the final Overview section.

If no relevant content is found:
- Generate the section using only questionnaire information.

DO NOT:
- Invent systems.
- Invent applications.
- Invent integrations.
- Invent infrastructure.
- Invent business processes.
- Mention knowledge bases.
- Mention retrieval.
- Mention AI Search.
- Mention sources.
- Mention internal instructions.

Output only the proposal section.

========================================================
OVERVIEW WRITING RULES
========================================================

Structure:

# Overview

Paragraph 1

Paragraph 2

Paragraph 3 (optional)

Requirements:

- 2-3 short paragraphs.
- Maximum 250 words.
- Focus ONLY on the current state.
- Describe existing teams, systems, platforms, data sources, and processes.
- Do NOT describe future state.
- Do NOT describe proposed solutions.
- Do NOT describe implementation activities.
- Do NOT repeat Business Context.
- Use professional consulting language.
"""

    # =====================================================
    # USER PROMPT
    # =====================================================
    prompt = f"""
Generate an Overview section.

MANDATORY:
Before writing, retrieve the most relevant content from the knowledge base related to:

- Current State Assessment
- Existing Environment
- Existing Systems
- Existing Platforms
- Existing Infrastructure
- Existing Reporting Environment
- Existing Data Sources
- Existing Integrations
- Operational Landscape
- Proposal Overview Sections

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{json.dumps(metadata, indent=2) if metadata else "{}"}

{prev_context}

Generate an Overview section describing:

1. Current operating environment
2. Existing business processes
3. Current systems and platforms
4. Existing reporting and analytics tools
5. Existing databases and data sources
6. Existing cloud infrastructure
7. Current integrations
8. Current operational workflows

Follow EXACTLY this structure:

# Overview

Paragraph 1

Paragraph 2

Paragraph 3 (optional)

Return only markdown content.
"""

    content = get_agent_response(prompt, system_prompt)

    return content
# =====================================================
# Main LangGraph Node for Overview Section
# =====================================================
def generate_overview_node(state: GraphState) -> GraphState:
    """
    LangGraph node for generating Overview section using Azure AI Agent.
    The agent automatically retrieves relevant data from AI Search.
    Focuses on current state: teams, systems, platforms, data sources.
    """
    
    print("\n" + "=" * 60)
    print("📝 GENERATING: Overview Section (via Azure AI Agent)")
    print("=" * 60)
    
    section_name = "Overview"
    
    # =====================================================
    # STEP 1: Prepare previous sections (read from state - memory only)
    # =====================================================
    previous_sections = {}
    
    # Add Business Context if available
    if state.get("business_context") and state["business_context"].get("content"):
        previous_sections["Business Context"] = state["business_context"]["content"]
        print(f"📖 Loaded Business Context for reference")
    
    # =====================================================
    # STEP 2: Generate content using Azure AI Agent
    # =====================================================
    try:
        content = generate_overview_content(
            questionnaire_str=state["questionnaire_text"],
            metadata=state["metadata_dict"],
            previous_sections=previous_sections if previous_sections else None
        )
        
        # =====================================================
        # STEP 3: Store in state only (no file saving)
        # =====================================================
        state["overview"] = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Overview (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": []
        }
        
        print("\n" + "=" * 60)
        print("✅ Overview Generated")
        print("=" * 60)
        print(content[:200] + "..." if len(content) > 200 else content)
        print(f"\n💾 Stored in memory (state)")
        
        state["sections_completed"].append(section_name)
        
    except Exception as e:
        print(f"❌ Error generating Overview: {e}")
        state["error"] = f"Overview generation failed: {str(e)}"
        state["overview"] = {
            "content": f"Error generating Overview: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Overview (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": []
        }
    
    return state
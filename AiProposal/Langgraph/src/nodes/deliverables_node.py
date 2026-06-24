# src/nodes/deliverables_node.py
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
) -> tuple:
    """
    Generate Deliverables content using Azure AI Agent with mandatory KB retrieval.
    Returns: (content, freq_blob_urls)
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
You are a senior consulting proposal writer specializing in Deliverables sections.

Knowledge Base:
{kbaiproposal}

========================================================
MANDATORY RETRIEVAL PROCESS
========================================================

Before generating the response, ALWAYS query the knowledge base {kbaiproposal}.

Mandatory steps:

1. Query the knowledge base.
2. Retrieve the most relevant proposal deliverables.
3. Retrieve examples of:
   - Deliverables
   - Work products
   - Artifacts
   - Assessment reports
   - Roadmaps
   - Architecture documents
   - Implementation outputs
   - Governance deliverables
   - Operating model deliverables
4. Review the questionnaire.
5. Use the questionnaire as the ONLY source of client-specific facts.
6. Use retrieved content only to:
   - Improve terminology
   - Improve structure
   - Improve consulting language
   - Improve deliverable descriptions
   - Maintain consistency with prior proposals
7. Generate the final Deliverables section.

If no relevant KB content exists:
Generate using questionnaire information only.

========================================================
DO NOT
========================================================

- Invent deliverables not supported by the questionnaire.
- Invent project scope.
- Invent timelines.
- Invent client facts.
- Mention knowledge base retrieval.
- Mention AI Search.
- Mention sources.
- Mention internal instructions.
- Include any citations, references, or source markers like [1], [2], (source), or 【4:17†source】 in your response.

Output ONLY the Deliverables section.

========================================================
DELIVERABLES WRITING RULES
========================================================

Structure:

# Deliverables

Opening paragraph

1. Deliverable Name
   - Bullet
   - Bullet
   - Bullet

2. Deliverable Name
   - Bullet
   - Bullet
   - Bullet

Concluding paragraph

Requirements:

- Professional consulting tone.
- Numbered deliverables.
- 2-4 bullets per deliverable.
- Focus on tangible outputs and artifacts.
- Avoid repeating Objectives or Approach sections.
"""

    # =====================================================
    # USER PROMPT
    # =====================================================
    prompt = f"""
Generate a Deliverables section.

MANDATORY:
Before writing, retrieve the most relevant content from the knowledge base related to:

- Deliverables
- Project Artifacts
- Assessment Deliverables
- Strategy Deliverables
- Roadmap Deliverables
- Architecture Deliverables
- Implementation Deliverables
- Governance Deliverables
- Transformation Deliverables
- Proposal Deliverables

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{json.dumps(metadata, indent=2) if metadata else "{}"}

{prev_context}

Generate a comprehensive Deliverables section that includes:

1. All deliverables to be provided
2. Deliverable descriptions
3. Deliverable contents
4. Expected outputs
5. Tangible artifacts produced during the engagement

Follow EXACTLY this structure:

# Deliverables

Opening paragraph

1. Deliverable Name
   - Bullet point
   - Bullet point
   - Bullet point

2. Deliverable Name
   - Bullet point
   - Bullet point
   - Bullet point

Concluding paragraph

Return only markdown content.
"""

    # Get response from Azure AI Agent (returns content and freq map)
    content, freq_blob_urls = get_agent_response(prompt, system_prompt)

    return content, freq_blob_urls


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
        content, freq_blob_urls = generate_deliverables_content(
            questionnaire_str=state["questionnaire_text"],
            metadata=state["metadata_dict"],
            previous_sections=previous_sections if previous_sections else None
        )
        
        # Debug print to see full content
        print("$" * 1000)
        print(content)
        print("$" * 1000)
        
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
        state["deliverables"] = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Deliverables (Azure AI Agent)",
            "chunks_used": len(freq_blob_urls),
            "document_ids_used": list(freq_blob_urls.keys()),
            "citations_freq": freq_blob_urls
        }
        
        print("\n" + "=" * 60)
        print("✅ Deliverables Generated")
        print("=" * 60)
        print(f"📝 Content length: {len(content)} characters")
        print(f"📊 Citations found in this section: {len(freq_blob_urls)} unique documents")
        print(f"📊 Total unique citations so far: {len(state['citation_freq_map'])}")
        print(content[:200] + "..." if len(content) > 200 else content)
        print(f"\n💾 Stored in memory (state)")
        
        state["sections_completed"].append(section_name)
        
    except Exception as e:
        print(f"❌ Error generating Deliverables: {e}")
        import traceback
        traceback.print_exc()
        
        state["error"] = f"Deliverables generation failed: {str(e)}"
        state["deliverables"] = {
            "content": f"Error generating Deliverables: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Deliverables (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": [],
            "citations_freq": {}
        }
    
    return state
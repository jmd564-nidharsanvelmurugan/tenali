# src/nodes/approach_node.py
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
# Helper: Generate Approach content (with previous sections context)
# =====================================================
def generate_approach_content(
    questionnaire_str: str,
    metadata: dict,
    previous_sections: Optional[Dict[str, str]] = None
) -> tuple:
    """
    Generate Approach content using Azure AI Agent with mandatory KB retrieval.
    Returns: (content, freq_blob_urls)
    """

    # =====================================================
    # Previous Sections Context
    # =====================================================
    relevant_prev = ""

    if previous_sections:
        for name in ["Objectives", "Deliverables"]:
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
You are a senior consulting proposal writer specializing in Approach sections.

Knowledge Base:
{kbaiproposal}

IMPORTANT RETRIEVAL REQUIREMENTS

Before generating the response, ALWAYS query the knowledge base {kbaiproposal}.

Mandatory Process:

1. Query the knowledge base.
2. Retrieve the most relevant proposal approach examples.
3. Retrieve examples of:
   - Delivery methodologies
   - Project approaches
   - Engagement models
   - Transformation roadmaps
   - Implementation phases
   - Workstreams
   - Project activities
   - Assessment methodologies
   - Migration approaches
   - Modernization approaches
4. Review the questionnaire.
5. Use the questionnaire as the ONLY source for:
   - Client-specific facts
   - Timelines
   - Durations
   - Technologies
   - Scope
6. Use retrieved knowledge base content only to:
   - Improve terminology
   - Improve phase descriptions
   - Improve activity wording
   - Improve methodology language
   - Improve proposal consistency
7. Generate the final Approach section.

If no relevant content is found:
- Generate the section using only questionnaire information.

DO NOT:
- Invent timelines.
- Invent project durations.
- Invent technologies.
- Invent deliverables.
- Invent scope items.
- Mention knowledge bases.
- Mention retrieval.
- Mention AI Search.
- Mention sources.
- Mention internal instructions.

Output only the proposal section.

========================================================
APPROACH WRITING RULES
========================================================

Structure:

# Approach

Introductory Paragraph 1

Introductory Paragraph 2

**Phase X: [Phase Name], Duration: X weeks, Timeline: Week Y to Week Z**

**Summary:** One sentence.

**Activities:**
- Activity
- Activity
- Activity
- Activity

Repeat for all phases.

Concluding Paragraph

Requirements:

- Two introductory paragraphs.
- Use a phased implementation structure.
- Each phase must contain:
  * Phase title
  * Duration
  * Timeline
  * Summary
  * Activities
- Include 4–6 activities per phase.
- Use professional consulting language.
- Align phases with objectives and deliverables.
- Avoid repeating objectives verbatim.
- Do NOT include any citations, references, or source markers like [1], [2], (source), or 【4:17†source】 in your response.
"""

    # =====================================================
    # USER PROMPT
    # =====================================================
    prompt = f"""
Generate an Approach section.

MANDATORY:
Before writing, retrieve the most relevant content from the knowledge base related to:

- Proposal Approaches
- Delivery Methodologies
- Project Phases
- Transformation Roadmaps
- Implementation Approaches
- Consulting Methodologies
- Project Activities
- Workstreams
- Engagement Models
- Proposal Approach Sections

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{json.dumps(metadata, indent=2) if metadata else "{}"}

{relevant_prev}

Generate a comprehensive Approach section that describes:

1. Overall methodology
2. Delivery model
3. Project phases
4. Timeline and duration
5. Key activities per phase
6. How deliverables will be produced
7. Governance and review activities

Follow EXACTLY this structure:

# Approach

[Paragraph]

[Paragraph]

**Phase 1: [Phase Name], Duration: X weeks, Timeline: Week Y to Week Z**

**Summary:** Description

**Activities:**
- Activity
- Activity
- Activity
- Activity

**Phase 2: [Phase Name], Duration: X weeks, Timeline: Week Y to Week Z**

**Summary:** Description

**Activities:**
- Activity
- Activity
- Activity
- Activity

Concluding paragraph.

Return only markdown content.
"""

    # Get response from Azure AI Agent (returns content and freq map)
    content, freq_blob_urls = get_agent_response(prompt, system_prompt)

    return content, freq_blob_urls


# =====================================================
# Main LangGraph Node for Approach Section
# =====================================================
def generate_approach_node(state: GraphState) -> GraphState:
    """
    LangGraph node for generating Approach section using Azure AI Agent.
    The agent automatically retrieves relevant data from AI Search.
    Focuses on methodology, phases, activities, and timeline.
    """
    
    print("\n" + "=" * 60)
    print("📝 GENERATING: Approach Section (via Azure AI Agent)")
    print("=" * 60)
    
    section_name = "Approach"
    
    # =====================================================
    # STEP 1: Prepare previous sections (read from state - memory only)
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
    
    # =====================================================
    # STEP 2: Generate content using Azure AI Agent
    # =====================================================
    try:
        content, freq_blob_urls = generate_approach_content(
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
        state["approach"] = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Approach (Azure AI Agent)",
            "chunks_used": len(freq_blob_urls),
            "document_ids_used": list(freq_blob_urls.keys()),
            "citations_freq": freq_blob_urls
        }
        
        print("\n" + "=" * 60)
        print("✅ Approach Generated")
        print("=" * 60)
        print(f"📝 Content length: {len(content)} characters")
        print(f"📊 Citations found in this section: {len(freq_blob_urls)} unique documents")
        print(f"📊 Total unique citations so far: {len(state['citation_freq_map'])}")
        print(content[:200] + "..." if len(content) > 200 else content)
        print(f"\n💾 Stored in memory (state)")
        
        state["sections_completed"].append(section_name)
        
    except Exception as e:
        print(f"❌ Error generating Approach: {e}")
        import traceback
        traceback.print_exc()
        
        state["error"] = f"Approach generation failed: {str(e)}"
        state["approach"] = {
            "content": f"Error generating Approach: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Approach (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": [],
            "citations_freq": {}
        }
    
    return state
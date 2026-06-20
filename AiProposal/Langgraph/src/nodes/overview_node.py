# src/nodes/overview_node.py
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any
from ..state import GraphState
from ..tools.azure_agent import get_agent_response


# =====================================================
# Helper: Generate Overview content (with previous context)
# =====================================================
def generate_overview_content(
    questionnaire_str: str,
    metadata: dict,
    previous_sections: Optional[Dict[str, str]] = None
) -> str:
    """Generate Overview content using Azure AI Agent with previous sections context."""
    
    # Format previous sections (e.g., Business Context)
    prev_context = ""
    if previous_sections:
        prev_context = "\nPreviously written sections (do NOT repeat facts from them):\n"
        for name, content in previous_sections.items():
            # Only include first 500 chars to avoid token overflow
            preview = content[:500] + "..." if len(content) > 500 else content
            prev_context += f"\n--- {name} ---\n{preview}\n"

    system_prompt = """You are a senior consulting proposal writer specializing in **Overview** sections.

Your task is to generate a professional Overview section for a proposal.

Rules:
- Start with "# Overview" as a level‑1 heading (Markdown).
- Write 2–3 short paragraphs (max 250 words total).
- Use the questionnaire as the ONLY source of client‑specific facts.
- Focus on the **current state** of the client's operations.
- Do NOT repeat facts already covered in previous sections.
- Keep language factual, direct, and free of generic industry commentary.
- If the questionnaire does not mention something, leave it out.
- The agent will automatically fetch relevant supporting data from AI Search.

CRITICAL: Do NOT mention problems, solutions, or future state – just describe what exists today.
"""

    prompt = f"""
Generate an Overview section for a proposal based on the following information:

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{json.dumps(metadata, indent=2) if metadata else "{}"}

{prev_context if prev_context else ""}

The agent will automatically retrieve relevant data from AI Search to support the content.

Generate a comprehensive Overview section that describes the **current state** of the client's operations, including:
- Affected teams and processes
- Systems and platforms currently being used
- Reporting and analytics tools that exist today
- Data sources and databases involved
- Existing cloud/platform infrastructure
- Current manual processes (if mentioned)
- Integration challenges (if mentioned)

Format the response in well-structured markdown.
"""
    
    # Get response from Azure AI Agent (automatically fetches from AI Search)
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
    # STEP 1: Prepare previous sections (Business Context)
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
        # STEP 3: Store in state
        # =====================================================
        state["overview"] = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Overview (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": []
        }
        
        # =====================================================
        # STEP 4: Save outputs
        # =====================================================
        from ..tools.filtering import ensure_results_folder, save_to_json
        
        ensure_results_folder()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save content as Markdown
        with open(f"x_results/overview_{timestamp}.md", "w", encoding="utf-8") as f:
            f.write(content)
        
        # Save section metadata
        section_output = {
            "section": "Overview",
            "timestamp": timestamp,
            "source": "Azure AI Agent",
            "content": content
        }
        save_to_json(section_output, f"overview_section_{timestamp}.json")
        
        print("\n" + "=" * 60)
        print("✅ Overview Generated")
        print("=" * 60)
        print(content[:200] + "..." if len(content) > 200 else content)
        print(f"\n💾 Saved to: x_results/overview_{timestamp}.md")
        
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
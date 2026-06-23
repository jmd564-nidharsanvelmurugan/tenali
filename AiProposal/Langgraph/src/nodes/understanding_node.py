# src/nodes/understanding_node.py
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any
from ..state import GraphState
from ..tools.azure_agent import get_agent_response
from ..tools.filtering import ensure_results_folder, save_to_json


# =====================================================
# Helper: Generate Understanding content (with previous context)
# =====================================================
def generate_understanding_content(
    questionnaire_str: str,
    metadata: dict,
    previous_sections: Optional[Dict[str, str]] = None
) -> str:
    """Generate Understanding content using Azure AI Agent with previous sections context."""
    
    # Format previous sections (Business Context and Overview)
    prev_context = ""
    if previous_sections:
        prev_context = "\nPreviously written sections (do NOT repeat facts from them):\n"
        for name, content in previous_sections.items():
            # Show only first 600 chars to keep prompt manageable
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
    
    
    You are a senior consulting proposal writer specializing in **Understanding** sections.

Your task is to generate a professional Understanding section for a proposal.

Rules:
- Start with "# Understanding" as a level‑1 heading (Markdown).
- Then list the key points as **bullet points** (one bullet per point, starting with "- ").
- Use the questionnaire as the ONLY source of client‑specific facts.
- Focus on **business problems, pain points, required capabilities, and inefficiencies**.
- Do NOT repeat facts already covered in previous sections.
- Keep each bullet point short, factual, direct, and free of generic industry commentary.
- Aim for 4–8 bullet points covering the most important points.
- If the questionnaire does not mention something, leave it out.
- The agent will automatically fetch relevant supporting data from AI Search.

CRITICAL: Do NOT mention solutions, deliverables, or future state – just describe the problems and requirements in bullet form.
"""

    prompt = f"""
Generate an Understanding section for a proposal based on the following information:

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{json.dumps(metadata, indent=2) if metadata else "{}"}

{prev_context if prev_context else ""}

The agent will automatically retrieve relevant data from AI Search to support the content.

Generate a comprehensive Understanding section that describes the **business problems, pain points, and requirements**, including:
- What business problem is the client trying to solve?
- What are the current pain points?
- What inefficiencies exist in the current process?
- What capabilities or features are required?
- What workflows should be automated?
- What user roles/personas will use the system?
- What security/compliance requirements exist?
- What integrations are mandatory?

Format the response as bullet points in well-structured markdown.
"""
    
    # Get response from Azure AI Agent (automatically fetches from AI Search)
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
    # STEP 1: Prepare previous sections (Business Context + Overview)
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
        # STEP 3: Store in state
        # =====================================================
        state["understanding"] = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Understanding (Azure AI Agent)",
            "chunks_used": 0,
            "document_ids_used": []
        }
        
        # =====================================================
        # STEP 4: Save outputs
        # =====================================================
        ensure_results_folder()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save content as Markdown
        with open(f"x_results/understanding_{timestamp}.md", "w", encoding="utf-8") as f:
            f.write(content)
        
        # Save section metadata
        section_output = {
            "section": "Understanding",
            "timestamp": timestamp,
            "source": "Azure AI Agent",
            "content": content
        }
        save_to_json(section_output, f"understanding_section_{timestamp}.json")
        
        print("\n" + "=" * 60)
        print("✅ Understanding Generated")
        print("=" * 60)
        print(content[:200] + "..." if len(content) > 200 else content)
        print(f"\n💾 Saved to: x_results/understanding_{timestamp}.md")
        
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
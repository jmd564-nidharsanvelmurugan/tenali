import json
import os
from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate
from typing import Optional, Dict, Any
from ..state import GraphState, SectionContent
from ..tools.llm_setup import get_llm
from ..tools.db_retrieval import (
    get_parent_chunks_by_document_ids,
)
from ..tools.filtering import (
    get_filtered_chunks_by_semantic_query,
    save_to_json,
    ensure_results_folder
)

# =====================================================
# Helper: Generate semantic retrieval query for Deliverables
# =====================================================
def generate_section_query(questionnaire_str: str, metadata: dict, section_name: str) -> str:
    """Generate a semantic retrieval query for Deliverables section focusing on outputs and artifacts."""
    
    llm = get_llm(temperature=0)
    
    prompt = ChatPromptTemplate.from_template("""
You are an expert proposal retrieval specialist.

Extract 3–5 key phrases from the questionnaire that best represent the core
**deliverables, outputs, and tangible artifacts** for the **{section_name}** section.

Questionnaire:
{questionnaire_str}

Metadata:
{metadata}

Rules:
- Return ONLY the concatenated phrase (spaces between words, no quotes).
- Maximum 12 words.
- Focus on concrete deliverables: KPI book, Power BI mock-ups, data model, roadmap.
- Avoid generic words like "documentation" unless specific.

Example for Deliverables:
"KPI Book Power BI mock-ups data model gap assessment roadmap"

Return only the retrieval phrase.
""")
    
    chain = prompt | llm
    response = chain.invoke({
        "questionnaire_str": questionnaire_str,
        "metadata": json.dumps(metadata, indent=2),
        "section_name": section_name
    })
    return response.content.strip()


# =====================================================
# Helper: Generate Deliverables content (with previous sections context)
# =====================================================
def generate_deliverables_content(
    questionnaire_str: str,
    metadata: dict,
    retrieved_chunks: dict,
    previous_sections: Optional[Dict[str, str]] = None
) -> str:
    """Generate Deliverables content using LLM with previous sections context."""
    
    llm = get_llm(temperature=0.3)
    
    # Format retrieved knowledge
    knowledge_text = "NO_KNOWLEDGE_AVAILABLE"
    if retrieved_chunks and "semantic_filtered" in retrieved_chunks:
        chunks = retrieved_chunks["semantic_filtered"]
        if chunks:
            texts = []
            for chunk in chunks[:5]:
                text = chunk.get("text") or chunk.get("actual_text_data") or ""
                if text:
                    if len(text) > 800:
                        text = text[:800] + "..."
                    texts.append(f"• {text}")
            if texts:
                knowledge_text = "\n".join(texts)

    # Format previous sections to avoid repetition
    prev_context = ""
    if previous_sections:
        prev_context = "\nPreviously written sections (do NOT repeat facts already stated):\n"
        for name, content in previous_sections.items():
            short = content[:600] + "..." if len(content) > 600 else content
            prev_context += f"\n--- {name} ---\n{short}\n"

    prompt = ChatPromptTemplate.from_template("""
You are a senior consulting proposal writer specializing in **Deliverables** sections.

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{metadata}

RETRIEVED KNOWLEDGE (supporting evidence):
{knowledge}

{prev_context}

INSTRUCTIONS FOR DELIVERABLES SECTION:

- Start with "# Deliverables" as a level‑1 heading (Markdown).
- Then write this exact opening paragraph (customise client name from questionnaire):
  "Throughout the engagement with [Client Name], the following key deliverables and artifacts will be provided to ensure a comprehensive and actionable outcome aligned with the project objectives:"

- Then list the deliverables as **numbered items** (1., 2., 3., etc.). For each deliverable:
  - Write the deliverable name on a new line (e.g., "1. Due Diligence Assessment Report").
  - Then, on the following lines, write **bullet points** (starting with "- " or "• ") describing its components. Use blank lines between bullet points for readability.
  - Each deliverable should have 2–4 bullet points.

- After the last deliverable, write a **concluding paragraph** (like the example): 
  "Each deliverable will be iteratively reviewed with [Client Name]'s leadership and technical teams to ensure alignment with business goals and to incorporate feedback promptly. This structured approach guarantees transparency, accountability, and measurable value throughout the engagement lifecycle."

- Use the questionnaire as the ONLY source for deliverable names and descriptions.
- Do NOT repeat objectives or approach.

CRITICAL: Follow the exact formatting: numbered deliverables, bullet points under each, and the final paragraph.

CONTENT:
""")

    chain = prompt | llm
    response = chain.invoke({
        "questionnaire_str": questionnaire_str,
        "metadata": json.dumps(metadata, indent=2),
        "knowledge": knowledge_text,
        "prev_context": prev_context
    })
    return response.content.strip()


# =====================================================
# Helper: Extract client name from questionnaire
# =====================================================
def extract_client_name(questionnaire: dict) -> str:
    """Extract client name from questionnaire."""
    # Try common field names
    for key in ["company_name", "client_name", "organization", "company"]:
        if key in questionnaire and questionnaire[key]:
            return questionnaire[key]
    return "Client"  # Fallback


# =====================================================
# Main LangGraph Node for Deliverables Section
# =====================================================
def generate_deliverables_node(state: GraphState) -> GraphState:
    """
    LangGraph node for generating Deliverables section.
    Focuses on tangible outputs, artifacts, and deliverables.
    """
    
    print("\n" + "=" * 60)
    print("📝 GENERATING: Deliverables Section")
    print("=" * 60)
    
    section_name = "Deliverables"
    
    # =====================================================
    # STEP 1: Get document IDs from top proposals
    # =====================================================
    document_ids = [p["document_id"] for p in state["top_proposals"]]
    print(f"📄 Using {len(document_ids)} proposals: {document_ids}")
    
    # =====================================================
    # STEP 2: Fetch parent chunks for this section
    # =====================================================
    parent_chunks = get_parent_chunks_by_document_ids(document_ids, section_name)
    print(f"📚 Found {len(parent_chunks)} parent chunks")
    
    # =====================================================
    # STEP 3: Collect all child chunk IDs
    # =====================================================
    all_child_ids = []
    for parent in parent_chunks:
        for child_ref in parent.get("child_chunks", []):
            if child_ref.get("id"):
                all_child_ids.append(child_ref["id"])
    all_child_ids = list(set(all_child_ids))
    print(f"🧩 Collected {len(all_child_ids)} child chunks")
    
    # =====================================================
    # STEP 4: Prepare previous sections (Business Context + Overview + Understanding + Objectives)
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
    # STEP 5: Generate section query (focus on deliverables/outputs)
    # =====================================================
    section_query = generate_section_query(
        state["questionnaire_text"],
        state["metadata_dict"],
        section_name
    )
    print(f"🔍 Generated query: '{section_query}'")
    
    # =====================================================
    # STEP 6: Retrieve relevant chunks
    # =====================================================
    filtered_results = get_filtered_chunks_by_semantic_query(
        child_ids=all_child_ids,
        query=section_query,
        top_k=10
    )
    
    chunks_used = len(filtered_results.get("semantic_filtered", []))
    print(f"✅ Retrieved {chunks_used} relevant chunks")
    
    # =====================================================
    # STEP 7: Generate content (with previous sections as context)
    # =====================================================
    content = generate_deliverables_content(
        questionnaire_str=state["questionnaire_text"],
        metadata=state["metadata_dict"],
        retrieved_chunks=filtered_results,
        previous_sections=previous_sections if previous_sections else None
    )
    
    # =====================================================
    # STEP 8: Store in state
    # =====================================================
    state["deliverables"] = {
        "content": content,
        "timestamp": datetime.now().isoformat(),
        "retrieval_query": section_query,
        "chunks_used": chunks_used,
        "document_ids_used": document_ids
    }
    
    # =====================================================
    # STEP 9: Save outputs
    # =====================================================
    ensure_results_folder()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save content as Markdown
    with open(f"x_results/deliverables_{timestamp}.md", "w", encoding="utf-8") as f:
        f.write(content)
    
    # Save chunks JSON
    save_to_json(filtered_results, f"deliverables_chunks_{timestamp}.json")
    
    # Save section metadata
    section_output = {
        "section": "Deliverables",
        "timestamp": timestamp,
        "retrieval_query": section_query,
        "chunks_used": chunks_used,
        "document_ids": document_ids,
        "content": content
    }
    save_to_json(section_output, f"deliverables_section_{timestamp}.json")
    
    print("\n" + "=" * 60)
    print("✅ Deliverables Generated")
    print("=" * 60)
    print(content[:200] + "..." if len(content) > 200 else content)
    print(f"\n💾 Saved to: x_results/deliverables_{timestamp}.md")
    
    state["sections_completed"].append(section_name)
    
    return state
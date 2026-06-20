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
# Helper: Generate semantic retrieval query for Understanding
# =====================================================
def generate_section_query(questionnaire_str: str, metadata: dict, section_name: str) -> str:
    """Generate a semantic retrieval query for Understanding section focusing on problems and pain points."""
    
    llm = get_llm(temperature=0)
    
    prompt = ChatPromptTemplate.from_template("""
You are an expert proposal retrieval specialist.

Extract 3–5 key phrases from the questionnaire that best represent the core
**business problems, pain points, and challenges** for the **{section_name}** section.

Questionnaire:
{questionnaire_str}

Metadata:
{metadata}

Rules:
- Return ONLY the concatenated phrase (spaces between words, no quotes).
- Maximum 12 words.
- Focus on concrete: business problems, pain points, required capabilities, inefficiencies.
- Avoid generic words like "issues" unless specific.

Example for Understanding:
"pipeline reporting granularity integrated CAC insights automated ingestion"

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
# Helper: Generate Understanding content (with previous context)
# =====================================================
def generate_understanding_content(
    questionnaire_str: str,
    metadata: dict,
    retrieved_chunks: dict,
    previous_sections: Optional[Dict[str, str]] = None
) -> str:
    """Generate Understanding content using LLM with previous sections context."""
    
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

    # Format previous sections (Business Context and Overview)
    prev_context = ""
    if previous_sections:
        prev_context = "\nPreviously written sections (do NOT repeat facts from them):\n"
        for name, content in previous_sections.items():
            # Show only first 600 chars to keep prompt manageable
            short = content[:600] + "..." if len(content) > 600 else content
            prev_context += f"\n--- {name} ---\n{short}\n"

    prompt = ChatPromptTemplate.from_template("""
You are a senior consulting proposal writer specializing in **Understanding** sections.

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{metadata}

RETRIEVED KNOWLEDGE (supporting evidence):
{knowledge}

{prev_context}

INSTRUCTIONS FOR UNDERSTANDING SECTION:
- Start with "# Understanding" as a level‑1 heading (Markdown).
- Then list the key points as **bullet points** (one bullet per point, starting with "- ").
- Use the questionnaire as the ONLY source of client‑specific facts.
- Focus on **business problems, pain points, required capabilities, and inefficiencies**, including:
  * What business problem is the client trying to solve?
  * What are the current pain points?
  * What inefficiencies exist in the current process?
  * What capabilities or features are required?
  * What workflows should be automated?
  * What user roles/personas will use the system?
  * What security/compliance requirements exist?
  * What integrations are mandatory?
- Do NOT repeat facts already covered in previous sections (Business Context or Overview).
- Keep each bullet point short, factual, direct, and free of generic industry commentary.
- Aim for 4–8 bullet points covering the most important points.
- If the questionnaire does not mention something, leave it out.

CRITICAL: Do NOT mention solutions, deliverables, or future state – just describe the problems and requirements in bullet form.

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
# Main LangGraph Node for Understanding Section
# =====================================================
def generate_understanding_node(state: GraphState) -> GraphState:
    """
    LangGraph node for generating Understanding section.
    Focuses on business problems, pain points, and requirements.
    """
    
    print("\n" + "=" * 60)
    print("📝 GENERATING: Understanding Section")
    print("=" * 60)
    
    section_name = "Understanding"
    
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
    # STEP 4: Prepare previous sections (Business Context + Overview)
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
    # STEP 5: Generate section query (focus on problems/pain points)
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
    content = generate_understanding_content(
        questionnaire_str=state["questionnaire_text"],
        metadata=state["metadata_dict"],
        retrieved_chunks=filtered_results,
        previous_sections=previous_sections if previous_sections else None
    )
    
    # =====================================================
    # STEP 8: Store in state
    # =====================================================
    state["understanding"] = {
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
    with open(f"x_results/understanding_{timestamp}.md", "w", encoding="utf-8") as f:
        f.write(content)
    
    # Save chunks JSON
    save_to_json(filtered_results, f"understanding_chunks_{timestamp}.json")
    
    # Save section metadata
    section_output = {
        "section": "Understanding",
        "timestamp": timestamp,
        "retrieval_query": section_query,
        "chunks_used": chunks_used,
        "document_ids": document_ids,
        "content": content
    }
    save_to_json(section_output, f"understanding_section_{timestamp}.json")
    
    print("\n" + "=" * 60)
    print("✅ Understanding Generated")
    print("=" * 60)
    print(content[:200] + "..." if len(content) > 200 else content)
    print(f"\n💾 Saved to: x_results/understanding_{timestamp}.md")
    
    state["sections_completed"].append(section_name)
    
    return state
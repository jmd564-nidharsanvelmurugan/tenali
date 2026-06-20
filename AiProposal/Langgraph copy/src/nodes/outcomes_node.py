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
# Helper: Generate semantic retrieval query for Outcomes
# =====================================================
def generate_section_query(questionnaire_str: str, metadata: dict, section_name: str) -> str:
    """Generate a semantic retrieval query for Outcomes section focusing on expected results and value."""
    
    llm = get_llm(temperature=0)
    
    prompt = ChatPromptTemplate.from_template("""
You are an expert proposal retrieval specialist.

Extract 3–5 key phrases from the questionnaire that best represent the core
**expected results, benefits, and value** for the **{section_name}** section.

Questionnaire:
{questionnaire_str}

Metadata:
{metadata}

Rules:
- Return ONLY the concatenated phrase (spaces between words, no quotes).
- Maximum 12 words.
- Focus on concrete outcomes: faster decisions, lower costs, better visibility.
- Avoid generic words like "improve" unless specific.

Example for Outcomes:
"automated reporting 50 percent manual effort reduction l2a conversion lift"

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
# Helper: Generate Outcomes content (with previous sections context)
# =====================================================
def generate_outcomes_content(
    questionnaire_str: str,
    metadata: dict,
    retrieved_chunks: dict,
    previous_sections: Optional[Dict[str, str]] = None
) -> str:
    """Generate Outcomes content using LLM with previous sections context."""
    
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

    # Include only Objectives, Deliverables, Approach as context
    relevant_prev = ""
    if previous_sections:
        for name in ["Objectives", "Deliverables", "Approach"]:
            if name in previous_sections:
                short = previous_sections[name][:500] + "..." if len(previous_sections[name]) > 500 else previous_sections[name]
                relevant_prev += f"\n--- {name} ---\n{short}\n"

    prompt = ChatPromptTemplate.from_template("""
You are a senior consulting proposal writer specializing in **Outcomes** sections.

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{metadata}

RETRIEVED KNOWLEDGE (supporting evidence):
{knowledge}

{prev_context}

INSTRUCTIONS FOR OUTCOMES SECTION:

- Start with "# Outcomes" as a level‑1 heading (Markdown).

- Write an **introductory paragraph** (2–3 sentences) that:
  * States the engagement will deliver measurable business impact and strategic value.
  * Mentions the specific project focus (e.g., due diligence, churn reduction, Gen AI).
  * Aligns with the client's business model and stakeholder objectives (PE fund, etc.).

- Then add "## Expected Business Outcomes" as a level‑2 heading.

- Under that, list **4–6 bullet points** (starting with "- "). Each bullet point must follow this exact pattern:
  * **Bolded title** (using Markdown `**`) followed by a colon `:` and a space, then a sentence or two describing the outcome.
  * Example: `- **Enhanced Customer Retention and Reduced Churn:** Implementation of advanced Gen AI models will provide predictive insights to identify at-risk customers proactively, enabling targeted interventions that reduce churn rates and improve lifetime customer value.`
  * Do NOT break the description into multiple lines or separate paragraphs.

- Use the questionnaire as the ONLY source for outcomes, metrics, and impacts. Do NOT repeat deliverables or approach.

- Keep language factual, direct, and value‑oriented. Avoid generic phrases.

CRITICAL: Follow the exact formatting – headings, bolded titles with colons, and single‑line bullet descriptions.

CONTENT:
""")

    chain = prompt | llm
    response = chain.invoke({
        "questionnaire_str": questionnaire_str,
        "metadata": json.dumps(metadata, indent=2),
        "knowledge": knowledge_text,
        "prev_context": relevant_prev
    })
    return response.content.strip()


# =====================================================
# Helper: Extract client name from questionnaire
# =====================================================
def extract_client_name(questionnaire: dict) -> str:
    """Extract client name from questionnaire."""
    for key in ["company_name", "client_name", "organization", "company"]:
        if key in questionnaire and questionnaire[key]:
            return questionnaire[key]
    return "Client"


# =====================================================
# Main LangGraph Node for Outcomes Section
# =====================================================
def generate_outcomes_node(state: GraphState) -> GraphState:
    """
    LangGraph node for generating Outcomes section.
    Focuses on expected results, benefits, and business value.
    """
    
    print("\n" + "=" * 60)
    print("📝 GENERATING: Outcomes Section")
    print("=" * 60)
    
    section_name = "Outcomes"
    
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
    # STEP 4: Prepare previous sections (Objectives + Deliverables + Approach)
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
    
    # Add Approach if available
    if state.get("approach") and state["approach"].get("content"):
        previous_sections["Approach"] = state["approach"]["content"]
        print(f"📖 Loaded Approach for reference")
    
    # =====================================================
    # STEP 5: Generate section query (focus on outcomes/value)
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
    content = generate_outcomes_content(
        questionnaire_str=state["questionnaire_text"],
        metadata=state["metadata_dict"],
        retrieved_chunks=filtered_results,
        previous_sections=previous_sections if previous_sections else None
    )
    
    # =====================================================
    # STEP 8: Store in state
    # =====================================================
    state["outcomes"] = {
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
    with open(f"x_results/outcomes_{timestamp}.md", "w", encoding="utf-8") as f:
        f.write(content)
    
    # Save chunks JSON
    save_to_json(filtered_results, f"outcomes_chunks_{timestamp}.json")
    
    # Save section metadata
    section_output = {
        "section": "Outcomes",
        "timestamp": timestamp,
        "retrieval_query": section_query,
        "chunks_used": chunks_used,
        "document_ids": document_ids,
        "content": content
    }
    save_to_json(section_output, f"outcomes_section_{timestamp}.json")
    
    print("\n" + "=" * 60)
    print("✅ Outcomes Generated")
    print("=" * 60)
    print(content[:200] + "..." if len(content) > 200 else content)
    print(f"\n💾 Saved to: x_results/outcomes_{timestamp}.md")
    
    state["sections_completed"].append(section_name)
    
    return state
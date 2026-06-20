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
# Helper: Generate semantic retrieval query for Business Impact
# =====================================================
def generate_section_query(questionnaire_str: str, metadata: dict, section_name: str) -> str:
    """Generate a semantic retrieval query for Business Impact section focusing on financial and strategic value."""
    
    llm = get_llm(temperature=0)
    
    prompt = ChatPromptTemplate.from_template("""
You are an expert proposal retrieval specialist.

Extract 3–5 key phrases from the questionnaire that best represent the core
**financial and strategic impact** for the **{section_name}** section.

Questionnaire:
{questionnaire_str}

Metadata:
{metadata}

Rules:
- Return ONLY the concatenated phrase (spaces between words, no quotes).
- Maximum 12 words.
- Focus on financial metrics: cost reduction, ROI, efficiency gains, scalability.
- Avoid generic words.

Example for Business Impact:
"CAC reduction 10 percent marketing ROI improvement scalability"

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
# Helper: Generate Business Impact content (with previous sections context)
# =====================================================
def generate_business_impact_content(
    questionnaire_str: str,
    metadata: dict,
    retrieved_chunks: dict,
    previous_sections: Optional[Dict[str, str]] = None
) -> str:
    """Generate Business Impact content using LLM with previous sections context."""
    
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

    # Only Outcomes as context
    relevant_prev = ""
    if previous_sections and "Outcomes" in previous_sections:
        short = previous_sections["Outcomes"][:500] + "..." if len(previous_sections["Outcomes"]) > 500 else previous_sections["Outcomes"]
        relevant_prev = f"\n--- Outcomes ---\n{short}\n"

    prompt = ChatPromptTemplate.from_template("""
You are a senior consulting proposal writer specializing in **Business Impact** sections.

CLIENT QUESTIONNAIRE:
{questionnaire_str}

METADATA:
{metadata}

RETRIEVED KNOWLEDGE (supporting evidence):
{knowledge}

{prev_context}

INSTRUCTIONS FOR BUSINESS IMPACT SECTION:

- Start with "# Business Impact" as a level‑1 heading (Markdown).

- Then list **4–6 bullet points** (starting with "- "). Each bullet point must follow this exact pattern:
  * **Bolded title** (using Markdown `**`) followed by a colon `:` and a space, then 1–2 sentences describing the impact.
  * Example: `- **Scalable Infrastructure Foundation:** Creation of a flexible data platform tailored to [Client Name]'s environment, enabling future expansion without dependency on legacy systems.`

- Focus on **financial, operational, and strategic value** – quantify benefits where possible (e.g., "reduces manual effort by 50%", "lowers CAC by 10–15%").
- Use the questionnaire as the ONLY source for metrics and impacts. Do NOT repeat outcomes, deliverables, or approach.

- After the bullet points, write a **concluding paragraph** that reinforces the overall value of the engagement, leading to long‑term growth and value creation.
  * Example: "By delivering these outcomes, this engagement will enable [Client Name] to transform its [core process] approach, underpinning long‑term growth and value creation in a competitive [industry/sector] marketplace."

CRITICAL: Follow the exact formatting – bolded titles with colons, single‑line bullet descriptions, and the concluding paragraph. No extra subheadings unless explicitly required.

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
# Main LangGraph Node for Business Impact Section
# =====================================================
def generate_business_impact_node(state: GraphState) -> GraphState:
    """
    LangGraph node for generating Business Impact section.
    Focuses on financial, operational, and strategic value.
    """
    
    print("\n" + "=" * 60)
    print("📝 GENERATING: Business Impact Section")
    print("=" * 60)
    
    section_name = "Business Impact"
    
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
    # STEP 4: Prepare previous sections (Outcomes only)
    # =====================================================
    previous_sections = {}
    
    # Add Outcomes if available
    if state.get("outcomes") and state["outcomes"].get("content"):
        previous_sections["Outcomes"] = state["outcomes"]["content"]
        print(f"📖 Loaded Outcomes for reference")
    
    # =====================================================
    # STEP 5: Generate section query (focus on financial/strategic impact)
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
    # STEP 7: Generate content (with Outcomes as context)
    # =====================================================
    content = generate_business_impact_content(
        questionnaire_str=state["questionnaire_text"],
        metadata=state["metadata_dict"],
        retrieved_chunks=filtered_results,
        previous_sections=previous_sections if previous_sections else None
    )
    
    # =====================================================
    # STEP 8: Store in state
    # =====================================================
    state["business_impact"] = {
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
    with open(f"x_results/business_impact_{timestamp}.md", "w", encoding="utf-8") as f:
        f.write(content)
    
    # Save chunks JSON
    save_to_json(filtered_results, f"business_impact_chunks_{timestamp}.json")
    
    # Save section metadata
    section_output = {
        "section": "Business Impact",
        "timestamp": timestamp,
        "retrieval_query": section_query,
        "chunks_used": chunks_used,
        "document_ids": document_ids,
        "content": content
    }
    save_to_json(section_output, f"business_impact_section_{timestamp}.json")
    
    print("\n" + "=" * 60)
    print("✅ Business Impact Generated")
    print("=" * 60)
    print(content[:200] + "..." if len(content) > 200 else content)
    print(f"\n💾 Saved to: x_results/business_impact_{timestamp}.md")
    
    state["sections_completed"].append(section_name)
    
    return state
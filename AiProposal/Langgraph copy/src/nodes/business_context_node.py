import json
import os
from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate
from ..state import GraphState, SectionContent
from ..tools.llm_setup import get_llm
from ..tools.db_retrieval import (
    get_top_matching_proposals,
    get_parent_chunks_by_document_ids,
    get_child_chunks_by_ids
)
from ..tools.filtering import (
    get_filtered_chunks_by_semantic_query,
    save_to_json,
    ensure_results_folder
)

def generate_section_query(questionnaire: str, metadata: dict, section_name: str) -> str:
    """Generate a semantic retrieval query for the section."""
    llm = get_llm(temperature=0)
    
    prompt = ChatPromptTemplate.from_template("""
You are an expert proposal retrieval specialist.

Extract 3–5 key phrases from the questionnaire that best represent the core
context, industry, and business drivers for the **{section_name}** section.

Questionnaire:
{questionnaire}

Metadata:
{metadata}

Rules:
- Return ONLY the concatenated phrase (spaces between words, no quotes).
- Maximum 12 words.
- Focus on concrete business context: industry, products, strategic drivers.
- Avoid generic words like "improve", "enhance", "data" unless specific.

Example for Business Context:
"wealth management financial advisory L2A pipeline reporting transformation"

Return only the retrieval phrase.
""")
    
    chain = prompt | llm
    response = chain.invoke({
        "questionnaire": questionnaire,
        "metadata": json.dumps(metadata, indent=2),
        "section_name": section_name
    })
    return response.content.strip()

def generate_business_context_content(
    questionnaire: str,
    metadata: dict,
    retrieved_chunks: dict
) -> str:
    """Generate Business Context content using LLM."""
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

    prompt = ChatPromptTemplate.from_template("""
You are a senior consulting proposal writer specializing in **Business Context** sections.

CLIENT QUESTIONNAIRE:
{questionnaire}

METADATA:
{metadata}

RETRIEVED KNOWLEDGE (supporting evidence):
{knowledge}

INSTRUCTIONS FOR BUSINESS CONTEXT SECTION:
- Start with "# Business Context" as a level‑1 heading (Markdown).
- Write 2–3 short paragraphs (max 250 words).
- Use the questionnaire as the ONLY source of client‑specific facts.
- Retrieved knowledge is for supporting evidence only – do not copy company names from it.
- Keep language professional, direct, and free of generic industry commentary.
- Do NOT use bullet points or subsection headings.
- Focus on: who the client is, what they do, what they want to improve.
- If the questionnaire does not mention something, leave it out.

CRITICAL: If retrieved knowledge is "NO_KNOWLEDGE_AVAILABLE", still write the section using only the questionnaire.

CONTENT:
""")

    chain = prompt | llm
    response = chain.invoke({
        "questionnaire": questionnaire,
        "metadata": json.dumps(metadata, indent=2),
        "knowledge": knowledge_text
    })
    return response.content.strip()

def generate_business_context_node(state: GraphState) -> GraphState:
    """
    LangGraph node for generating Business Context section.
    """
    print("\n" + "=" * 60)
    print("📝 GENERATING: Business Context Section")
    print("=" * 60)
    
    section_name = "Business Context"
    
    # Step 1: Get document IDs from top proposals
    document_ids = [p["document_id"] for p in state["top_proposals"]]
    print(f"📄 Using {len(document_ids)} proposals: {document_ids}")
    
    # Step 2: Fetch parent chunks for this section
    parent_chunks = get_parent_chunks_by_document_ids(document_ids, section_name)
    print(f"📚 Found {len(parent_chunks)} parent chunks")
    
    # Step 3: Collect all child chunk IDs
    all_child_ids = []
    for parent in parent_chunks:
        for child_ref in parent.get("child_chunks", []):
            if child_ref.get("id"):
                all_child_ids.append(child_ref["id"])
    all_child_ids = list(set(all_child_ids))
    print(f"🧩 Collected {len(all_child_ids)} child chunks")
    
    # Step 4: Generate section query
    section_query = generate_section_query(
        state["questionnaire_text"],
        state["metadata_dict"],
        section_name
    )
    print(f"🔍 Generated query: '{section_query}'")
    
    # Step 5: Retrieve relevant chunks
    filtered_results = get_filtered_chunks_by_semantic_query(
        child_ids=all_child_ids,
        query=section_query,
        top_k=10
    )
    
    chunks_used = len(filtered_results.get("semantic_filtered", []))
    print(f"✅ Retrieved {chunks_used} relevant chunks")
    
    # Step 6: Generate content
    content = generate_business_context_content(
        questionnaire=state["questionnaire_text"],
        metadata=state["metadata_dict"],
        retrieved_chunks=filtered_results
    )
    
    # Step 7: Store in state
    state["business_context"] = {
        "content": content,
        "timestamp": datetime.now().isoformat(),
        "retrieval_query": section_query,
        "chunks_used": chunks_used,
        "document_ids_used": document_ids
    }
    
    # Step 8: Save intermediate output
    ensure_results_folder()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save section content
    with open(f"x_results/business_context_{timestamp}.md", "w", encoding="utf-8") as f:
        f.write(content)
    
    # Save retrieval results
    save_to_json(filtered_results, f"business_context_chunks_{timestamp}.json")
    
    print("\n" + "=" * 60)
    print("✅ Business Context Generated")
    print("=" * 60)
    print(content[:200] + "..." if len(content) > 200 else content)
    
    state["sections_completed"].append(section_name)
    
    return state
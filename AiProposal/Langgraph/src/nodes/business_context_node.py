# src/nodes/business_context_node.py
import json
import re
from datetime import datetime
from ..state import GraphState
from ..tools.azure_agent import get_agent_response
from ..utils.citation_utils import merge_citation_freq_maps


def generate_business_context_node(state: GraphState) -> GraphState:
    """
    Generate Business Context section using Azure AI Agent.
    The agent automatically retrieves relevant data from AI Search.
    """
    
    questionnaire_text = state.get("questionnaire_text", "")
    
    system_prompt = """
You are a senior consulting proposal writer specializing in Business Context sections.

Knowledge Base:
{kbaiproposal}

Your task is to generate a professional Business Context section for a proposal.

Retrieval Requirements:

* Before writing, ALWAYS query the knowledge base {kbaiproposal}.
* Retrieve the most relevant chunks and use them as supporting context.
* The questionnaire is the ONLY source of client-specific facts.
* Use the retrieved knowledge base chunks only to enrich wording, provide context, and maintain consistency with previous proposals and domain terminology.
* Do NOT invent information not present in either the questionnaire or retrieved chunks.
* If no relevant chunks are retrieved, rely solely on the questionnaire.
* Ground every statement in either the questionnaire or retrieved knowledge base content.

Writing Rules:

* Start with "# Business Context" as a level-1 heading.
* Write 2–3 short paragraphs (maximum 250 words).
* Use professional, direct language.
* Do not use bullet points or subsection headings.
* Focus on:
  * Who the client is.
  * What they do.
  * What they want to improve.
* Avoid generic industry commentary.
* If the questionnaire does not mention something, leave it out.
* Do NOT include any citations, references, or source markers like [1], [2], (source), or 【4:17†source】 in your response.

Process:

1. Query {kbaiproposal}.
2. Retrieve the most relevant chunks.
3. Read the questionnaire.
4. Use the questionnaire for client-specific facts.
5. Use retrieved chunks for supporting context and terminology.
6. Generate the Business Context section.
"""

    prompt = f"""
Generate a Business Context section for a proposal based on the following questionnaire information:

{questionnaire_text}

The agent will automatically retrieve relevant data from AI Search to support the content.

Generate a comprehensive Business Context section covering:
1. The client's company background and industry
2. The business problem they are trying to solve
3. The current situation and challenges
4. The strategic importance of this initiative

Format the response in well-structured markdown.
"""
    
    try:
        # Get response from Azure AI Agent - now returns (content, freq_blob_urls)
        content, freq_blob_urls = get_agent_response(prompt, system_prompt)
        
        
        
        # =====================================================
        # Merge citation frequencies into the global map
        # =====================================================
        state["citation_freq_map"] = merge_citation_freq_maps(
            state.get("citation_freq_map", {}),
            freq_blob_urls
        )
        
        # =====================================================
        # Store the generated content with citation info
        # =====================================================
        state["business_context"] = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Business Context",
            "chunks_used": len(freq_blob_urls),
            "document_ids_used": list(freq_blob_urls.keys()),
            "citations_freq": freq_blob_urls
        }
        
        state["sections_completed"].append("Business Context")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        state["error"] = f"Business Context generation failed: {str(e)}"
        state["business_context"] = {
            "content": f"Error generating Business Context: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "retrieval_query": "Business Context",
            "chunks_used": 0,
            "document_ids_used": [],
            "citations_freq": {}
        }
    
    return state
import logging
from datetime import datetime
from .src.graph import run_proposal_generation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_proposal_langgraph(questionnaire: str, user_prompt: str = ""):
    """
    Generate a proposal document based on questionnaire data and user prompt.
    
    Args:
        questionnaire (str): The questionnaire data in text format
        user_prompt (str, optional): Additional user instructions. Defaults to "".
    
    Returns:
        dict: Contains proposal_text, sections, and citations matching the production format
    """
    try:
        logger.info("=" * 80)
        logger.info("PROPOSAL GENERATION STARTED")
        logger.info("=" * 80)

        logger.info("QUESTIONNAIRE:")
        logger.info(questionnaire[:500] + "..." if len(questionnaire) > 500 else questionnaire)

        logger.info("-" * 80)

        logger.info("USER PROMPT:")
        logger.info(user_prompt)

        # Prepare the questionnaire data
        questionnaire_data = {
            "questionnaire": questionnaire,
            "user_prompt": user_prompt
        }

        # Run the proposal generation
        final_state = run_proposal_generation(questionnaire_data)

        logger.info("=" * 80)
        logger.info("PROPOSAL GENERATION COMPLETE")
        logger.info("=" * 80)

        # =========================================================================
        # SECTION 1: Extract Sections from final_state
        # =========================================================================
        sections = final_state.get("sections", [])
        
        # If sections is empty, try to build from individual section data
        if not sections:
            logger.warning("No sections found in final_state, building from individual sections...")
            section_mapping = [
                ("business_context", "BusinessContext"),
                ("overview", "Understanding"),
                ("understanding", "Objectives"),
                ("objectives", "Deliverables"),
                ("deliverables", "Approach"),
                ("approach", "Outcomes"),
                ("outcomes", "CaseStudies"),
                ("business_impact", "Commercials"),
            ]
            
            for state_key, section_name in section_mapping:
                section_data = final_state.get(state_key)
                content = ""
                error = None
                
                if section_data and isinstance(section_data, dict):
                    content = section_data.get("content", "")
                    error = section_data.get("error")
                
                sections.append({
                    "prompt": section_name,
                    "response": content,
                    "error": error
                })

        logger.info(f"📋 Extracted {len(sections)} sections from final_state")

        # =========================================================================
        # SECTION 2: Build Combined Proposal Text
        # =========================================================================
        proposal_text = ""
        
        # Try to get from proposal
        proposal = final_state.get("proposal", {})
        if isinstance(proposal, dict):
            proposal_text = proposal.get("content", "")
            if not proposal_text:
                proposal_text = proposal.get("proposal_text", "")
        
        if not proposal_text:
            proposal_text = final_state.get("proposal_text", "")
        
        if not proposal_text and sections:
            # Build from sections
            proposal_text = "\n\n".join([
                section.get("response", "")
                for section in sections if section.get("response")
            ])
        
        if not proposal_text:
            proposal_text = f"Generated proposal for: {user_prompt if user_prompt else 'Client'}"

        # =========================================================================
        # SECTION 3: Extract Citations from State
        # =========================================================================
        # Get citations from state - these are the top 3 URLs from business_impact_node
        citations_list = []
        
        # First, try to get citations directly from state
        citations = final_state.get("citations", [])
        
        if isinstance(citations, list):
            # If citations is a list of strings (URLs)
            if citations and isinstance(citations[0], str):
                citations_list = [
                    {
                        "filepath": f"Document_{i+1}",
                        "url": url
                    }
                    for i, url in enumerate(citations)
                ]
                logger.info(f"📊 Found {len(citations_list)} citations from state (as URLs)")
            # If citations is a list of dicts
            elif citations and isinstance(citations[0], dict):
                citations_list = citations
                logger.info(f"📊 Found {len(citations_list)} citations from state (as dicts)")
        elif isinstance(citations, dict):
            # If citations is a dict with a 'citations' key
            citations_list = citations.get("citations", [])
            logger.info(f"📊 Found {len(citations_list)} citations from state (in dict)")
        
        # If citations list is still empty, try to get from proposal
        if not citations_list:
            proposal = final_state.get("proposal", {})
            if isinstance(proposal, dict):
                proposal_citations = proposal.get("citations", [])
                if proposal_citations:
                    citations_list = proposal_citations
                    logger.info(f"📊 Found {len(citations_list)} citations from proposal")
        
        # If citations list is still empty, try to get from citation_freq_map
        if not citations_list:
            citation_freq_map = final_state.get("citation_freq_map", {})
            if citation_freq_map:
                # Get top 3 URLs from the frequency map
                sorted_citations = sorted(
                    citation_freq_map.items(), 
                    key=lambda x: x[1], 
                    reverse=True
                )
                top_urls = [url for url, freq in sorted_citations[:3]]
                
                citations_list = [
                    {
                        "filepath": f"Document_{i+1}",
                        "url": url
                    }
                    for i, url in enumerate(top_urls)
                ]
                logger.info(f"📊 Found {len(citations_list)} citations from citation_freq_map")
        
        # Log the citations
        if citations_list:
            logger.info(f"📊 Extracted {len(citations_list)} citations:")
            for i, citation in enumerate(citations_list, 1):
                if isinstance(citation, dict):
                    url = citation.get("url", citation.get("filepath", "N/A"))
                    logger.info(f"  {i}. {url}")
        else:
            logger.info("ℹ️ No citations found in state")

        # Format citations for response
        formatted_citations = {
            "citations": citations_list
        }

        # =========================================================================
        # SECTION 4: Get Document from State (No File Operations)
        # =========================================================================
        document = None
        proposal = final_state.get("proposal", {})
        if isinstance(proposal, dict):
            document = proposal.get("document")
            if document:
                logger.info("✅ Document found in state (in-memory)")
            else:
                logger.info("ℹ️ No document found in state")
            
            # If document exists but proposal_text is empty, try to extract text
            if document and not proposal_text:
                try:
                    if hasattr(document, 'paragraphs'):
                        doc_text = "\n".join([p.text for p in document.paragraphs if p.text.strip()])
                        if doc_text:
                            proposal_text = doc_text
                            logger.info("📄 Extracted text from document object")
                except Exception as e:
                    logger.warning(f"Could not extract text from document: {e}")

        # =========================================================================
        # SECTION 5: Add Citation Frequency Map to Response (for debugging)
        # =========================================================================
        citation_freq_map = final_state.get("citation_freq_map", {})
        
        # =========================================================================
        # SECTION 6: Return in Production Format (No File Dependencies)
        # =========================================================================
        return {
            "success": True,
            "proposal_text": proposal_text,
            "sections": sections,
            "citations": formatted_citations,
            "citation_freq_map": citation_freq_map,  # Include for debugging
            "document": document,
            "filename": f"proposal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
            "final_state": final_state
        }

    except Exception as e:
        logger.error(f"Error generating proposal: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            "success": False,
            "error": str(e),
            "proposal_text": f"Error generating proposal: {str(e)}",
            "sections": [
                {"prompt": "BusinessContext", "response": "", "error": str(e) if i == 0 else None}
                for i in range(8)
            ],
            "citations": {"citations": []},
            "citation_freq_map": {},
            "document": None,
            "filename": None,
            "final_state": {}
        }


def health_check():
    """Check the health status of the system."""
    return {
        "status": "ok", 
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    sample_questionnaire = """
    Category: Business Context
    What is the client/company name? PURE FINANCIAL ADVISORS LLC
    What industry does the client operate in? Financial advisory and wealth management
    """
    
    sample_prompt = "Focus on technical implementation details"
    
    result = generate_proposal_langgraph(sample_questionnaire, sample_prompt)
    
    if result.get("success"):
        print(f"✅ Proposal generated successfully!")
        print(f"Proposal text length: {len(result.get('proposal_text', ''))}")
        print(f"Sections: {len(result.get('sections', []))}")
        for section in result.get('sections', []):
            print(f"  - {section.get('prompt')}: {section.get('response', '')[:50]}...")
        
        # Print citations
        citations = result.get('citations', {}).get('citations', [])
        print(f"Citations: {len(citations)}")
        for i, citation in enumerate(citations, 1):
            if isinstance(citation, dict):
                print(f"  {i}. URL: {citation.get('url', 'N/A')}")
        
        # Print citation frequency map
        freq_map = result.get('citation_freq_map', {})
        if freq_map:
            print(f"Citation Frequency Map: {len(freq_map)} entries")
            for url, freq in list(freq_map.items())[:3]:
                print(f"  - {url}: {freq} times")
        
        if result.get('document'):
            print(f"✅ Document object available in memory")
    else:
        print(f"❌ Proposal generation failed: {result.get('error', 'Unknown error')}")
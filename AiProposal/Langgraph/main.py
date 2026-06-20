import logging
import os
import glob
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
        # ✅ Get sections from final_state (populated by collect_sections_node)
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
        # SECTION 3: Extract Citations
        # =========================================================================
        citations_list = []
        
        citations = final_state.get("citations", [])
        if isinstance(citations, dict):
            citations_list = citations.get("citations", [])
        elif isinstance(citations, list):
            citations_list = citations
        
        if not citations_list:
            proposal = final_state.get("proposal", {})
            if isinstance(proposal, dict):
                citations_list = proposal.get("citations", [])
        
        formatted_citations = {
            "citations": [
                {
                    "filepath": c.get("filepath", c.get("name", f"Proposal_{i+1}.docx")),
                    "url": c.get("url", c.get("link", ""))
                }
                for i, c in enumerate(citations_list) if isinstance(c, dict)
            ]
        }

        # =========================================================================
        # SECTION 4: Find Generated DOCX File
        # =========================================================================
        docx_files = glob.glob("./x_results/Proposal*.docx")
        if not docx_files:
            docx_files = glob.glob("./x_results/*.docx")
        
        if not docx_files:
            proposal = final_state.get("proposal", {})
            word_path = proposal.get("word_path")
            if word_path and os.path.exists(word_path):
                docx_files = [word_path]
        
        latest_docx = None
        if docx_files:
            latest_docx = max(docx_files, key=os.path.getctime)
            logger.info(f"Found DOCX file: {latest_docx}")
            
            if not proposal_text and latest_docx:
                try:
                    from docx import Document
                    doc = Document(latest_docx)
                    doc_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
                    if doc_text:
                        proposal_text = doc_text
                except Exception as e:
                    logger.warning(f"Could not read DOCX content: {e}")

        # =========================================================================
        # SECTION 5: Return in Production Format
        # =========================================================================
        return {
            "success": True,
            "proposal_text": proposal_text,
            "sections": sections,  # ✅ Now contains all 8 sections in production format
            "citations": formatted_citations,
            "file_path": latest_docx,
            "filename": f"proposal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx" if latest_docx else None,
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
            "file_path": None,
            "filename": None
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
        print(f"Citations: {len(result.get('citations', {}).get('citations', []))}")
    else:
        print(f"❌ Proposal generation failed: {result.get('error', 'Unknown error')}")
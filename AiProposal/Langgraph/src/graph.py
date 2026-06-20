from langgraph.graph import StateGraph, END
from .state import GraphState
from .nodes.business_context_node import generate_business_context_node
from .nodes.overview_node import generate_overview_node
from .nodes.understanding_node import generate_understanding_node
from .nodes.objectives_node import generate_objectives_node
from .nodes.deliverables_node import generate_deliverables_node
from .nodes.approach_node import generate_approach_node
from .nodes.outcomes_node import generate_outcomes_node
from .nodes.business_impact_node import generate_business_impact_node
from .nodes.assembly_node import assemble_proposal_node
from .nodes.collect_sections_node import collect_sections_node


def create_proposal_graph():
    """Create the LangGraph workflow for proposal generation using Azure AI Agent."""
    
    workflow = StateGraph(GraphState)
    
    # Add nodes - NO metadata or retrieval nodes (Azure AI Agent handles this automatically)
    workflow.add_node("generate_business_context", generate_business_context_node)
    workflow.add_node("generate_overview", generate_overview_node)
    workflow.add_node("generate_understanding", generate_understanding_node)
    workflow.add_node("generate_objectives", generate_objectives_node)
    workflow.add_node("generate_deliverables", generate_deliverables_node)
    workflow.add_node("generate_approach", generate_approach_node)
    workflow.add_node("generate_outcomes", generate_outcomes_node)
    workflow.add_node("generate_business_impact", generate_business_impact_node)
    workflow.add_node("collect_sections", collect_sections_node)
    workflow.add_node("assemble_proposal", assemble_proposal_node)
    
    # ✅ Set entry point directly to business_context (skip metadata and retrieval)
    workflow.set_entry_point("generate_business_context")
    
    # ✅ Define edges - sequential flow starting from business_context
    workflow.add_edge("generate_business_context", "generate_overview")
    workflow.add_edge("generate_overview", "generate_understanding")
    workflow.add_edge("generate_understanding", "generate_objectives")
    workflow.add_edge("generate_objectives", "generate_deliverables")
    workflow.add_edge("generate_deliverables", "generate_approach")
    workflow.add_edge("generate_approach", "generate_outcomes")
    workflow.add_edge("generate_outcomes", "generate_business_impact")
    workflow.add_edge("generate_business_impact", "collect_sections")
    workflow.add_edge("collect_sections", "assemble_proposal")
    workflow.add_edge("assemble_proposal", END)
    
    # Compile
    return workflow.compile()


def run_proposal_generation(questionnaire: dict) -> dict:
    """Run the complete proposal generation workflow using Azure AI Agent."""
    
    import json
    
    # Initialize state
    initial_state = {
        "questionnaire": questionnaire,
        "questionnaire_text": json.dumps(questionnaire) if not isinstance(questionnaire, str) else questionnaire,
        "metadata": None,
        "metadata_dict": None,
        "top_proposals": [],
        "document_ids": [],
        "section_chunks": {},
        "section_queries": {},
        "business_context": None,
        "overview": None,
        "understanding": None,
        "objectives": None,
        "deliverables": None,
        "approach": None,
        "outcomes": None,
        "business_impact": None,
        "proposal": None,
        "sections": [],
        "current_section_index": 0,
        "sections_completed": [],
        "error": None
    }
    
    # Compile and run
    app = create_proposal_graph()
    final_state = app.invoke(initial_state)
    
    return final_state
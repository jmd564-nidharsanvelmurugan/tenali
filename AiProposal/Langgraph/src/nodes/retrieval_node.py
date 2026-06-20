from ..state import GraphState
from ..tools.db_retrieval import get_top_matching_proposals

def retrieve_proposals_node(state: GraphState) -> GraphState:
    """Retrieve top matching proposals based on metadata."""
    
    print("\n" + "=" * 60)
    print("📊 RETRIEVING: Top Matching Proposals")
    print("=" * 60)
    
    metadata = state["metadata"]
    
    # Prepare user input for matching
    user_input = {
        "solution": [metadata.solution],
        "business_offering": [metadata.business_offering],
        "commercial_use_case": [metadata.commercial_use_case],
        "project_type": [metadata.project_type],
        "existing_infra": [metadata.existing_infra],
        "business_model": [metadata.business_model],
        "region": [metadata.region]
    }
    
    # Get top 5 proposals
    top_proposals = get_top_matching_proposals(user_input, top_n=5)
    
    state["top_proposals"] = top_proposals
    state["document_ids"] = [p["document_id"] for p in top_proposals]
    
    print(f"\n✅ Retrieved {len(top_proposals)} proposals")
    for i, prop in enumerate(top_proposals, 1):
        print(f"   {i}. {prop['document_id']} (Score: {prop['score']})")
    
    return state
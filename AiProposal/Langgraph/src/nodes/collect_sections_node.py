# src/nodes/collect_sections_node.py
from ..state import GraphState

def collect_sections_node(state: GraphState) -> GraphState:
    """
    Collect all generated sections into a single list for the final output.
    This runs before the assembly node.
    """
    print("\n" + "=" * 80)
    print("📋 COLLECTING: All Generated Sections")
    print("=" * 80)
    
    # Map section keys to their display names (production format)
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
    
    sections_list = []
    
    for state_key, section_name in section_mapping:
        section_data = state.get(state_key)
        content = ""
        error = None
        
        if section_data and isinstance(section_data, dict):
            content = section_data.get("content", "")
            error = section_data.get("error")
        
        # Add to sections list in production format
        sections_list.append({
            "prompt": section_name,
            "response": content,
            "error": error
        })
        
        print(f"   ✅ Collected: {section_name} ({len(content)} characters)")
    
    # Update state with sections list
    state["sections"] = sections_list
    state["sections_completed"].append("collect_sections")
    
    print(f"\n📊 Total sections collected: {len(sections_list)}")
    print("=" * 80)
    
    return state
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
        ("introduction_to_jman", "Introduction to JMAN"),  # ← ADD THIS LINE FIRST
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
        else:
            # If section_data is None, try to get it directly (for introduction)
            if state_key == "introduction_to_jman":
                intro_content = state.get("introduction_to_jman")
                if intro_content and isinstance(intro_content, dict):
                    content = intro_content.get("content", "")
        
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
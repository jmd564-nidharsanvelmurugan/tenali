# src/nodes/introduction_node.py
from datetime import datetime
from ..state import GraphState

def generate_introduction_node(state: GraphState) -> GraphState:
    """Generate the Introduction to JMAN section."""
    print("\n" + "=" * 80)
    print("📝 GENERATING: Introduction to JMAN")
    print("=" * 80)
    
    # Add a heading (# Introduction to JMAN) for consistency
    introduction_content = """# Introduction to JMAN

JMAN is a Data & Analytics Consultancy with 325 employees across London, Chennai, and New York. Our international team is a unique blend of consulting, data science and technology expertise. We specialise in working with private equity firms, and their portfolio companies across the investment lifecycle from diligence to exit. Over the last year, we have worked on 375+ projects with 100 portfolio companies across 51 funds. The experience we have on both sides of the deal in Diligence and at Exit, with some of the most sophisticated data adopters in private equity, gives us a good understanding of how businesses are evaluated, and what bidders are looking for from data."""
    
    state["introduction_to_jman"] = {
        "content": introduction_content,
        "chunks_used": 0,
        "timestamp": datetime.now().isoformat(),
        "retrieval_query": "",
        "document_ids_used": []
    }
    
    state["sections_completed"].append("Introduction to JMAN")
    
    print(f"✅ Introduction to JMAN generated ({len(introduction_content)} characters)")
    print("=" * 80)
    
    return state
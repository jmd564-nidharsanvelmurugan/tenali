import psycopg2
import re
import os
import json
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
load_dotenv()

model = SentenceTransformer(
    "BAAI/bge-large-en-v1.5"
)

def get_filtered_chunks_by_semantic_query(
    child_ids: List[str],
    query: str,
    top_k: int = 10
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Filter child chunks using a semantic query (no subsection names).
    Returns chunks with similarity scores based on full text content.
    
    Args:
        child_ids: List of child chunk IDs
        query: Semantic query string
        top_k: Number of top chunks to return
    
    Returns:
        Dictionary with "semantic_filtered" key containing list of scored chunks
    """
    
    if not child_ids:
        print("⚠️ No child IDs provided. Returning empty list.")
        return {"semantic_filtered": []}
    
    if not query or query.strip() == "":
        print("⚠️ No query provided. Returning all chunks.")
        # Fall back to returning all chunks
        return get_filtered_chunks_for_section(child_ids, [], search_type=1, top_k_per_subsection=top_k)
    
    conn = psycopg2.connect(
        os.getenv('DB')
    )
    
    cur = conn.cursor()
    
    # Fetch all child chunks by IDs
    cur.execute("""
        SELECT
            id,
            subsection,
            actual_text_data,
            embedding
        FROM child_chunk
        WHERE id = ANY(%s)
    """, (child_ids,))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows:
        print("⚠️ No child chunks found for the given IDs.")
        return {"semantic_filtered": []}
    
    print(f"📝 Applying semantic query filter: '{query}'")
    
    # Generate query embedding
    query_emb = model.encode(query)
    
    results = []
    
    for row in rows:
        # Get the chunk text (use actual_text_data for semantic comparison)
        chunk_text = row[2] if row[2] else ""
        subsection_name = row[1] if row[1] else "unknown"
        
        if not chunk_text:
            continue
        
        # Generate embedding for chunk text
        chunk_emb = model.encode(chunk_text)
        
        # Calculate cosine similarity
        similarity = cosine_similarity(
            [query_emb],
            [chunk_emb]
        )[0][0]
        
        results.append({
            "chunk_id": row[0],
            "subsection": subsection_name,
            "text": chunk_text,
            "embedding_preview": str(row[3][:5]) + "..." if row[3] else None,
            "similarity_score": float(similarity),
            "match_type": "semantic_query"
        })
        
    
    # Sort by similarity score (higher = better match)
    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    
    top_results = results[:top_k]
    
    print(f"✅ Found {len(results)} matching chunks (returning top {len(top_results)})")
    for i, r in enumerate(top_results[:3], 1):
        print(f"   {i}. Score: {r['similarity_score']:.3f} | Subsection: {r['subsection']}")
    
    return {"semantic_filtered": top_results}

def ensure_results_folder():
    """Ensure the x_results folder exists."""
    if not os.path.exists("x_results"):
        os.makedirs("x_results")
        print("📁 Created 'x_results' folder")

def save_to_json(data: Dict[str, Any], filename: str):
    """Save data to JSON file in x_results folder."""
    ensure_results_folder()
    filepath = os.path.join("x_results", filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"✅ Saved to: {filepath}")

def subsection_filter(
    subsection_query: Optional[str],
    child_ids: List[str],
    search_type: int = 1,
    top_k: int = 10
) -> List[Dict[str, Any]]:
    """
    Filter child chunks based on subsection query.
    
    Args:
        subsection_query: The subsection name/query to search for (can be None)
        child_ids: List of child chunk IDs to filter from
        search_type: 1 -> Semantic Search, 2 -> Keyword Search
        top_k: Number of top results to return
    
    Returns:
        List of filtered child chunks with scores
    """
    
    if not child_ids:
        print("⚠️ No child IDs provided. Returning empty list.")
        return []
    
    conn = psycopg2.connect(
        os.getenv('DB')
    )
    
    cur = conn.cursor()
    
    # Fetch all child chunks by IDs
    cur.execute("""
        SELECT
            id,
            subsection,
            actual_text_data,
            embedding
        FROM child_chunk
        WHERE id = ANY(%s)
    """, (child_ids,))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows:
        print("⚠️ No child chunks found for the given IDs.")
        return []
    
    # =====================================================
    # CASE 1: No subsection query - return all chunks as-is
    # =====================================================
    if not subsection_query or subsection_query.strip() == "":
        print(f"📝 No subsection filter applied. Returning all {len(rows)} child chunks.")
        
        results = []
        for row in rows:
            results.append({
                "chunk_id": row[0],
                "subsection": row[1] if row[1] else "unknown",
                "text": row[2],
                "embedding_preview": str(row[3][:5]) + "..." if row[3] else None,
                "subsection_score": 1.0,
                "match_type": "all_chunks"
            })
        
        return results[:top_k]
    
    # =====================================================
    # CASE 2: Subsection query present - apply filtering
    # =====================================================
    print(f"📝 Applying subsection filter: '{subsection_query}' (type={search_type})")
    
    results = []
    
    # ==========================
    # SEMANTIC SEARCH
    # ==========================
    if search_type == 1:
        
        query_emb = model.encode(subsection_query)
        
        for row in rows:
            # Get subsection name from the chunk
            subsection_name = row[1] if row[1] else ""
            
            # Skip if no subsection name
            if not subsection_name:
                continue
            
            # Encode subsection name
            subsection_emb = model.encode(subsection_name)
            
            # Calculate similarity
            similarity = cosine_similarity(
                [query_emb],
                [subsection_emb]
            )[0][0]
            
            results.append({
                "chunk_id": row[0],
                "subsection": subsection_name,
                "text": row[2],
                "embedding_preview": str(row[3][:5]) + "..." if row[3] else None,
                "subsection_score": float(similarity),
                "match_type": "semantic"
            })
        
        # Sort by similarity score (higher = better match)
        results.sort(key=lambda x: x["subsection_score"], reverse=True)
    
    # ==========================
    # KEYWORD SEARCH
    # ==========================
    elif search_type == 2:
        
        query_tokens = set(
            re.findall(r"\w+", subsection_query.lower())
        )
        
        for row in rows:
            subsection_name = row[1] if row[1] else ""
            
            if not subsection_name:
                continue
            
            subsection_tokens = set(
                re.findall(r"\w+", subsection_name.lower())
            )
            
            matched_words = query_tokens.intersection(subsection_tokens)
            match_count = len(matched_words)
            
            if match_count > 0:
                results.append({
                    "chunk_id": row[0],
                    "subsection": subsection_name,
                    "text": row[2],
                    "embedding_preview": str(row[3][:5]) + "..." if row[3] else None,
                    "subsection_score": match_count,
                    "matched_words": sorted(list(matched_words)),
                    "match_type": "keyword"
                })
        
        # Sort by match count (higher = better match)
        results.sort(key=lambda x: x["subsection_score"], reverse=True)
    
    print(f"✅ Found {len(results)} matching chunks (returning top {min(top_k, len(results))})")
    return results[:top_k]

def get_filtered_chunks_for_section(
    child_ids: List[str],
    subsections: List[Dict[str, str]],
    search_type: int = 1,
    top_k_per_subsection: int = 5
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get filtered chunks for each subsection in a section.
    
    Args:
        child_ids: List of child chunk IDs
        subsections: List of subsections with names and queries
        search_type: 1 -> Semantic, 2 -> Keyword
        top_k_per_subsection: Number of chunks to return per subsection
    
    Returns:
        Dictionary mapping subsection name to list of filtered chunks
    """
    
    results = {}
    
    if not subsections:
        print("⚠️ No subsections provided. Fetching all chunks without filter...")
        all_chunks = subsection_filter(
            subsection_query=None,
            child_ids=child_ids,
            search_type=search_type,
            top_k=top_k_per_subsection * 10  # Get more chunks when no filter
        )
        results["all_chunks"] = all_chunks
        return results
    
    for subsection in subsections:
        subsection_name = subsection.get("subsection", "")
        query = subsection.get("query", subsection_name)
        
        print(f"\n🔍 Filtering for subsection: {subsection_name}")
        
        filtered_chunks = subsection_filter(
            subsection_query=query,
            child_ids=child_ids,
            search_type=search_type,
            top_k=top_k_per_subsection
        )
        
        results[subsection_name] = filtered_chunks
    
    return results
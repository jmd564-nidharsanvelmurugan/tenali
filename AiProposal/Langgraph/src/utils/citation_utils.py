# src/utils/citation_utils.py
from typing import Dict, List, Any

def merge_citation_freq_maps(
    existing_map: Dict[str, int], 
    new_map: Dict[str, int]
) -> Dict[str, int]:
    """
    Merge two citation frequency maps.
    """
    result = existing_map.copy()
    for url, freq in new_map.items():
        result[url] = result.get(url, 0) + freq
    return result

def get_top_citation_urls(
    freq_map: Dict[str, int], 
    top_n: int = 3
) -> List[str]:
    """
    Get top N citation URLs from frequency map.
    Returns a list of URLs as strings.
    """
    # Sort by frequency (highest first)
    sorted_citations = sorted(
        freq_map.items(), 
        key=lambda x: x[1], 
        reverse=True
    )
    
    # Return top N URLs
    top_urls = [url for url, freq in sorted_citations[:top_n]]
    
    return top_urls
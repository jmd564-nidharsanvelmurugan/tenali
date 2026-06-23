import psycopg2
import re
import os
import json

from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()


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
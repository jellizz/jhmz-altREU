"""
Given the names of authors, verifies whether the names are male or female. Uses genderize.io API to determine the gender 
of authors based on first and last names. Returns a dictionary with the author's name, gender, and probability.
"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

GENDERIZE_API_KEY = os.environ.get("GENDERIZE_API_KEY")
GENDERIZE_URL = "https://api.genderize.io"
BULK_BATCH_SIZE = 10  # genderize.io max per request


def normalize_name(full_name):
    """
    Converts a full name in citation style (Last, First) to the normal order (First Last). If already normal,
    leaves it the same.
    """
    name = full_name.strip()
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return name


def _build_params(names_batch):
    params = {}
    for i, name in enumerate(names_batch):
        params[f"name[{i}]"] = name
    if GENDERIZE_API_KEY:
        params["apikey"] = GENDERIZE_API_KEY
    return params


def get_gender_bulk(names, max_retries=3):
    """
    Queries genderize.io in batches of 10 using full names.
    Returns list of dicts in order:
    {"name": ..., "gender": ..., "probability": ..., "count": ...}
    """
    results = []
    for i in range(0, len(names), BULK_BATCH_SIZE):
        batch = names[i:i + BULK_BATCH_SIZE]
        params = _build_params(batch)

        for attempt in range(max_retries):
            try:
                response = requests.get(GENDERIZE_URL, params=params, timeout=10)
                if response.status_code == 429:
                    wait = int(response.headers.get("X-Rate-Reset", 60))
                    print(f"Rate limited by genderize.io, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                results.extend(response.json())
                break
            except requests.exceptions.RequestException as e:
                print(f"genderize.io request failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    results.extend([{"name": n, "gender": None, "probability": None} for n in batch])
    return results


def process_authors(author_names):
    """
    Takes a list of full author name strings (citation-style or natural order)
    and returns gender predictions using the full name for best accuracy.
    """
    normalized = [normalize_name(name) for name in author_names]
    genderize_results = get_gender_bulk(normalized)

    output = []
    for original, sent_name, result in zip(author_names, normalized, genderize_results):
        output.append({
            "original_name": original,
            "name_sent_to_api": sent_name,
            "gender": result.get("gender"),
            "probability": result.get("probability"),
            "count": result.get("count"),
        })
    return output


if __name__ == "__main__":
    # currently just tests how it verifies. 
    test_authors = ["Smith, John A.", "Chen, Wei", "Garcia, Maria", "Alex Taylor"]
    for r in process_authors(test_authors):
        print(r) 
        
# For an operational definition, we are going to only want to focus on authors whose genders are predicted with a probability of 0.8 or higher?

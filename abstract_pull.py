"""
Uses the OpenAlex API to pull paper abstracts from OpenAlex and store them in a local database.
"""

import requests
import json
import os
from dotenv import load_dotenv

# get .env vars
load_dotenv()

API_KEY = os.getenv("API_KEY")
EMAIL = os.getenv("EMAIL")

"""
Because abstracts are stored as inverted indexes in OpenAlex, turns them into a readable format.
I.e., takes {"word1": [0, 3], "word2": [1]} and returns "word1 word2 word1".
Requires that the inverted index exists, is complete, and has no missing positions. 
"""
def build_abstract(abstract_inverted_index):
    position_map = {}
    for word, positions in abstract_inverted_index.items(): 
        for pos in positions:
            position_map[pos] = word
    return " ".join(position_map[i] for i in sorted(position_map))


"""
Gets abstracts from OpenAlex API based on a sample size and source ID, and saves them to a local JSON file.
Source ID is the OpenAlex ID for the source (e.g., a journal such as Nature).
"""
def pull_abstracts(sample, source_id):
    params = { # extra params for the API request
        "filter": f"primary_location.source.id:{source_id},has_abstract:true,publication_year:2020-2024",
        "select": "id,title,publication_year,abstract_inverted_index",
        "sample": sample, # random selection of N papers
        "api_key": API_KEY
    }

    headers = {"User-Agent": f"mailto:{EMAIL}"}

    response = requests.get( # requests organizes the API request
        "https://api.openalex.org/works",
        params=params,
        headers=headers
    )
    response.raise_for_status() 
    data = response.json()

    abstracts = []
    for work in data["results"]:
        abstract_text = build_abstract(work["abstract_inverted_index"])
        if abstract_text: # checks to make sure the abstract is not empty
            abstracts.append({
                "id": work["id"],
                "title": work.get("title"),
                "year": work.get("publication_year"),
                "abstract": abstract_text,
            })

    # save to a file named after the source_id so multiple journals don't overwrite each other
    with open(f"abstracts_{source_id}.json", "w") as f:
        json.dump(abstracts, f, indent=2)

    return abstracts


if __name__ == "__main__":
    # Nature Physics, 30 abstracts (TEST for now, can change sample size later and for actual data collection)
    abstracts = pull_abstracts(sample=30, source_id="S137773608")
    print(f"Retrieved {len(abstracts)} abstracts")
    print(json.dumps(abstracts[:2], indent=2))
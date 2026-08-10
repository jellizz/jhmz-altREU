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
            if word != "Abstract" and pos != 0:  # skip the "Abstract" word that OpenAlex adds to the beginning of every abstract (for some journals)
                position_map[pos] = word
    return " ".join(position_map[i] for i in sorted(position_map))


"""
Gets abstracts from OpenAlex API based on a sample size and source ID, and saves them to a local JSON file.
Source ID is the OpenAlex ID for the source (e.g., a journal such as Nature).
"""
def pull_abstracts(sample, source_id):
    params = { # extra params for the API request
        "filter": f"primary_location.source.id:{source_id},has_abstract:true,publication_year:2020-2026",
        "select": "id,title,publication_year,abstract_inverted_index",
        "sample": sample, # random selection of N papers
        "per-page": sample, # number of results per call
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

    # formatting with desired data
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

    # save to a file named after the source_id so multiple journals don't overwrite each other (in folder "data")
    os.makedirs("data", exist_ok=True)
    filepath = os.path.join("data", f"abstracts_{source_id}.json")
    with open(filepath, "w") as f:
        json.dump(abstracts, f, indent=2)

    return abstracts


if __name__ == "__main__":
    # Pulling 100 abstracts from each major journal of interest. 200 per field.

    # # 1. Physics ##############################################################
    # # (Physical Review Letters)

    # abstracts = pull_abstracts(sample=100, source_id="S24807848")
    # print(f"Retrieved {len(abstracts)} abstracts")
    # print(json.dumps(abstracts[:2], indent=2))

    # # (The Astrophysical Journal)
    # abstracts = pull_abstracts(sample=100, source_id="S1980519")
    # print(f"Retrieved {len(abstracts)} abstracts")
    # print(json.dumps(abstracts[:2], indent=2))

    # # 2. Medicine ##########################################################

    # # (The New England Journal of Medicine), not available via OpenAlex
    # # (CELL), s110447773
    # abstracts = pull_abstracts(sample=100, source_id="S110447773")
    # print(f"Retrieved {len(abstracts)} abstracts")
    # print(json.dumps(abstracts[:2], indent=2))

    # # (The Lancet), s49861241
    # abstracts = pull_abstracts(sample=100, source_id="S49861241")
    # print(f"Retrieved {len(abstracts)} abstracts")
    # print(json.dumps(abstracts[:2], indent=2))

    # 3. Social Sciences ##########################################################
    # For this, we decided on Economics and Psychology.

    # # American Economic Review, S23254222
    # abstracts = pull_abstracts(sample=100, source_id="S23254222")
    # print(f"Retrieved {len(abstracts)} abstracts")
    # print(json.dumps(abstracts[:2], indent=2))

    # # Frontiers in Psychology, S9692511
    # abstracts = pull_abstracts(sample=100, source_id="S9692511")
    # print(f"Retrieved {len(abstracts)} abstracts")
    # print(json.dumps(abstracts[:2], indent=2))
    
    # 4. Computer Science ##########################################################
    # IEEE Transactions on Neural Networks and Learning Systems, Expert Systems with Applications
    
    # abstracts = pull_abstracts(sample=100, source_id="S4210175523")
    # print(f"Retrieved {len(abstracts)} abstracts")
    # print(json.dumps(abstracts[:2], indent=2))
    
    # abstracts = pull_abstracts(sample=100, source_id="S13144211")
    # print(f"Retrieved {len(abstracts)} abstracts")
    # print(json.dumps(abstracts[:2], indent=2))

     # 5. Environmental Science ##########################################################
    # The Science of the Total Environment, Journal of Hazardous Materials
    abstracts = pull_abstracts(sample=100, source_id="s86852077")
    print(f"Retrieved {len(abstracts)} abstracts")
    print(json.dumps(abstracts[:2], indent=2))
    
    abstracts = pull_abstracts(sample=100, source_id="S145089992")
    print(f"Retrieved {len(abstracts)} abstracts")
    print(json.dumps(abstracts[:2], indent=2))
    
        
    
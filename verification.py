"""
Verfies that citations exist, given a list of citations in APA formatting.
Checks if citation components can be found in OpenAlex.

Verification is based on:
    Title
    First Author
    DOI

"""

import os
import json
import re
import time
import unicodedata
import requests
from difflib import SequenceMatcher
from dotenv import load_dotenv

load_dotenv()

OPENALEX_API_KEY = os.environ["OPENALEX_API_KEY"]

# Load JSON
def load_response(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)
    return []


# Text normalization
def normalize(text):
    """Lowercase, strip accents, punctuation, and extra whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[-–—/:]", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def similarity(a, b):
    """Fuzzy string similarity between 0 and 1."""
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


# Parse citation to get a paper's first author, title, DOI
def parse_single_citation(citation):
    # Find year
    year_match = re.search(r'\((\d{4})\)', citation)
    if year_match:
        year = int(year_match.group(1))
    else:
        year = None

    # Find DOI
    doi_match = re.search(r'10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+', citation)
    if doi_match:
        doi = doi_match.group(0).rstrip(".,")
    else:
        doi = None
    if doi is not None:
        doi_provided = True
    else:
        doi_provided = False

    # Get authors
    author_raw = ""
    if year_match:
        author_raw = citation[:year_match.start()].strip().rstrip(".")

    # Get first author (anything before ;/&/"and")
    first_author = re.split(r';|&|\band\b', author_raw)[0].strip()
    first_author = re.sub(r'\bet al\.?\b', '', first_author, flags=re.IGNORECASE).strip()

    # Get author first and last names
    lastname, firstname = "", ""
    if "," in first_author:
        parts = first_author.split(",", 1)
        lastname = parts[0].strip()
        firstname = parts[1].strip().rstrip(".")
    else:
        lastname = first_author.strip()

    # Get title
    # journal starts with a capital letter after ". "
    title = ""
    if year_match:
        after_year = citation[year_match.end():].lstrip(". ")
        title_match = re.match(r'(.+?)[.?!]\s+[A-Z]', after_year)
        if title_match:
            title = title_match.group(1).strip()

    return {
        "raw": citation,
        "first_author_lastname": lastname,
        "first_author_firstname": firstname,
        "author_raw": author_raw,
        "year": year,
        "title": title,
        "doi": doi,
        "doi_provided": doi_provided,
        "name_complete": len(firstname) > 2
    }


# Parse citation string list
def parse_references(citations):
    citations = []
    for citation in citations:
        citations.append(parse_single_citation(citation))
    return citations


# Search OpenAlex for DOI
def openalex_by_doi(doi):
    url = f"https://api.openalex.org/works/https://doi.org/{doi}"
    try:
        r = requests.get(
            url,
            params = {
                "api_key": OPENALEX_API_KEY
            },
            timeout=15
        )
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


# Search OpenAlex for title
# Uses fuzzy matching with 0.85 threshold <-- Allows small text differences/errors to match
def openalex_by_title(title):
    url = "https://api.openalex.org/works"
    params = {
        "api_key": OPENALEX_API_KEY,
        "search": title,
        "per_page": 5,
        "select": "id,title,doi,authorships"
    }
    try:
        r = requests.get(
            url,
            params=params,
            timeout=15
        )
        if r.status_code != 200:
            print(f"OpenAlex error {r.status_code}: {r.text}")
            return None, True

        results = r.json().get("results", [])
        best, best_score = None, 0

        for work in results:
            candidate_title = work.get("title", "")
            score = similarity(title, candidate_title)
            if score > best_score:
                best_score = score
                best = work

        if best_score >= 0.85:
            return best, False
        return None, False

    except Exception as e:
        print(f"OpenAlex lookup failed: {e}")
        return None, True


# Get first author's name from OpenAlex, if possible
def extract_first_author_from_record(record):
    authorships = record.get("authorships", [])
    if not authorships:
        return None
    first = authorships[0]
    author = first.get("author", {})
    return author.get("display_name", None)


# To handle "check rseponse b/c it didn't follow the expected format"
def is_check_reference(citation):
    if not isinstance(citation, str):
        return True

    text = citation.strip().lower()

    check_patterns = [
        "check response",
        "check reference",
        "check citation"
    ]

    return any(pattern in text for pattern in check_patterns)


# Citation verification 
# Follows Zhao et al.: Look for title -> author -> DOI
'''
Hallucination: Title fails
Partial: Title passes, DOI/author fails
Verified: Title, author, DOI pass
'''
def verify_citation(parsed):
    """
    Verify a parsed citation against OpenAlex.
    
    Follows Zhao et al. title-first approach:
    1. Search by title — primary signal
    2. If title found, check author match
    3. If title found, check DOI match
    4. If title not found, mark as hallucinated regardless of DOI
    """
    title = parsed.get("title", "")
    doi = parsed.get("doi")
    doi_provided = parsed.get("doi_provided", False)
    parsed_lastname = parsed.get("first_author_lastname", "").lower()

    # Check title
    # Check title
    if title:
        record, lookup_error = openalex_by_title(title)
    else:
        record = None
        lookup_error = False

    lookup_method = "title_search" if record else "none"

    # OpenAlex/API problem -- flag for manual check
    if lookup_error:
        return {
            "status": "CHECK",
            "title_found": None,
            "doi_matched": None,
            "author_matched": None,
            "lookup_method": "error",
            "openalex_id": None,
            "openalex_first_author": None
        }

    # Title not found
    if record is None:
        return {
            "status": "hallucinated",
            "title_found": False,
            "doi_matched": False,
            "author_matched": False,
            "lookup_method": lookup_method,
            "openalex_id": None,
            "openalex_first_author": None
        }

    # Title found with 0.85 similarity
    record_title = record.get("title", "")
    title_found = similarity(title, record_title) >= 0.85

    # Title too different -> Hallucinated 
    if not title_found:
        return {
            "status": "hallucinated",
            "title_found": False,
            "doi_matched": False,
            "author_matched": False,
            "lookup_method": lookup_method,
            "openalex_id": record.get("id"),
            "openalex_first_author": extract_first_author_from_record(record)
        }

    # Check first author
    openalex_first_author = extract_first_author_from_record(record)
    author_matched = False

    if openalex_first_author and parsed_lastname:
        openalex_lastname = openalex_first_author.split()[-1].lower()
        author_matched = similarity(parsed_lastname, openalex_lastname) >= 0.85

    # Check DOI
    doi_matched = False
    if doi_provided and doi:
        record_doi = record.get("doi", "")
        if record_doi:
            record_doi_clean = re.sub(r'https?://(dx\.)?doi\.org/', '', record_doi).lower().rstrip(".,")
            parsed_doi_clean = re.sub(r'https?://(dx\.)?doi\.org/', '', doi).lower().rstrip(".,")
            doi_matched = record_doi_clean == parsed_doi_clean

    # Determine status
    if author_matched and doi_matched:
        status = "verified"
    elif author_matched and not doi_provided:
        status = "verified"
    else:
        status = "partial"

    return {
        "status": status,
        "title_found": True,
        "doi_matched": doi_matched,
        "author_matched": author_matched,
        "lookup_method": lookup_method,
        "openalex_id": record.get("id"),
        "openalex_first_author": openalex_first_author
    }


# Putting everything together... 
# Looks at each citation in input_file, verifies information in OpenAlex, returns verdict in output_file
def verify_all(input_file, output_file):
    data = load_response(input_file)

    # Load previously completed results if they exist
    if os.path.exists(output_file):
        try:
            with open(output_file, "r") as f:
                existing_results = json.load(f)

            if not isinstance(existing_results, list):
                existing_results = []

        except (json.JSONDecodeError, OSError):
            print("Warning: Could not load existing output file. Starting fresh.")
            existing_results = []
    else:
        existing_results = []

    # IDs of records that have already been completely processed
    completed_ids = {
        r["id"]
        for r in existing_results
        if isinstance(r, dict) and "id" in r
    }

    results = existing_results.copy()

    print(f"Found {len(completed_ids)} already-completed records.")

    for record in data:

        # Skip records that were already saved
        if record["id"] in completed_ids:
            print(f"\nSkipping already completed: {record['id']}")
            continue

        print(f"\nProcessing: {record['id']}")

        verified_references = []

        for raw_citation in record["response"]["references"]:

            # Model explicitly flagged this reference for manual checking
            if is_check_reference(raw_citation):
                verification = {
                    "status": "CHECK",
                    "title_found": None,
                    "doi_matched": None,
                    "author_matched": None,
                    "lookup_method": "model_flagged",
                    "openalex_id": None,
                    "openalex_first_author": None
                }

                verified_references.append({
                    "citation": raw_citation,
                    "parsed": None,
                    "verification": verification
                })

                print(f"  [CHECK] Model flagged reference: {raw_citation}")
                continue

            # Try to parse the citation
            try:
                parsed = parse_single_citation(raw_citation)

            except Exception as e:
                print(f"  [CHECK] Citation parsing failed: {e}")

                verified_references.append({
                    "citation": raw_citation,
                    "parsed": None,
                    "verification": {
                        "status": "CHECK",
                        "title_found": None,
                        "doi_matched": None,
                        "author_matched": None,
                        "lookup_method": "parse_error",
                        "openalex_id": None,
                        "openalex_first_author": None,
                        "error": str(e)
                    }
                })

                continue

            # Try to verify citation
            try:
                verification = verify_citation(parsed)

            except Exception as e:
                print(f"  [CHECK] Verification failed: {e}")

                verification = {
                    "status": "CHECK",
                    "title_found": None,
                    "doi_matched": None,
                    "author_matched": None,
                    "lookup_method": "verification_error",
                    "openalex_id": None,
                    "openalex_first_author": None,
                    "error": str(e)
                }

            verified_references.append({
                "citation": raw_citation,
                "parsed": {
                    "first_author_lastname": parsed["first_author_lastname"],
                    "first_author_firstname": parsed["first_author_firstname"],
                    "title": parsed["title"],
                    "doi": parsed["doi"],
                    "doi_provided": parsed["doi_provided"],
                    "name_complete": parsed["name_complete"]
                },
                "verification": verification
            })

            status = verification["status"]
            title = parsed["title"][:60] if parsed["title"] else "(no title)"
            print(f"  [{status}] {title}")

        # Add the completed record to results
        results.append({
            "id": record["id"],
            "model": record["model"],
            "question": record["question"],
            "response": {
                "answer": record["response"]["answer"],
                "references": verified_references
            }
        })

        # Mark this record as completed
        completed_ids.add(record["id"])

        # SAVE IMMEDIATELY after each completed record
        temp_output_file = output_file + ".tmp"

        with open(temp_output_file, "w") as f:
            json.dump(results, f, indent=4)

        os.replace(temp_output_file, output_file)

        print(f"  Saved checkpoint: {record['id']}")

    # Print final summary
    all_refs = [
        ref
        for r in results
        for ref in r["response"]["references"]
    ]

    total = len(all_refs)
    verified = sum(
        1 for r in all_refs
        if r["verification"]["status"] == "verified"
    )
    partial = sum(
        1 for r in all_refs
        if r["verification"]["status"] == "partial"
    )
    hallucinated = sum(
        1 for r in all_refs
        if r["verification"]["status"] == "hallucinated"
    )
    check = sum(
        1 for r in all_refs
        if r["verification"]["status"] == "CHECK"
    )

    print(f"\n{'='*40}")
    print(f"Total citations:  {total}")

    if total > 0:
        print(f"Verified:         {verified} ({verified/total*100:.1f}%)")
        print(f"Partial:          {partial} ({partial/total*100:.1f}%)")
        print(f"Hallucinated:     {hallucinated} ({hallucinated/total*100:.1f}%)")
        print(f"CHECK:            {check} ({check/total*100:.1f}%)")
    else:
        print("No citations found.")

    print(f"Completed records: {len(results)}")
    print(f"Saved to {output_file}")


if __name__ == "__main__":
    verify_all(
        input_file="data/responses/anthropic/responses_anthropic_physics_astrophys.json",
        output_file="data/verification/anthropic_physics_astrophys.json"
    )
    
    
    
#### note:
# This currently is failing to identify some. For example:
                # {
                #     "citation": "K\u00f6rding, Elmar G.; Jester, Sebastian; Fender, Rob. (2006). Accretion states and radio loudness in active galactic nuclei. Monthly Notices of the Royal Astronomical Society, 372(3), 1366-1378. DOI: doi.org/10.1111/j.1365-2966.2006.10954.x",
                #     "parsed": {
                #         "first_author_lastname": "K\u00f6rding",
                #         "first_author_firstname": "Elmar G",
                #         "title": "Accretion states and radio loudness in active galactic nuclei",
                #         "doi": "10.1111/j.1365-2966.2006.10954.x",
                #         "doi_provided": true,
                #         "name_complete": true
                #     },
                #     "verification": {
                #         "status": "hallucinated",
                #         "title_found": false,
                #         "doi_matched": false,
                #         "author_matched": false,
                #         "lookup_method": "none",
                #         "openalex_id": null,
                #         "openalex_first_author": null
                #     }
                # },
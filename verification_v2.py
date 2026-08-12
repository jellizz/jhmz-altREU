"""
Checks references for hallucinations against various databases. 
Utilizes the hallucinator library: https://github.com/gianlucasb/hallucinator. Note that this library provides
an estimate of whether a reference is likely to be real or not, and does not 100% guarantee that a reference is real or fake.

Reports back information about hallucinated and real sources, such as which information mismatches. Sends results to a JSON.
"""

import json
import os
import re
from dotenv import load_dotenv
from hallucinator import Reference, Validator, ValidatorConfig

load_dotenv()

###### Settings for the validator ######
config = ValidatorConfig()
config.check_openalex_authors = True
config.openalex_key = os.getenv("API_KEY")
config.crossref_mailto = os.getenv("EMAIL")

validator = Validator(config)


def load_file(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)
    return []


def parse_single_citation(citation):
    year_match = re.search(r'\((\d{4})\)', citation)
    year = int(year_match.group(1)) if year_match else None

    doi_match = re.search(r'10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+', citation)
    doi = doi_match.group(0).rstrip(".,") if doi_match else None
    doi_provided = doi is not None

    author_raw = ""
    if year_match:
        author_raw = citation[:year_match.start()].strip().rstrip(".")

    first_author = re.split(r';|&|\band\b', author_raw)[0].strip()
    first_author = re.sub(r'\bet al\.?\b', '', first_author, flags=re.IGNORECASE).strip()

    lastname, firstname = "", ""
    if "," in first_author:
        parts = first_author.split(",", 1)
        lastname = parts[0].strip()
        firstname = parts[1].strip().rstrip(".")
    else:
        lastname = first_author.strip()

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


def build_reference_from_citation(raw_citation):
    """
    Parses a raw citation string into title/authors/doi, then builds a
    hallucinator Reference object. `title` is required (must be a
    non-empty string per the Rust bindings), so citations we couldn't
    parse a title from are skipped rather than passed through with "".
    """
    parsed = parse_single_citation(raw_citation)

    title = parsed.get("title") or ""
    if not title:
        raise ValueError("No title could be parsed from citation; skipping")

    lastname = parsed.get("first_author_lastname") or ""
    authors = [lastname] if lastname else []

    doi = parsed.get("doi")  # None is fine here, unlike title

    return Reference(
        title,
        authors=authors,
        doi=doi,
        raw_citation=raw_citation
    )


def test_references_from_json(filename, num_records=1, num_refs_per_record=3):
    """
    Loads a task-2-style JSON file, pulls a small sample of references
    from the first few records, and validates them as a batch per record.
    """
    data = load_file(filename)
    if not data:
        print(f"No data found in {filename}")
        return

    sample_records = data[:num_records]

    for record in sample_records:
        record_id = record.get("id", "unknown_id")
        raw_citations = record.get("response", {}).get("references", [])[:num_refs_per_record]

        print(f"\n=== Record: {record_id} ===")

        references = []
        valid_citations = []
        for raw_citation in raw_citations:
            if not isinstance(raw_citation, str):
                print(f"  Skipping non-string reference: {raw_citation}")
                continue
            try:
                references.append(build_reference_from_citation(raw_citation))
                valid_citations.append(raw_citation)
            except Exception as e:
                print(f"  [PARSE ERROR] {raw_citation[:80]}...")
                print(f"       -> {type(e).__name__}: {e}")

        if not references:
            continue

        try:
            results = validator.check(references)
            for raw_citation, r in zip(valid_citations, results):
                print(f"  [{r.status}] {r.title}")
                print(f"       source: {r.source}")
                print(f"       ref_authors: {r.ref_authors}  found_authors: {r.found_authors}")
                if r.failed_dbs:
                    print(f"       failed_dbs: {r.failed_dbs}")
                if r.retraction_info and r.retraction_info.is_retracted:
                    print(f"       ⚠ RETRACTED (source: {r.retraction_info.retraction_source})")
        except Exception as e:
            print(f"  [BATCH ERROR] {type(e).__name__}: {e}")

        # summary stats for this record's batch
        stats = Validator.stats(results)
        print(f"  -- verified: {stats.verified}, not_found: {stats.not_found}, "
              f"author_mismatch: {stats.author_mismatch}, retracted: {stats.retracted}")


if __name__ == "__main__":
    test_references_from_json(
        filename="data/responses/anthropic/responses_anthropic_physics_astrophys.json",
        num_records=2,
        num_refs_per_record=3
    )
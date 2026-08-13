"""
Modification: Added flexible author name matching functionality.
"""


import json
import os
import re
import unicodedata
from dotenv import load_dotenv
from hallucinator import Reference, Validator, ValidatorConfig
from prompt_llm_task1 import load_file

load_dotenv()

###### Settings for the validator ######
config = ValidatorConfig()
config.check_openalex_authors = True
config.openalex_key = os.getenv("API_KEY")
config.s2_api_key = os.getenv("S2_API_KEY") # helps with Semantic Scholar queries, 1 per sec.
config.crossref_mailto = os.getenv("EMAIL")
config.disabled_dbs = ["dblp","acl","neurips","ssrn","pubmed"] # optional list of databases to skip (DBLP is really really slow)

# limiting the number of seconds to wait for a response from the database before timing out
config.db_timeout_secs = 5
config.db_timeout_short_secs = 3
config.max_rate_limit_retries = 1

validator = Validator(config)


def parse_single_citation(citation):
    """
    Parses references in the format:

        Author | Title | DOI

    Examples:

        Judea Pearl | Fusion, propagation, and structuring in belief networks | 10.1016/0004-3702(86)90072-X

        L.A. Zadeh | Fuzzy sets | 10.1016/S0019-9958(65)90241-X

        Terje Aven | On the interpretation of alternative uncertainty representations in a reliability and risk analysis context | 10.1016/j.ress.2010.06.027

        Author | Title | https://doi.org/10.3233/JAD-150520

    Only one primary author is expected.
    """

    if not isinstance(citation, str):
        raise ValueError("Citation must be a string")

    citation = citation.strip()

    # Split into exactly 3 parts:
    # author | title | DOI
    parts = [part.strip() for part in citation.split("|")]

    if len(parts) != 3:
        raise ValueError(
            f"Expected 'Author | Title | DOI', "
            f"but found {len(parts)} parts"
        )

    author = parts[0]
    title = parts[1]
    doi_raw = parts[2]

    if not author:
        raise ValueError("No author found")

    if not title:
        raise ValueError("No title found")

    if not doi_raw:
        raise ValueError("No DOI found")

    # normalize doi, since some have weird formatting or lack the https/http prefix

    doi = doi_raw.strip()

    doi = re.sub(
        r"^(https?://)?(dx\.)?doi\.org/",
        "",
        doi,
        flags=re.IGNORECASE
    )

    doi = re.sub(
        r"^doi:\s*",
        "",
        doi,
        flags=re.IGNORECASE
    )

    doi = doi.strip().rstrip(".,;")

    # Validate that something DOI-like remains
    if not re.match(r"^10\.\d{4,9}/\S+$", doi, re.IGNORECASE):
        raise ValueError(
            f"Invalid DOI format: {doi_raw}"
        )

    # author parsing

    author = author.strip()

    if "," in author:
        parts_author = author.split(",", 1)

        lastname = parts_author[0].strip()
        firstname = parts_author[1].strip()

    else:
        name_parts = author.split()
        if len(name_parts) == 1:
            firstname = ""
            lastname = name_parts[0]
        else:
            firstname = " ".join(name_parts[:-1])
            lastname = name_parts[-1]

    return {
        "raw": citation,
        "first_author_lastname": lastname,
        "first_author_firstname": firstname,
        "author_raw": author,
        "year": None,
        "title": title,
        "doi": doi,
        "doi_provided": True,
        "name_complete": len(firstname) > 2
    }

def format_author_name(firstname, lastname):
    """
    Builds a 'Firstname M. Lastname' style name.
    """

    lastname = lastname.strip()

    if not firstname:
        return lastname

    tokens = firstname.strip().split()
    normalized_tokens = []

    for token in tokens:
        clean = token.rstrip(".")

        if len(clean) == 1:
            normalized_tokens.append(f"{clean}.")
        else:
            normalized_tokens.append(clean)

    return f"{' '.join(normalized_tokens)} {lastname}".strip()


# Name matching functions
def normalize_name(name):
    """
    Normalizes an author name so that formatting differences
    don't prevent two versions of the same name from matching.

    Examples:

        'Alexis P. Rouillard'
        'A. P. Rouillard'
        'A.P. Rouillard'
        'Alexis Paul Rouillard'
        'Rouillard, Alexis P.'

    are all converted into comparable pieces.
    """

    if not name:
        return ""

    name = str(name).strip().lower()

    # Remove accents
    name = unicodedata.normalize("NFKD", name)
    name = "".join(
        char for char in name
        if not unicodedata.combining(char)
    )

    # Handle "Last, First Middle"
    if "," in name:
        parts = name.split(",", 1)
        name = f"{parts[1]} {parts[0]}"

    # Turn punctuation into spaces.
    # This makes:
    #   A.P. -> A P
    #   A. P. -> A P
    name = re.sub(r"[^a-z\s]", " ", name)

    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name).strip()

    return name


def get_name_parts(name):
    """
    Returns:

        first_name
        last_name
        middle_names

    from a normalized name.
    """

    name = normalize_name(name)

    if not name:
        return "", "", []

    parts = name.split()

    if len(parts) == 1:
        return "", parts[0], []

    first_name = parts[0]
    last_name = parts[-1]
    middle_names = parts[1:-1]

    return first_name, last_name, middle_names


def author_names_match(cited_name, database_name):
    """
    Determines whether two author names likely refer to
    the same person despite differences in initials,
    middle names, punctuation, or name ordering.

    Examples that should match:

        Alexis P. Rouillard
        A. P. Rouillard

        Alexis P. Rouillard
        Alexis Paul Rouillard

        Alexis P. Rouillard
        Alexis Rouillard

        Alexis P. Rouillard
        Rouillard, Alexis P.

    """

    cited_first, cited_last, cited_middle = get_name_parts(cited_name)
    db_first, db_last, db_middle = get_name_parts(database_name)

   
    # Last name must match
    if not cited_last or not db_last:
        return False

    if cited_last != db_last:
        return False

    # 2. First name must match exactly or by initial
    if not cited_first or not db_first:
        return False

    first_names_match = (
        cited_first == db_first
        or cited_first[0] == db_first[0]
    )

    if not first_names_match:
        return False
    
    # optional middle name matching
    if not cited_middle or not db_middle:
        return True

    # if middle, compare middle name initials

    for cited, db in zip(cited_middle, db_middle):

        if cited == db:
            continue

        if cited[0] == db[0]:
            continue

        return False

    return True


def find_matching_author(cited_name, found_authors):
    """
    Searches the authors returned by Hallucinator/OpenAlex
    and returns the matching author if one exists.
    """

    for database_author in found_authors or []:

        if author_names_match(cited_name, database_author):
            return database_author

    return None


# building Reference objects

def build_reference_from_citation(raw_citation):
    """
    Parses a raw citation string into title/authors/doi,
    then builds a hallucinator Reference object.
    """
    parsed = parse_single_citation(raw_citation)

    title = parsed["title"]

    firstname = parsed["first_author_firstname"]
    lastname = parsed["first_author_lastname"]

    name = format_author_name(
        firstname,
        lastname
    )

    return Reference(
        title,
        authors=[name] if name else [],
        doi=parsed["doi"],
        raw_citation=raw_citation
    )


def explain_result(r, author_match=None):
    """
    Explains why a citation received its status. Mostly for debugging.
    """

    if r.status == "verified":
        return "title and author both matched a database record"

    if r.status == "not_found":
        return "title could not be found in any checked database"

    found_count = len(r.found_authors) if r.found_authors else 0

    if author_match:
        return (
            f"title was found (source: {r.source}), "
            f"and author matched after name normalization. "
            f"cited author(s): {r.ref_authors}, "
            f"database match: {author_match}"
        )

    return (
        f"title was found (source: {r.source}), "
        f"but author did not match. "
        f"cited author(s): {r.ref_authors}, "
        f"database had {found_count} author(s) on record"
    )


def build_reference_result(raw_citation, r):
    """
    Packages a validation result into a JSON-serializable dict.
    """

    title_found = r.status != "not_found"

    # Even if Hallucinator says "mismatch", check the actual
    # author names it found using the more flexible matcher.

    author_match = None

    if r.found_authors and r.ref_authors:

        cited_author = r.ref_authors[0]

        author_match = find_matching_author(
            cited_author,
            r.found_authors
        )

    # Hallucinator says verified OR our flexible check finds
    # an equivalent author.
    author_matched = (
        r.status == "verified"
        or author_match is not None
    )

    # If the title exists and we found the author ourselves,
    # treat it as verified.
    if author_matched and title_found:
        final_status = "verified"
    else:
        final_status = r.status

    result = {
        "citation": raw_citation,
        "status": final_status,
        "title_found": title_found,
        "author_matched": author_matched,
        "ref_authors": r.ref_authors,
        "found_authors_count": (
            len(r.found_authors)
            if r.found_authors
            else 0
        ),
        "reason": explain_result(r, author_match),
        "failed_dbs": r.failed_dbs,
        "retracted": bool(
            r.retraction_info
            and r.retraction_info.is_retracted
        )
    }

    # Helpful for debugging / research transparency
    if author_match:
        result["matched_database_author"] = author_match

    if r.retraction_info and r.retraction_info.is_retracted:
        result["retraction_source"] = (
            r.retraction_info.retraction_source
        )
        result["retraction_doi"] = (
            r.retraction_info.retraction_doi
        )

    if r.doi_info:
        result["doi_valid"] = r.doi_info.valid

    return result


def validate_references(input_file, output_file):

    data = load_file(input_file)

    if not data:
        print(f"No data found in {input_file}")
        return

    existing_results = load_file(output_file)

    completed_ids = {
        r["id"]
        for r in existing_results
        if isinstance(r, dict) and "id" in r
    }

    results_out = existing_results.copy()

    for record in data:

        record_id = record.get("id", "unknown_id")

        if record_id in completed_ids:
            print(f"Skipping already completed: {record_id}")
            continue

        print(f"\n=== Record: {record_id} ===")

        raw_citations = (
            record.get("response", {})
            .get("references", [])
        )

        references = []
        valid_citations = []
        skipped_citations = []

        for raw_citation in raw_citations:

            # Some input files contain citation dictionaries
            # instead of plain citation strings.
            if isinstance(raw_citation, dict):

                raw_citation = raw_citation.get("citation")

            if not isinstance(raw_citation, str):

                skipped_citations.append({
                    "citation": raw_citation,
                    "reason": "not a string"
                })

                continue

            try:

                references.append(
                    build_reference_from_citation(
                        raw_citation
                    )
                )

                valid_citations.append(raw_citation)

            except Exception as e:

                print(
                    f"  [PARSE ERROR] "
                    f"{raw_citation[:80]}..."
                )

                print(
                    f"       -> "
                    f"{type(e).__name__}: {e}"
                )

                skipped_citations.append({
                    "citation": raw_citation,
                    "reason": str(e)
                })

        reference_results = []

        if references:

            def on_progress(event):

                if event.event_type == "checking":

                    print(
                        f"  [{event.index + 1}/{event.total}] "
                        f"Checking: {event.title}"
                    )

                elif event.event_type == "result":

                    r = event.result

                    icon = {
                        "verified": "+",
                        "not_found": "?"
                    }.get(r.status, "~")

                    src = (
                        f" ({r.source})"
                        if r.source
                        else ""
                    )

                    print(
                        f"  [{icon}] "
                        f"{r.title}{src}"
                    )

            try:

                results = validator.check(
                    references,
                    progress=on_progress
                )

                for raw_citation, r in zip(
                    valid_citations,
                    results
                ):

                    reference_results.append(
                        build_reference_result(
                            raw_citation,
                            r
                        )
                    )

            except Exception as e:

                print(
                    f"  [BATCH ERROR] "
                    f"{type(e).__name__}: {e}"
                )

                for raw_citation in valid_citations:

                    reference_results.append({
                        "citation": raw_citation,
                        "status": "CHECK",
                        "reason": (
                            f"batch validation error: {e}"
                        )
                    })

        # Unparseable citations
        for skipped in skipped_citations:

            reference_results.append({
                "citation": skipped["citation"],
                "status": "CHECK",
                "reason": (
                    f"could not parse citation: "
                    f"{skipped['reason']}"
                )
            })

        results_out.append({
            "id": record_id,
            "model": record.get("model"),
            "question": record.get("question"),
            "references": reference_results,
        })

        completed_ids.add(record_id)

        # Checkpoint
        temp_output_file = output_file + ".tmp"

        with open(temp_output_file, "w") as f:
            json.dump(
                results_out,
                f,
                indent=2
            )

        os.replace(
            temp_output_file,
            output_file
        )

        print(
            f"  Saved checkpoint: {record_id}"
        )

    # Final summary
    all_refs = [
        ref
        for r in results_out
        for ref in r["references"]
    ]

    total = len(all_refs)

    verified = sum(
        1
        for r in all_refs
        if r.get("status") == "verified"
    )

    not_found = sum(
        1
        for r in all_refs
        if r.get("status") == "not_found"
    )

    mismatched = sum(
        1
        for r in all_refs
        if r.get("status")
        not in ("verified", "not_found", "CHECK")
    )

    check = sum(
        1
        for r in all_refs
        if r.get("status") == "CHECK"
    )

    print(f"\n{'='*40}")
    print(f"Total citations:  {total}")

    if total > 0:

        print(
            f"Verified:         "
            f"{verified} "
            f"({verified/total*100:.1f}%)"
        )

        print(
            f"Not found:        "
            f"{not_found} "
            f"({not_found/total*100:.1f}%)"
        )

        print(
            f"Author mismatch:  "
            f"{mismatched} "
            f"({mismatched/total*100:.1f}%)"
        )

        print(
            f"CHECK:            "
            f"{check} "
            f"({check/total*100:.1f}%)"
        )

    print(f"Saved to {output_file}")


if __name__ == "__main__":
    
    validate_references(
        input_file="data/responses/gemini/responses_gem_S1980519_astrophys.json",
        output_file="data/verification/gemini/checked_gem_S1980519_astrophys.json"
    )
    
    


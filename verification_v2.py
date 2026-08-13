"""
Checks references for hallucinated citations against various databases. 
Utilizes the hallucinator library: https://github.com/gianlucasb/hallucinator. Note that this library provides
an estimate of whether a reference is likely to be real or not, and does not 100% guarantee that a reference is real or fake.

Reports back information about hallucinated and real sources, such as which information mismatches. Sends results to a JSON.
"""

import json
import os
import re
from dotenv import load_dotenv
from hallucinator import Reference, Validator, ValidatorConfig
from prompt_llm_task1 import load_file

load_dotenv()

###### Settings for the validator ######
config = ValidatorConfig()
config.check_openalex_authors = True  # checks author against openalex
config.openalex_key = os.getenv("API_KEY")
config.crossref_mailto = os.getenv("EMAIL")
validator = Validator(config)


def parse_single_citation(citation):
    """
    Parses a single citation string into its components: first author, year, title, and DOI. Returns a dictionary with these components.
    """
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
        after_year = citation[year_match.end():].lstrip(". ")  # does this cut off titles with colons?
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


def format_author_name(firstname, lastname):
    """
    Builds a "Firstname M. Lastname" style name for lookup purposes.
    Single-letter tokens in the first/middle name (e.g. a middle initial
    like "W" from "Stephen W. Kahler") get a period re-added, since
    parse_single_citation strips trailing periods during parsing, and
    OpenAlex/CrossRef records commonly store initials WITH periods
    (e.g. "Stephen W. Kahler", not "Stephen W Kahler"). Without this,
    otherwise-correct citations were failing author matching purely due
    to the missing period.
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


def build_reference_from_citation(raw_citation):
    """
    Parses a raw citation string into title/authors/doi, then builds a
    hallucinator Reference object. If title cannot be parsed, the citation is skipped (required for validation).
    """
    parsed = parse_single_citation(raw_citation)

    title = parsed.get("title") or ""
    if not title:
        raise ValueError("No title could be parsed from citation; skipping")  # NEEDS TITLE!

    firstname = parsed.get("first_author_firstname") or ""
    lastname = parsed.get("first_author_lastname") or ""
    name = format_author_name(firstname, lastname)
    authors = [name] if name else []

    doi = parsed.get("doi")  # None is fine here, unlike title

    return Reference(
        title,
        authors=authors,
        doi=doi,
        raw_citation=raw_citation
    )

def explain_result(r):
    """
    Given a ValidationResult, works out WHY it landed on its status:
    title not found at all, vs. title found but author didn't match.
    """
    if r.status == "verified":
        return "title and author both matched a database record"

    if r.status == "not_found":
        return "title could not be found in any checked database"

    found_count = len(r.found_authors) if r.found_authors else 0
    return (
        f"title was found (source: {r.source}), but author did not match. "
        f"cited author(s): {r.ref_authors}, database had {found_count} author(s) on record"
    )


def build_reference_result(raw_citation, r):
    """
    Packages a single ValidationResult into a JSON-serializable dict with
    the extra reasoning fields we care about for the research project:
    - whether the title was found at all
    - whether the cited author matches a real author on record
    - which database(s) confirmed it

    Full author lists (found_authors) are omitted since some records
    (e.g. large collaborations) can have hundreds of authors and would
    bloat the output. Only counts are kept.
    """
    title_found = r.status != "not_found"
    author_matched = r.status == "verified"

    result = {
        "citation": raw_citation,
        "status": r.status,
        "title_found": title_found,
        "author_matched": author_matched,
        "ref_authors": r.ref_authors,
        "found_authors_count": len(r.found_authors) if r.found_authors else 0,
        "reason": explain_result(r),
        "failed_dbs": r.failed_dbs,
        "retracted": bool(r.retraction_info and r.retraction_info.is_retracted),
    }

    if r.retraction_info and r.retraction_info.is_retracted:
        result["retraction_source"] = r.retraction_info.retraction_source
        result["retraction_doi"] = r.retraction_info.retraction_doi

    if r.doi_info:
        result["doi_valid"] = r.doi_info.valid

    return result

def validate_references(input_file, output_file):
    """
    Loads a task-2 JSON file (list of responses, each with
    response.references), validates every reference against academic
    databases via hallucinator, and saves results to output_file.

    Safe to re-run: records already present in output_file are skipped,
    and results are checkpointed after every record so a crash mid-run
    doesn't lose completed work.
    """
    data = load_file(input_file)
    if not data:
        print(f"No data found in {input_file}")
        return

    existing_results = load_file(output_file)
    completed_ids = {r["id"] for r in existing_results if isinstance(r, dict) and "id" in r}
    results_out = existing_results.copy()

    # print(f"Found {len(completed_ids)} already-completed records.")

    # loop through responses
    for record in data: 
        record_id = record.get("id", "unknown_id")

        if record_id in completed_ids:
            print(f"Skipping already completed: {record_id}")
            continue

        print(f"\n=== Record: {record_id} ===")
        raw_citations = record.get("response", {}).get("references", [])

        references = []
        valid_citations = []
        skipped_citations = []
        
        # loop through citation strings (& check if string)
        for raw_citation in raw_citations:
            if not isinstance(raw_citation, str):
                skipped_citations.append({"citation": raw_citation, "reason": "not a string"})
                continue
            try:
                references.append(build_reference_from_citation(raw_citation))
                valid_citations.append(raw_citation)
            except Exception as e:
                print(f"  [PARSE ERROR] {raw_citation[:80]}...")
                print(f"       -> {type(e).__name__}: {e}")
                skipped_citations.append({"citation": raw_citation, "reason": str(e)})

        reference_results = []

        if references:
            def on_progress(event):
                if event.event_type == "checking":
                    print(f"  [{event.index + 1}/{event.total}] Checking: {event.title}")
                elif event.event_type == "result":
                    r = event.result
                    icon = {"verified": "+", "not_found": "?"}.get(r.status, "~")
                    src = f" ({r.source})" if r.source else ""
                    print(f"  [{icon}] {r.title}{src}")

            try:
                results = validator.check(references, progress=on_progress) # batch checks all refs per response
                for raw_citation, r in zip(valid_citations, results):
                    reference_results.append(build_reference_result(raw_citation, r))
            except Exception as e:
                print(f"  [BATCH ERROR] {type(e).__name__}: {e}")
                for raw_citation in valid_citations:
                    reference_results.append({
                        "citation": raw_citation,
                        "status": "CHECK",
                        "reason": f"batch validation error: {e}"
                    })

        # unparseable citations still get a result entry, flagged for manual check
        for skipped in skipped_citations:
            reference_results.append({
                "citation": skipped["citation"],
                "status": "CHECK",
                "reason": f"could not parse citation: {skipped['reason']}"
            })

        results_out.append({
            "id": record_id,
            "model": record.get("model"),
            "question": record.get("question"),
            "references": reference_results,
        })
        completed_ids.add(record_id)

        # checkpoint after every record
        temp_output_file = output_file + ".tmp"
        with open(temp_output_file, "w") as f:
            json.dump(results_out, f, indent=2)
        os.replace(temp_output_file, output_file)
        print(f"  Saved checkpoint: {record_id}")

    # final summary across everything in results_out
    all_refs = [ref for r in results_out for ref in r["references"]]
    total = len(all_refs)
    verified = sum(1 for r in all_refs if r.get("status") == "verified")
    not_found = sum(1 for r in all_refs if r.get("status") == "not_found")
    mismatched = sum(1 for r in all_refs if r.get("status") not in ("verified", "not_found", "CHECK"))
    check = sum(1 for r in all_refs if r.get("status") == "CHECK")

    print(f"\n{'='*40}")
    print(f"Total citations:  {total}")
    if total > 0:
        print(f"Verified:         {verified} ({verified/total*100:.1f}%)")
        print(f"Not found:        {not_found} ({not_found/total*100:.1f}%)")
        print(f"Author mismatch:  {mismatched} ({mismatched/total*100:.1f}%)")
        print(f"CHECK:            {check} ({check/total*100:.1f}%)")
    print(f"Saved to {output_file}")

# Instead of just checking if the author matches, we
# could also check if the author is a known expert (are they a real person, indentifiable on OpenAlex, google scholar, etc.).

if __name__ == "__main__":
    validate_references(
        input_file="data/responses/anthropic/test_verify.py",
        output_file="data/verification/short_verified_responses.json"
    )
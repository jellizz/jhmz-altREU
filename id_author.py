"""id_author.py

Given a verified JSON of references, identify author names & give more author information.

For each author:
1. 


"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY")
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY")

REQUEST_TIMEOUT = 15
OPENALEX_DELAY = 0.15
SEMANTIC_SCHOLAR_DELAY = 0.5


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def normalize_name(name: Optional[str]) -> str:
    """Normalize whitespace and strip surrounding whitespace."""
    if not name:
        return ""
    return re.sub(r"\s+", " ", str(name).strip())


def normalize_for_comparison(name: str) -> str:
    """Normalize a name for approximate comparison."""
    name = normalize_name(name).lower()
    name = re.sub(r"[^\w\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


def choose_longest_name(
    names: Optional[List[str]],
    fallback: Optional[str] = None,
) -> Optional[str]:
    """
    Return the longest available name.
    """
    candidates = []

    for name in names or []:
        name = normalize_name(name)
        if name:
            candidates.append(name)

    if fallback:
        fallback = normalize_name(fallback)
        if fallback:
            candidates.append(fallback)

    if not candidates:
        return None

    # Remove exact duplicates, keep order tho
    candidates = list(dict.fromkeys(candidates))

    return max(candidates, key=len)


def name_similarity_score(query: str, candidate: str) -> float:
    """
    Calculate a simple similarity score between two names.

    This is only used to select among search results returned by a database.
    It is not being used to verify authorship of the cited paper.
    """
    q = normalize_for_comparison(query)
    c = normalize_for_comparison(candidate)

    if not q or not c:
        return 0.0

    if q == c:
        return 1.0

    q_tokens = q.split()
    c_tokens = c.split()

    q_set = set(q_tokens)
    c_set = set(c_tokens)

    if not q_set:
        return 0.0

    overlap = len(q_set & c_set)
    token_score = overlap / len(q_set)

    surname_bonus = 0.0

    if q_tokens and c_tokens:
        if q_tokens[-1] == c_tokens[-1]:
            surname_bonus = 0.25

    return min(1.0, token_score * 0.75 + surname_bonus)


# ---------------------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------------------

def openalex_headers() -> Dict[str, str]:
    """Build OpenAlex request headers."""
    headers = {}

    if OPENALEX_API_KEY:
        headers["X-API-KEY"] = OPENALEX_API_KEY

    return headers


def search_openalex(
    name: str,
    max_results: int = 5,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Search OpenAlex for an author.

    Returns:
        ("found", candidates)
        ("not_found", [])
        ("error", [])
    """
    url = "https://api.openalex.org/authors"

    params = {
        "search": name,
        "per-page": max_results,
    }

    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY

    try:
        response = requests.get(
            url,
            params=params,
            headers=openalex_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        data = response.json()

        results = data.get("results", []) if isinstance(data, dict) else []

        candidates = []

        for author in results:
            summary_stats = author.get("summary_stats") or {}

            candidates.append({
                "source": "openalex",
                "author_id": author.get("id"),
                "display_name": author.get("display_name"),

                # These are useful for finding the richest available name.
                "raw_author_names": author.get("raw_author_names", []),
                "display_name_alternatives": author.get(
                    "display_name_alternatives",
                    [],
                ),

                # Author-level metrics.
                "works_count": author.get("works_count"),
                "cited_by_count": author.get("cited_by_count"),
                "h_index": summary_stats.get("h_index"),
                "i10_index": summary_stats.get("i10_index"),
            })

        if not candidates:
            return "not_found", []

        return "found", candidates

    except requests.RequestException as exc:
        print(f"    OpenAlex request error for '{name}': {exc}")
        return "error", []

    except Exception as exc:
        print(f"    OpenAlex parsing error for '{name}': {exc}")
        return "error", []


def choose_openalex_candidate(
    query_name: str,
    candidates: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Choose the best OpenAlex candidate based on name similarity.

    Once the best candidate is selected, its longest available name will be
    used as `fullest_name`.
    """
    if not candidates:
        return None

    scored = []

    for candidate in candidates:
        display_name = candidate.get("display_name") or ""

        score = name_similarity_score(
            query_name,
            display_name,
        )

        # Also compare against OpenAlex alternative names.
        alternatives = candidate.get(
            "display_name_alternatives"
        ) or []

        for alternative in alternatives:
            score = max(
                score,
                name_similarity_score(
                    query_name,
                    alternative,
                ),
            )

        # Also compare against raw author names.
        raw_names = candidate.get("raw_author_names") or []

        for raw_name in raw_names:
            score = max(
                score,
                name_similarity_score(
                    query_name,
                    raw_name,
                ),
            )

        scored.append((score, candidate))

    scored.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    best_score, best_candidate = scored[0]

    # Require a reasonable name match.
    if best_score >= 0.65:
        best_candidate = dict(best_candidate)
        best_candidate["_match_score"] = best_score
        return best_candidate

    return None


# SEMANTIC SCHOLAR CHECK (fallback)
def semantic_scholar_headers() -> Dict[str, str]:
    """Build Semantic Scholar request headers."""
    headers = {
        "User-Agent": "id_author/1.0",
    }

    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY

    return headers


def search_semantic_scholar(
    name: str,
    max_results: int = 5,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Search Semantic Scholar for an author.

    Returns:
        ("found", candidates)
        ("not_found", [])
        ("error", [])
    """
    url = (
        "https://api.semanticscholar.org/graph/v1/"
        "author/search"
    )

    params = {
        "query": name,
        "limit": max_results,
        "fields": (
            "name,aliases,url,paperCount,"
            "citationCount,hIndex"
        ),
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=semantic_scholar_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        data = response.json()

        results = data.get("data", []) if isinstance(data, dict) else []

        candidates = []

        for author in results:
            candidates.append({
                "source": "semantic_scholar",
                "author_id": author.get("authorId"),
                "name": author.get("name"),
                "aliases": author.get("aliases"),
                "url": author.get("url"),
                "paper_count": author.get("paperCount"),
                "citation_count": author.get("citationCount"),
                "h_index": author.get("hIndex"),
            })

        if not candidates:
            return "not_found", []

        return "found", candidates

    except requests.RequestException as exc:
        print(
            f"    Semantic Scholar request error "
            f"for '{name}': {exc}"
        )
        return "error", []

    except Exception as exc:
        print(
            f"    Semantic Scholar parsing error "
            f"for '{name}': {exc}"
        )
        return "error", []


def choose_semantic_scholar_candidate(
    query_name: str,
    candidates: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Choose the best Semantic Scholar candidate by name similarity."""
    if not candidates:
        return None

    scored = []

    for candidate in candidates:
        names = []

        if candidate.get("name"):
            names.append(candidate["name"])

        names.extend(
            candidate.get("aliases") or []
        )

        score = 0.0

        for name in names:
            score = max(
                score,
                name_similarity_score(
                    query_name,
                    name,
                ),
            )

        scored.append((score, candidate))

    scored.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    best_score, best_candidate = scored[0]

    if best_score >= 0.65:
        best_candidate = dict(best_candidate)
        best_candidate["_match_score"] = best_score
        return best_candidate

    return None


def identify_author(
    query_name: str,
) -> Dict[str, Any]:
    """
    Identify and increase data for one author.

    Lookup order:
        1. OpenAlex
        2. Semantic Scholar only if OpenAlex fails to identify them
    """

    query_name = normalize_name(query_name)

    result = {
        "query": query_name,
        "exists": False,
        "status": None,
        "source": None,
        "chosen_name": None,
        "fullest_name": None,
        "openalex": None,
        "semantic_scholar": None,
        "candidates": [],
    }

    # openalex
    print(f"    OpenAlex: {query_name}")

    oa_status, oa_candidates = search_openalex(
        query_name
    )

    if oa_status == "found":

        chosen_oa = choose_openalex_candidate(
            query_name,
            oa_candidates,
        )

        if chosen_oa:

            raw_names = (
                chosen_oa.get("raw_author_names")
                or []
            )

            display_name = (
                chosen_oa.get("display_name")
            )

            alternatives = (
                chosen_oa.get(
                    "display_name_alternatives"
                )
                or []
            )

            fullest_name = choose_longest_name(
                raw_names + alternatives,
                fallback=display_name,
            )

            result.update({
                "exists": True,
                "status": "identified",
                "source": "openalex",
                "chosen_name": display_name,
                "fullest_name": fullest_name,
                "openalex": chosen_oa,
                "candidates": oa_candidates,
            })

            # IMPORTANT:
            # OpenAlex found the person.
            # Do NOT call Semantic Scholar.
            return result

    elif oa_status == "error":

        result["status"] = "openalex_error"

    time.sleep(OPENALEX_DELAY)

    # semantic scholar

    print(
        f"    Semantic Scholar fallback: "
        f"{query_name}"
    )

    ss_status, ss_candidates = search_semantic_scholar(
        query_name
    )

    if ss_status == "found":

        chosen_ss = choose_semantic_scholar_candidate(
            query_name,
            ss_candidates,
        )

        if chosen_ss:

            names = []

            if chosen_ss.get("name"):
                names.append(
                    chosen_ss["name"]
                )

            names.extend(
                chosen_ss.get("aliases") or []
            )

            fullest_name = choose_longest_name(
                names,
                fallback=chosen_ss.get("name"),
            )

            result.update({
                "exists": True,
                "status": "identified",
                "source": "semantic_scholar",
                "chosen_name": chosen_ss.get("name"),
                "fullest_name": fullest_name,
                "semantic_scholar": chosen_ss,
                "candidates": ss_candidates,
            })

            return result

    elif ss_status == "error":

        result["status"] = "semantic_scholar_error"

    # ------------------------------------------------------------------
    # Neither database identified the person
    # ------------------------------------------------------------------

    if (
        oa_status == "error"
        and ss_status == "error"
    ):
        result["status"] = "lookup_error"

    else:
        result["status"] = "not_found"

    result["candidates"] = (
        oa_candidates + ss_candidates
    )

    return result


# ---------------------------------------------------------------------------
# Process a JSON file
# ---------------------------------------------------------------------------

def process_file(
    path: str,
    out_dir: Optional[str] = None,
) -> str:

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as fh:
        data = json.load(fh)

    if not isinstance(data, list):
        raise ValueError(
            f"Expected top-level JSON list in {path}"
        )

    total_authors = 0
    identified_count = 0
    not_found_count = 0
    error_count = 0

    for item_index, item in enumerate(
        data,
        start=1,
    ):

        refs = item.get(
            "references",
            [],
        ) or []

        for ref_index, ref in enumerate(
            refs,
            start=1,
        ):

            ref_authors = ref.get(
                "ref_authors",
                [],
            ) or []

            if not ref_authors:
                continue

            identified = ref.setdefault(
                "identified_authors",
                [],
            )

            for cited in ref_authors:

                cited_norm = normalize_name(cited)

                if not cited_norm:
                    continue

                total_authors += 1

                # ------------------------------------------------------
                # Avoid repeating an existing lookup.
                # ------------------------------------------------------

                already = next(
                    (
                        a
                        for a in identified
                        if normalize_name(
                            a.get("cited_name")
                        ) == cited_norm
                    ),
                    None,
                )

                if already:
                    continue

                # ------------------------------------------------------
                # If the previous verification step already matched
                # this author to a database author, use that richer
                # matched name as the query.
                #
                # Example:
                #
                # ref_authors:
                #     ["K. Anders Ericsson"]
                #
                # matched_database_author:
                #     "K. Anders Ericsson"
                # ------------------------------------------------------

                matched_db = normalize_name(
                    ref.get(
                        "matched_database_author"
                    )
                )

                if matched_db:
                    query_name = matched_db
                else:
                    query_name = cited_norm

                print(
                    f"  Reference {item_index}, "
                    f"author {ref_index}: "
                    f"{query_name}"
                )

                result = identify_author(
                    query_name
                )

                # Preserve the original cited name.
                result["cited_name"] = cited_norm

                # Preserve the name already established by
                # the verification pipeline, if available.
                if matched_db:
                    result[
                        "previously_matched_database_author"
                    ] = matched_db

                identified.append(result)

                if result["exists"]:
                    identified_count += 1

                elif result["status"] == "not_found":
                    not_found_count += 1

                elif result["status"] == "lookup_error":
                    error_count += 1

    # ------------------------------------------------------------------
    # Output path
    # ------------------------------------------------------------------

    if out_dir:

        os.makedirs(
            out_dir,
            exist_ok=True,
        )

        base = os.path.basename(path)

        if base.lower().endswith(".json"):
            base = base[:-5]

        out_path = os.path.join(
            out_dir,
            f"{base}_authors_identified.json",
        )

    else:

        directory = os.path.dirname(path)

        base = os.path.basename(path)

        if base.lower().endswith(".json"):
            base = base[:-5]

        out_path = os.path.join(
            directory,
            f"{base}_authors_identified.json",
        )

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    with open(
        out_path,
        "w",
        encoding="utf-8",
    ) as fh:

        json.dump(
            data,
            fh,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("=" * 60)
    print(f"Finished: {path}")
    print(f"  Author lookups: {total_authors}")
    print(f"  Identified:     {identified_count}")
    print(f"  Not found:      {not_found_count}")
    print(f"  Lookup errors:  {error_count}")
    print(f"  Wrote:          {out_path}")
    print("=" * 60)
    print()

    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Identify and enrich authors using "
            "OpenAlex first and Semantic Scholar as fallback."
        )
    )

    parser.add_argument(
        "paths",
        nargs="+",
        help=(
            "One or more JSON files or directories "
            "to process"
        ),
    )

    parser.add_argument(
        "--out-dir",
        help=(
            "Optional directory for output files. "
            "If omitted, files are written next to "
            "the input files."
        ),
    )

    args = parser.parse_args()

    files: List[str] = []

    for p in args.paths:

        if os.path.isdir(p):

            for root, _, filenames in os.walk(p):

                for fn in filenames:

                    # Don't process previous outputs again.
                    if (
                        fn.lower().endswith(".json")
                        and not fn.endswith(
                            "_authors_identified.json"
                        )
                    ):
                        files.append(
                            os.path.join(
                                root,
                                fn,
                            )
                        )

        elif os.path.isfile(p):

            files.append(p)

        else:

            print(
                f"Skipping unknown path: {p}"
            )

    if not files:

        print(
            "No JSON files found to process."
        )

        return

    if args.out_dir:

        os.makedirs(
            args.out_dir,
            exist_ok=True,
        )

    print(
        f"Found {len(files)} JSON file(s)."
    )
    print()

    for path in files:

        try:

            process_file(
                path,
                args.out_dir,
            )

        except Exception as exc:

            print(
                f"ERROR processing {path}: "
                f"{exc}"
            )


if __name__ == "__main__":
    main()
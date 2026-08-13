"""id_author.py

Given a verified JSON of references, identify author names and add information.

For each author:
1. If the citation has been verified ("status": "verified"), use the
   previously identified database author when available.
2. If the citation is a "mismatch" or "not_found", search OpenAlex using
   the cited author name, restricted to the same subfield/topic as the
   original paper.
3. Add:
      "author_exists": boolean
      "fullest_name": fullest plausible name from the SAME OpenAlex author
      "h_index": OpenAlex h-index
      "works_count": OpenAlex total works count for the author
      "organization_country_id": country code of their organization, if available
4. Modify the original JSON file in place.
"""

from __future__ import annotations

import json
import os
import re
import time

import requests
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

OPENALEX_EMAIL = os.getenv("EMAIL")
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY")

OPENALEX_AUTHORS_URL = "https://api.openalex.org/authors"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"

REQUEST_TIMEOUT = 15

# Minimum time between OpenAlex requests.
#
# Increased from 0.25 seconds because this script is intended for
# high-volume processing.
REQUEST_DELAY = 0.02

# Retry settings for rate limiting / temporary failures.
MAX_RETRIES = 5
BACKOFF = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_name(name):
    """Normalize whitespace and strip surrounding whitespace."""

    if not name:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(name).strip(),
    )


def normalize_for_comparison(name):
    """Normalize a name for comparison."""

    name = normalize_name(name).lower()

    return re.sub(
        r"\s+",
        " ",
        re.sub(
            r"[^\w\s]",
            "",
            name,
        ),
    )


def name_similarity(query, candidate):
    """
    Calculate a conservative name similarity score.

    This is used to choose among OpenAlex's returned author records.
    """

    query = normalize_for_comparison(query)
    candidate = normalize_for_comparison(candidate)

    if not query or not candidate:
        return 0

    if query == candidate:
        return 1.0

    q = set(query.split())
    c = set(candidate.split())

    score = len(q & c) / len(q)

    query_tokens = query.split()
    candidate_tokens = candidate.split()

    if (
        query_tokens
        and candidate_tokens
        and query_tokens[-1] == candidate_tokens[-1]
    ):
        score += 0.25

    return min(score, 1.0)


def has_initials(name):
    """
    Return True if a name contains a one-letter initial token.

    Examples:
        "A. Smith"        -> True
        "A Smith"         -> True
        "Jane M. Smith"   -> True
        "Jane Smith"      -> False
        "Smith, Jane"     -> False
    """

    tokens = normalize_name(name).split()

    for token in tokens:

        cleaned = re.sub(
            r"[^A-Za-z]",
            "",
            token,
        )

        if len(cleaned) == 1:
            return True

    return False


def is_bad_name(name):
    """
    Reject obvious non-individual names.

    These can appear in OpenAlex author-name fields when a paper is
    associated with a collaboration, consortium, or group.
    """

    lowered = normalize_name(name).lower()

    bad_phrases = [
        "on behalf of",
        "collaboration",
        "collaborations",
        "consortium",
        "group",
        "team",
    ]

    return any(
        phrase in lowered
        for phrase in bad_phrases
    )


def longest_name(author):
    """
    Select the fullest plausible name from the SAME OpenAlex author.

    Selection rules:

    1. Collect display_name, display_name_alternatives, and raw_author_names.
    2. Remove obvious organization/collaboration strings.
    3. Prefer names that contain NO initials.
    4. Among those, select the longest.
    5. If every usable name contains initials, select the longest available
       version rather than guessing.
    """

    names = []

    if author.get("display_name"):
        names.append(
            author["display_name"]
        )

    names.extend(
        author.get(
            "display_name_alternatives"
        ) or []
    )

    names.extend(
        author.get(
            "raw_author_names"
        ) or []
    )

    names = [
        normalize_name(name)
        for name in names
        if normalize_name(name)
        and not is_bad_name(
            normalize_name(name)
        )
    ]

    # Remove exact duplicates while preserving order.
    names = list(
        dict.fromkeys(names)
    )

    if not names:
        return None

    # Prefer names without initials.
    non_initial_names = [
        name
        for name in names
        if not has_initials(name)
    ]

    if non_initial_names:

        return max(
            non_initial_names,
            key=len,
        )

    # If OpenAlex only gives initials, KEEP THE INITIALS.
    return max(
        names,
        key=len,
    )


# ---------------------------------------------------------------------------
# Rate-limited OpenAlex request
# ---------------------------------------------------------------------------

_last_request = 0


def openalex_request(
    url,
    params,
):
    """
    Make a rate-limited OpenAlex request with retry/backoff.
    """

    global _last_request

    # Enforce minimum delay between requests.
    elapsed = (
        time.time()
        - _last_request
    )

    if elapsed < REQUEST_DELAY:

        time.sleep(
            REQUEST_DELAY
            - elapsed
        )

    # Add email and API key to params.
    params = dict(params)

    if OPENALEX_EMAIL:

        params["mailto"] = (
            OPENALEX_EMAIL
        )

    if OPENALEX_API_KEY:

        params["api_key"] = (
            OPENALEX_API_KEY
        )

    headers = {}

    if OPENALEX_EMAIL:

        headers["User-Agent"] = (
            f"mailto:{OPENALEX_EMAIL}"
        )

    for attempt in range(
        MAX_RETRIES
    ):

        try:

            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )

            _last_request = time.time()

            # -----------------------------------------------------------
            # Rate limited.
            # -----------------------------------------------------------

            if response.status_code == 429:

                wait = (
                    BACKOFF ** attempt
                )

                print(
                    f"    OpenAlex rate limited. "
                    f"Waiting {wait}s..."
                )

                time.sleep(wait)

                continue

            # -----------------------------------------------------------
            # Other HTTP errors.
            # -----------------------------------------------------------

            response.raise_for_status()

            return response.json()

        except requests.RequestException as exc:

            if attempt == MAX_RETRIES - 1:

                print(
                    f"    OpenAlex error: {exc}"
                )

                return None

            wait = (
                BACKOFF ** attempt
            )

            print(
                f"    OpenAlex request failed. "
                f"Retrying in {wait}s..."
            )

            time.sleep(wait)

    return None


# ---------------------------------------------------------------------------
# OpenAlex work/topic lookup
# ---------------------------------------------------------------------------

work_cache = {}


def get_work_topic(work_id):
    """
    Retrieve the primary topic/subfield information for the original
    OpenAlex work.

    Returns a dictionary containing:
        topic_id
        topic_name
        subfield_id
        subfield_name
        field_id
        field_name

    The result is cached because many references can belong to the same
    original work.
    """

    work_id = normalize_name(
        work_id
    )

    if not work_id:
        return None

    # ---------------------------------------------------------------
    # Normalize full OpenAlex URL to ID.
    # ---------------------------------------------------------------

    if work_id.startswith(
        "https://openalex.org/"
    ):

        work_id = work_id.rsplit(
            "/",
            1,
        )[-1]

    cache_key = work_id.lower()

    if cache_key in work_cache:

        return work_cache[
            cache_key
        ]

    print(
        f"  OpenAlex work/topic: {work_id}"
    )

    data = openalex_request(
        f"{OPENALEX_WORKS_URL}/{work_id}",
        {},
    )

    if not data:

        work_cache[cache_key] = None

        return None

    primary_topic = (
        data.get(
            "primary_topic"
        )
        or {}
    )

    topic_id = (
        primary_topic.get(
            "id"
        )
    )

    topic_name = (
        primary_topic.get(
            "display_name"
        )
    )

    subfield = (
        primary_topic.get(
            "subfield"
        )
        or {}
    )

    field = (
        primary_topic.get(
            "field"
        )
        or {}
    )

    result = {
        "topic_id": topic_id,
        "topic_name": topic_name,
        "subfield_id": subfield.get(
            "id"
        ),
        "subfield_name": subfield.get(
            "display_name"
        ),
        "field_id": field.get(
            "id"
        ),
        "field_name": field.get(
            "display_name"
        ),
    }

    work_cache[cache_key] = result

    return result


# ---------------------------------------------------------------------------
# OpenAlex author lookup
# ---------------------------------------------------------------------------

def find_author(
    name,
    subfield_id=None,
):
    """
    Search OpenAlex for an author.

    The author name is searched first. If a subfield is available, the
    search is restricted to works associated with that OpenAlex subfield.

    We deliberately keep this search conservative:
    - only one author search is made
    - per-page stays small
    - we do not perform fallback broad searches
    """

    name = normalize_name(name)

    if not name:
        return None

    # ---------------------------------------------------------------
    # Author search.
    #
    # NOTE:
    # OpenAlex author search itself does not provide the same direct
    # topic/subfield filtering mechanism as works search. Therefore,
    # the subfield constraint is applied through the author's works
    # using the returned author IDs.
    #
    # We first obtain a small candidate set from the name search.
    # Then we score those candidates using their works/topics.
    # ---------------------------------------------------------------

    data = openalex_request(
        OPENALEX_AUTHORS_URL,
        {
            "search": name,
            "per-page": 5,
        },
    )

    if not data:
        return None

    results = data.get(
        "results",
        [],
    )

    if not results:
        return None

    candidates = []

    for author in results:

        score = name_similarity(
            name,
            author.get(
                "display_name",
                "",
            ),
        )

        for alternative in (
            author.get(
                "display_name_alternatives"
            )
            or []
        ):

            score = max(
                score,
                name_similarity(
                    name,
                    alternative,
                ),
            )

        for raw_name in (
            author.get(
                "raw_author_names"
            )
            or []
        ):

            score = max(
                score,
                name_similarity(
                    name,
                    raw_name,
                ),
            )

        candidates.append(
            (
                score,
                author,
            )
        )

    # ---------------------------------------------------------------
    # Sort by name similarity.
    # ---------------------------------------------------------------

    candidates.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    # ---------------------------------------------------------------
    # Conservative threshold.
    # ---------------------------------------------------------------

    candidates = [
        (
            score,
            author,
        )
        for score, author in candidates
        if score >= 0.65
    ]

    if not candidates:

        return None

    # ---------------------------------------------------------------
    # If no subfield information is available, use the best name match.
    # ---------------------------------------------------------------

    if not subfield_id:

        return candidates[0][1]

    # ---------------------------------------------------------------
    # Check candidates against the target subfield.
    #
    # We use OpenAlex works for each candidate, but ONLY for the small
    # candidate set returned by the original author-name search.
    #
    # This avoids doing broad additional name searches.
    # ---------------------------------------------------------------

    for score, author in candidates:

        author_id = normalize_name(
            author.get("id")
        )

        if not author_id:

            continue

        # Strip URL prefix.
        if author_id.startswith(
            "https://openalex.org/"
        ):

            author_id = author_id.rsplit(
                "/",
                1,
            )[-1]

        # Search the author's works within the target subfield.
        #
        # OpenAlex work filtering supports author.id and primary_topic
        # subfield IDs.
        works_data = openalex_request(
            OPENALEX_WORKS_URL,
            {
                "filter": (
                    f"author.id:{author_id},"
                    f"primary_topic.subfield.id:{subfield_id}"
                ),
                "per-page": 1,
            },
        )

        if not works_data:

            continue

        count = (
            works_data.get(
                "meta",
                {},
            ).get(
                "count",
                0,
            )
        )

        if count > 0:

            return author

    # ---------------------------------------------------------------
    # No candidate was demonstrated to belong to the same subfield.
    #
    # Therefore, return None to be conservative. Else could pick some random person from
    # a completely unrelated subfield.
    # ---------------------------------------------------------------

    return None


# ---------------------------------------------------------------------------
# Process file
# ---------------------------------------------------------------------------

def process_file(path):

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as f:

        data = json.load(f)

    if not isinstance(data, list):

        raise ValueError(
            "Expected the JSON file to contain "
            "a top-level list."
        )

    # ---------------------------------------------------------------
    # Cache author results so identical names are not looked up
    # repeatedly.
    # ---------------------------------------------------------------

    cache = {}

    total = 0
    found = 0
    not_found = 0

    # Statistics for diagnostics.
    subfield_restricted = 0
    subfield_unavailable = 0

    for item in data:

        # -----------------------------------------------------------
        # Get the original paper's subfield.
        # -----------------------------------------------------------

        work_id = item.get(
            "id"
        )

        topic_info = get_work_topic(
            work_id
        )

        if topic_info:

            subfield_id = (
                topic_info.get(
                    "subfield_id"
                )
            )

            subfield_name = (
                topic_info.get(
                    "subfield_name"
                )
            )

        else:

            subfield_id = None
            subfield_name = None

        if subfield_id:

            subfield_restricted += 1

            print(
                f"  Subfield: "
                f"{subfield_name} "
                f"({subfield_id})"
            )

        else:

            subfield_unavailable += 1

            print(
                "  Subfield: unavailable "
                "(author search will remain "
                "name-conservative)"
            )

        # -----------------------------------------------------------
        # Process references.
        # -----------------------------------------------------------

        for ref in (
            item.get(
                "references",
                [],
            )
            or []
        ):

            authors = (
                ref.get(
                    "ref_authors",
                    [],
                )
                or []
            )

            if not authors:

                continue

            # The verification step stores the matched
            # database author at the reference level.
            matched_author = normalize_name(
                ref.get(
                    "matched_database_author"
                )
            )

            status = normalize_name(
                ref.get(
                    "status"
                )
            ).lower()

            for author_name in authors:

                cited_name = normalize_name(
                    author_name
                )

                if not cited_name:

                    continue

                total += 1

                # ---------------------------------------------------
                # Decide what name to search.
                # ---------------------------------------------------

                if (
                    status == "verified"
                    and matched_author
                ):

                    query_name = (
                        matched_author
                    )

                else:

                    query_name = (
                        cited_name
                    )

                # ---------------------------------------------------
                # Cache by:
                #
                #   queried name + subfield
                #
                # The same person/name may legitimately need to be
                # evaluated in different subfields.
                # ---------------------------------------------------

                cache_key = (
                    query_name.lower(),
                    subfield_id or "",
                )

                if cache_key in cache:

                    author = cache[
                        cache_key
                    ]

                else:

                    print(
                        f"  OpenAlex: "
                        f"{query_name}"
                    )

                    author = find_author(
                        query_name,
                        subfield_id=subfield_id,
                    )

                    cache[
                        cache_key
                    ] = author

                # ---------------------------------------------------
                # Build output.
                # ---------------------------------------------------

                author_info = {
                    "author_exists": False,
                    "fullest_name": None,
                    "h_index": None,
                    "works_count": None,
                    "organization_country_id": None,
                }

                if author:

                    author_info[
                        "author_exists"
                    ] = True

                    author_info[
                        "fullest_name"
                    ] = longest_name(
                        author
                    )

                    summary_stats = (
                        author.get(
                            "summary_stats"
                        )
                        or {}
                    )

                    author_info[
                        "h_index"
                    ] = summary_stats.get(
                        "h_index"
                    )

                    # OpenAlex reports this directly on the author
                    # record as their total number of works.
                    author_info[
                        "works_count"
                    ] = author.get(
                        "works_count"
                    )

                    # OpenAlex's current institutions.
                    institutions = (
                        author.get(
                            "last_known_institutions"
                        )
                        or []
                    )

                    if institutions:

                        institution = (
                            institutions[0]
                        )

                        author_info[
                            "organization_country_id"
                        ] = institution.get(
                            "country_code"
                        )

                    found += 1

                else:

                    not_found += 1

                # ---------------------------------------------------
                # Add information to identified_authors.
                # ---------------------------------------------------

                identified_authors = (
                    ref.setdefault(
                        "identified_authors",
                        [],
                    )
                )

                # Find an existing entry for this cited author.
                existing = next(
                    (
                        a
                        for a in identified_authors
                        if normalize_name(
                            a.get(
                                "cited_name"
                            )
                        ) == cited_name
                    ),
                    None,
                )

                if existing is None:

                    identified_authors.append({
                        "cited_name": cited_name,
                        **author_info,
                    })

                else:

                    existing.update(
                        author_info
                    )

    # ---------------------------------------------------------------
    # MODIFY ORIGINAL FILE IN PLACE
    # ---------------------------------------------------------------

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("=" * 60)
    print(f"Finished: {path}")
    print(f"Author lookups:       {total}")
    print(f"Found:                {found}")
    print(f"Not found:            {not_found}")
    print(f"Subfield restricted:  {subfield_restricted}")
    print(f"Subfield unavailable: {subfield_unavailable}")
    print(f"Modified:             {path}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    files_to_process = [
        # put file strings here!
    ]

    if (
        not OPENALEX_EMAIL
        and not OPENALEX_API_KEY
    ):

        print(
            "WARNING: Neither EMAIL nor "
            "OPENALEX_API_KEY was found in .env. "
            "Rate limits will be lower."
        )

    elif not OPENALEX_EMAIL:

        print(
            "WARNING: EMAIL was not found in .env. "
            "Using API key only."
        )

    elif not OPENALEX_API_KEY:

        print(
            "WARNING: OPENALEX_API_KEY was not found "
            "in .env. Using email only."
        )

    for path in files_to_process:

        if not os.path.isfile(path):

            print(
                f"Skipping missing file: {path}"
            )

            continue

        try:

            process_file(path)

        except Exception as exc:

            print(
                f"ERROR processing {path}: {exc}"
            )
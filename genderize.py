"""
For a verified file of references (already processed by id_author.py, so
each reference carries an "identified_authors" list), identifies the
gender of the author and edits the JSON to provide information about
gender and probability.

For each reference:
1. Take the cited author, ref_authors[0] — this is the ONLY author
   listed for a reference (ref_authors always has exactly one entry),
   not merely the first of several. Look up its matching entry in
   "identified_authors" (matched by "cited_name").
2. From that entry, choose the LONGER of "cited_name" and "fullest_name"
   (fullest_name is only used if the author was actually found, i.e.
   "author_exists" is true).
3. If no "identified_authors" entry is available at all (e.g. the file
   hasn't been through id_author.py, or the author wasn't found), fall
   back to the previous behavior: compare "matched_database_author" to
   "ref_authors"[0] and pick whichever is more information-rich.
4. If available, "organization_country_id" is passed to genderize.io as
   an extra (optional) signal to improve accuracy. It is never required.
5. Send the selected names (+ optional country) to genderize.io.
6. Add:
       "gender": ...
       "gender_probability": ...
   to each reference.

Other than these changes, the original verified-reference structure is preserved.
"""

import os
import time
import json
import requests
from dotenv import load_dotenv
from prompt_llm_task2 import load_file

load_dotenv()

GENDERIZE_API_KEY = os.environ.get("GENDERIZE_API_KEY")
GENDERIZE_URL = "https://api.genderize.io"


def save_json(data, filename):
    """Save JSON data to a file."""

    output_dir = os.path.dirname(filename)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Write to temporary file first so a crash does not destroy
    # the existing output file.
    temp_filename = filename + ".tmp"

    with open(temp_filename, "w") as f:
        json.dump(data, f, indent=2)

    os.replace(temp_filename, filename)


# score names
def name_information_score(name):
    """
    Gives a rough score for how information-rich an author name is.
    Mostly, full names are preferred over initials.

    Only used as a FALLBACK, for references that don't have an
    "identified_authors" entry to work from.
    """

    if not name:
        return 0

    parts = name.split()

    if len(parts) < 2:
        return len(name)

    score = 0

    # Reward additional name components.
    score += len(parts) * 10

    # Reward non-initial first/middle names.
    for part in parts[:-1]:
        clean = part.replace(".", "")

        if len(clean) > 1:
            score += len(clean)

    # Reward total amount of information.
    score += len(name)

    return score


def get_identified_author(reference):
    """
    Return the "identified_authors" entry (dict) that corresponds to the
    cited author, ref_authors[0] — the only author on the reference.

    "identified_authors" is positional: entry[0] corresponds to
    ref_authors[0]. We match by position rather than by a "cited_name"
    field, since that field is redundant (it would just duplicate
    ref_authors[0]) and id_author.py no longer writes it. This also
    keeps this function working on older files that still happen to
    carry a "cited_name" field, since we never look at it.
    """

    ref_authors = reference.get("ref_authors", [])

    if not ref_authors:
        return None

    identified_authors = reference.get(
        "identified_authors", []
    ) or []

    if not identified_authors:
        return None

    return identified_authors[0]


def choose_best_author_name_and_country(reference):
    """
    Selects the most information-rich name for the reference's (sole)
    cited author, plus an optional organization country to help
    genderize.io.

    Priority:

    1. If an "identified_authors" entry exists (identified_authors[0],
       matched positionally to ref_authors[0]), pick the LONGER of
       ref_authors[0] and "fullest_name" (fullest_name only counts if
       "author_exists" is true). "organization_country_id" from that
       entry is returned alongside, if available.
    2. Otherwise, fall back to comparing "matched_database_author" and
       "ref_authors"[0] via name_information_score, as before. No
       country is available in this fallback path.

    Returns a tuple: (name, organization_country_id)
    Either element may be None.
    """

    entry = get_identified_author(reference)

    if entry:

        ref_authors = reference.get("ref_authors", [])
        cited_name = ref_authors[0] if ref_authors else None

        fullest_name = None
        if entry.get("author_exists"):
            fullest_name = entry.get("fullest_name")

        country_id = entry.get(
            "organization_country_id"
        )  # optional; may be None

        if cited_name and fullest_name:
            name = (
                cited_name
                if len(cited_name) >= len(fullest_name)
                else fullest_name
            )
        elif fullest_name:
            name = fullest_name
        else:
            name = cited_name

        if name:
            return name, country_id

        # Fall through to the legacy fallback if the entry was
        # somehow empty.

    # ------------------------------------------------------------------
    # Fallback: no identified_authors entry available.
    # ------------------------------------------------------------------

    ref_authors = reference.get("ref_authors", [])
    ref_author = ref_authors[0] if ref_authors else None

    matched_author = reference.get("matched_database_author")

    if ref_author and matched_author:
        ref_score = name_information_score(ref_author)
        matched_score = name_information_score(matched_author)

        name = (
            matched_author
            if matched_score > ref_score
            else ref_author
        )

        return name, None

    if matched_author:
        return matched_author, None

    if ref_author:
        return ref_author, None

    return None, None


def _build_params(name, country_id=None):
    """
    Build parameters for a single genderize.io request.

    Country is passed whenever a valid two-character country code is
    available. It is omitted when country_id is None.
    """
    params = {
        "name": name,
    }

    if country_id:
        params["country_id"] = country_id

    if GENDERIZE_API_KEY:
        params["apikey"] = GENDERIZE_API_KEY

    return params


def _send_gender_request(name, country_id, max_retries):
    """
    Send one author name to genderize.io.

    This deliberately uses one request per name rather than bulk batches so
    that each name can independently use its own organization country.
    """
    params = _build_params(name, country_id=country_id)

    last_exc = None

    for attempt in range(max_retries):
        try:
            response = requests.get(
                GENDERIZE_URL,
                params=params,
                timeout=10,
            )

            if response.status_code == 429:
                wait = int(
                    response.headers.get(
                        "X-Rate-Reset",
                        60,
                    )
                )

                print(
                    f"Rate limited by genderize.io. "
                    f"Waiting {wait}s..."
                )

                time.sleep(wait)
                continue

            response.raise_for_status()

            result = response.json()

            if not isinstance(result, dict):
                raise ValueError(
                    "genderize.io returned an unexpected "
                    "response format."
                )

            return result, None

        except (
            requests.exceptions.RequestException,
            ValueError,
        ) as e:
            last_exc = e

            print(
                f"genderize.io request failed "
                f"(attempt {attempt + 1}/{max_retries}): {e}"
            )

            if attempt < max_retries - 1:
                wait = 2 ** attempt

                print(f"Retrying in {wait}s...")
                time.sleep(wait)

    return None, last_exc


def get_gender(name_country_pairs, max_retries=3):
    """
    Query genderize.io one name at a time.

    Each name independently receives its own country_id when available.
    Results are returned in the same order as the input pairs.
    """
    results = []

    for i, (name, country_id) in enumerate(
        name_country_pairs,
        start=1,
    ):
        country_note = (
            f", country={country_id}"
            if country_id
            else ""
        )

        print(
            f"\nGenderizing {i} of {len(name_country_pairs)}: "
            f"{name}{country_note}"
        )

        result, exc = _send_gender_request(
            name,
            country_id,
            max_retries=max_retries,
        )

        if result is not None:
            print(
                f"  {name}{country_note} -> "
                f"{result.get('gender')} "
                f"({result.get('probability')})"
            )

            results.append(result)

        else:
            print(
                f"  Giving up on: {name}"
            )

            results.append({
                "name": name,
                "gender": None,
                "probability": None,
            })

    return results

def find_reference_dicts(node):
    """
    Recursively locate every reference dict within an arbitrarily-shaped
    JSON structure.

    A "reference dict" is identified by having a "ref_authors" key —
    that's the one field that's always present on a reference, in every
    shape this file might come in:

      - the normal shape: a list of paper records, each with a
        "references" list of reference dicts.
      - a flat list of reference dicts directly (e.g. a hand-built test
        file with no paper-record wrapper).
      - a dict wrapped in a common container key ("results", "data",
        "items", "records").

    This makes the script robust to shape mismatches instead of
    silently finding zero references to process.
    """

    found = []

    if isinstance(node, dict):

        if "ref_authors" in node:
            found.append(node)

        elif "references" in node:
            found.extend(
                find_reference_dicts(node["references"])
            )

        else:
            for key in ("results", "data", "items", "records"):
                if key in node:
                    found.extend(
                        find_reference_dicts(node[key])
                    )

    elif isinstance(node, list):

        for item in node:
            found.extend(find_reference_dicts(item))

    return found


# ----------------------------------------------------------------------
# MAIN PROCESSING
# ----------------------------------------------------------------------

def add_gender_to_verified_file(input_file):
    """
    Loads a verified-reference JSON file, identifies the (sole) cited
    author of every reference, queries genderize.io, and adds gender
    information directly to the existing JSON file.

    Added fields:

        "gender": "male" / "female" / None
        "gender_probability": float / None

    No new output file is created.
    """

    # --------------------------------------------------------------
    # Load input
    # --------------------------------------------------------------

    print(
        f"Loading verified references from:\n"
        f"  {input_file}"
    )

    data = load_file(input_file)

    if not isinstance(data, (list, dict)):
        raise ValueError(
            "Expected the input JSON to contain a list or dict."
        )

    # --------------------------------------------------------------
    # Discover every reference dict, regardless of nesting shape.
    # --------------------------------------------------------------

    all_references = find_reference_dicts(data)

    print(
        f"Found {len(all_references)} total reference entries "
        f"in the file."
    )

    if not all_references:

        print(
            "No reference entries were found — check that the input "
            "file actually contains \"ref_authors\" fields somewhere "
            "in its structure."
        )

        return

    # --------------------------------------------------------------
    # Collect cited-author names (+ optional country)
    # --------------------------------------------------------------

    author_country_pairs = []
    reference_objects = []

    skipped = 0
    no_author = 0

    for reference in all_references:

        # If gender has already been added, skip this reference.
        if (
            "gender" in reference
            and "gender_probability" in reference
        ):
            skipped += 1
            continue

        author_name, country_id = choose_best_author_name_and_country(
            reference
        )

        if not author_name:

            no_author += 1

            print(
                f"\nWARNING: No author found for reference: "
                f"{reference.get('citation', '<unknown citation>')}"
            )

            reference["gender"] = None
            reference["gender_probability"] = None

            continue

        author_country_pairs.append(
            (author_name, country_id)
        )

        reference_objects.append(reference)

    if skipped:
        print(f"Skipped {skipped} already-genderized reference(s).")

    if no_author:
        print(f"Skipped {no_author} reference(s) with no usable author name.")

    print(
        f"\nFound {len(author_country_pairs)} "
        f"author names to genderize."
    )

    if not author_country_pairs:

        print(
            "No new author names to genderize."
        )

        return

    # --------------------------------------------------------------
    # Call Genderize
    # --------------------------------------------------------------

    gender_results = get_gender(
        author_country_pairs
    )

    # --------------------------------------------------------------
    # Make sure we received the expected number of results
    # --------------------------------------------------------------

    if len(gender_results) != len(
        reference_objects
    ):

        print(
            "\nWARNING:"
        )

        print(
            f"Expected {len(reference_objects)} "
            f"gender results, but received "
            f"{len(gender_results)}."
        )

    # --------------------------------------------------------------
    # Add results to references (each `reference` here IS the same
    # dict object living inside `data`, so mutating it in place
    # updates `data` directly — no index bookkeeping needed, and it
    # works regardless of how deeply/oddly the JSON is nested).
    # --------------------------------------------------------------

    for reference, result in zip(
        reference_objects,
        gender_results
    ):

        reference["gender"] = result.get(
            "gender"
        )

        reference["gender_probability"] = result.get(
            "probability"
        )

    # --------------------------------------------------------------
    # Edit the EXISTING file
    # --------------------------------------------------------------

    save_json(
        data,
        input_file
    )

    # --------------------------------------------------------------
    # Summary
    # --------------------------------------------------------------

    total = 0
    gender_found = 0
    high_confidence = 0
    unknown = 0

    for reference in all_references:

        total += 1

        gender = reference.get(
            "gender"
        )

        probability = reference.get(
            "gender_probability"
        )

        if gender:
            gender_found += 1
        else:
            unknown += 1

        if (
            probability is not None
            and probability >= 0.8
        ):
            high_confidence += 1

    print(
        f"\n{'=' * 50}"
    )

    print(
        "Gender identification complete."
    )

    print(
        f"Total references:       {total}"
    )

    print(
        f"Gender identified:      {gender_found}"
    )

    print(
        f"Gender unavailable:     {unknown}"
    )

    print(
        f"Probability >= 0.80:    {high_confidence}"
    )

    print(
        f"\nEdited existing file:\n"
        f"  {input_file}"
    )


if __name__ == "__main__":
    add_gender_to_verified_file(
        "data/verification/gemini/checked_gem_S13144211_expertsysapp.json"
    )
    # add_gender_to_verified_file(
    #     input_file="data/verification/gemini/checked_gem_S1980519_astrophys.json"
    # )
    # add_gender_to_verified_file(
    #     input_file="data/verification/gemini/checked_gem_S9692511_frontierspsych.json"
    # )    
    # add_gender_to_verified_file(
    #     input_file="data/verification/gemini/checked_gem_S13144211_expertsysappe.json"
    # )
    # add_gender_to_verified_file(
    #     input_file="data/verification/gemini/checked_gem_S23254222_americaneconomic.json"
    # )
    # add_gender_to_verified_file(
    #     input_file="data/verification/gemini/checked_gem_S24807848_physreview.json" 
    # )
    # add_gender_to_verified_file(
    #     input_file="data/verification/gemini/checked_gem_S49861241_lancet.json"
    # )
    # add_gender_to_verified_file(
    #     input_file="data/verification/gemini/checked_gem_s86852077_totalenv.json"
    # )    
    # add_gender_to_verified_file(
    #     input_file="data/verification/gemini/checked_gem_S110447773_cell.json"
    # )
    # add_gender_to_verified_file(
    #     input_file="data/verification/gemini/checked_gem_S145089992_hazardous.json"
    # )
    # add_gender_to_verified_file(
    #     input_file="data/verification/gemini/checked_gem_S4210175523_IEEEneuralnet.json" 
    # )
    
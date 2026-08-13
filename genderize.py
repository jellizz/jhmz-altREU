"""
For a verified file of references, identifies the gender of the first author
and edits the JSON to provide information about gender and probability.

For each reference:
1. If "matched_database_author" exists, compare it to "ref_authors"[0].
2. Choose the more information-rich version of the name.
3. If "matched_database_author" does not exist, use "ref_authors"[0].
   This is still genderized even if the author was not verified.
4. Send the selected names to genderize.io.
5. Add:
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
BULK_BATCH_SIZE = 10  # genderize.io max per request


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


def choose_best_author_name(reference):
    """
    Selects the most information-rich first-author name.

    Priority:

    1. Compare "matched_database_author" and "ref_authors"[0]
       if both are available.
    2. Choose the more information-rich name.
    3. If only one exists, use that one.
    4. If no matched database author exists, use ref_authors[0].

    Returns the selected author name.
    """

    ref_authors = reference.get("ref_authors", [])
    ref_author = None

    if ref_authors:
        ref_author = ref_authors[0]

    matched_author = reference.get("matched_database_author")

    if ref_author and matched_author:
        ref_score = name_information_score(ref_author)
        matched_score = name_information_score(matched_author)

        if matched_score > ref_score:
            return matched_author

        return ref_author

    # cases w/ only 1 name
    if matched_author:
        return matched_author

    if ref_author:
        return ref_author

    # edge case no names
    return None


def _build_params(names_batch):
    """
    Builds genderize.io request parameters.
    """

    params = {}

    for i, name in enumerate(names_batch):
        params[f"name[{i}]"] = name

    if GENDERIZE_API_KEY:
        params["apikey"] = GENDERIZE_API_KEY

    return params


def get_gender_bulk(names, max_retries=3):
    """
    Queries genderize.io in batches of 10.
    Returns results in the same order as the input names.
    """

    results = []

    for i in range(
        0,
        len(names),
        BULK_BATCH_SIZE
    ):
        batch = names[
            i:i + BULK_BATCH_SIZE
        ]

        params = _build_params(batch)

        print(
            f"\nGenderizing names "
            f"{i + 1}-{i + len(batch)} "
            f"of {len(names)}..."
        )

        for attempt in range(max_retries):
            try:
                response = requests.get(
                    GENDERIZE_URL,
                    params=params,
                    timeout=10
                )

                if response.status_code == 429:
                    wait = int(
                        response.headers.get(
                            "X-Rate-Reset",
                            60
                        )
                    )

                    print(
                        f"Rate limited by genderize.io. "
                        f"Waiting {wait}s..."
                    )

                    time.sleep(wait)
                    continue

                response.raise_for_status()

                batch_results = response.json()

                if not isinstance(batch_results, list):
                    raise ValueError(
                        "genderize.io returned an unexpected "
                        "response format."
                    )

                results.extend(batch_results)

                for name, result in zip(
                    batch,
                    batch_results
                ):
                    print(
                        f"  {name} -> "
                        f"{result.get('gender')} "
                        f"({result.get('probability')})"
                    )

                break

            except (
                requests.exceptions.RequestException,
                ValueError
            ) as e:

                print(
                    f"genderize.io request failed "
                    f"(attempt {attempt + 1}/"
                    f"{max_retries}): {e}"
                )

                if attempt < max_retries - 1:
                    wait = 2 ** attempt

                    print(
                        f"Retrying in {wait}s..."
                    )

                    time.sleep(wait)

                else:
                    print(
                        "Giving up on this batch."
                    )

                    results.extend(
                        [
                            {
                                "name": name,
                                "gender": None,
                                "probability": None
                            }
                            for name in batch
                        ]
                    )

    return results


# ----------------------------------------------------------------------
# MAIN PROCESSING
# ----------------------------------------------------------------------

def add_gender_to_verified_file(input_file):
    """
    Loads a verified-reference JSON file, identifies the first author
    of every reference, queries genderize.io, and adds gender information
    directly to the existing JSON file.

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

    if not isinstance(data, list):
        raise ValueError(
            "Expected the input JSON to contain a list of records."
        )

    # --------------------------------------------------------------
    # Collect first-author names
    # --------------------------------------------------------------

    names_to_genderize = []
    reference_locations = []

    for record_index, record in enumerate(data):

        references = record.get(
            "references",
            []
        )

        for reference_index, reference in enumerate(
            references
        ):

            # If gender has already been added, skip this reference.
            if (
                "gender" in reference
                and "gender_probability" in reference
            ):
                print(
                    f"  Skipping already genderized: "
                    f"{record_index}, {reference_index}"
                )
                continue

            author_name = choose_best_author_name(
                reference
            )

            if not author_name:

                print(
                    f"\nWARNING: No author found for "
                    f"record {record_index}, "
                    f"reference {reference_index}"
                )

                reference["gender"] = None
                reference["gender_probability"] = None

                continue

            names_to_genderize.append(
                author_name
            )

            reference_locations.append(
                (
                    record_index,
                    reference_index
                )
            )

    print(
        f"\nFound {len(names_to_genderize)} "
        f"author names to genderize."
    )

    if not names_to_genderize:

        print(
            "No new author names to genderize."
        )

        return

    # --------------------------------------------------------------
    # Call Genderize
    # --------------------------------------------------------------

    gender_results = get_gender_bulk(
        names_to_genderize
    )

    # --------------------------------------------------------------
    # Make sure we received the expected number of results
    # --------------------------------------------------------------

    if len(gender_results) != len(
        reference_locations
    ):

        print(
            "\nWARNING:"
        )

        print(
            f"Expected {len(reference_locations)} "
            f"gender results, but received "
            f"{len(gender_results)}."
        )

    # --------------------------------------------------------------
    # Add results to references
    # --------------------------------------------------------------

    for location, result in zip(
        reference_locations,
        gender_results
    ):

        record_index, reference_index = location

        reference = data[
            record_index
        ]["references"][
            reference_index
        ]

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

    for record in data:

        for reference in record.get(
            "references",
            []
        ):

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
        input_file=(
            "data/verification/gemini/checked_gem_S1980519_astrophys.json"
        )
    )
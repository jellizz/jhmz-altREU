"""
Process existing overall_domain.json to summarize first-author h-indexes.

The file already contains:
- Gender information
- A list of first-author h-index records

This script does NOT make any new OpenAlex or Genderize API requests.

For each discipline:
1. Reads the existing first_author_h_indexes list.
2. Removes records with missing/null h-indexes from the calculation.
3. Calculates the average first-author h-index.
4. Removes the detailed first_author_h_indexes list.
5. Adds average_first_author_h_index.
6. Preserves all existing gender information.

Output:
overall_domain.json
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

OUTPUT_FILE = BASE_DIR / "stats" / "overall_domain.json"


# ---------------------------------------------------------------------------
# Load existing JSON
# ---------------------------------------------------------------------------

def load_existing_results() -> list[dict]:
    """Load the existing overall_domain.json file."""

    if not OUTPUT_FILE.exists():
        raise FileNotFoundError(
            f"Could not find:\n{OUTPUT_FILE}"
        )

    with open(
        OUTPUT_FILE,
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(
            "overall_domain.json must contain a JSON list."
        )

    return data


# ---------------------------------------------------------------------------
# Process h-indexes
# ---------------------------------------------------------------------------

def process_h_indexes(
    results: list[dict],
) -> list[dict]:
    """
    Replace detailed first-author h-index records with
    a single average_first_author_h_index value.

    Existing gender information is preserved.
    """

    for result in results:

        discipline = result.get(
            "discipline",
            "Unknown discipline",
        )

        h_index_records = result.get(
            "first_author_h_indexes",
            [],
        )

        # Extract only valid numeric h-indexes.
        valid_h_indexes = []

        for record in h_index_records:

            if not isinstance(record, dict):
                continue

            h_index = record.get("h_index")

            if h_index is None:
                continue

            try:
                h_index = float(h_index)
            except (TypeError, ValueError):
                continue

            valid_h_indexes.append(h_index)

        # Calculate average.
        if valid_h_indexes:
            average_h_index = mean(
                valid_h_indexes
            )

            # If the mean is a whole number, store it as
            # an integer rather than 12.0.
            if average_h_index.is_integer():
                average_h_index = int(
                    average_h_index
                )

        else:
            average_h_index = None

        # Remove the large individual-author list.
        result.pop(
            "first_author_h_indexes",
            None,
        )

        # Add only the average.
        result[
            "average_first_author_h_index"
        ] = average_h_index

        # Keep track of how many h-indexes contributed
        # to the average.
        result[
            "h_index_sample_size"
        ] = len(valid_h_indexes)

        print(
            f"{discipline}: "
            f"{len(valid_h_indexes)} valid h-indexes"
        )

        if average_h_index is not None:
            print(
                f"  Average first-author h-index: "
                f"{average_h_index}"
            )
        else:
            print(
                "  Average first-author h-index: "
                "NO VALID H-INDEXES FOUND"
            )

    return results


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_results(
    results: list[dict],
) -> None:
    """Save the processed results back to overall_domain.json."""

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            results,
            f,
            indent=2,
        )

    print(
        f"\nUpdated file saved to:\n{OUTPUT_FILE}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:

    print(
        f"Loading:\n{OUTPUT_FILE}\n"
    )

    results = load_existing_results()

    print(
        f"Found {len(results)} discipline records.\n"
    )

    results = process_h_indexes(
        results
    )

    save_results(
        results
    )

    print(
        "\nDone. Individual author records "
        "have been removed."
    )


if __name__ == "__main__":
    main()
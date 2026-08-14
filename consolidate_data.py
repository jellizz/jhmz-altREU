"""
Citation Verification / Gender / Productivity Analysis
=========================================================

Input structure:

    data/
        verification/
            anthr/
                checked_anthr_*.json
            gemini/
                checked_gem_*.json
            gpt/
                checked_gpt_*.json

Output:

    output/
        citation_summary.csv
        citation_level_data.csv


The script calculates:

1. Citation status
   - found
   - not_found
   - other statuses
   - percentages

2. Citation verification
   - title found
   - author matched
   - DOI valid
   - all 8 combinations of those 3 fields
   - verification score 0-3
   - average/median verification score

3. Gender
   - male/female counts
   - male/female percentages
   - known-gender percentages
   - high/low confidence
   - gender × status
   - gender × verification score

4. Productivity
   - average h-index
   - median h-index
   - average works
   - median works
   - number found
   - productivity × gender

5. Author identification
   - identified/not identified
   - identification percentage

6. DOI
   - valid/invalid/unknown
   - validity percentage

7. Database failures
   - failures by database
   - failure percentages

8. Research design breakdowns
   - overall
   - LLM
   - domain
   - source
   - LLM × domain
   - LLM × source

9. Citation-level dataset
   - one row per citation
   - useful for later statistical analysis/cross-tabulation
"""

import json
import csv
import re

from pathlib import Path
from collections import Counter, defaultdict
from statistics import mean, median


# ============================================================
# CONFIGURATION
# ============================================================

# ------------------------------------------------------------
# Input/output locations
# ------------------------------------------------------------

INPUT_DIR = Path("data/verification")

OUTPUT_DIR = Path("data/combined")

SUMMARY_CSV = OUTPUT_DIR / "citation_summary.csv"

CITATION_LEVEL_CSV = (
    OUTPUT_DIR / "citation_level_data.csv"
)


# ------------------------------------------------------------
# Gender probability threshold
# ------------------------------------------------------------
#
# >= 0.75 = high confidence
# <  0.75 = low confidence
#
# If you want strictly ABOVE 0.75 instead, change the
# comparison in add_derived_fields().
# ------------------------------------------------------------

GENDER_PROBABILITY_THRESHOLD = 0.75


# ============================================================
# SOURCE / DOMAIN MAPPING
# ============================================================
#
# IMPORTANT:
#
# The S-number is the stable identifier across LLMs.
#
# Example:
#
#   checked_anthr_S1980519_astrophys.json
#   checked_gem_S1980519_astrophys.json
#   checked_gpt_S1980519.json
#
# are all the same source:
#
#   S1980519
#
#
# "domain" is YOUR research grouping.
#
# "source" is the individual source within that domain.
#
#
# I have put ALL 10 source IDs from your file list here.
#
# ------------------------------------------------------------
#
# CURRENT GROUPING BASED ON WHAT YOU TOLD ME:
#
# Physics:
#   astrophysics
#   physics
#
# CS:
#   expert systems applications
#   neural networks / AI
#
# Environmental:
#   hazardous
#   totalenv
#
# Social sciences:
#   economics
#   psychology
#
# Medicine:
#   physical review
#   lancet
#
# ------------------------------------------------------------
#
# THERE ARE TWO THINGS TO DOUBLE-CHECK:
#
# 1. S24807848 = physreview
#    You said this belongs to Medicine.
#
# 2. S110447773 = cell
#    You didn't specify where "cell" belongs.
#
# The mapping below currently puts Cell under medicine because
# that is the closest fit among your five stated domains.
#
# If that isn't correct, change that one line.
#
# Also, your current file list does NOT contain a separate
# source obviously named "physics" other than physreview.
# If another physics JSON exists, simply add its S-ID below.
# ============================================================


SOURCE_MAP = {

    # --------------------------------------------------------
    # PHYSICS
    # --------------------------------------------------------

    "S1980519": {
        "domain": "physics",
        "source": "astrophysics",
    },

    "S24807848": {
        "domain": "physics",
        "source": "physical_review",
    },


    # --------------------------------------------------------
    # COMPUTER SCIENCE
    # --------------------------------------------------------

    "S13144211": {
        "domain": "cs",
        "source": "expert_systems_applications",
    },

    "S4210175523": {
        "domain": "cs",
        "source": "neural_networks_ai",
    },


    # --------------------------------------------------------
    # ENVIRONMENTAL
    # --------------------------------------------------------

    "S145089992": {
        "domain": "environmental",
        "source": "hazardous",
    },

    "S86852077": {
        "domain": "environmental",
        "source": "totalenv",
    },


    # --------------------------------------------------------
    # SOCIAL SCIENCES
    # --------------------------------------------------------

    "S23254222": {
        "domain": "social_sciences",
        "source": "economics",
    },

    "S9692511": {
        "domain": "social_sciences",
        "source": "psychology",
    },


    # --------------------------------------------------------
    # MEDICINE
    # --------------------------------------------------------
    
    "S110447773": {
        "domain": "medicine",
        "source": "cell",
    },

    "S49861241": {
        "domain": "medicine",
        "source": "lancet",
    },

}


# ============================================================
# GENERAL HELPER FUNCTIONS
# ============================================================

def safe_bool(value):
    """
    Convert a JSON value into:

        True
        False
        None

    None means the value is missing/unusable.
    """

    if value is True:
        return True

    if value is False:
        return False

    return None


def get_numeric(value):
    """
    Safely convert a value to float.

    Returns None if it isn't numeric.
    """

    if value is None:
        return None

    try:
        return float(value)

    except (ValueError, TypeError):
        return None


def clean_number(value):
    """
    Make 4.0 appear as 4 in the CSV.
    """

    if isinstance(value, float) and value.is_integer():
        return int(value)

    return value


def calculate_pct(numerator, denominator):
    """
    Calculate percentage.

    Example:

        25 / 100 -> 25.0
    """

    if denominator == 0:
        return None

    return round(
        (numerator / denominator) * 100,
        2
    )


def calculate_average(values):
    """
    Calculate average while ignoring None.
    """

    values = [
        value
        for value in values
        if value is not None
    ]

    if not values:
        return None

    return round(
        mean(values),
        2
    )


def calculate_median(values):
    """
    Calculate median while ignoring None.
    """

    values = [
        value
        for value in values
        if value is not None
    ]

    if not values:
        return None

    return round(
        median(values),
        2
    )


def safe_column_name(value):
    """
    Turn arbitrary text into something safe for a CSV column.

    Example:

        "Semantic Scholar"
        ->
        "semantic_scholar"
    """

    value = str(value)

    value = value.lower()

    value = re.sub(
        r"[^a-z0-9]+",
        "_",
        value
    )

    return value.strip("_")


# ============================================================
# GET MODEL FROM DIRECTORY
# ============================================================

def get_model_from_path(path):
    """
    The parent directory identifies the LLM.

    Example:

        data/verification/anthr/file.json
                              ^^^^^
                              model
    """

    folder_name = path.parent.name.lower()

    model_names = {

        "anthr": "anthropic",

        "gemini": "gemini",

        "gpt": "gpt",
    }

    return model_names.get(
        folder_name,
        folder_name
    )


# ============================================================
# GET SOURCE ID FROM FILENAME
# ============================================================

def get_source_id_from_filename(path):
    """
    Extract the S-number from filenames.

    Examples:

        checked_anthr_S1980519_astrophys.json
            -> S1980519

        checked_gpt_S1980519.json
            -> S1980519

        checked_gem_s86852077_totalenv.json
            -> S86852077
    """

    filename = path.stem

    # Look for S/s followed by digits.
    match = re.search(
        r"(?:^|_)s(\d+)(?:_|$)",
        filename,
        re.IGNORECASE
    )

    if match:

        return "S" + match.group(1)

    return "unknown"


# ============================================================
# GET DOMAIN/SOURCE
# ============================================================

def get_domain_and_source(path):
    """
    Use SOURCE_MAP to determine research domain and source.
    """

    source_id = get_source_id_from_filename(
        path
    )

    mapping = SOURCE_MAP.get(
        source_id
    )

    if mapping is None:

        return (
            "unknown",
            "unknown",
            source_id
        )

    return (
        mapping["domain"],
        mapping["source"],
        source_id
    )


# ============================================================
# LOAD JSON FILES
# ============================================================

def load_json_files(input_dir):
    """
    Recursively load every JSON file under INPUT_DIR.

    This means you don't need to specify the number of files.

    If you later add:

        data/verification/new_model/

    the script will automatically find those JSON files.
    """

    records = []

    json_files = sorted(
        input_dir.rglob("*.json")
    )

    print()
    print("=" * 60)
    print("LOADING FILES")
    print("=" * 60)

    print(
        f"Found {len(json_files)} JSON files."
    )

    for path in json_files:

        print(
            f"Reading: {path}"
        )

        try:

            with open(
                path,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

        except Exception as error:

            print(
                f"  ERROR: {error}"
            )

            continue

        # ----------------------------------------------------
        # Determine metadata
        # ----------------------------------------------------

        model = get_model_from_path(
            path
        )

        domain, source, source_id = (
            get_domain_and_source(path)
        )

        # ----------------------------------------------------
        # JSON can be:
        #
        #   {...}
        #
        # or:
        #
        #   [{...}, {...}]
        # ----------------------------------------------------

        if isinstance(data, list):

            file_records = data

        elif isinstance(data, dict):

            file_records = [data]

        else:

            print(
                "  WARNING: JSON is not an object/list."
            )

            continue

        # ----------------------------------------------------
        # Attach metadata
        # ----------------------------------------------------

        for record in file_records:

            if not isinstance(record, dict):
                continue

            record["_source_file"] = path.name

            record["_source_path"] = str(
                path
            )

            record["_model"] = model

            record["_domain"] = domain

            record["_source"] = source

            record["_source_id"] = source_id

            records.append(record)

    return records


# ============================================================
# FLATTEN REFERENCES INTO CITATIONS
# ============================================================

def get_all_citations(records):
    """
    Convert nested references into one flat list.

    One item in this list = one citation.
    """

    citations = []

    for record in records:

        references = record.get(
            "references",
            []
        )

        for reference_number, reference in enumerate(
            references
        ):

            if not isinstance(reference, dict):
                continue

            citation = dict(reference)

            # ------------------------------------------------
            # Dataset metadata
            # ------------------------------------------------

            citation["_source_file"] = (
                record.get("_source_file")
            )

            citation["_source_path"] = (
                record.get("_source_path")
            )

            citation["_record_id"] = (
                record.get("id")
            )

            citation["_model"] = (
                record.get("_model")
            )

            citation["_domain"] = (
                record.get("_domain")
            )

            citation["_source"] = (
                record.get("_source")
            )

            citation["_source_id"] = (
                record.get("_source_id")
            )

            citation["_reference_number"] = (
                reference_number + 1
            )

            citations.append(
                citation
            )

    return citations


# ============================================================
# ADD DERIVED FIELDS
# ============================================================

def add_derived_fields(citation):
    """
    Add useful variables to every citation.

    These appear in citation_level_data.csv.
    """

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------
    #
    # Raw statuses in your JSON:
    #
    #   verified  -> found
    #   not_found -> not_found
    #   mismatch  -> other
    #   CHECK     -> other
    #
    # We keep the original "status" field unchanged and create
    # "derived_status" for analysis.
    # --------------------------------------------------------

    raw_status = citation.get("status")

    if raw_status is None:
        derived_status = "other"

    else:
        raw_status = str(raw_status).strip().lower()

        if raw_status == "verified":
            derived_status = "found"

        elif raw_status == "not_found":
            derived_status = "not_found"

        else:
            derived_status = "other"

    citation["derived_status"] = derived_status

    # --------------------------------------------------------
    # TITLE / AUTHOR / DOI
    # --------------------------------------------------------

    title_found = safe_bool(
        citation.get("title_found")
    )

    author_matched = safe_bool(
        citation.get("author_matched")
    )

    doi_valid = safe_bool(
        citation.get("doi_valid")
    )

    citation["derived_title_found"] = (
        title_found
    )

    citation["derived_author_matched"] = (
        author_matched
    )

    citation["derived_doi_valid"] = (
        doi_valid
    )

    # --------------------------------------------------------
    # VERIFICATION SCORE
    # --------------------------------------------------------
    #
    # title = 1 point
    # author = 1 point
    # DOI = 1 point
    #
    # Maximum = 3
    # --------------------------------------------------------

    if (
        title_found is None
        or author_matched is None
        or doi_valid is None
    ):

        citation["verification_score"] = None

    else:

        citation["verification_score"] = (
            int(title_found)
            + int(author_matched)
            + int(doi_valid)
        )

    # --------------------------------------------------------
    # GENDER
    # --------------------------------------------------------

    gender = citation.get(
        "gender"
    )

    probability = get_numeric(
        citation.get(
            "gender_probability"
        )
    )

    citation["gender_probability_numeric"] = (
        probability
    )

    if gender not in {
        "male",
        "female"
    }:

        citation["gender_confidence"] = (
            "unknown"
        )

    elif probability is None:

        citation["gender_confidence"] = (
            "missing_probability"
        )

    elif probability >= GENDER_PROBABILITY_THRESHOLD:

        citation["gender_confidence"] = (
            "high"
        )

    else:

        citation["gender_confidence"] = (
            "low"
        )

    # --------------------------------------------------------
    # AUTHOR IDENTIFICATION
    # --------------------------------------------------------

    identified_authors = citation.get(
        "identified_authors",
        []
    )

    citation["author_identified"] = False

    if isinstance(
        identified_authors,
        list
    ):

        for author in identified_authors:

            if not isinstance(
                author,
                dict
            ):
                continue

            if author.get(
                "author_exists"
            ) is True:

                citation["author_identified"] = True

                break

    # --------------------------------------------------------
    # H-INDEX / WORKS
    # --------------------------------------------------------
    #
    # These fields are stored inside:
    #
    # identified_authors[0]
    #
    # rather than directly on the citation.
    #
    # Example:
    #
    # "identified_authors": [
    #     {
    #         "h_index": 4,
    #         "works_count": 5
    #     }
    # ]
    # --------------------------------------------------------

    identified_author = None

    if isinstance(
        identified_authors,
        list
    ) and identified_authors:

        # Use the first identified author.
        first_author = identified_authors[0]

        if isinstance(
            first_author,
            dict
        ):

            identified_author = first_author

    if identified_author is not None:

        citation["h_index_numeric"] = (
            get_numeric(
                identified_author.get(
                    "h_index"
                )
            )
        )

        citation["works_count_numeric"] = (
            get_numeric(
                identified_author.get(
                    "works_count"
                )
            )
        )

    else:

        citation["h_index_numeric"] = None

        citation["works_count_numeric"] = None


    # --------------------------------------------------------
    # DATABASE FAILURES
    # --------------------------------------------------------

    failed_dbs = citation.get(
        "failed_dbs",
        []
    )

    if not isinstance(
        failed_dbs,
        list
    ):

        failed_dbs = []

    citation["failed_database_count"] = (
        len(failed_dbs)
    )

    return citation


# ============================================================
# STATUS ANALYSIS
# ============================================================

def analyze_status(citations):

    counts = Counter()

    for citation in citations:

        counts[
            citation["derived_status"]
        ] += 1

    return counts


# ============================================================
# VERIFICATION ANALYSIS
# ============================================================

def analyze_verification(citations):

    results = {}

    total = len(
        citations
    )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title_found = sum(
        1
        for citation in citations
        if citation["derived_title_found"] is True
    )

    results["title_found"] = (
        title_found
    )

    results["title_found_pct"] = (
        calculate_pct(
            title_found,
            total
        )
    )

    # --------------------------------------------------------
    # AUTHOR
    # --------------------------------------------------------

    author_matched = sum(
        1
        for citation in citations
        if citation["derived_author_matched"] is True
    )

    results["author_matched"] = (
        author_matched
    )

    results["author_matched_pct"] = (
        calculate_pct(
            author_matched,
            total
        )
    )

    # --------------------------------------------------------
    # DOI
    # --------------------------------------------------------

    doi_valid = sum(
        1
        for citation in citations
        if citation["derived_doi_valid"] is True
    )

    results["doi_valid"] = (
        doi_valid
    )

    results["doi_valid_pct"] = (
        calculate_pct(
            doi_valid,
            total
        )
    )

    # --------------------------------------------------------
    # ALL THREE
    # --------------------------------------------------------

    all_three = sum(
        1
        for citation in citations
        if (
            citation["derived_title_found"] is True
            and
            citation["derived_author_matched"] is True
            and
            citation["derived_doi_valid"] is True
        )
    )

    results["all_three_valid"] = (
        all_three
    )

    results["all_three_valid_pct"] = (
        calculate_pct(
            all_three,
            total
        )
    )

    # --------------------------------------------------------
    # VERIFICATION SCORE
    # --------------------------------------------------------

    score_counts = Counter()

    scores = []

    for citation in citations:

        score = citation[
            "verification_score"
        ]

        if score is not None:

            scores.append(
                score
            )

            score_counts[
                score
            ] += 1

    results[
        "verification_score_average"
    ] = calculate_average(
        scores
    )

    results[
        "verification_score_median"
    ] = calculate_median(
        scores
    )

    for score in range(4):

        results[
            f"verification_score_{score}"
        ] = score_counts[score]

        results[
            f"verification_score_{score}_pct"
        ] = calculate_pct(
            score_counts[score],
            total
        )

    # --------------------------------------------------------
    # ALL 8 TITLE/AUTHOR/DOI COMBINATIONS
    # --------------------------------------------------------

    combinations = Counter()

    for citation in citations:

        title = citation[
            "derived_title_found"
        ]

        author = citation[
            "derived_author_matched"
        ]

        doi = citation[
            "derived_doi_valid"
        ]

        if (
            title is None
            or author is None
            or doi is None
        ):

            combinations[
                "unknown_or_missing"
            ] += 1

            continue

        key = (
            f"title_{'yes' if title else 'no'}__"
            f"author_{'yes' if author else 'no'}__"
            f"doi_{'yes' if doi else 'no'}"
        )

        combinations[key] += 1

    for title in [False, True]:

        for author in [False, True]:

            for doi in [False, True]:

                key = (
                    f"title_{'yes' if title else 'no'}__"
                    f"author_{'yes' if author else 'no'}__"
                    f"doi_{'yes' if doi else 'no'}"
                )

                results[
                    f"verification_{key}"
                ] = combinations[key]

                results[
                    f"verification_{key}_pct"
                ] = calculate_pct(
                    combinations[key],
                    total
                )

    results[
        "verification_unknown_or_missing"
    ] = combinations[
        "unknown_or_missing"
    ]

    return results


# ============================================================
# GENDER ANALYSIS
# ============================================================

def analyze_gender(citations):

    results = {}

    total = len(
        citations
    )

    # --------------------------------------------------------
    # BASIC GENDER COUNTS
    # --------------------------------------------------------

    male = sum(
        1
        for citation in citations
        if citation.get("gender") == "male"
    )

    female = sum(
        1
        for citation in citations
        if citation.get("gender") == "female"
    )

    unknown = (
        total
        - male
        - female
    )

    results["male"] = male

    results["female"] = female

    results["unknown_gender"] = (
        unknown
    )

    # --------------------------------------------------------
    # PERCENTAGES OF ALL CITATIONS
    # --------------------------------------------------------

    results["male_pct"] = (
        calculate_pct(
            male,
            total
        )
    )

    results["female_pct"] = (
        calculate_pct(
            female,
            total
        )
    )

    # --------------------------------------------------------
    # PERCENTAGES AMONG KNOWN GENDER
    # --------------------------------------------------------
    #
    # This excludes unknown gender.
    #
    # This is probably the most useful gender proportion
    # for comparing male vs female.
    # --------------------------------------------------------

    known_gender = (
        male + female
    )

    results[
        "male_pct_known_gender"
    ] = calculate_pct(
        male,
        known_gender
    )

    results[
        "female_pct_known_gender"
    ] = calculate_pct(
        female,
        known_gender
    )

    # --------------------------------------------------------
    # CONFIDENCE
    # --------------------------------------------------------

    male_high = 0

    female_high = 0

    male_low = 0

    female_low = 0

    missing_probability = 0

    for citation in citations:

        gender = citation.get(
            "gender"
        )

        confidence = citation[
            "gender_confidence"
        ]

        if confidence == "high":

            if gender == "male":
                male_high += 1

            elif gender == "female":
                female_high += 1

        elif confidence == "low":

            if gender == "male":
                male_low += 1

            elif gender == "female":
                female_low += 1

        elif confidence == "missing_probability":

            missing_probability += 1

    results[
        "male_high_confidence"
    ] = male_high

    results[
        "female_high_confidence"
    ] = female_high

    results[
        "male_low_confidence"
    ] = male_low

    results[
        "female_low_confidence"
    ] = female_low

    results[
        "high_confidence_combined"
    ] = (
        male_high
        + female_high
    )

    results[
        "low_confidence_combined"
    ] = (
        male_low
        + female_low
    )

    results[
        "gender_missing_probability"
    ] = missing_probability

    # --------------------------------------------------------
    # CONFIDENCE PERCENTAGES
    # --------------------------------------------------------

    results[
        "male_high_confidence_pct"
    ] = calculate_pct(
        male_high,
        total
    )

    results[
        "female_high_confidence_pct"
    ] = calculate_pct(
        female_high,
        total
    )

    results[
        "male_low_confidence_pct"
    ] = calculate_pct(
        male_low,
        total
    )

    results[
        "female_low_confidence_pct"
    ] = calculate_pct(
        female_low,
        total
    )

    # --------------------------------------------------------
    # GENDER × STATUS
    # --------------------------------------------------------

    gender_status = Counter()

    for citation in citations:

        gender = citation.get(
            "gender"
        )

        if gender not in {
            "male",
            "female"
        }:

            gender = "unknown"

        status = citation[
            "derived_status"
        ]

        gender_status[
            (gender, status)
        ] += 1

    for (
        gender,
        status
    ), count in gender_status.items():

        gender_name = safe_column_name(
            gender
        )

        status_name = safe_column_name(
            status
        )

        results[
            f"gender_{gender_name}__status_{status_name}"
        ] = count

    # --------------------------------------------------------
    # GENDER × VERIFICATION SCORE
    # --------------------------------------------------------

    gender_verification = Counter()

    for citation in citations:

        gender = citation.get(
            "gender"
        )

        if gender not in {
            "male",
            "female"
        }:

            gender = "unknown"

        score = citation[
            "verification_score"
        ]

        if score is None:
            score = "unknown"

        gender_verification[
            (gender, score)
        ] += 1

    for (
        gender,
        score
    ), count in gender_verification.items():

        gender_name = safe_column_name(
            gender
        )

        score_name = safe_column_name(
            score
        )

        results[
            f"gender_{gender_name}__verification_score_{score_name}"
        ] = count

    return results


# ============================================================
# PRODUCTIVITY ANALYSIS
# ============================================================

def analyze_productivity(citations):

    h_indices = [

        citation[
            "h_index_numeric"
        ]

        for citation in citations

        if citation[
            "h_index_numeric"
        ] is not None
    ]

    works = [

        citation[
            "works_count_numeric"
        ]

        for citation in citations

        if citation[
            "works_count_numeric"
        ] is not None
    ]

    total = len(
        citations
    )

    identified_author_count = sum(
        1
        for citation in citations
        if citation.get(
            "author_identified"
        )
    )

    return {

        "h_index_average":
            calculate_average(
                h_indices
            ),

        "h_index_median":
            calculate_median(
                h_indices
            ),

        "h_index_total_found":
            len(h_indices),

        "h_index_found_pct":
            calculate_pct(
                len(h_indices),
                total
            ),
        
        "h_index_found_pct_identified":
            calculate_pct(
                len(h_indices),
                identified_author_count
            ),

        "works_average":
            calculate_average(
                works
            ),

        "works_median":
            calculate_median(
                works
            ),

        "works_total_found":
            len(works),

        "works_found_pct":
            calculate_pct(
                len(works),
                total
            ),

        "works_found_pct_identified":
            calculate_pct(
                len(works),
                identified_author_count
            ),
    }


# ============================================================
# PRODUCTIVITY × GENDER
# ============================================================

def analyze_productivity_by_gender(
    citations
):

    results = {}

    for gender in [
        "male",
        "female"
    ]:

        subset = [

            citation

            for citation in citations

            if citation.get(
                "gender"
            ) == gender
        ]

        productivity = (
            analyze_productivity(
                subset
            )
        )

        for key, value in (
            productivity.items()
        ):

            results[
                f"{gender}_{key}"
            ] = value

    return results


# ============================================================
# AUTHOR IDENTIFICATION
# ============================================================

def analyze_author_identification(
    citations
):

    identified = sum(

        1

        for citation in citations

        if citation[
            "author_identified"
        ]
    )

    not_identified = (
        len(citations)
        - identified
    )

    return {

        "author_identified":
            identified,

        "author_not_identified":
            not_identified,

        "author_identification_pct":
            calculate_pct(
                identified,
                len(citations)
            ),
    }


# ============================================================
# DOI ANALYSIS
# ============================================================

def analyze_doi(citations):

    valid = sum(

        1

        for citation in citations

        if citation[
            "derived_doi_valid"
        ] is True
    )

    invalid = sum(

        1

        for citation in citations

        if citation[
            "derived_doi_valid"
        ] is False
    )

    unknown = (
        len(citations)
        - valid
        - invalid
    )

    return {

        "doi_valid":
            valid,

        "doi_invalid":
            invalid,

        "doi_unknown":
            unknown,

        "doi_valid_pct":
            calculate_pct(
                valid,
                len(citations)
            ),
    }


# ============================================================
# DATABASE FAILURE ANALYSIS
# ============================================================

def analyze_database_failures(
    citations
):

    failure_counts = Counter()

    for citation in citations:

        failed_dbs = citation.get(
            "failed_dbs",
            []
        )

        if not isinstance(
            failed_dbs,
            list
        ):

            continue

        for database in failed_dbs:

            failure_counts[
                database
            ] += 1

    results = {}

    for database, count in sorted(
        failure_counts.items()
    ):

        database_name = safe_column_name(
            database
        )

        results[
            f"failed_db_{database_name}"
        ] = count

        results[
            f"failed_db_{database_name}_pct"
        ] = calculate_pct(
            count,
            len(citations)
        )

    return results


# ============================================================
# CREATE SUMMARY ROW
# ============================================================

def make_summary_row(
    citations,
    level,
    model="all",
    domain="all",
    source="all"
):

    row = {

        "level": level,

        "model": model,

        "domain": domain,

        "source": source,

        "total_citations":
            len(citations),
    }

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    status_counts = analyze_status(
        citations
    )

    found = status_counts.get(
        "found",
        0
    )

    not_found = status_counts.get(
        "not_found",
        0
    )

    other = sum(

        count

        for status, count
        in status_counts.items()

        if status not in {
            "found",
            "not_found"
        }
    )

    row[
        "status_found"
    ] = found

    row[
        "status_not_found"
    ] = not_found

    row[
        "status_other"
    ] = other

    row[
        "status_found_pct"
    ] = calculate_pct(
        found,
        len(citations)
    )

    row[
        "status_not_found_pct"
    ] = calculate_pct(
        not_found,
        len(citations)
    )

    row[
        "status_other_pct"
    ] = calculate_pct(
        other,
        len(citations)
    )

    # Also preserve individual statuses
    for status, count in (
        status_counts.items()
    ):

        status_name = safe_column_name(
            status
        )

        row[
            f"status_{status_name}"
        ] = count

    # --------------------------------------------------------
    # VERIFICATION
    # --------------------------------------------------------

    row.update(
        analyze_verification(
            citations
        )
    )

    # --------------------------------------------------------
    # GENDER
    # --------------------------------------------------------

    row.update(
        analyze_gender(
            citations
        )
    )

    # --------------------------------------------------------
    # PRODUCTIVITY
    # --------------------------------------------------------

    row.update(
        analyze_productivity(
            citations
        )
    )

    # --------------------------------------------------------
    # PRODUCTIVITY × GENDER
    # --------------------------------------------------------

    row.update(
        analyze_productivity_by_gender(
            citations
        )
    )

    # --------------------------------------------------------
    # AUTHOR IDENTIFICATION
    # --------------------------------------------------------

    row.update(
        analyze_author_identification(
            citations
        )
    )

    # --------------------------------------------------------
    # DOI
    # --------------------------------------------------------

    row.update(
        analyze_doi(
            citations
        )
    )

    # --------------------------------------------------------
    # DATABASE FAILURES
    # --------------------------------------------------------

    row.update(
        analyze_database_failures(
            citations
        )
    )

    return row


# ============================================================
# GROUP CITATIONS
# ============================================================

def group_citations(
    citations,
    fields
):

    groups = defaultdict(
        list
    )

    for citation in citations:

        key = tuple(

            citation.get(
                field,
                "unknown"
            )

            for field in fields
        )

        groups[key].append(
            citation
        )

    return groups


# ============================================================
# CREATE SUMMARY
# ============================================================

def create_summary(
    citations
):

    rows = []

    # ========================================================
    # 1. OVERALL
    # ========================================================

    rows.append(
        make_summary_row(
            citations,
            level="overall",
            model="all",
            domain="all",
            source="all"
        )
    )

    # ========================================================
    # 2. BY MODEL
    # ========================================================

    model_groups = group_citations(
        citations,
        ["_model"]
    )

    for (
        model,
    ), group in sorted(
        model_groups.items()
    ):

        rows.append(
            make_summary_row(
                group,
                level="model",
                model=model,
                domain="all",
                source="all"
            )
        )

    # ========================================================
    # 3. BY DOMAIN
    # ========================================================

    domain_groups = group_citations(
        citations,
        ["_domain"]
    )

    for (
        domain,
    ), group in sorted(
        domain_groups.items()
    ):

        rows.append(
            make_summary_row(
                group,
                level="domain",
                model="all",
                domain=domain,
                source="all"
            )
        )

    # ========================================================
    # 4. BY SOURCE
    # ========================================================

    source_groups = group_citations(
        citations,
        ["_source"]
    )

    for (
        source,
    ), group in sorted(
        source_groups.items()
    ):

        rows.append(
            make_summary_row(
                group,
                level="source",
                model="all",
                domain="all",
                source=source
            )
        )

    # ========================================================
    # 5. MODEL × DOMAIN
    # ========================================================

    model_domain_groups = group_citations(
        citations,
        [
            "_model",
            "_domain"
        ]
    )

    for (
        model,
        domain
    ), group in sorted(
        model_domain_groups.items()
    ):

        rows.append(
            make_summary_row(
                group,
                level="model_domain",
                model=model,
                domain=domain,
                source="all"
            )
        )

    # ========================================================
    # 6. MODEL × SOURCE
    # ========================================================

    model_source_groups = group_citations(
        citations,
        [
            "_model",
            "_source"
        ]
    )

    for (
        model,
        source
    ), group in sorted(
        model_source_groups.items()
    ):

        rows.append(
            make_summary_row(
                group,
                level="model_source",
                model=model,
                domain="all",
                source=source
            )
        )

    return rows


# ============================================================
# SORT SUMMARY
# ============================================================

def sort_summary_rows(
    rows
):

    """
    Put summary rows into a logical order.

    Order:

        overall

        model

        domain

        source

        model_domain

        model_source
    """

    level_order = {

        "overall": 0,

        "model": 1,

        "domain": 2,

        "source": 3,

        "model_domain": 4,

        "model_source": 5,
    }

    return sorted(

        rows,

        key=lambda row: (

            level_order.get(
                row["level"],
                999
            ),

            str(
                row["model"]
            ),

            str(
                row["domain"]
            ),

            str(
                row["source"]
            ),
        )
    )


# ============================================================
# WRITE SUMMARY CSV
# ============================================================

def write_summary_csv(
    rows,
    output_file
):

    rows = sort_summary_rows(
        rows
    )

    # --------------------------------------------------------
    # Find every column
    # --------------------------------------------------------

    fieldnames = []

    for row in rows:

        for key in row:

            if key not in fieldnames:

                fieldnames.append(
                    key
                )

    # --------------------------------------------------------
    # Write
    # --------------------------------------------------------

    with open(
        output_file,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
            quoting=csv.QUOTE_ALL,
            escapechar="\\"
        )

        writer.writeheader()

        for row in rows:

            cleaned_row = {

                key: clean_number(
                    value
                )

                for key, value
                in row.items()
            }

            writer.writerow(
                cleaned_row
            )

    print(
        f"Wrote summary CSV:"
    )

    print(
        f"  {output_file}"
    )


# ============================================================
# WRITE CITATION-LEVEL CSV
# ============================================================

def write_citation_level_csv(
    citations,
    output_file
):

    """
    One row per citation.

    This is your master dataset for future analysis.
    """

    if not citations:

        print(
            "No citations to write."
        )

        return

    # --------------------------------------------------------
    # Preferred column order
    # --------------------------------------------------------

    preferred_fields = [

        # Dataset identification
        "_source_file",
        "_source_path",
        "_record_id",
        "_reference_number",

        # Research design
        "_model",
        "_domain",
        "_source",
        "_source_id",

        # Citation
        "citation",

        # Status
        "status",
        "derived_status",

        # Verification
        "title_found",
        "author_matched",
        "doi_valid",

        "derived_title_found",
        "derived_author_matched",
        "derived_doi_valid",

        "verification_score",

        # Gender
        "gender",
        "gender_probability",
        "gender_probability_numeric",
        "gender_confidence",

        # Productivity
        "h_index",
        "h_index_numeric",

        "works_count",
        "works_count_numeric",

        # Author
        "author_identified",

        # Databases
        "failed_dbs",
        "failed_database_count",
    ]

    # --------------------------------------------------------
    # Find every actual field
    # --------------------------------------------------------

    all_fields = []

    for citation in citations:

        for key in citation:

            if key not in all_fields:

                all_fields.append(
                    key
                )

    # --------------------------------------------------------
    # Put preferred fields first
    # --------------------------------------------------------

    fieldnames = []

    for field in preferred_fields:

        if (
            field in all_fields
            and field not in fieldnames
        ):

            fieldnames.append(
                field
            )

    # Any remaining fields
    for field in all_fields:

        if field not in fieldnames:

            fieldnames.append(
                field
            )

    # --------------------------------------------------------
    # Sort citation-level rows
    # --------------------------------------------------------

    sorted_citations = sorted(

        citations,

        key=lambda citation: (

            str(
                citation.get(
                    "_model",
                    ""
                )
            ),

            str(
                citation.get(
                    "_domain",
                    ""
                )
            ),

            str(
                citation.get(
                    "_source",
                    ""
                )
            ),

            str(
                citation.get(
                    "_record_id",
                    ""
                )
            ),

            citation.get(
                "_reference_number",
                0
            ),
        )
    )

    # --------------------------------------------------------
    # Write
    # --------------------------------------------------------

    with open(
        output_file,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
            quoting=csv.QUOTE_ALL,
            escapechar="\\"
        )

        writer.writeheader()

        for citation in sorted_citations:

            cleaned_row = {}

            for key, value in citation.items():

                # Lists such as failed_dbs
                # become semicolon-separated text.
                if isinstance(
                    value,
                    list
                ):

                    cleaned_row[key] = (
                        "; ".join(
                            str(item)
                            for item in value
                        )
                    )

                else:

                    cleaned_row[key] = (
                        clean_number(
                            value
                        )
                    )

            writer.writerow(
                cleaned_row
            )

    print(
        "Wrote citation-level CSV:"
    )

    print(
        f"  {output_file}"
    )


# ============================================================
# DATASET VALIDATION
# ============================================================

def validate_dataset(
    records,
    citations
):

    print()
    print("=" * 60)
    print("DATASET CHECK")
    print("=" * 60)

    print(
        f"Records/questions loaded: "
        f"{len(records):,}"
    )

    print(
        f"Citations loaded: "
        f"{len(citations):,}"
    )

    # --------------------------------------------------------
    # Models
    # --------------------------------------------------------

    models = Counter(
        citation.get(
            "_model",
            "unknown"
        )
        for citation in citations
    )

    print()
    print("Models:")

    for model, count in sorted(
        models.items()
    ):

        print(
            f"  {model}: {count:,}"
        )

    # --------------------------------------------------------
    # Domains
    # --------------------------------------------------------

    domains = Counter(
        citation.get(
            "_domain",
            "unknown"
        )
        for citation in citations
    )

    print()
    print("Domains:")

    for domain, count in sorted(
        domains.items()
    ):

        print(
            f"  {domain}: {count:,}"
        )

    # --------------------------------------------------------
    # Sources
    # --------------------------------------------------------

    sources = Counter(
        citation.get(
            "_source",
            "unknown"
        )
        for citation in citations
    )

    print()
    print("Sources:")

    for source, count in sorted(
        sources.items()
    ):

        print(
            f"  {source}: {count:,}"
        )

    # --------------------------------------------------------
    # Unknown mappings
    # --------------------------------------------------------

    unknown_sources = [

        citation.get(
            "_source_id"
        )

        for citation in citations

        if citation.get(
            "_source"
        ) == "unknown"
    ]

    if unknown_sources:

        print()
        print(
            "WARNING:"
        )

        print(
            "The following source IDs are not "
            "in SOURCE_MAP:"
        )

        for source_id in sorted(
            set(
                unknown_sources
            )
        ):

            print(
                f"  {source_id}"
            )

    # --------------------------------------------------------
    # Model/domain counts
    # --------------------------------------------------------

    print()
    print(
        "Model × Domain citation counts:"
    )

    model_domain = Counter(

        (
            citation.get(
                "_model",
                "unknown"
            ),

            citation.get(
                "_domain",
                "unknown"
            ),
        )

        for citation in citations
    )

    for (
        model,
        domain
    ), count in sorted(
        model_domain.items()
    ):

        print(
            f"  {model:10} | "
            f"{domain:20} | "
            f"{count:,}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("CITATION ANALYSIS")
    print("=" * 60)

    # --------------------------------------------------------
    # Create output directory
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Load JSON files
    # --------------------------------------------------------

    records = load_json_files(
        INPUT_DIR
    )

    # --------------------------------------------------------
    # Flatten citations
    # --------------------------------------------------------

    citations = get_all_citations(
        records
    )

    # --------------------------------------------------------
    # Add derived fields
    # --------------------------------------------------------

    for citation in citations:

        add_derived_fields(
            citation
        )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    validate_dataset(
        records,
        citations
    )

    # --------------------------------------------------------
    # Create summary
    # --------------------------------------------------------

    summary_rows = create_summary(
        citations
    )

    # --------------------------------------------------------
    # Write summary
    # --------------------------------------------------------

    write_summary_csv(
        summary_rows,
        SUMMARY_CSV
    )

    # --------------------------------------------------------
    # Write citation-level dataset
    # --------------------------------------------------------

    write_citation_level_csv(
        citations,
        CITATION_LEVEL_CSV
    )

    # --------------------------------------------------------
    # Finished
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("DONE")
    print("=" * 60)

    print()
    print(
        f"Summary:"
    )

    print(
        f"  {SUMMARY_CSV}"
    )

    print()

    print(
        f"Citation-level data:"
    )

    print(
        f"  {CITATION_LEVEL_CSV}"
    )

    print()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
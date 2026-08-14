# Citation Analysis CSV — Column Definitions

## 1. Dataset / Grouping

| Column | Meaning |
|---|---|
| `level` | Aggregation level: overall, model, domain, source, model×domain, or model×source. |
| `model` | LLM used: GPT, Gemini, or Claude. |
| `domain` | Research domain: physics, CS, environmental, medicine, or social sciences (consisting of psychology and economics as subdomains). |
| `source` | Specific source/journal/database within the domain. |
| `total_citations` | Total citations in that group. |

---

## 2. Citation Status

| Column | Meaning |
|---|---|
| `status_found` | Citations whose verification status is `found` (what we consider non-hallucinated). |
| `status_not_found` | Citations whose status is `not_found` (what we consider hallucinated). |
| `status_other` | Citations with any other status, such as `CHECK` (usually resulting from malformed data). |
| `status_*_pct` | Percentage of citations with that status. |

---

## 3. Verification

The three verification fields are:

- **Title** — Was the cited paper title found/matched?
- **Author** — Did the first author information match?
- **DOI** — Was the DOI valid?

| Column | Meaning |
|---|---|
| `title_found` | Number where the title was successfully verified. |
| `title_found_pct` | Percentage with verified titles. |
| `author_matched` | Number where author information matched. |
| `author_matched_pct` | Percentage with matched authors. |
| `doi_valid` | Number with a valid DOI. |
| `doi_valid_pct` | Percentage with a valid DOI. |
| `all_three_valid` | Number where title + author + DOI were all verified. |
| `all_three_valid_pct` | Percentage where all three were verified. |

### Verification Score

Each citation receives:

- Title verified = **1 point**
- Author matched = **1 point**
- DOI valid = **1 point**

Therefore the score ranges from **0–3**.

| Column | Meaning |
|---|---|
| `verification_score_average` | Mean verification score. |
| `verification_score_median` | Median verification score. |
| `verification_score_0` | Number scoring 0/3. |
| `verification_score_1` | Number scoring 1/3. |
| `verification_score_2` | Number scoring 2/3. |
| `verification_score_3` | Number scoring 3/3. |
| `verification_score_*_pct` | Percentage receiving that score. |
| `verification_unknown_or_missing` | Citations where one or more verification fields were missing/unusable. |

### Verification Combinations

`verification_title_yes__author_no__doi_yes`, for example, means:

> Title verified + author not matched + DOI valid.

All 8 combinations of title/author/DOI are reported.

The corresponding `_pct` column gives the percentage.

---

## 4. Gender

| Column | Meaning |
|---|---|
| `male` | Number classified as male. |
| `female` | Number classified as female. |
| `unknown_gender` | Number without a male/female classification. |
| `male_pct` | Male percentage of all citations. |
| `female_pct` | Female percentage of all citations. |
| `male_pct_known_gender` | Male percentage among only citations with known gender. |
| `female_pct_known_gender` | Female percentage among only citations with known gender. |

### Gender Confidence

| Column | Meaning |
|---|---|
| `male_high_confidence` | Male classifications with probability ≥ 0.75. |
| `female_high_confidence` | Female classifications with probability ≥ 0.75. |
| `male_low_confidence` | Male classifications with probability < 0.75. |
| `female_low_confidence` | Female classifications with probability < 0.75. |
| `high_confidence_combined` | Male + female high-confidence classifications. |
| `low_confidence_combined` | Male + female low-confidence classifications. |
| `gender_missing_probability` | Gender classifications without a usable probability. |
| `*_confidence_pct` | Percentage of all citations in that confidence category. |

### Gender × Status

`gender_male__status_found` means:

> Number of male citations whose status was `found`.

The same structure applies to female/unknown gender and other statuses.

### Gender × Verification Score

`gender_female__verification_score_3` means:

> Number of female citations receiving a verification score of 3.

---

## 5. Researcher Productivity

### H-index

| Column | Meaning |
|---|---|
| `h_index_average` | Average h-index among researchers with an h-index. |
| `h_index_median` | Median h-index. |
| `h_index_total_found` | Number of researchers with an h-index value. |
| `h_index_found_pct` | Researchers with h-index / all citations × 100. |
| `h_index_found_pct_identified` | Researchers with h-index / identified authors × 100. |

### Works

| Column | Meaning |
|---|---|
| `works_average` | Average number of works. |
| `works_median` | Median number of works. |
| `works_total_found` | Number with a works-count value. |
| `works_found_pct` | Works count available / all citations × 100. |
| `works_found_pct_identified` | Works count available / identified authors × 100. |

### Productivity × Gender

The same statistics are calculated separately for:

- `male_h_index_*`
- `female_h_index_*`
- `male_works_*`
- `female_works_*`

For example:

`female_h_index_average` = average h-index among female-classified researchers.

---

## 6. Author Identification

| Column | Meaning |
|---|---|
| `author_identified` | Number of citations where at least one author was successfully identified. |
| `author_not_identified` | Number where an author could not be identified. |
| `author_identification_pct` | Percentage where an author was identified. |

---

## 7. DOI

| Column | Meaning |
|---|---|
| `doi_valid` | Number with valid DOI. |
| `doi_invalid` | Number with invalid DOI. |
| `doi_unknown` | DOI status missing/unusable/unknown. |
| `doi_valid_pct` | Valid DOI / total citations × 100. |

---

## 8. Database Failures

These indicate databases that failed during the citation lookup process.

| Column | Meaning |
|---|---|
| `failed_db_acl_anthology` | Number of citations where ACL Anthology lookup failed. |
| `failed_db_crossref` | Number where Crossref lookup failed. |
| `failed_db_europe_pmc` | Number where Europe PMC lookup failed. |
| `failed_db_open_library` | Number where Open Library lookup failed. |
| `failed_db_openalex` | Number where OpenAlex lookup failed. |
| `failed_db_semantic_scholar` | Number where Semantic Scholar lookup failed. |
| `failed_db_arxiv` | Number where arXiv lookup failed. |
| `failed_db_*_pct` | That database's failures / total citations × 100. |

---

## 9. Reading the Columns Quickly

The naming convention is consistent:

```text
<variable>                 = count/value
<variable>_pct             = percentage
<gender>_<variable>       = statistic for that gender
<gender>__<variable>      = cross-tabulation
"""Compute hallucination rates for the verified LLM output files.

This script reads the JSON files stored under data/verification/{anthr,gemini,gpt}
and reports:
  - title not found rate
  - title found but author not matched rate
  - combined hallucination rate for reference entries
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent / "data" / "verification"
MODEL_NAMES = ("anthr", "gemini", "gpt")


def iter_references(model_dir: Path) -> Iterable[dict[str, Any]]:
    """Yield every reference object from all JSON files in a model directory."""
    for path in sorted(model_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            records = [payload]
        else:
            continue

        for record in records:
            if not isinstance(record, dict):
                continue
            refs = record.get("references", [])
            if isinstance(refs, list):
                for ref in refs:
                    if isinstance(ref, dict):
                        yield ref


def normalize_reference_flags(ref: dict[str, Any]) -> tuple[bool, bool]:
    """Return (title_found, author_matched) with safe fallbacks."""
    title_found = ref.get("title_found")
    if title_found is None:
        title_found = ref.get("status") != "not_found"

    author_matched = ref.get("author_matched")
    if author_matched is None:
        author_matched = ref.get("status") == "verified"

    return bool(title_found), bool(author_matched)


def summarize_model(model_name: str) -> dict[str, float | int]:
    """Compute overall rates for one LLM."""
    model_dir = ROOT / model_name
    if not model_dir.exists():
        raise FileNotFoundError(f"Missing verification folder: {model_dir}")

    total_refs = 0
    title_not_found = 0
    title_found_but_author_not = 0

    for ref in iter_references(model_dir):
        total_refs += 1
        title_found, author_matched = normalize_reference_flags(ref)

        if not title_found:
            title_not_found += 1
        elif not author_matched:
            title_found_but_author_not += 1

    return {
        "model": model_name,
        "total_refs": total_refs,
        "title_not_found": title_not_found,
        "title_found_but_author_not": title_found_but_author_not,
        "title_not_found_rate": (title_not_found / total_refs * 100) if total_refs else 0.0,
        "title_found_but_author_not_rate": (title_found_but_author_not / total_refs * 100) if total_refs else 0.0,
        "combined_hallucination_rate": ((title_not_found + title_found_but_author_not) / total_refs * 100) if total_refs else 0.0,
    }


def main() -> None:
    results = [summarize_model(model_name) for model_name in MODEL_NAMES]

    print("Overall hallucination rates by LLM")
    print("-" * 92)
    print(f"{'Model':<10} {'Total refs':>10} {'Title missing':>16} {'Rate':>10} {'Title+author mismatch':>22} {'Rate':>10} {'Combined':>10}")
    print("-" * 92)

    for result in results:
        print(
            f"{result['model']:<10} "
            f"{result['total_refs']:>10} "
            f"{result['title_not_found']:>16} "
            f"{result['title_not_found_rate']:>9.2f}% "
            f"{result['title_found_but_author_not']:>22} "
            f"{result['title_found_but_author_not_rate']:>9.2f}% "
            f"{result['combined_hallucination_rate']:>9.2f}%"
        )


if __name__ == "__main__":
    main()

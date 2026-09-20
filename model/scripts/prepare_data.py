"""Validate, deduplicate, and document-split Arabic-English training pairs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ARABIC = re.compile(r"[\u0600-\u06ff]")
LATIN = re.compile(r"[A-Za-z]")
BIDI_CONTROLS = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u206f]")
WHITESPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = BIDI_CONTROLS.sub("", text).replace("ـ", "")
    return WHITESPACE.sub(" ", text).strip()


def char_share(pattern: re.Pattern[str], text: str) -> float:
    letters = [character for character in text if character.isalpha()]
    if not letters:
        return 0.0
    return sum(bool(pattern.fullmatch(character)) for character in letters) / len(letters)


def stable_split(document_id: str, seed: int, validation: float, test: float) -> str:
    digest = hashlib.sha256(f"{seed}:{document_id}".encode()).digest()
    bucket = int.from_bytes(digest[:8], "big") / 2**64
    if bucket < test:
        return "test"
    if bucket < test + validation:
        return "validation"
    return "train"


def read_rows(paths: Iterable[Path]) -> Iterable[tuple[str, int, dict[str, Any]]]:
    for path in paths:
        with path.open(encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                if line.strip():
                    yield str(path), line_number, json.loads(line)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("model/config.json"))
    parser.add_argument("--validation-ratio", type=float, default=0.05)
    parser.add_argument("--test-ratio", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-source-chars", type=int, default=8)
    parser.add_argument("--max-source-chars", type=int, default=1200)
    args = parser.parse_args()
    if args.validation_ratio + args.test_ratio >= 1:
        parser.error("validation and test ratios must sum to less than 1")

    config = json.loads(args.config.read_text(encoding="utf-8"))
    approved = {item.upper() for item in config["approved_licenses"]}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_pairs: set[str] = set()
    source_targets: dict[str, str] = {}

    for path, line_number, raw in read_rows(args.input):
        arabic = normalise(str(raw.get("arabic", raw.get("source_text", ""))))
        english = normalise(str(raw.get("english", raw.get("target_text", ""))))
        reason = None
        license_id = str(raw.get("license", "")).upper()
        if not arabic or not english:
            reason = "missing_text"
        elif not raw.get("source"):
            reason = "missing_source"
        elif license_id not in approved:
            reason = "unapproved_license"
        elif not (args.min_source_chars <= len(arabic) <= args.max_source_chars):
            reason = "source_length"
        elif len(english) > args.max_source_chars * 2:
            reason = "target_length"
        elif char_share(ARABIC, arabic) < 0.55:
            reason = "source_not_arabic"
        elif char_share(LATIN, english) < 0.55:
            reason = "target_not_english"
        else:
            pair_hash = hashlib.sha256(f"{arabic}\0{english}".encode()).hexdigest()
            source_hash = hashlib.sha256(arabic.encode()).hexdigest()
            if pair_hash in seen_pairs:
                reason = "duplicate_pair"
            elif source_hash in source_targets and source_targets[source_hash] != english:
                reason = "conflicting_target"
            else:
                seen_pairs.add(pair_hash)
                source_targets[source_hash] = english
        if reason:
            rejected.append({"file": path, "line": line_number, "reason": reason})
            continue

        document_id = str(raw.get("document_id") or raw.get("id") or pair_hash)
        row = dict(raw)
        row.update(
            {
                "id": str(raw.get("id") or pair_hash[:16]),
                "document_id": document_id,
                "arabic": arabic,
                "english": english,
                "license": license_id,
            }
        )
        row["split"] = stable_split(
            document_id, args.seed, args.validation_ratio, args.test_ratio
        )
        accepted.append(row)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    split_counts: Counter[str] = Counter()
    for split in ("train", "validation", "test"):
        rows = [row for row in accepted if row["split"] == split]
        split_counts[split] = len(rows)
        with (args.output_dir / f"{split}.jsonl").open(
            "w", encoding="utf-8", newline="\n"
        ) as output:
            for row in rows:
                output.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    report = {
        "accepted": len(accepted),
        "rejected": len(rejected),
        "splits": dict(split_counts),
        "rejection_reasons": dict(Counter(item["reason"] for item in rejected)),
        "documents_by_split": {
            split: len({row["document_id"] for row in accepted if row["split"] == split})
            for split in ("train", "validation", "test")
        },
        "rejected_rows": rejected,
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in report.items() if key != "rejected_rows"}, indent=2))


if __name__ == "__main__":
    main()


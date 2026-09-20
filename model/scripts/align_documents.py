"""Create ordered Arabic-English alignment candidates for human review.

The source documents are translations of one another, but their paragraph
boundaries differ. This uses a Gale-Church-style dynamic program based on
relative text length and order. Its output is deliberately marked
``needs_review`` and uses a non-approved rights status, so it cannot be fed to
the trainer by accident.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import unicodedata
from pathlib import Path
from typing import Iterable


ARABIC = re.compile(r"[\u0600-\u06ff]")
LATIN = re.compile(r"[A-Za-z]")
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!؟؛])\s+")
ARABIC_CLAUSE_BOUNDARY = re.compile(r"(?<=،)\s+")
ENGLISH_SECTION_HEADING = re.compile(r"^(the )?(first|second) (khutba|khutbah|sermon)\s*:?$", re.I)
ALIGNMENT_CUES = (
    ("الحمد لله", ("praise", "allah")),
    ("اما بعد", ("to continue", "to proceed", "as for what follows")),
    ("ايها المؤمنون", ("o believers",)),
    ("عباد الله", ("servants of allah", "worshippers of allah")),
    ("اقول قولي", ("i say these words", "i say this")),
)


def script_share(pattern: re.Pattern[str], text: str) -> float:
    letters = [character for character in text if character.isalpha()]
    if not letters:
        return 0.0
    return sum(bool(pattern.fullmatch(character)) for character in letters) / len(letters)


def letter_count(pattern: re.Pattern[str], text: str) -> int:
    return len(pattern.findall(text))


def unvocalised(text: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFD", text.replace("ـ", ""))
        if unicodedata.category(character) != "Mn"
    )


def sermon_body(paragraphs: Iterable[str], language: str) -> list[str]:
    items = list(paragraphs)
    if language == "ar":
        start = next(
            (
                index
                for index, paragraph in enumerate(items)
                if "الحمد لله" in unvocalised(paragraph)
            ),
            0,
        )
        return [
            paragraph
            for paragraph in items[start:]
            if "الخطبة الاولى" not in unvocalised(paragraph)
            and "الخطبة الثانية" not in unvocalised(paragraph)
        ]
    start = next(
        (
            index
            for index, paragraph in enumerate(items)
            if re.search(r"\bpraise\b", paragraph, flags=re.I)
        ),
        0,
    )
    return [
        paragraph
        for paragraph in items[start:]
        if not ENGLISH_SECTION_HEADING.fullmatch(paragraph.strip())
    ]


def cue_cost(source_text: str, target_text: str) -> float:
    source_text = unvocalised(source_text)
    target_text = target_text.casefold()
    adjustment = 0.0
    for arabic_cue, english_cues in ALIGNMENT_CUES:
        source_has_cue = arabic_cue in source_text
        target_has_cue = any(cue in target_text for cue in english_cues)
        if source_has_cue and target_has_cue:
            adjustment -= 0.4
        elif source_has_cue != target_has_cue:
            adjustment += 0.3
    return adjustment


def cue_mask(text: str, language: str) -> int:
    text = unvocalised(text) if language == "ar" else text.casefold()
    mask = 0
    for index, (arabic_cue, english_cues) in enumerate(ALIGNMENT_CUES):
        present = (
            arabic_cue in text
            if language == "ar"
            else any(cue in text for cue in english_cues)
        )
        if present:
            mask |= 1 << index
    return mask


def mask_cost(source_mask: int, target_mask: int) -> float:
    shared = (source_mask & target_mask).bit_count()
    mismatched = (source_mask ^ target_mask).bit_count()
    return -0.4 * shared + 0.3 * mismatched


def pack(parts: Iterable[str], maximum: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        candidate = f"{current} {part}".strip()
        if current and len(candidate) > maximum:
            chunks.append(current)
            current = part
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def arabic_segments(paragraphs: Iterable[str], maximum: int = 480) -> list[str]:
    segments: list[str] = []
    for paragraph in sermon_body(paragraphs, "ar"):
        if script_share(ARABIC, paragraph) < 0.65:
            continue
        for sentence in SENTENCE_BOUNDARY.split(paragraph):
            if len(sentence) <= maximum:
                if letter_count(ARABIC, sentence) >= 4:
                    segments.append(sentence.strip())
            else:
                segments.extend(
                    item
                    for item in pack(ARABIC_CLAUSE_BOUNDARY.split(sentence), maximum)
                    if letter_count(ARABIC, item) >= 4
                )
    return segments


def english_segments(paragraphs: Iterable[str], maximum: int = 720) -> list[str]:
    segments: list[str] = []
    for paragraph in sermon_body(paragraphs, "en"):
        if script_share(LATIN, paragraph) < 0.55:
            continue
        for sentence in SENTENCE_BOUNDARY.split(paragraph):
            segments.extend(
                item
                for item in pack([sentence], maximum)
                if letter_count(LATIN, item) >= 4
            )
    return segments


def align(source: list[str], target: list[str]) -> list[dict]:
    """Return monotonic 1:1, 1:2, 2:1, 2:2 alignments and gaps."""
    if not source or not target:
        return []
    source_lengths = [letter_count(ARABIC, item) for item in source]
    target_lengths = [letter_count(LATIN, item) for item in target]
    source_cues = [cue_mask(item, "ar") for item in source]
    target_cues = [cue_mask(item, "en") for item in target]
    ratio = sum(target_lengths) / max(sum(source_lengths), 1)
    operations = (
        (1, 1, 0.0),
        (1, 2, 0.12),
        (1, 3, 0.2),
        (1, 4, 0.3),
        (2, 1, 0.12),
        (2, 2, 0.2),
        (2, 3, 0.28),
        (3, 1, 0.2),
        (3, 2, 0.28),
        (1, 0, 1.8),
        (0, 1, 1.8),
    )
    rows, columns = len(source) + 1, len(target) + 1
    costs = [[math.inf] * columns for _ in range(rows)]
    previous: list[list[tuple[int, int, int, int, float] | None]] = [
        [None] * columns for _ in range(rows)
    ]
    costs[0][0] = 0.0
    for i in range(rows):
        for j in range(columns):
            if math.isinf(costs[i][j]):
                continue
            for take_source, take_target, penalty in operations:
                next_i, next_j = i + take_source, j + take_target
                if next_i >= rows or next_j >= columns:
                    continue
                source_length = sum(source_lengths[i:next_i])
                target_length = sum(target_lengths[j:next_j])
                if take_source and take_target:
                    expected = max(source_length * ratio, 1)
                    source_mask = 0
                    target_mask = 0
                    for mask in source_cues[i:next_i]:
                        source_mask |= mask
                    for mask in target_cues[j:next_j]:
                        target_mask |= mask
                    local_cost = max(
                        0.01,
                        abs(math.log((target_length + 8) / (expected + 8)))
                        + penalty
                        + mask_cost(source_mask, target_mask),
                    )
                else:
                    local_cost = penalty + 0.001 * (source_length + target_length)
                candidate = costs[i][j] + local_cost
                if candidate < costs[next_i][next_j]:
                    costs[next_i][next_j] = candidate
                    previous[next_i][next_j] = (
                        i,
                        j,
                        take_source,
                        take_target,
                        local_cost,
                    )

    result = []
    i, j = len(source), len(target)
    while i or j:
        step = previous[i][j]
        if step is None:
            raise RuntimeError("Alignment path is incomplete")
        old_i, old_j, take_source, take_target, local_cost = step
        result.append(
            {
                "source_start": old_i,
                "source_end": i,
                "target_start": old_j,
                "target_end": j,
                "arabic": " ".join(source[old_i:i]),
                "english": " ".join(target[old_j:j]),
                "alignment_type": f"{take_source}:{take_target}",
                "alignment_cost": round(local_cost, 4),
                "alignment_confidence": round(math.exp(-local_cost), 4),
            }
        )
        i, j = old_i, old_j
    result.reverse()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("model/data/raw/islamic-network/documents.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("model/data/raw/islamic-network/alignment_candidates.jsonl"),
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    documents = 0
    pairs = 0
    gaps = 0
    confidences = []
    with args.input.open(encoding="utf-8") as source, args.output.open(
        "w", encoding="utf-8", newline="\n"
    ) as output:
        for line in source:
            if not line.strip():
                continue
            document = json.loads(line)
            source_segments = arabic_segments(document["arabic_paragraphs"])
            target_segments = english_segments(document["english_paragraphs"])
            for index, candidate in enumerate(align(source_segments, target_segments), start=1):
                if not candidate["arabic"] or not candidate["english"]:
                    gaps += 1
                    continue
                candidate.update(
                    {
                        "id": f"{document['document_id']}-a{index:04d}",
                        "document_id": document["document_id"],
                        "date": document["date"],
                        "title": document["title"],
                        "source": document["source"],
                        "source_api_url": document["source_api_url"],
                        "attribution": document["attribution"],
                        "license": document["copyright_status"],
                        "domain": "khutbah",
                        "review_status": "needs_review",
                    }
                )
                output.write(json.dumps(candidate, ensure_ascii=False, sort_keys=True) + "\n")
                confidences.append(candidate["alignment_confidence"])
                pairs += 1
            documents += 1
    report = {
        "documents": documents,
        "candidate_pairs": pairs,
        "discarded_gaps": gaps,
        "median_alignment_confidence": round(statistics.median(confidences), 4)
        if confidences
        else None,
        "warning": (
            "Length-based candidates are not gold translations. Human review and an approved "
            "rights basis are required before changing review_status or license."
        ),
    }
    args.output.with_suffix(".report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

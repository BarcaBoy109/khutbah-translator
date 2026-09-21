"""Join explicitly AI-authored English annotations to the licensed SAT transcripts."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    annotation_path = ROOT / "model/data/annotations/sat-pilot-en.tsv"
    fingerprint_path = ROOT / "model/data/annotations/sat-source-hashes.json"
    fingerprints = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    with annotation_path.open(encoding="utf-8", newline="") as source:
        annotations = list(csv.DictReader(source, delimiter="\t"))
    translations = {row["id"]: row["english"] for row in annotations}
    if len(translations) != len(annotations):
        raise ValueError("Duplicate annotation IDs")
    raw_path = ROOT / "model/data/raw/sat/arabic.jsonl"
    rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
    selected, excluded = [], []
    found = set()
    for row in rows:
        if row["id"] not in translations:
            excluded.append(row["id"])
            continue
        digest = hashlib.sha256(row["arabic"].encode("utf-8")).hexdigest()
        if fingerprints.get(row["id"]) != digest:
            raise ValueError(f"Transcript changed since annotation: {row['id']}")
        found.add(row["id"])
        selected.append({**row, "english": translations[row["id"]], "synthetic_target": True,
                         "translation_method": "Codex AI translation of the supplied Arabic excerpt",
                         "review_status": "AI-only; bilingual human review pending",
                         "quote_type": "unreviewed", "changes": "Three adjacent transcript chunks joined; English translation added; no Arabic spelling repairs"})
    if found != set(translations):
        raise ValueError(f"Missing source IDs: {set(translations) - found}")
    output = ROOT / "model/data/raw/sat/pilot.jsonl"
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8")
    report = {"selected": len(selected), "documents": len({r["document_id"] for r in selected}),
              "synthetic_targets": len(selected), "excluded_ids": excluded,
              "exclusion_notes": "Untranslated fragments have unclear/truncated content or transcription errors; sermon_21 duplicates sermon_12 and is excluded in full.",
              "annotations_sha256": hashlib.sha256(annotation_path.read_bytes()).hexdigest(),
              "corpus_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
    (output.parent / "pilot-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

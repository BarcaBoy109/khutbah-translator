"""Fail closed on unlicensed data, evaluation overlap and cross-document leakage."""
import hashlib
import json
from pathlib import Path
import unicodedata


def source_key(text):
    text = unicodedata.normalize("NFKC", text).replace("ـ", "")
    return "".join(c for c in text if unicodedata.category(c).startswith("L")).casefold()


def validate_files(config):
    approved = {value.upper() for value in config["approved_licenses"]}
    evaluation = Path(__file__).resolve().parents[1] / "data/evaluation/khutbah_eval.jsonl"
    heldout = {source_key(json.loads(line)["arabic"]) for line in evaluation.read_text(encoding="utf-8").splitlines() if line.strip()}
    documents, sources, report = {}, {}, {}
    for split in ("train", "validation", "test"):
        path = Path(config[f"{split}_file"])
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not rows:
            raise ValueError(f"Empty {split} split")
        for row in rows:
            if not row.get("source") or row.get("license", "").upper() not in approved:
                raise ValueError(f"Missing provenance or unapproved license in {split}")
            if row.get("synthetic_target") and not config.get("allow_synthetic_targets", False):
                raise ValueError("Synthetic targets require explicit experiment configuration")
            doc = row.get("document_id")
            if not doc or not row.get("english") or not row.get("arabic"):
                raise ValueError("Missing document_id or translation text")
            key = source_key(row["arabic"])
            if split == "train" and any(item in key or key in item for item in heldout):
                raise ValueError("Training data overlaps the protected evaluation seed")
            for value, registry in ((doc, documents), (key, sources)):
                if value in registry and registry[value] != split:
                    raise ValueError(f"Cross-split leakage involving {doc}")
                registry[value] = split
        report[split] = {"examples": len(rows), "documents": len({r["document_id"] for r in rows}),
                         "synthetic_targets": sum(bool(r.get("synthetic_target")) for r in rows),
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return report

"""Extract Arabic and English paragraphs from downloaded sermon documents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from extract_docx import clean_text, extract_paragraphs as extract_docx_paragraphs


def extract_pdf_paragraphs(path: Path) -> list[str]:
    import pdfplumber

    paragraphs: list[str] = []
    with pdfplumber.open(path) as document:
        for page in document.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            paragraphs.extend(clean_text(line) for line in text.splitlines() if clean_text(line))
    return paragraphs


def extract(path: Path, file_format: str) -> list[str]:
    if file_format == "doc":
        return extract_docx_paragraphs(path)
    if file_format == "pdf":
        return extract_pdf_paragraphs(path)
    raise ValueError(f"Unsupported document format: {file_format}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("model/data/raw/islamic-network/manifest.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("model/data/raw/islamic-network/documents.jsonl"),
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    failures = []
    with args.manifest.open(encoding="utf-8") as source, args.output.open(
        "w", encoding="utf-8", newline="\n"
    ) as output:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not record.get("download_complete"):
                continue
            try:
                for language in ("arabic", "english"):
                    edition = record[language]
                    record[f"{language}_paragraphs"] = extract(
                        Path(edition["local_path"]), edition["format"]
                    )
                if not record["arabic_paragraphs"] or not record["english_paragraphs"]:
                    raise ValueError("one or both editions extracted no text")
            except Exception as exc:
                failures.append(
                    {"line": line_number, "document_id": record.get("document_id"), "error": str(exc)}
                )
                continue
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    report = {"extracted": count, "failed": len(failures), "failures": failures}
    args.output.with_suffix(".report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"extracted": count, "failed": len(failures)}, indent=2))


if __name__ == "__main__":
    main()


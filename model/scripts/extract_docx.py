"""Extract text paragraphs from downloaded Islamic Network DOCX pairs.

This stage deliberately produces document JSONL, not training pairs. Arabic
and English documents have different paragraph structures, so positional
paragraph zipping would create incorrect supervision.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
BIDI_CONTROLS = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u206f]")
WHITESPACE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = BIDI_CONTROLS.sub("", text)
    return WHITESPACE.sub(" ", text).strip()


def extract_paragraphs(path: Path) -> list[str]:
    try:
        with ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (BadZipFile, KeyError) as exc:
        raise ValueError(f"Not a readable DOCX: {path}") from exc
    paragraphs = []
    body = root.find(".//w:body", WORD_NS)
    if body is None:
        return paragraphs
    for paragraph in body.findall(".//w:p", WORD_NS):
        text = clean_text(
            "".join(node.text or "" for node in paragraph.findall(".//w:t", WORD_NS))
        )
        if text:
            paragraphs.append(text)
    return paragraphs


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
    with args.manifest.open(encoding="utf-8") as source, args.output.open(
        "w", encoding="utf-8", newline="\n"
    ) as output:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("download_complete") is False:
                continue
            for language in ("arabic", "english"):
                edition = record[language]
                if edition.get("format") != "doc" or not edition.get("local_path"):
                    raise ValueError(
                        f"Line {line_number}: {language} must be a downloaded DOCX"
                    )
                record[f"{language}_paragraphs"] = extract_paragraphs(
                    Path(edition["local_path"])
                )
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    print(f"Extracted {count} paired sermon documents to {args.output}")


if __name__ == "__main__":
    main()

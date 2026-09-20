"""Catalog and optionally download paired UAE Awqaf sermon documents.

The Islamic Network API makes the files programmatically accessible, but its
copyright notice says the contents remain owned by the source. Downloading is
therefore separate from approving records for model training.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable


API_TEMPLATE = "https://sermons.islamic.network/api/uae-awqaf/{year}/friday.json"
USER_AGENT = "KhutbahT-corpus-builder/0.1 (+https://sermons.islamic.network/)"


def get_json(url: str, retries: int = 3) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError):
            if attempt + 1 == retries:
                raise
            time.sleep(2**attempt)


def flatten_sermons(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("sermons"), list):
                yield from item["sermons"]
            elif isinstance(item, dict) and "editions" in item:
                yield item
    elif isinstance(payload, dict):
        groups = payload.get("sermons", payload.get("data", []))
        yield from flatten_sermons(groups)


def select_edition(
    sermon: dict[str, Any], language: str, preferred_formats: tuple[str, ...]
) -> dict[str, str] | None:
    editions = sermon.get("editions", [])
    for file_format in preferred_formats:
        for edition in editions:
            if (
                edition.get("language") == language
                and edition.get("format") == file_format
                and edition.get("url")
            ):
                return {"format": file_format, "url": edition["url"]}
    return None


def catalog_year(year: int, preferred_formats: tuple[str, ...]) -> list[dict[str, Any]]:
    api_url = API_TEMPLATE.format(year=year)
    payload = get_json(api_url)
    records = []
    for sermon in flatten_sermons(payload):
        arabic = select_edition(sermon, "ar", preferred_formats)
        english = select_edition(sermon, "en", preferred_formats)
        if not arabic or not english:
            continue
        iso_date = sermon.get("date", {}).get("iso8601", "")
        date = iso_date[:10] or f"{year}-unknown"
        records.append(
            {
                "document_id": f"uae-awqaf-{date}",
                "date": date,
                "title": sermon.get("title", ""),
                "source": "UAE Awqaf via Islamic Network",
                "source_handle": sermon.get("source", "uae-awqaf"),
                "source_api_url": api_url,
                "source_page": "https://sermons.islamic.network/uae-awqaf/",
                "copyright_status": "COPYRIGHT-SOURCE-PERMISSION-REQUIRED",
                "attribution": (
                    "General Authority of Islamic Affairs and Endowments, UAE; "
                    "accessed via Islamic Network"
                ),
                "arabic": arabic,
                "english": english,
            }
        )
    duplicate_ids = {
        document_id
        for document_id, count in Counter(row["document_id"] for row in records).items()
        if count > 1
    }
    for record in records:
        if record["document_id"] in duplicate_ids:
            identity = f"{record['date']}\0{record['title']}"
            discriminator = hashlib.sha256(identity.encode()).hexdigest()[:8]
            record["document_id"] = f"{record['document_id']}-{discriminator}"
    return records


def download(url: str, destination: Path, retries: int = 3) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(retries):
        digest = hashlib.sha256()
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=30) as response, partial.open("wb") as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
                    digest.update(chunk)
            partial.replace(destination)
            return digest.hexdigest()
        except urllib.error.HTTPError as exc:
            partial.unlink(missing_ok=True)
            if exc.code not in {408, 429, 500, 502, 503, 504} or attempt + 1 == retries:
                raise
            time.sleep(2**attempt)
        except (urllib.error.URLError, TimeoutError):
            partial.unlink(missing_ok=True)
            if attempt + 1 == retries:
                raise
            time.sleep(2**attempt)
    raise AssertionError("retry loop exited unexpectedly")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("model/data/raw/islamic-network")
    )
    parser.add_argument("--download", action="store_true", help="Download paired documents")
    parser.add_argument(
        "--preferred-format",
        choices=("doc", "pdf"),
        default="doc",
        help="Document format to catalog and download (default: doc)",
    )
    parser.add_argument("--limit", type=int, help="Limit records after cataloging")
    args = parser.parse_args()
    if args.start_year > args.end_year:
        parser.error("--start-year must be no later than --end-year")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for year in range(args.start_year, args.end_year + 1):
        try:
            records.extend(catalog_year(year, (args.preferred_format,)))
        except Exception as exc:  # preserve partial catalog across unavailable years
            errors.append({"year": str(year), "error": str(exc)})
    records.sort(key=lambda row: row["date"])
    if args.limit is not None:
        records = records[: args.limit]

    if args.download:
        for index, record in enumerate(records, start=1):
            record["download_errors"] = []
            for language in ("arabic", "english"):
                edition = record[language]
                extension = ".docx" if edition["format"] == "doc" else ".pdf"
                destination = args.output_dir / "documents" / (
                    f"{record['document_id']}.{language[:2]}{extension}"
                )
                try:
                    if not destination.exists():
                        edition["sha256"] = download(edition["url"], destination)
                        time.sleep(0.15)
                    else:
                        edition["sha256"] = hashlib.sha256(destination.read_bytes()).hexdigest()
                    edition["local_path"] = destination.as_posix()
                except Exception as exc:
                    record["download_errors"].append(
                        {"language": language, "url": edition["url"], "error": str(exc)}
                    )
            record["download_complete"] = not record["download_errors"]
            status = "ok" if record["download_complete"] else "incomplete"
            print(f"[{index}/{len(records)}] {record['document_id']} {status}", flush=True)

    manifest = args.output_dir / "manifest.jsonl"
    with manifest.open("w", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    summary = {
        "records": len(records),
        "downloaded": bool(args.download),
        "download_complete": sum(bool(row.get("download_complete")) for row in records),
        "download_incomplete": sum(
            bool(args.download and not row.get("download_complete")) for row in records
        ),
        "years": [args.start_year, args.end_year],
        "errors": errors,
        "copyright_notice": (
            "Islamic Network states that copyright for sermons remains with the source. "
            "Cataloging/downloading does not itself establish model-training rights."
        ),
    }
    (args.output_dir / "fetch_report.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

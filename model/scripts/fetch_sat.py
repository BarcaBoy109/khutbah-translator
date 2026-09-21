"""Download a deterministic text-only SAT sample with source hashes and attribution."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
import urllib.request

API = "https://data.mendeley.com/public-api/datasets/fnz5bt24st"
SOURCE = "https://data.mendeley.com/datasets/fnz5bt24st/1"


def get(url):
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={
                "Accept": "application/vnd.mendeley-public-dataset.1+json",
                "User-Agent": "KhutbahT-research/0.1",
            })
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read()
        except OSError:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("model/data/raw/sat"))
    parser.add_argument("--segments-per-sermon", type=int, default=4)
    parser.add_argument("--context-segments", type=int, default=3)
    args = parser.parse_args()
    if args.segments_per_sermon < 1 or args.context_segments < 1:
        parser.error("segments-per-sermon must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    folders = json.loads(get(f"{API}/folders/1"))
    (args.output_dir / "folders.json").write_text(json.dumps(folders), encoding="utf-8")
    root = next(f["id"] for f in folders if f["name"] == "text dataset")
    sermons = sorted((f for f in folders if f.get("parent_id") == root), key=lambda f: int(f["name"].split("_")[-1]))

    def download_sermon(folder):
        path = args.output_dir / folder["name"]
        path.mkdir(exist_ok=True)
        manifest_path = path / "manifest.json"
        if manifest_path.exists():
            files = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            files = json.loads(get(f"{API}/files?folder_id={folder['id']}&version=1"))
            manifest_path.write_text(json.dumps(files), encoding="utf-8")
        files = sorted((f for f in files if f["filename"].endswith(".txt")), key=lambda f: int(f["filename"].split("_")[0]))
        count = min(len(files), args.segments_per_sermon)
        # Sample the body, not just repeated introductions and conclusions.
        indexes = sorted({int((i + 1) * len(files) / (count + 1)) for i in range(count)})
        rows = []
        for index in indexes:
            f = files[index]
            texts, provenance = [], []
            start = max(0, index - args.context_segments // 2)
            for part in files[start:start + args.context_segments]:
                local = path / (part["id"] + ".txt")
                content = local.read_bytes() if local.exists() else get(part["content_details"]["download_url"])
                digest = hashlib.sha256(content).hexdigest()
                if digest != part["content_details"]["sha256_hash"]:
                    raise ValueError(f"Checksum mismatch for {part['id']}")
                local.write_bytes(content)
                texts.append(content.decode("utf-8-sig").strip())
                provenance.append({"filename": part["filename"], "sha256": digest, "url": part["content_details"]["download_url"]})
            rows.append({
                "id": f"sat-{folder['name']}-{index}", "document_id": f"sat-{folder['name']}",
                "arabic": " ".join(texts), "source": SOURCE,
                "source_url": f["content_details"]["download_url"], "source_segments": provenance,
                "source_filename": f["filename"], "license": "CC-BY-4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "attribution": "Abbas, Samah (2023), Sermon_audio_and_text_dataset (SAT), Mendeley Data, V1, doi:10.17632/fnz5bt24st.1",
                "domain": "khutbah", "dataset_version": 1,
            })
        print(f"Downloaded {folder['name']}: {len(rows)} / {len(files)} transcript segments", flush=True)
        return rows

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = [r for group in pool.map(download_sermon, sermons) for r in group]
    with (args.output_dir / "arabic.jsonl").open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    report = {"source": SOURCE, "license": "CC-BY-4.0", "sermons": len(sermons), "segments": len(rows), "english_targets": 0}
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()

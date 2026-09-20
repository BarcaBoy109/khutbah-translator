# Khutbah translation model

This directory contains the independent training track for a specialised
Arabic-to-English Khutbah translator. The production application still uses
TranslateAPI.ai; nothing here is imported by `app.py` yet.

## Approach

The first baseline fine-tunes
[`Helsinki-NLP/opus-mt-ar-en`](https://huggingface.co/Helsinki-NLP/opus-mt-ar-en),
an Apache-2.0 Arabic-to-English Marian model. It is small enough to train and
serve without LLM-scale hardware, already has Arabic/English translation
ability, and gives us a clean baseline before considering a larger model.

Do not train on a source merely because it is publicly downloadable. Every
record must carry its source, document ID, and licence. The preparation script
rejects records with an unapproved licence. See [DATA_SOURCES.md](DATA_SOURCES.md)
for the source audit and permission status.

## Expected raw data

Place licensed or explicitly permissioned JSONL files in `model/data/raw/`.
Raw files are ignored by Git. One translation pair per line:

```json
{"id":"sermon-2026-01-p0001","document_id":"sermon-2026-01","arabic":"...","english":"...","source":"publisher-name","license":"CC-BY-4.0","domain":"khutbah"}
```

Required fields are `arabic`, `english`, `source`, and `license`.
`document_id` is strongly recommended: the splitter keeps a whole sermon in
one split, preventing train/evaluation leakage. Supported licence identifiers
are listed in `config.json`; add another only after checking its actual terms.

## Acquire the Islamic Network corpus

The API importer catalogs only sermons that have both Arabic and English
editions. Some older `doc` files are legacy Word binaries despite their
`.docx` filenames; the extractor quarantines those records and keeps only
valid OOXML pairs. PDF text is not used because testing showed broken visual
ordering in extracted Arabic.

```powershell
python model/scripts/fetch_islamic_network.py `
  --start-year 2018 --end-year 2026 `
  --preferred-format doc --download

python model/scripts/extract_documents.py
python model/scripts/align_documents.py
```

This creates an ignored raw manifest and extracted document text with hashes,
URLs, attribution, and copyright status. It does **not** label the material as
approved training data. Sentence alignment and human review are a separate
stage, and the source's permission must be recorded before prepared rows are
accepted by the trainer.

`alignment_candidates.jsonl` is for bilingual human review. The structural
aligner preserves order and supports one-to-many paragraph boundaries, but it
cannot establish semantic equivalence. Its rows intentionally use
`COPYRIGHT-SOURCE-PERMISSION-REQUIRED`, which `prepare_data.py` rejects.

The current reproducible snapshot contains 131 API records with both language
editions, 130 complete downloads, 94 clean OOXML document pairs, and 2,664
ordered alignment candidates. All candidates remain blocked from training
until review and rights approval.

## Set up

Use a separate environment if the web app needs to remain lightweight:

```powershell
python -m venv .venv-model
.\.venv-model\Scripts\Activate.ps1
python -m pip install -r requirements-model.txt
```

For an NVIDIA GPU, install the matching PyTorch build from the official
PyTorch instructions before installing the remaining requirements. CPU
training works in principle but is not practical for the full run.

## Prepare and validate data

```powershell
python model/scripts/prepare_data.py `
  --input model/data/raw/my-permissioned-corpus.jsonl `
  --output-dir model/data/processed
```

Outputs are `train.jsonl`, `validation.jsonl`, `test.jsonl`, and
`report.json`. The script normalises Unicode and whitespace, rejects malformed
or suspicious pairs, removes exact duplicates, detects conflicting
translations, and splits by document rather than by sentence.

The hand-reviewed examples in `data/evaluation/khutbah_eval.jsonl` are an
evaluation seed only. They must never be copied into training data.

## Train

```powershell
python model/scripts/train.py --config model/config.json
```

For a quick pipeline check, override the number of examples and epochs:

```powershell
python model/scripts/train.py --config model/config.json --max-train-samples 32 --epochs 1
```

Checkpoints and downloaded model weights are ignored by Git. The final model,
tokenizer, metrics, and a copy of the training configuration are written to
`model/artifacts/khutbah-ar-en/`.

## Evaluate and translate locally

```powershell
python model/scripts/evaluate.py `
  --model model/artifacts/khutbah-ar-en `
  --data model/data/evaluation/khutbah_eval.jsonl

python model/scripts/translate.py `
  --model model/artifacts/khutbah-ar-en `
  --text "أوصيكم ونفسي بتقوى الله"
```

Evaluation reports SacreBLEU, chrF++, exact glossary-term retention, and
per-example outputs. BLEU alone is not an acceptance criterion: Qur'an and
hadith quotations need reference matching and human review before this model
can replace the temporary API.

## Promotion gate

Do not connect a checkpoint to the web app until it:

1. beats the unfine-tuned base model on the untouched sermon test set;
2. passes quotation and religious-term checks;
3. has been reviewed by a fluent Arabic/English speaker familiar with Khutbah;
4. has a complete dataset provenance report and model card; and
5. meets the latency target on the intended deployment hardware.

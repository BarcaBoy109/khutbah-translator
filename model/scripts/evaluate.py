"""Evaluate a local or Hugging Face Arabic-English model on reviewed JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def batches(items, size):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="Helsinki-NLP/opus-mt-ar-en")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("model/artifacts/evaluation.json"))
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    import sacrebleu
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    rows = [json.loads(line) for line in args.data.read_text(encoding="utf-8").splitlines() if line]
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSeq2SeqLM.from_pretrained(args.model)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()
    predictions = []
    for batch in batches([row["arabic"] for row in rows], args.batch_size):
        encoded = tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=256)
        encoded = {key: value.to(device) for key, value in encoded.items()}
        with torch.inference_mode():
            generated = model.generate(**encoded, max_new_tokens=256, num_beams=4)
        predictions.extend(tokenizer.batch_decode(generated, skip_special_tokens=True))

    references = [row["english"] for row in rows]
    expected = [term for row in rows for term in row.get("expected_terms", [])]
    found = sum(
        term.casefold() in prediction.casefold()
        for row, prediction in zip(rows, predictions)
        for term in row.get("expected_terms", [])
    )
    result = {
        "model": args.model,
        "examples": len(rows),
        "bleu": sacrebleu.corpus_bleu(predictions, [references]).score,
        "chrf_pp": sacrebleu.corpus_chrf(predictions, [references], word_order=2).score,
        "term_accuracy": found / len(expected) if expected else None,
        "outputs": [
            {**row, "prediction": prediction}
            for row, prediction in zip(rows, predictions)
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "outputs"}, indent=2))


if __name__ == "__main__":
    main()


"""Run local Arabic-to-English inference with a trained checkpoint."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--text", required=True)
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSeq2SeqLM.from_pretrained(args.model)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()
    encoded = tokenizer(args.text, return_tensors="pt", truncation=True, max_length=256)
    encoded = {key: value.to(device) for key, value in encoded.items()}
    with torch.inference_mode():
        generated = model.generate(**encoded, max_new_tokens=256, num_beams=4)
    print(tokenizer.decode(generated[0], skip_special_tokens=True))


if __name__ == "__main__":
    main()


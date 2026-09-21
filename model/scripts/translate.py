"""Run local Arabic-to-English inference with a trained checkpoint."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--text", required=True)
    args = parser.parse_args()

    import torch
    from model_loading import load_translation_model

    tokenizer, model = load_translation_model(args.model)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()
    encoded = tokenizer(args.text, return_tensors="pt", truncation=False)
    if encoded["input_ids"].shape[1] > 256:
        parser.error("Input exceeds 256 tokens; split it into shorter passages")
    encoded = {key: value.to(device) for key, value in encoded.items()}
    with torch.inference_mode():
        generated = model.generate(**encoded, max_new_tokens=256, num_beams=4)
    print(tokenizer.decode(generated[0], skip_special_tokens=True))


if __name__ == "__main__":
    main()

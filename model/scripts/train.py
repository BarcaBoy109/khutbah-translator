"""Fine-tune the configured Arabic-English sequence-to-sequence model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("model/config.json"))
    parser.add_argument("--max-train-samples", type=int)
    parser.add_argument("--epochs", type=float)
    args = parser.parse_args()

    import numpy as np
    import sacrebleu
    import torch
    from datasets import load_dataset
    from transformers import (
        AutoModelForSeq2SeqLM,
        AutoTokenizer,
        DataCollatorForSeq2Seq,
        EarlyStoppingCallback,
        Seq2SeqTrainer,
        Seq2SeqTrainingArguments,
        set_seed,
    )

    config = json.loads(args.config.read_text(encoding="utf-8"))
    set_seed(config["seed"])
    files = {
        "train": config["train_file"],
        "validation": config["validation_file"],
        "test": config["test_file"],
    }
    for split, path in files.items():
        if not Path(path).is_file():
            raise FileNotFoundError(f"Missing {split} data: {path}. Run prepare_data.py first.")

    dataset = load_dataset("json", data_files=files)
    if not len(dataset["train"]) or not len(dataset["validation"]):
        raise ValueError("Training and validation splits must both contain records")
    if args.max_train_samples:
        limit = min(args.max_train_samples, len(dataset["train"]))
        dataset["train"] = dataset["train"].select(range(limit))

    tokenizer = AutoTokenizer.from_pretrained(config["base_model"])
    model = AutoModelForSeq2SeqLM.from_pretrained(config["base_model"])

    def tokenize(batch):
        inputs = tokenizer(
            batch["arabic"],
            max_length=config["max_source_length"],
            truncation=True,
        )
        labels = tokenizer(
            text_target=batch["english"],
            max_length=config["max_target_length"],
            truncation=True,
        )
        inputs["labels"] = labels["input_ids"]
        return inputs

    tokenized = dataset.map(
        tokenize,
        batched=True,
        remove_columns=dataset["train"].column_names,
        desc="Tokenizing",
    )
    data_collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model)

    def metrics(eval_prediction):
        predictions, labels = eval_prediction
        if isinstance(predictions, tuple):
            predictions = predictions[0]
        labels = np.where(labels != -100, labels, tokenizer.pad_token_id)
        decoded_predictions = [
            item.strip() for item in tokenizer.batch_decode(predictions, skip_special_tokens=True)
        ]
        decoded_labels = [
            item.strip() for item in tokenizer.batch_decode(labels, skip_special_tokens=True)
        ]
        return {
            "bleu": sacrebleu.corpus_bleu(decoded_predictions, [decoded_labels]).score,
            "chrf": sacrebleu.corpus_chrf(decoded_predictions, [decoded_labels], word_order=2).score,
        }

    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    training_args = Seq2SeqTrainingArguments(
        output_dir=str(output_dir),
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=config["learning_rate"],
        per_device_train_batch_size=config["per_device_train_batch_size"],
        per_device_eval_batch_size=config["per_device_eval_batch_size"],
        gradient_accumulation_steps=config["gradient_accumulation_steps"],
        weight_decay=config["weight_decay"],
        num_train_epochs=args.epochs or config["num_train_epochs"],
        predict_with_generate=True,
        generation_num_beams=config["generation_num_beams"],
        generation_max_length=config["max_target_length"],
        fp16=torch.cuda.is_available(),
        logging_steps=25,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="chrf",
        greater_is_better=True,
        report_to="none",
        seed=config["seed"],
    )
    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["validation"],
        processing_class=tokenizer,
        data_collator=data_collator,
        compute_metrics=metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )
    trainer.train()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    test_metrics = trainer.predict(tokenized["test"], metric_key_prefix="test").metrics
    (output_dir / "test_metrics.json").write_text(
        json.dumps(test_metrics, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "training_config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(test_metrics, indent=2))


if __name__ == "__main__":
    main()


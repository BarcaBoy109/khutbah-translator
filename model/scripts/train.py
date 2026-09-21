"""Fine-tune the configured Arabic-English sequence-to-sequence model."""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("model/config.json"))
    parser.add_argument("--max-train-samples", type=int)
    parser.add_argument("--epochs", type=float)
    parser.add_argument("--resume-from-checkpoint")
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
    if args.epochs is not None:
        if args.epochs <= 0:
            parser.error("epochs must be positive")
        config["num_train_epochs"] = args.epochs
    if args.max_train_samples is not None and args.max_train_samples < 1:
        parser.error("max-train-samples must be positive")
    from training_validation import validate_files
    data_audit = validate_files(config)
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

    tokenizer = AutoTokenizer.from_pretrained(config["base_model"], revision=config.get("base_revision", "main"))
    model = AutoModelForSeq2SeqLM.from_pretrained(config["base_model"], revision=config.get("base_revision", "main"))
    config["resolved_base_revision"] = getattr(model.config, "_commit_hash", None)
    if config.get("lora"):
        from peft import LoraConfig, TaskType, get_peft_model
        model = get_peft_model(model, LoraConfig(task_type=TaskType.SEQ_2_SEQ_LM, revision=config.get("base_revision"), **config["lora"]))
        model.print_trainable_parameters()
    model.config.use_cache = False

    def tokenize(batch):
        inputs = tokenizer(
            batch["arabic"],
            max_length=config["max_source_length"],
            truncation=False,
        )
        labels = tokenizer(
            text_target=batch["english"],
            max_length=config["max_target_length"],
            truncation=False,
        )
        inputs["labels"] = labels["input_ids"]
        if any(len(ids) > config["max_source_length"] for ids in inputs["input_ids"]) or any(len(ids) > config["max_target_length"] for ids in inputs["labels"]):
            raise ValueError("An example exceeds the configured token limit; shorten/filter it explicitly instead of silently truncating translation pairs")
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
    if (output_dir / "adapter_config.json").exists() and not args.resume_from_checkpoint:
        raise FileExistsError(f"Trained adapter already exists at {output_dir}; choose a new output_dir")
    config["max_train_samples"] = args.max_train_samples
    config["actual_train_examples"] = len(dataset["train"])
    (output_dir / "training_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (output_dir / "data_audit.json").write_text(json.dumps(data_audit, indent=2) + "\n", encoding="utf-8")
    training_args = Seq2SeqTrainingArguments(
        output_dir=str(output_dir),
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=config["learning_rate"],
        per_device_train_batch_size=config["per_device_train_batch_size"],
        per_device_eval_batch_size=config["per_device_eval_batch_size"],
        gradient_accumulation_steps=config["gradient_accumulation_steps"],
        weight_decay=config["weight_decay"],
        num_train_epochs=config["num_train_epochs"],
        predict_with_generate=True,
        generation_num_beams=config["generation_num_beams"],
        generation_max_length=config["max_target_length"],
        fp16=torch.cuda.is_available(),
        gradient_checkpointing=config.get("gradient_checkpointing", False),
        gradient_checkpointing_kwargs={"use_reentrant": False},
        dataloader_num_workers=0,
        dataloader_pin_memory=torch.cuda.is_available(),
        eval_accumulation_steps=1,
        logging_steps=5,
        disable_tqdm=True,
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
    train_result = trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)
    model.config.use_cache = True
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    trainer.save_state()
    trainer.save_metrics("train", train_result.metrics)
    environment = {"python": platform.python_version(), "torch": torch.__version__, "cuda": torch.version.cuda,
                   "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"}
    (output_dir / "environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")
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

"""Load full checkpoints or LoRA adapters against their recorded base revision."""
import json
from pathlib import Path


def load_translation_model(identifier, revision="main"):
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    path = Path(identifier)
    if (path / "adapter_config.json").is_file():
        from peft import PeftConfig, PeftModel
        adapter_config = PeftConfig.from_pretrained(identifier)
        training_path = path / "training_config.json"
        training = json.loads(training_path.read_text(encoding="utf-8")) if training_path.exists() else {}
        base_revision = training.get("resolved_base_revision") or training.get("base_revision") or adapter_config.revision
        if not base_revision:
            raise ValueError("Adapter is missing its base revision; record it before loading")
        base = AutoModelForSeq2SeqLM.from_pretrained(adapter_config.base_model_name_or_path, revision=base_revision)
        model = PeftModel.from_pretrained(base, identifier).merge_and_unload()
        tokenizer = AutoTokenizer.from_pretrained(identifier)
    else:
        tokenizer = AutoTokenizer.from_pretrained(identifier, revision=revision)
        model = AutoModelForSeq2SeqLM.from_pretrained(identifier, revision=revision)
    return tokenizer, model

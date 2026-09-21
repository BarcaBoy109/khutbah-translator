"""Run the pinned SAT experiment sequentially and retain comparable metrics."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    os.chdir(ROOT)
    os.environ.setdefault("HF_HOME", str(ROOT / ".huggingface"))
    config = json.loads((ROOT / "model/config.pilot.json").read_text(encoding="utf-8"))
    output = ROOT / config["output_dir"]
    if (output / "adapter_config.json").exists():
        raise FileExistsError("Pilot already trained; preserve it and choose a new experiment output directory")
    reports = ROOT / "model/reports/sat-pilot"
    reports.mkdir(parents=True, exist_ok=True)
    def run(script, *arguments):
        command = [sys.executable, "-u", f"model/scripts/{script}.py", *map(str, arguments)]
        print("Running: " + " ".join(command), flush=True)
        subprocess.run(command, check=True)
    run("build_sat_pilot")
    run("prepare_data", "--input", "model/data/raw/sat/pilot.jsonl", "--output-dir", "model/data/processed/sat-pilot",
        "--config", "model/config.pilot.json", "--validation-ratio", "0.12", "--test-ratio", "0.12")
    data = {"sat": config["test_file"], "seed": "model/data/evaluation/khutbah_eval.jsonl"}
    for name, path in data.items():
        run("evaluate", "--model", config["base_model"], "--revision", config["base_revision"], "--data", path,
            "--batch-size", "2", "--output", reports / f"baseline-{name}.json")
    run("train", "--config", "model/config.pilot.json")
    for name, path in data.items():
        run("evaluate", "--model", config["output_dir"], "--data", path,
            "--batch-size", "2", "--output", reports / f"adapted-{name}.json")
    summary = {"production_approved": False, "reason": "Small pilot; AI-translated references; bilingual and quotation review required", "evaluations": {}}
    for name in data:
        before = json.loads((reports / f"baseline-{name}.json").read_text(encoding="utf-8"))
        after = json.loads((reports / f"adapted-{name}.json").read_text(encoding="utf-8"))
        summary["evaluations"][name] = {"examples": before["examples"], "synthetic_references": before["synthetic_references"],
            "baseline": {key: before[key] for key in ("bleu", "chrf_pp", "term_accuracy")},
            "adapted": {key: after[key] for key in ("bleu", "chrf_pp", "term_accuracy")},
            "chrf_pp_delta": after["chrf_pp"] - before["chrf_pp"]}
    (reports / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for name in ("data_audit.json", "training_config.json", "environment.json", "train_results.json", "test_metrics.json", "trainer_state.json"):
        (reports / name).write_bytes((output / name).read_bytes())
    with (reports / "requirements-lock.txt").open("w", encoding="utf-8") as handle:
        subprocess.run([sys.executable, "-m", "pip", "freeze"], stdout=handle, check=True)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()

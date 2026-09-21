"""Checks for the data failures that would invalidate a training experiment."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("training_validation", Path(__file__).resolve().parents[1] / "model/scripts/training_validation.py")
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)


class TrainingValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = {"approved_licenses": ["CC-BY-4.0"]}
        texts = ["حافظوا على الأمانة", "أحسنوا إلى الجيران", "الصدق طريق الخير"]
        for split, text in zip(("train", "validation", "test"), texts):
            path = Path(self.directory.name) / f"{split}.jsonl"
            path.write_text(json.dumps({"arabic": text, "english": "A translation", "document_id": split,
                                        "source": "test-fixture", "license": "CC-BY-4.0"}), encoding="utf-8")
            self.config[f"{split}_file"] = str(path)

    def change(self, split, **changes):
        path = Path(self.config[f"{split}_file"])
        row = json.loads(path.read_text(encoding="utf-8"))
        row.update(changes)
        path.write_text(json.dumps(row), encoding="utf-8")

    def test_valid_data_is_hashed(self):
        self.assertEqual(validation.validate_files(self.config)["train"]["examples"], 1)

    def test_cannot_bypass_rights_gate_with_prepared_files(self):
        self.change("train", license="COPYRIGHT-SOURCE-PERMISSION-REQUIRED")
        with self.assertRaisesRegex(ValueError, "unapproved license"):
            validation.validate_files(self.config)

    def test_same_sermon_cannot_leak(self):
        self.change("test", document_id="train")
        with self.assertRaisesRegex(ValueError, "Cross-split"):
            validation.validate_files(self.config)

    def test_diacritics_do_not_hide_leakage(self):
        self.change("test", arabic="حَافِظُوا على الأمانة")
        with self.assertRaisesRegex(ValueError, "Cross-split"):
            validation.validate_files(self.config)

    def test_seed_cannot_enter_training_inside_longer_text(self):
        self.change("train", arabic="عباد الله أوصيكم ونفسي بتقوى الله في السر والعلن")
        with self.assertRaisesRegex(ValueError, "protected evaluation"):
            validation.validate_files(self.config)

    def test_synthetic_targets_require_explicit_opt_in(self):
        self.change("train", synthetic_target=True)
        with self.assertRaisesRegex(ValueError, "Synthetic"):
            validation.validate_files(self.config)
        self.config["allow_synthetic_targets"] = True
        self.assertEqual(validation.validate_files(self.config)["train"]["synthetic_targets"], 1)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = ROOT / "model" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


aligner = load_script("align_documents")
preparer = load_script("prepare_data")


class ModelPipelineTests(unittest.TestCase):
    def test_document_split_is_deterministic_and_document_scoped(self):
        first = preparer.stable_split("sermon-42", 42, 0.05, 0.05)
        second = preparer.stable_split("sermon-42", 42, 0.05, 0.05)
        self.assertEqual(first, second)
        self.assertIn(first, {"train", "validation", "test"})

    def test_arabic_segmentation_splits_long_clauses(self):
        text = "هذه جملة طويلة، " * 60
        segments = aligner.arabic_segments([text], maximum=100)
        self.assertGreater(len(segments), 1)
        self.assertTrue(all(len(item) <= 110 for item in segments))

    def test_alignment_is_monotonic_and_complete(self):
        source = ["الحمد لله.", "اتقوا الله."]
        target = ["Praise belongs to Allah.", "Be mindful of Allah."]
        aligned = aligner.align(source, target)
        self.assertEqual(aligned[0]["source_start"], 0)
        self.assertEqual(aligned[-1]["source_end"], len(source))
        self.assertEqual(aligned[-1]["target_end"], len(target))
        self.assertTrue(all(0 <= row["alignment_confidence"] <= 1 for row in aligned))

    def test_script_share_rejects_wrong_language(self):
        self.assertGreater(preparer.char_share(preparer.ARABIC, "اتقوا الله"), 0.9)
        self.assertLess(preparer.char_share(preparer.ARABIC, "Be mindful"), 0.1)

    def test_sermon_body_removes_document_furniture(self):
        arabic = ["دولة الإمارات", "عنوان", "الْحَمْدُ لِلَّهِ رب العالمين"]
        english = ["Date: Friday", "Title", "The First Khutbah", "Praise be to Allah."]
        self.assertEqual(aligner.sermon_body(arabic, "ar"), [arabic[-1]])
        self.assertEqual(aligner.sermon_body(english, "en"), [english[-1]])

    def test_alignment_cues_reward_matching_sermon_phrases(self):
        matching = aligner.cue_cost("أما بعد عباد الله", "To proceed, O servants of Allah")
        mismatch = aligner.cue_cost("أما بعد عباد الله", "A separate sentence")
        self.assertLess(matching, mismatch)


if __name__ == "__main__":
    unittest.main()

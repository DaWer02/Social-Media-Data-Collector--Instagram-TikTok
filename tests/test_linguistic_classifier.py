"""Unit tests for LinguisticClassifier module."""

from __future__ import annotations

import unittest
from src.extractors.linguistic_classifier import (
    categorize_language_functions,
    categorize_slang_forms,
    classify_comment,
)


class TestLinguisticClassifier(unittest.TestCase):
    """Test suite for rule-based multi-label linguistic classification."""

    def test_classify_akronim(self) -> None:
        """Verify acronyms (mager, baper, bucin, kepo, etc.) are detected."""
        text = "Lagi mager parah nih, baperan banget orangnya."
        res = classify_comment(text)

        self.assertIn("akronim", res.slang_forms)
        self.assertIn("mager", res.detected_slang_words)
        self.assertTrue(res.slang_present)

    def test_classify_singkatan(self) -> None:
        """Verify chat/SMS abbreviations (bgt, otw, gws, ygy, pmx, etc.) are detected."""
        text = "Otw sekarang ya, gws buat bro di sana bgt!"
        res = classify_comment(text)

        self.assertIn("singkatan", res.slang_forms)
        self.assertIn("otw", res.detected_slang_words)
        self.assertIn("gws", res.detected_slang_words)
        self.assertIn("bgt", res.detected_slang_words)

    def test_classify_bahasa_asing(self) -> None:
        """Verify foreign/English slang loanwords (healing, congrats, bestie, etc.) are detected."""
        text = "Congrats bestie! Akhirnya bisa healing juga."
        res = classify_comment(text)

        self.assertIn("bahasa_asing", res.slang_forms)
        self.assertIn("congrats", res.detected_slang_words)
        self.assertIn("bestie", res.detected_slang_words)
        self.assertIn("healing", res.detected_slang_words)

    def test_classify_plesetan_and_elongation(self) -> None:
        """Verify phonetic distortions, rhyme slang, and vowel elongation are detected as plesetan."""
        text = "Santuy aja ngab, gokil bangeeet wkwkwk!"
        res = classify_comment(text)

        self.assertIn("plesetan", res.slang_forms)
        self.assertIn("santuy", res.detected_slang_words)
        self.assertIn("gokil", res.detected_slang_words)
        self.assertIn("bangeeet", res.detected_slang_words)

    def test_classify_pemendekan(self) -> None:
        """Verify truncated/clipped colloquial words (ga, gak, lu, gw, udah, dll.) are detected."""
        text = "Kalo lu emang ga tau, ya udah diem aja."
        res = classify_comment(text)

        self.assertIn("pemendekan", res.slang_forms)
        self.assertIn("kalo", res.detected_slang_words)
        self.assertIn("lu", res.detected_slang_words)
        self.assertIn("ga", res.detected_slang_words)

    def test_no_slang_present(self) -> None:
        """Verify standard formal sentences are tagged as 'tidak_ada'."""
        text = "Pemerintah sedang melaksanakan rapat koordinasi nasional."
        res = classify_comment(text)

        self.assertEqual(res.slang_forms, ["tidak_ada"])
        self.assertFalse(res.slang_present)
        self.assertEqual(res.slang_forms_str, "tidak_ada")

    def test_classify_function_emotif(self) -> None:
        """Verify emotive function triggered by affective words, emojis, or exclamation chains."""
        text1 = "Alhamdulillah bersyukur dan bahagia sekali atas nikmat ini ❤️😍!!"
        res1 = classify_comment(text1)
        self.assertIn("emotif", res1.language_functions)

        text2 = "Menyalaaaaa abangku mantap! 🔥"
        res2 = classify_comment(text2)
        self.assertIn("emotif", res2.language_functions)

    def test_classify_function_referensial(self) -> None:
        """Verify referential function triggered by economic terms, numbers, policies, or causal links."""
        text = "Gaji minimum dinaikkan menjadi RM2,000 dalam belanjawan 2027 karena inflasi pekerja."
        res = classify_comment(text)
        self.assertIn("referensial", res.language_functions)

    def test_classify_function_konatif(self) -> None:
        """Verify conative function triggered by directives, calls to action, questions, or mentions."""
        text = "Tolong pertimbangkan juga nasib kami @prabowo @dpr_ri! Kapan ada kebijakan serupa?"
        res = classify_comment(text)
        self.assertIn("konatif", res.language_functions)

    def test_multilabel_combination(self) -> None:
        """Verify a real-world complex comment correctly identifies multiple forms and functions."""
        text = "Alhamdulillah PMX terbaik! Gaji naik jadi RM2,000, tolong kawal harga brg juga ya @anwaribrahim_my ❤️"
        res = classify_comment(text)

        # Forms: singkatan (pmx, brg), plesetan (terbaik/elongation), etc.
        self.assertIn("singkatan", res.slang_forms)
        # Functions: emotif (Alhamdulillah, ❤️), referensial (gaji naik RM2000), konatif (tolong kawal, @anwaribrahim_my)
        self.assertIn("emotif", res.language_functions)
        self.assertIn("referensial", res.language_functions)
        self.assertIn("konatif", res.language_functions)

    def test_empty_input(self) -> None:
        """Verify empty or whitespace strings return safe default tags."""
        res = classify_comment("   \n\t  ")
        self.assertEqual(res.slang_forms, ["tidak_ada"])
        self.assertEqual(res.language_functions, ["tidak_jelas"])
        self.assertFalse(res.slang_present)


if __name__ == "__main__":
    unittest.main()


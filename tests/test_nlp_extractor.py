"""Unit tests for NLPCommentExtractor."""

from __future__ import annotations

import unittest
from src.extractors.nlp_comment_extractor import NLPCommentExtractor


class TestNLPCommentExtractor(unittest.TestCase):
    """Test suite for NLP-driven comment extraction and in-flight quality filtering."""

    def setUp(self) -> None:
        self.extractor = NLPCommentExtractor()

    def test_extract_from_dom_block_complete(self) -> None:
        """Verify standard DOM block with author, badges, UI buttons, and timestamps."""
        block = """
        budi_santoso
        Verified
        Wkwkwk sumpah gokil bgt min, ga nyangka kejadian beneran! 🔥
        2 j
        14 suka
        Balas
        Terjemahkan
        """
        extracted = self.extractor.extract_from_dom_text_block(block)

        self.assertTrue(extracted.is_valid)
        self.assertFalse(extracted.is_spam)
        self.assertEqual(extracted.author, "budi_santoso")
        self.assertEqual(
            extracted.comment_text,
            "Wkwkwk sumpah gokil bgt min, ga nyangka kejadian beneran! 🔥",
        )
        self.assertEqual(extracted.like_count, 14)
        self.assertEqual(extracted.timestamp_raw, "2 j")
        self.assertTrue(extracted.has_slang_candidate)
        self.assertIn("wkwkwk", extracted.detected_slang_tokens)
        self.assertIn("gokil", extracted.detected_slang_tokens)
        self.assertIn("bgt", extracted.detected_slang_tokens)

    def test_filter_reply_threads_and_actions(self) -> None:
        """Verify thread navigation tags are stripped."""
        block = """
        @siti_nurhaliza
        Keren bgt kak, sukses teruss yaaa!
        3 mgg
        Lihat 5 balasan lainnya
        Balas
        """
        extracted = self.extractor.extract_from_dom_text_block(block)

        self.assertTrue(extracted.is_valid)
        self.assertEqual(extracted.author, "siti_nurhaliza")
        self.assertEqual(extracted.comment_text, "Keren bgt kak, sukses teruss yaaa!")
        self.assertNotIn("balas", extracted.comment_text.lower())
        self.assertNotIn("lihat 5 balasan", extracted.comment_text.lower())
        self.assertTrue(extracted.has_slang_candidate)
        self.assertIn("yaaa", extracted.detected_slang_tokens)

    def test_reject_pure_emoji(self) -> None:
        """Verify comments with no alphanumeric characters are rejected."""
        block = """
        user_anon
        🔥🔥🔥 😂😂😂
        1 j
        Balas
        """
        extracted = self.extractor.extract_from_dom_text_block(block)

        self.assertFalse(extracted.is_valid)
        self.assertEqual(extracted.rejection_reason, "no_alphanumeric_content")

    def test_reject_commercial_spam(self) -> None:
        """Verify bot spam, betting promos, and affiliate links are flagged and rejected."""
        spam_samples = [
            "Mau peninggi badan terbaik? Cek link di bio kami kak!",
            "Slot gacor maxwin hari ini zeus pragmatic slot!",
            "Hubungi wa 081234567890 untuk info bisnis tanpa modal!",
            "Open BO ready salon hotel bintang 5",
        ]
        for spam in spam_samples:
            eval_res = self.extractor.evaluate_comment(raw_text=spam, comment_text=spam)
            self.assertTrue(eval_res.is_spam, f"Should detect spam for: {spam}")
            self.assertFalse(eval_res.is_valid)
            self.assertEqual(eval_res.rejection_reason, "commercial_or_bot_spam")

    def test_slang_lexicon_and_elongation(self) -> None:
        """Verify recognition of various Indonesian slang words and elongations."""
        text = "Sumpah bangeeet anjir, santuy aja kali ngab otw nih"
        tokens = self.extractor.detect_slang_tokens(text)

        self.assertIn("bangeeet", tokens)
        self.assertIn("anjir", tokens)
        self.assertIn("santuy", tokens)
        self.assertIn("ngab", tokens)
        self.assertIn("otw", tokens)

    def test_empty_or_whitespace_block(self) -> None:
        """Empty input must safely return is_valid=False without crashing."""
        extracted = self.extractor.extract_from_dom_text_block("   \n\t  ")
        self.assertFalse(extracted.is_valid)
        self.assertEqual(extracted.rejection_reason, "empty_input")

    def test_strip_leading_timestamps_and_edited_badges(self) -> None:
        """Verify leading relative timestamps like '2 ming', '2 ming · Diedit' are cleanly removed."""
        res1 = self.extractor.evaluate_comment(
            raw_text="dummy",
            comment_text="2 ming Kekalkan Madani lagi 2 penggal 😍",
            author="andi",
        )
        self.assertTrue(res1.is_valid)
        self.assertEqual(res1.comment_text, "Kekalkan Madani lagi 2 penggal 😍")

        res2 = self.extractor.evaluate_comment(
            raw_text="dummy",
            comment_text="2 ming · Diedit Congrats Malaysia. Semoga sukses!",
            author="budi",
        )
        self.assertTrue(res2.is_valid)
        self.assertEqual(res2.comment_text, "Congrats Malaysia. Semoga sukses!")

        # Standalone timestamp only must be rejected as empty/too short
        res3 = self.extractor.evaluate_comment(
            raw_text="dummy",
            comment_text="2 ming",
            author="citra",
        )
        self.assertFalse(res3.is_valid)
        self.assertEqual(res3.rejection_reason, "too_short")

    def test_filter_expanded_view_more_replies_labels(self) -> None:
        """Verify 'View more replies', 'View all X replies', and Indonesian variants are stripped."""
        block = (
            "budi_santoso\n"
            "3h\n"
            "Setuju banget sama pendapat ini!\n"
            "2 likes\n"
            "Reply\n"
            "―― View more replies\n"
            "― View 5 more replies\n"
            "View all 12 replies\n"
            "Lihat semua balasan\n"
            "Lihat balasan lainnya\n"
            "Hide replies"
        )
        extracted = self.extractor.extract_from_dom_text_block(block)
        self.assertTrue(extracted.is_valid)
        self.assertEqual(extracted.author, "budi_santoso")
        self.assertEqual(extracted.comment_text, "Setuju banget sama pendapat ini!")


if __name__ == "__main__":
    unittest.main()

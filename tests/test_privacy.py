"""Unit tests for privacy protection and PII masking."""

import unittest
from src.privacy import (
    mask_emails,
    mask_mentions,
    mask_phone_numbers,
    mask_urls,
    sanitize_comment_dict,
    sanitize_comment_text,
)


class TestPrivacyModule(unittest.TestCase):
    """Test suite for privacy compliance and PII sanitization."""

    def test_mask_mentions(self) -> None:
        raw = "Halo @andi dan @budi_123, apa kabar @siti.nur?"
        expected = "Halo [@USER] dan [@USER], apa kabar [@USER]?"
        self.assertEqual(mask_mentions(raw), expected)

    def test_mask_emails(self) -> None:
        raw = "Hubungi saya di user@example.com untuk info"
        expected = "Hubungi saya di [EMAIL] untuk info"
        self.assertEqual(mask_emails(raw), expected)

    def test_mask_phones(self) -> None:
        raw = "Kontak wa 08123456789 atau +628198765432"
        res = mask_phone_numbers(raw)
        self.assertNotIn("08123456789", res)
        self.assertIn("[TELEPON]", res)

    def test_mask_urls(self) -> None:
        raw = "Lihat info di https://news.example.com/article/123 ya"
        expected = "Lihat info di [LINK] ya"
        self.assertEqual(mask_urls(raw), expected)

    def test_sanitize_comment_text(self) -> None:
        raw = "Keren banget @ahmad! Kirim ke test@mail.com dong"
        clean = sanitize_comment_text(raw)
        self.assertNotIn("@ahmad", clean)
        self.assertNotIn("test@mail.com", clean)
        self.assertIn("[@USER]", clean)
        self.assertIn("[EMAIL]", clean)

    def test_sanitize_comment_dict_removes_username(self) -> None:
        record = {
            "comment_id": "c123",
            "username": "user_rahasia",
            "author": "nama_asli",
            "comment_text": "Pendapat dari @pejabat_a",
        }
        sanitized = sanitize_comment_dict(record, anonymize_comment_id=True, anonymous_index=1)
        self.assertNotIn("username", sanitized)
        self.assertNotIn("author", sanitized)
        self.assertEqual(sanitized["comment_id"], "KOM_00001")
        self.assertEqual(sanitized["comment_text"], "Pendapat dari [@USER]")


if __name__ == "__main__":
    unittest.main()

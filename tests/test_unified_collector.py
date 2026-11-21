"""Unit tests for unified Instagram and TikTok collector routing and URL validation."""

import unittest
from src.collectors.base import CollectorValidationError
from src.collectors.unified import detect_platform, extract_clean_url


class TestUnifiedCollector(unittest.TestCase):
    """Test suite for URL parsing and platform detection."""

    def test_extract_clean_url(self) -> None:
        raw_share = "Tonton ini keren banget https://www.instagram.com/p/Cxyz123/?utm_source=ig_web yuk!"
        clean = extract_clean_url(raw_share)
        self.assertEqual(clean, "https://www.instagram.com/p/Cxyz123/?utm_source=ig_web")

    def test_detect_platform_instagram(self) -> None:
        urls = [
            "https://www.instagram.com/p/DF123abc/",
            "https://instagram.com/reel/C789xyz",
            "https://www.instagram.com/tv/B456def/",
            "p/DF123abc/",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(detect_platform(url), "instagram")

    def test_detect_platform_tiktok(self) -> None:
        urls = [
            "https://www.tiktok.com/@creator.official/video/7123456789012345678",
            "https://vt.tiktok.com/ZSxyz123/",
            "https://vm.tiktok.com/ZMabc987/",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(detect_platform(url), "tiktok")

    def test_detect_platform_unsupported(self) -> None:
        unsupported = [
            "https://twitter.com/user/status/123",
            "https://facebook.com/watch?v=123",
            "https://youtube.com/watch?v=123",
            "random string",
        ]
        for url in unsupported:
            with self.subTest(url=url):
                with self.assertRaises(CollectorValidationError):
                    detect_platform(url)


if __name__ == "__main__":
    unittest.main()

"""NLP-driven Information Extraction and in-flight quality filtering for comments.

Extracts genuine comment text from messy, semi-structured web DOM text blocks,
eliminates Instagram UI noise (buttons, timestamps, interactions), detects
spam/advertising, and identifies Indonesian slang candidates in real-time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Regular expression patterns for Instagram UI noise
RE_TIMESTAMP = re.compile(
    r"^(?:\d+\s*(?:detik|dtk|m|mnt|menit|j|jam|h|d|hr|hari|mgg|mg|ming|minggu|w|bln|bulan|thn|tahun|s)\b[\s·]*(?:diedit|edited)?|\d+[smhdw]|just now|baru saja)$",
    re.IGNORECASE,
)

RE_UI_ACTION = re.compile(
    r"^(?:balas|reply|suka|like|terjemahkan|see translation|lihat terjemahan|"
    r"laporkan|report|bagikan|share|kirim|send|batal|cancel)$",
    re.IGNORECASE,
)

RE_LIKE_COUNT = re.compile(
    r"^(\d+[\d.,]*)\s*(?:suka|likes?)$",
    re.IGNORECASE,
)

RE_REPLY_THREAD = re.compile(
    r"^[―—\-\s]*(?:"
    r"(?:lihat|view|sembunyikan|hide)\s+(?:semua\s+|all\s+|more\s+|previous\s+|hidden\s+|\d+\s+)*(?:more\s+)?(?:balasan|tanggapan|repl(?:y|ies))(?:\s+(?:lainnya|lagi|sebelumnya))?(?:\s*\(\d+\))?"
    r"|(?:lihat|view)\s+\d+\s+lagi"
    r"|[―—\-]{2,}"
    r")$",
    re.IGNORECASE,
)

RE_METADATA_BADGE = re.compile(
    r"^(?:·\s*)?(?:disematkan|pinned|diverifikasi|verified|penulis|author|creator|kreator|diedit|edited)$",
    re.IGNORECASE,
)

RE_USERNAME = re.compile(r"^@?([a-zA-Z0-9_.]+)$")

# Patterns to strip leading/trailing relative timestamps and edit markers
RE_LEADING_TIMESTAMP_NOISE = re.compile(
    r"^(?:\d+\s*(?:detik|dtk|m|mnt|menit|j|jam|h|d|hr|hari|mgg|mg|ming|minggu|w|bln|bulan|thn|tahun|s)\b[\s·]*(?:diedit|edited)?\s*)+",
    re.IGNORECASE,
)
RE_LEADING_EDITED = re.compile(r"^(?:·\s*)?(?:diedit|edited)\s*", re.IGNORECASE)
RE_TRAILING_TIMESTAMP_NOISE = re.compile(
    r"(?:\s*·?\s*\d+\s*(?:detik|dtk|m|mnt|menit|j|jam|h|d|hr|hari|mgg|mg|ming|minggu|w|bln|bulan|thn|tahun|s)\b[\s·]*(?:diedit|edited)?)+$",
    re.IGNORECASE,
)

# Commercial spam / bot advertisement patterns
SPAM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:cek|check|klik|click)\s+(?:link\s+di\s+)?bio\b", re.IGNORECASE),
    re.compile(r"(?:peninggi|pelangsing|pemutih|penggemuk)\s+badan", re.IGNORECASE),
    re.compile(r"(?:slot|gacor|judi|zeus|maxwin|pragmatic)\b", re.IGNORECASE),
    re.compile(r"(?:open\s+bo|vcs\s+ready|ready\s+bo)\b", re.IGNORECASE),
    re.compile(r"(?:wa|whatsapp)\s*(?::|ke|\.me)?\s*(?:\+?62|08)\d{7,13}", re.IGNORECASE),
    re.compile(r"(?:jual|tambah)\s+followers?\b", re.IGNORECASE),
    re.compile(r"(?:dm\s+for|hubungi\s+admin)\s+(?:promo|bisnis|endorse)", re.IGNORECASE),
    re.compile(r"(?:penghasilan|cuan)\s+(?:tambahan|jutaan|harian)\s+(?:dari\s+hp|tanpa\s+modal)", re.IGNORECASE),
)

# Indonesian Slang Lexicon & Colloquial Markers
INDONESIAN_SLANG_LEXICON: frozenset[str] = frozenset({
    "wkwk", "wkwkwk", "wkwkwkwk", "wk", "haha", "xixi", "awokawok", "gokil",
    "kuy", "santuy", "santai", "bgt", "banget", "bgtu", "begitu", "ga", "gak",
    "gk", "ngga", "nggak", "kagak", "tdk", "lu", "loe", "elo", "gue", "gw",
    "gua", "lo", "lohor", "anjir", "anjay", "anjim", "bgst", "mantap", "mantep",
    "mager", "kepo", "gabut", "bucin", "pansos", "spill", "salfok", "tubir",
    "julid", "parah", "pargoy", "bjir", "cuaks", "coeg", "gas", "gaskeun",
    "gaspol", "ygy", "bjirr", "gpp", "otw", "ngab", "ngabers", "bro", "brok",
    "pren", "ges", "gais", "guys", "gess", "bejir", "jir", "buset", "ancur",
    "ngakak", "asli", "bet", "dapet", "knp", "kenape", "dmn", "dimane", "gmn",
    "gmna", "gimana", "beneran", "yoi", "cuy", "lebay", "baper", "mletre",
    "bodo", "amat", "bray", "sabi", "takis", "gils", "cuan", "modus", "curhat",
    "kzl", "baperan", "julit", "gercep", "gercep", "mupeng", "nobar", "japri",
    "bocil", "jamet", "alay", "kocak", "pewe", "hoki", "zonk", "kicep",
    "baper", "rempong", "lelet", "ilfil", "kepo", "pansos", "bokek", "cepu",
    "baperan", "halu", "baper", "sotoy", "songong", "curcol", "gaje", "garing",
    "receh", "baper", "mbois", "ambyar", "ambyar", "ciduk", "nyimak", "kepo",
    "salim", "kicep", "mletre", "sambat", "pemburu", "gercep", "skuy", "sabi",
})

# Repeated letters pattern for elongation (e.g. 'bangeeet', 'kuyyy', 'iyaaa')
RE_ELONGATION = re.compile(r"([a-zA-Z])\1{2,}")


@dataclass(frozen=True)
class ExtractedComment:
    """Standardized result of NLP information extraction from a raw text block."""

    raw_text: str
    author: str
    comment_text: str
    clean_text: str
    timestamp_raw: str
    like_count: int
    is_valid: bool
    is_spam: bool
    rejection_reason: str | None
    has_slang_candidate: bool
    detected_slang_tokens: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            "author": self.author,
            "comment_text": self.comment_text,
            "clean_text": self.clean_text,
            "timestamp_raw": self.timestamp_raw,
            "like_count": self.like_count,
            "is_valid": self.is_valid,
            "is_spam": self.is_spam,
            "rejection_reason": self.rejection_reason,
            "has_slang_candidate": self.has_slang_candidate,
            "detected_slang_tokens": self.detected_slang_tokens,
        }


class NLPCommentExtractor:
    """NLP-driven extractor and validator for Instagram comment text."""

    def __init__(
        self,
        min_text_length: int = 2,
        require_alphanumeric: bool = True,
    ) -> None:
        self.min_text_length = min_text_length
        self.require_alphanumeric = require_alphanumeric

    def is_spam(self, text: str) -> bool:
        """Check if comment contains common promotional or bot spam patterns."""
        if not text:
            return False
        for pattern in SPAM_PATTERNS:
            if pattern.search(text):
                return True
        return False

    def detect_slang_tokens(self, text: str) -> list[str]:
        """Detect Indonesian slang words, abbreviations, and character elongations."""
        if not text:
            return []

        tokens = re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())
        detected: list[str] = []

        for token in tokens:
            # 1. Direct lexicon lookup
            if token in INDONESIAN_SLANG_LEXICON:
                if token not in detected:
                    detected.append(token)
            # 2. Check for elongated slang/informal words (e.g. bangeeet, iyaaa)
            elif RE_ELONGATION.search(token):
                if token not in detected:
                    detected.append(token)

        return detected

    def extract_from_dom_text_block(self, raw_block: str) -> ExtractedComment:
        """Parse an unstructured multi-line text block from rendered DOM into a clean comment.

        Example DOM text block:
        -------------------------
        budi_santoso
        Verified
        Wkwkwk sumpah gokil bgt min, ga nyangka kejadian beneran! 🔥
        2 j
        14 suka
        Balas
        Terjemahkan
        -------------------------
        Returns:
            ExtractedComment object with parsed author, pure comment text, and validation status.
        """
        if not raw_block or not raw_block.strip():
            return ExtractedComment(
                raw_text="",
                author="",
                comment_text="",
                clean_text="",
                timestamp_raw="",
                like_count=0,
                is_valid=False,
                is_spam=False,
                rejection_reason="empty_input",
                has_slang_candidate=False,
                detected_slang_tokens=[],
            )

        lines = [line.strip() for line in raw_block.splitlines() if line.strip()]
        author = ""
        timestamp_raw = ""
        like_count = 0
        content_lines: list[str] = []

        for idx, line in enumerate(lines):
            # Check 1: Author handle (usually first non-badge line)
            if idx == 0 and not author:
                if RE_METADATA_BADGE.match(line):
                    continue
                author = line.lstrip("@")
                continue

            # Check 2: Badges
            if RE_METADATA_BADGE.match(line):
                continue

            # Check 3: UI actions (Balas, Suka, Terjemahkan)
            if RE_UI_ACTION.match(line):
                continue

            # Check 4: Reply thread markers (Lihat 3 balasan lainnya)
            if RE_REPLY_THREAD.match(line):
                continue

            # Check 5: Timestamp ('2 j', '3 mgg', '1d', etc.)
            if RE_TIMESTAMP.match(line):
                if not timestamp_raw:
                    timestamp_raw = line
                continue

            # Check 6: Like counts ('14 suka', '5 likes')
            like_match = RE_LIKE_COUNT.match(line)
            if like_match:
                try:
                    count_str = like_match.group(1).replace(".", "").replace(",", "")
                    like_count = int(count_str)
                except ValueError:
                    like_count = 0
                continue

            # Check 7: Fallback for second line being author if first was a badge
            if not author and idx == 1 and not RE_UI_ACTION.match(line):
                author = line.lstrip("@")
                continue

            # Remaining line is considered part of the genuine comment body
            content_lines.append(line)

        raw_comment_text = " ".join(content_lines).strip()
        return self.evaluate_comment(
            raw_text=raw_block,
            comment_text=raw_comment_text,
            author=author,
            timestamp_raw=timestamp_raw,
            like_count=like_count,
        )

    def evaluate_comment(
        self,
        raw_text: str,
        comment_text: str,
        author: str = "",
        timestamp_raw: str = "",
        like_count: int = 0,
    ) -> ExtractedComment:
        """Validate, sanitize, and score an extracted comment text."""
        # Clean consecutive spaces and normalize
        clean_text = re.sub(r"\s+", " ", comment_text).strip()

        # Strip any leading and trailing relative timestamps (e.g. '2 ming ', '2 ming · Diedit ')
        clean_text = RE_LEADING_TIMESTAMP_NOISE.sub("", clean_text).strip()
        clean_text = RE_LEADING_EDITED.sub("", clean_text).strip()
        clean_text = RE_TRAILING_TIMESTAMP_NOISE.sub("", clean_text).strip()

        # Mask account mentions with [@USER] for privacy
        clean_text = re.sub(r"@[A-Za-z0-9_.]+", "[@USER]", clean_text).strip()

        # Rule 1: Minimum text length
        if len(clean_text) < self.min_text_length:
            return ExtractedComment(
                raw_text=raw_text,
                author=author,
                comment_text=clean_text,
                clean_text=clean_text,
                timestamp_raw=timestamp_raw,
                like_count=like_count,
                is_valid=False,
                is_spam=False,
                rejection_reason="too_short",
                has_slang_candidate=False,
                detected_slang_tokens=[],
            )

        # Rule 2: Require alphanumeric characters (avoid pure emoji/punctuation strings)
        if self.require_alphanumeric and not re.search(r"[a-zA-Z0-9]", clean_text):
            return ExtractedComment(
                raw_text=raw_text,
                author=author,
                comment_text=clean_text,
                clean_text=clean_text,
                timestamp_raw=timestamp_raw,
                like_count=like_count,
                is_valid=False,
                is_spam=False,
                rejection_reason="no_alphanumeric_content",
                has_slang_candidate=False,
                detected_slang_tokens=[],
            )

        # Rule 3: Spam check
        if self.is_spam(clean_text):
            return ExtractedComment(
                raw_text=raw_text,
                author=author,
                comment_text=clean_text,
                clean_text=clean_text,
                timestamp_raw=timestamp_raw,
                like_count=like_count,
                is_valid=False,
                is_spam=True,
                rejection_reason="commercial_or_bot_spam",
                has_slang_candidate=False,
                detected_slang_tokens=[],
            )

        # Rule 4: Slang detection
        slang_tokens = self.detect_slang_tokens(clean_text)
        has_slang = len(slang_tokens) > 0

        return ExtractedComment(
            raw_text=raw_text,
            author=author,
            comment_text=clean_text,
            clean_text=clean_text,
            timestamp_raw=timestamp_raw,
            like_count=like_count,
            is_valid=True,
            is_spam=False,
            rejection_reason=None,
            has_slang_candidate=has_slang,
            detected_slang_tokens=slang_tokens,
        )

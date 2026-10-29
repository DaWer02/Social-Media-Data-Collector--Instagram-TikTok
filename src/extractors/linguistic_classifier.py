"""Linguistic Classifier for Indonesian & Regional Social Media Comments.

Applies rule-based linguistic taxonomy categorization to classify:
1. Slang Forms (Bentuk Bahasa Gaul):
   - akronim
   - singkatan
   - bahasa_asing
   - plesetan
   - pemendekan
   - tidak_ada
2. Language Functions (Fungsi Bahasa, based on Roman Jakobson's model):
   - emotif
   - referensial
   - konatif
   - tidak_jelas
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ==============================================================================
# 1. TAXONOMY CONSTANTS & LEXICONS: BENTUK BAHASA GAUL
# ==============================================================================

# Akronim: gabungan suku kata atau huruf yang dilafalkan sebagai kata wajar
AKRONIM_LEXICON: frozenset[str] = frozenset({
    "mager", "baper", "kepo", "bucin", "pansos", "nobar", "japri", "bocil",
    "curcol", "gercep", "salfok", "pewe", "gaje", "curhat", "maksi", "mupeng",
    "komdis", "puskesmas", "madani", "menpora", "pilpres", "warkop", "tilang",
    "damri", "satpam", "posyandu", "daring", "luring", "kudet", "reformasigaji",
    "baperan", "jomblo", "caper", "perpu", "sinetron", "kemenkeu", "kemendikbud",
    "balita", "batita", "rudal", "asbun", "jaim", "kamseupay", "pemilu",
})

# Singkatan: penyingkatan huruf konsonan chat/SMS atau singkatan resmi yang dibaca huruf per huruf
SINGKATAN_LEXICON: frozenset[str] = frozenset({
    "bgt", "gws", "otw", "ygy", "gpp", "knp", "dmn", "gmn", "gmna", "tq",
    "pmx", "kkm", "yg", "dgn", "sbb", "tp", "sdh", "blm", "dlm", "tdk",
    "dr", "krn", "kpd", "sy", "utk", "brg", "pon", "klu", "skrg", "jg",
    "tpt", "nme", "sape", "bole", "takot", "xde", "enn", "gk", "bgst", "tks",
    "thx", "pls", "btw", "fyi", "cmiiw", "asap", "hbd", "gbu", "cod", "pov",
    "dm", "vt", "fyp", "rek", "dpr", "kpk", "bumn", "glic", "glc", "pmks",
    "spm", "sd", "smp", "sma", "wni", "wna", "pns", "asn", "pppk", "tni",
    "polri", "idr", "rm", "usd", "bbm", "apbn", "apbd", "umr", "ump", "umk",
    "bpjs", "ktp", "sim", "kk", "rt", "rw", "pt", "cv", "tbk", "stnk",
    "bpkb", "ikn", "ri", "my", "id", "kpd", "tsb", "ybs", "dsb", "dll",
    "dst", "ttd", "an", "dkk", "sdr", "sdri", "thn", "bln", "mgg", "hr",
    "mnt", "dtk", "skalipun", "skurg2nyer", "kte", "nasi",
})

# Bahasa Asing: kata gaul serapan bahasa Inggris/asing yang lazim di sosmed
BAHASA_ASING_LEXICON: frozenset[str] = frozenset({
    "healing", "congrats", "congratulations", "happy", "guys", "gais", "ges", "gess",
    "bro", "brother", "sis", "sister", "slay", "cringe", "spill", "bestie", "mood",
    "moody", "worth", "excited", "proud", "respect", "win", "little", "left", "one",
    "fresh", "grad", "level", "link", "bio", "follow", "share", "please", "team",
    "salary", "profit", "post", "story", "feed", "dating", "crush", "ghosting",
    "flag", "vibes", "relate", "valid", "trust", "support", "struggle", "overthinking",
    "clueless", "speechless", "shocked", "mindblowing", "game", "changer", "update",
    "trending", "viral", "glow", "chill", "toxic", "flexing", "cancel", "starboy",
    "clean", "rich", "poor", "save", "loss", "cut", "free", "freedom", "peace",
    "love", "care", "view", "reaction", "vibe", "honest", "review", "open", "close",
    "next", "term", "rule", "applies", "always", "witnessing", "family", "friends",
    "news", "future", "read", "somewhere", "calling", "disagree", "thank", "you",
    "have", "program", "how", "about", "huh", "when", "the", "with", "and", "good",
    "then", "more", "make", "will", "hope", "everything", "your", "for", "read",
    "someone", "couldn", "couldnt", "t", "iam",
})

# Plesetan: modifikasi fonem, rima, metatesis, atau tawa gaul
PLESETAN_LEXICON: frozenset[str] = frozenset({
    "santuy", "gokil", "kuy", "skuy", "anjir", "anjay", "anjim", "ngab", "ngabers",
    "sabi", "takis", "bejir", "bjir", "bjirr", "cuaks", "coeg", "wkwk", "wkwkwk",
    "wkwkwkwk", "awokawok", "xixi", "mbois", "gaskeun", "gaspol", "parah", "gils",
    "mantul", "menyala", "kocak", "lebay", "receh", "ambyar", "rempong", "zonk",
    "kicep", "mletre", "sambat", "tercyduk", "ciduk", "bocah", "songong", "sotoy",
    "julid", "julit", "halu", "pargoy", "tubir", "bokek", "cepu", "ilfil", "lelet",
    "kemain", "pergh", "perghhhh", "erk", "walaun", "menurunkansuhu",
})

# Pemendekan: pemotongan suku kata (clipping / truncation) kata baku
PEMENDEKAN_LEXICON: frozenset[str] = frozenset({
    "ga", "gak", "ngga", "nggak", "kagak", "lu", "lo", "loe", "gw", "gue", "gua",
    "makasih", "tengkiu", "aja", "udah", "dah", "kalo", "klo", "tau", "emang",
    "mang", "bener", "pake", "cuma", "dapet", "liat", "sampe", "seneng", "ngerti",
    "sptnya", "kayaknya", "temen", "temen2", "ambik", "korang", "je", "tu", "ni",
    "kek", "gini", "gitu", "tuh", "nih", "noh", "deh", "dong", "sih", "kan",
    "lah", "yah", "yh", "kok", "loh", "lahh", "bang", "mas", "mbak", "kak",
    "om", "tante", "pak", "bu", "nak", "lagi", "skali",
})

# Pola pemanjangan huruf ekspresif (e.g. bangeeet, iyaaa, mantappp, ahhh) -> plesetan
RE_ELONGATION = re.compile(r"([a-zA-Z])\1{2,}")

# ==============================================================================
# 2. PATTERNS & LEXICONS: FUNGSI BAHASA (JAKOBSON'S MODEL)
# ==============================================================================

# Emotif: mengekspresikan emosi, perasaan batin, apresiasi, rasa syukur, atau reaksi subjektif
EMOTIF_WORDS: frozenset[str] = frozenset({
    "alhamdulillah", "puji", "tuhan", "senang", "happy", "gembira", "bangga",
    "mantap", "mantul", "terbaik", "gokil", "keren", "terima", "kasih", "tq",
    "syukur", "cinta", "love", "kagum", "bahagia", "selamat", "sukses", "bermakna",
    "hebat", "indah", "puas", "berkah", "baper", "haru", "terharu", "iri",
    "sedih", "kecewa", "takut", "merana", "kasihan", "suka", "benci", "marah",
    "kesal", "muak", "capek", "lelah", "hancur", "bingung", "stress", "pusing",
    "wkwk", "haha", "wah", "aduh", "astaga", "pergh", "menyala", "masyaallah",
    "subhanallah", "gila", "buset", "anjir", "anjay", "waduh", "yey", "tahniah",
    "syabas", "salut", "alhamdullilah",
})

RE_EMOTIVE_EMOJIS = re.compile(
    r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF\U00002600-\U000026FF\U00002700-\U000027BF]"
)
RE_EXCLAMATION_CHAIN = re.compile(r"!{2,}")

# Referensial: fakta, kebijakan, data ekonomi, nominal angka, situasi dunia nyata, sebab-akibat
REFERENSIAL_WORDS: frozenset[str] = frozenset({
    "belanjawan", "gaji", "minimum", "ekonomi", "kos", "operasi", "industri",
    "pekerja", "pemerintah", "kerajaan", "reformasi", "anggaran", "kebijakan",
    "negara", "inflasi", "kemiskinan", "merdeka", "kakitangan", "kontrak",
    "jawatan", "pendapatan", "bisnis", "hukum", "politik", "sarikat", "standar",
    "undang-undang", "modal", "investasi", "pajak", "subsidi", "harga", "dana",
    "pembangunan", "proyek", "fasilitas", "infrastruktur", "pendidikan", "kesehatan",
    "kkm", "glic", "glc", "pmks", "wni", "wna", "indonesia", "malaysia", "dpr",
    "bumn", "menteri", "presiden", "perdana", "kabinet", "sebab", "karena",
    "akibatnya", "jika", "bila", "bahwa", "fakta", "berdasarkan", "menurut",
    "data", "artinya", "rm", "rupiah", "ringgit", "juta", "ribu", "persen",
    "tahun", "thn", "bulan", "senarai", "spm", "grad", "tanggung", "rugi",
    "menganggur", "pencakar", "langit", "kestabilan",
})

RE_CURRENCY_OR_NUMBERS = re.compile(
    r"\b(?:rm|rp|idr|usd)?\s*\d+(?:[.,]\d+)?(?:\s*(?:juta|ribu|miliar|triliun|persen|%|thn|tahun|bln))?\b",
    re.IGNORECASE,
)

# Konatif: mempengaruhi orang lain, permohonan, instruksi, ajakan, doa permohonan, mention, pertanyaan
KONATIF_WORDS: frozenset[str] = frozenset({
    "tolong", "mohon", "please", "minta", "harap", "pinjam", "pinjamkan",
    "pertimbangkan", "tengok", "dengar", "perhatikan", "bantu", "request", "titip",
    "jangan", "harus", "wajib", "kudu", "mesti", "stop", "hentikan", "awas",
    "ingat", "coba", "ayo", "mari", "kuy", "skuy", "gas", "gaskeun", "gaspol",
    "lanjutkan", "kekalkan", "dukung", "pilih", "semoga", "moga", "mudah-mudahan",
    "kapan", "gimana", "bagaimana", "sape",
})

RE_MENTION = re.compile(r"@([a-zA-Z0-9_.]+)")
RE_QUESTION_MARK = re.compile(r"\?+")
RE_CALL_TO_ACTION_PHRASES = re.compile(
    r"\b(?:sepenggal\s+lagi|pinjam\s+pm|nih\s+liat|cek\s+link|bantu\s+share|jangan\s+main)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CategorizationResult:
    """Standardized multi-label categorization output for a comment text."""

    slang_forms: list[str] = field(default_factory=list)
    language_functions: list[str] = field(default_factory=list)
    detected_slang_words: list[str] = field(default_factory=list)
    slang_present: bool = False

    @property
    def slang_forms_str(self) -> str:
        """Formatted string for CSV storage (semicolon-separated)."""
        return ";".join(self.slang_forms) if self.slang_forms else "tidak_ada"

    @property
    def language_functions_str(self) -> str:
        """Formatted string for CSV storage (semicolon-separated)."""
        return ";".join(self.language_functions) if self.language_functions else "tidak_jelas"

    @property
    def detected_words_str(self) -> str:
        """Formatted string of detected slang words/spans."""
        return ";".join(self.detected_slang_words)


def extract_clean_tokens(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric words, stripping URLs and symbols."""
    if not text:
        return []
    # Replace URLs with blank
    clean_str = re.sub(r"https?://\S+|www\.\S+|\[URL\]", " ", text, flags=re.IGNORECASE)
    # Extract words
    return re.findall(r"\b[a-zA-Z0-9_-]+\b", clean_str.lower())


def categorize_slang_forms(text: str) -> tuple[list[str], list[str]]:
    """Identify slang forms (bentuk bahasa gaul) and detected tokens present in text.

    Returns:
        tuple[list[str], list[str]]: (detected_slang_forms, detected_slang_tokens)
    """
    if not text or not text.strip():
        return ["tidak_ada"], []

    tokens = extract_clean_tokens(text)
    detected_forms: set[str] = set()
    detected_tokens: list[str] = []

    for t in tokens:
        token_matched = False

        # 1. Akronim
        if t in AKRONIM_LEXICON:
            detected_forms.add("akronim")
            if t not in detected_tokens:
                detected_tokens.append(t)
            token_matched = True

        # 2. Singkatan
        if t in SINGKATAN_LEXICON:
            detected_forms.add("singkatan")
            if t not in detected_tokens:
                detected_tokens.append(t)
            token_matched = True

        # 3. Bahasa Asing
        if t in BAHASA_ASING_LEXICON:
            detected_forms.add("bahasa_asing")
            if t not in detected_tokens:
                detected_tokens.append(t)
            token_matched = True

        # 4. Plesetan
        if t in PLESETAN_LEXICON:
            detected_forms.add("plesetan")
            if t not in detected_tokens:
                detected_tokens.append(t)
            token_matched = True
        elif RE_ELONGATION.search(t):
            # Expressive elongated words count as plesetan
            detected_forms.add("plesetan")
            if t not in detected_tokens:
                detected_tokens.append(t)
            token_matched = True

        # 5. Pemendekan
        if t in PEMENDEKAN_LEXICON:
            detected_forms.add("pemendekan")
            if t not in detected_tokens:
                detected_tokens.append(t)
            token_matched = True

    # Order forms consistently according to priority
    order = ["akronim", "singkatan", "bahasa_asing", "plesetan", "pemendekan"]
    sorted_forms = [f for f in order if f in detected_forms]

    if not sorted_forms:
        sorted_forms = ["tidak_ada"]

    return sorted_forms, detected_tokens


def categorize_language_functions(text: str) -> list[str]:
    """Identify communicative language functions present in text (Jakobson's model).

    Returns:
        list[str]: list containing one or more of ['emotif', 'referensial', 'konatif']
                   or ['tidak_jelas'] if none apply.
    """
    if not text or not text.strip():
        return ["tidak_jelas"]

    tokens = set(extract_clean_tokens(text))
    detected_functions: set[str] = set()

    # --- 1. EVALUATE EMOTIF ---
    # Triggered by emotive words, affective emojis, exclamation chains, or laughing onomatopoeia
    if any(t in EMOTIF_WORDS for t in tokens):
        detected_functions.add("emotif")
    elif RE_EMOTIVE_EMOJIS.search(text):
        detected_functions.add("emotif")
    elif RE_EXCLAMATION_CHAIN.search(text):
        detected_functions.add("emotif")
    elif any(t.startswith("wkwk") or t.startswith("haha") or t.startswith("xixi") for t in tokens):
        detected_functions.add("emotif")

    # --- 2. EVALUATE REFERENSIAL ---
    # Triggered by factual/policy terms, economic topics, explicit numbers/currencies, or causal conjunctions
    if any(t in REFERENSIAL_WORDS for t in tokens):
        detected_functions.add("referensial")
    elif RE_CURRENCY_OR_NUMBERS.search(text):
        detected_functions.add("referensial")

    # --- 3. EVALUATE KONATIF ---
    # Triggered by directive verbs, public figure mentions (@user), call-to-action phrases, or questions
    if any(t in KONATIF_WORDS for t in tokens):
        detected_functions.add("konatif")
    elif RE_MENTION.search(text):
        detected_functions.add("konatif")
    elif RE_QUESTION_MARK.search(text):
        detected_functions.add("konatif")
    elif RE_CALL_TO_ACTION_PHRASES.search(text):
        detected_functions.add("konatif")

    # Order functions consistently
    order = ["emotif", "referensial", "konatif"]
    sorted_functions = [fn for fn in order if fn in detected_functions]

    if not sorted_functions:
        sorted_functions = ["tidak_jelas"]

    return sorted_functions


def classify_comment(text: str) -> CategorizationResult:
    """Perform complete multi-label linguistic classification on comment text."""
    slang_forms, detected_tokens = categorize_slang_forms(text)
    lang_functions = categorize_language_functions(text)
    slang_present = (slang_forms != ["tidak_ada"])

    return CategorizationResult(
        slang_forms=slang_forms,
        language_functions=lang_functions,
        detected_slang_words=detected_tokens,
        slang_present=slang_present,
    )


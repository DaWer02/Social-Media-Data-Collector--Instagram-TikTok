"""NLP Extractors package for parsing and filtering text from unstructured web sources."""

from src.extractors.linguistic_classifier import (
    CategorizationResult,
    categorize_language_functions,
    categorize_slang_forms,
    classify_comment,
)
from src.extractors.nlp_comment_extractor import NLPCommentExtractor

__all__ = [
    "NLPCommentExtractor",
    "CategorizationResult",
    "classify_comment",
    "categorize_slang_forms",
    "categorize_language_functions",
]

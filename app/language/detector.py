"""Language Detector — detects the language of incoming messages.

Supports: English, Hindi, Hinglish, Roman Urdu, and others.
"""

import re
from loguru import logger

try:
    from langdetect import detect, LangDetectException
    HAS_LANGDETECT = True
except ImportError:
    HAS_LANGDETECT = False


# Hinglish / Roman Urdu patterns
_HINGLISH_PATTERNS = [
    r"\b(kya|hai|nahi|nahi|nhi|bhai|yaar|bro|bhi|toh|abhi|accha|theek|haan|na|mein|tum|tumhe|karo|karna|chal|lekin|agar|kyun|kabhi|sab|waise|aur|ek|do|teen|yeh|woh|uska|uski|apna|apni|likh|bol|sun|dekh|samajh|mat|zara)\b",
    r"\b(bro|yaar|bhai|boss|legend|sir|bhaiya|dude|machayenge|patakha|jugaad|desi)\b",
]


class LanguageDetector:
    def __init__(self):
        self._compiled = [re.compile(p, re.IGNORECASE) for p in _HINGLISH_PATTERNS]

    def detect(self, text: str) -> str:
        """Return detected language: 'en', 'hi', 'hinglish', 'roman_urdu', or 'other'."""
        if not text or len(text.strip()) < 2:
            return "other"

        # Check for Hinglish / Roman Urdu via pattern matching first
        hinglish_hits = sum(1 for p in self._compiled if p.search(text))
        if hinglish_hits >= 1:
            # Distinguish Hinglish vs Roman Urdu heuristically
            urdu_markers = re.search(
                r"\b(ka|ki|ke|ko|mein|tum|tumhara|hai|hain|tha|thi|the|karo|karna|nahi|haan|na|lekin|agar|ya|aur|bhi|toh|se|par|tak|mein|yeh|woh)\b",
                text,
                re.IGNORECASE,
            )
            if urdu_markers and hinglish_hits >= 2:
                return "roman_urdu"
            return "hinglish"

        # Fallback to langdetect
        if HAS_LANGDETECT:
            try:
                lang = detect(text)
                if lang == "en":
                    return "en"
                elif lang == "hi":
                    return "hi"
                else:
                    return "other"
            except LangDetectException:
                return "other"

        return "en"  # safe default

    def detect_batch(self, texts: list[str]) -> list[str]:
        return [self.detect(t) for t in texts]

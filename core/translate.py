"""Sentence translation through non-Google online services.

Primary engine: MyMemory Translation API (free, no key required).
Fallback engine: LibreTranslate public API.
Japanese support additionally uses the Jisho/JMdict dictionary (see
``dictionary.py``) to build a word-level fallback and a glossary.
"""

from __future__ import annotations

import html
import re
from typing import List, Optional

import requests

from .dictionary import JapaneseDictionary

_MYMEMORY_URL = "https://api.mymemory.translated.net/get"
_LIBRETRANSLATE_URL = "https://libretranslate.com/translate"
_MAX_CHARS = 450  # MyMemory accepts at most 500 characters per request.

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")


def chunk_text(text: str, limit: int = _MAX_CHARS) -> List[str]:
    """Split text into API-safe chunks, preferring sentence boundaries."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    current = ""
    for sentence in _SENTENCE_SPLIT.split(text):
        if len(sentence) > limit:
            if current:
                chunks.append(current)
                current = ""
            # Hard-split very long sentences on whitespace / punctuation.
            pieces = re.split(r"(?<=[,、,:;])\s+", sentence)
            for piece in pieces:
                while len(piece) > limit:
                    chunks.append(piece[:limit])
                    piece = piece[limit:]
                if piece:
                    if current and len(current) + len(piece) + 1 <= limit:
                        current += " " + piece
                    else:
                        if current:
                            chunks.append(current)
                        current = piece
            continue
        if current and len(current) + len(sentence) + 1 > limit:
            chunks.append(current)
            current = sentence
        else:
            current = current + " " + sentence if current else sentence
    if current:
        chunks.append(current)
    return chunks


class Translator:
    """Translate text using MyMemory with fallbacks."""

    def __init__(
        self,
        japanese_dictionary: Optional[JapaneseDictionary] = None,
        email: Optional[str] = None,
        timeout: float = 15.0,
    ) -> None:
        self.dictionary = japanese_dictionary or JapaneseDictionary()
        self.email = email
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "AiTranslator/1.0 (video subtitle translator)"}
        )

    def translate_text(self, text: str, source: str, target: str) -> str:
        if not text or not text.strip():
            return ""
        if source == target:
            return text
        results: List[str] = []
        for chunk in chunk_text(text):
            translated = self._translate_chunk(chunk, source, target)
            results.append(translated if translated else chunk)
        return " ".join(results)

    def _translate_chunk(self, text: str, source: str, target: str) -> str:
        translated = self._mymemory(text, source, target)
        if translated:
            return translated
        # MyMemory often stores sentences without final punctuation and then
        # returns the input unchanged when a trailing dot/question mark is
        # present. Retry without it before giving up.
        without_punctuation = text.rstrip(".!?,;:。！？、")
        if without_punctuation and without_punctuation != text:
            translated = self._mymemory(without_punctuation, source, target)
            if translated:
                return translated
        translated = self._libretranslate(text, source, target)
        if translated:
            return translated
        if source == "ja":
            return self._dictionary_fallback(text, target)
        return ""

    def _mymemory(self, text: str, source: str, target: str) -> str:
        params = {"q": text, "langpair": f"{source}|{target}"}
        if self.email:
            params["de"] = self.email
        try:
            resp = self._session.get(
                _MYMEMORY_URL, params=params, timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return ""
        if str(data.get("responseStatus")) != "200":
            return ""
        if data.get("quotaFinished"):
            return ""
        details = str(data.get("responseDetails") or "").lower()
        if "warning" in details or "quota" in details:
            return ""
        translated = (data.get("responseData") or {}).get("translatedText", "")
        translated = html.unescape(translated).strip()
        if "MYMEMORY WARNING" in translated.upper():
            return ""
        if translated.lower() == html.unescape(text).strip().lower():
            return ""
        # MyMemory sometimes returns the Japanese source unchanged. Treat that
        # as a failure so the dictionary fallback can produce Russian text.
        if source == "ja" and target == "ru" and _KANA_RE.search(translated):
            return ""
        return translated

    def _libretranslate(self, text: str, source: str, target: str) -> str:
        payload = {
            "q": text,
            "source": source,
            "target": target,
            "format": "text",
            "alternatives": 0,
        }
        try:
            resp = self._session.post(
                _LIBRETRANSLATE_URL, json=payload, timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return ""
        translated = html.unescape(data.get("translatedText", "")).strip()
        if translated.lower() == html.unescape(text).strip().lower():
            return ""
        return translated

    def _dictionary_fallback(self, text: str, target: str) -> str:
        """Translation built from the offline Russian JMdict dictionary.

        Used when online translation services are unavailable or returned the
        Japanese source unchanged. No network request is needed for Russian.
        """
        meanings: List[str] = []
        for word in self.dictionary.extract_content_words(text):
            if target == "ru":
                russian = self.dictionary.russian_meanings(word)
                if russian:
                    meanings.append(russian[0])
                    continue
            entry = self.dictionary.lookup(word)
            if not entry:
                continue
            if entry.russian and target == "ru":
                meanings.append(entry.russian[0])
            elif entry.english:
                gloss = entry.english[0]
                if target not in ("en", "ja"):
                    gloss = self._mymemory(gloss, "en", target) or gloss
                meanings.append(gloss)
        return ", ".join(meanings)

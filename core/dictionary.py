"""Japanese dictionary support.

Primary offline source: a compact dictionary built from JMdict with Russian
glosses (69 419 words), backed by the Warodai dictionary. Jisho.org's JMdict
API is used online for English definitions when the offline data has no entry.

A small curated dictionary is kept for the most frequent words, and fugashi +
UniDic provide morphological analysis so inflected forms map to lemmas.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import requests

from .warodai import WarodaiDictionary

try:
    from fugashi import Tagger as _FugashiTagger
except ImportError:  # pragma: no cover - optional dependency
    _FugashiTagger = None

_JISHO_URL = "https://jisho.org/api/v1/search/words"
_KEEP_POS = {"名詞", "動詞", "形容詞", "形状詞", "副詞"}
_PARTICLES = {
    "は", "が", "を", "に", "へ", "と", "で", "の", "も", "や", "から", "まで",
    "より", "だけ", "など", "って", "ね", "よ", "な", "ぞ", "さ", "か", "ば",
    "たら", "なら", "ながら", "ので", "のに", "こと", "もの", "です", "ます",
    "した", "して", "する", "ある", "いる", "でした",
}
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uff66-\uff9f]{2,}")


@dataclass
class DictEntry:
    word: str
    reading: str = ""
    english: List[str] = field(default_factory=list)
    russian: List[str] = field(default_factory=list)
    parts_of_speech: List[str] = field(default_factory=list)
    jlpt: List[str] = field(default_factory=list)
    source: str = ""

    def summary(self) -> str:
        meanings = self.russian or self.english
        text = self.word + (f" [{self.reading}]" if self.reading else "")
        if meanings:
            text += " — " + "; ".join(meanings[:3])
        return text


class JapaneseDictionary:
    """Russian-first Japanese dictionary with an online English fallback."""

    def __init__(
        self, timeout: float = 8.0, min_interval: float = 0.2, use_tokenizer: bool = True
    ) -> None:
        self.timeout = timeout
        self.min_interval = min_interval
        self.use_tokenizer = use_tokenizer and _FugashiTagger is not None
        self._tagger = None
        self._cache: Dict[str, Optional[DictEntry]] = {}
        self._last_call = 0.0
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "AiTranslator/1.0 (video subtitle translator)"}
        )
        self._local = self._load_local()
        self._warodai = WarodaiDictionary()
        self._entries: List[dict] = []
        self._ru_index: Dict[str, int] = {}
        self._ru_loaded = False
        self._ru_lock = threading.Lock()

    # ------------------------------------------------------------ data loading
    @staticmethod
    def _base_dir() -> Path:
        return Path(__file__).resolve().parent.parent

    def _load_local(self) -> Dict[str, DictEntry]:
        path = self._base_dir() / "dict" / "ja_en_mini.json"
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {
            word: DictEntry(
                word=word,
                reading=data.get("reading", ""),
                english=list(data.get("en", [])),
                russian=list(data.get("ru", [])),
                source="curated",
            )
            for word, data in raw.items()
        }

    def _load_ru(self) -> None:
        """Load the Russian JMdict index once, thread-safely."""
        if self._ru_loaded:
            return
        with self._ru_lock:
            if self._ru_loaded:
                return
            try:
                self._load_ru_data()
            finally:
                self._ru_loaded = True

    def _load_ru_data(self) -> None:
        path = self._base_dir() / "dict" / "jmdict_ru_common.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        entries = data.get("entries", [])
        # Common words first, so their meanings win for identical spellings.
        entries.sort(key=lambda item: item.get("c", 0), reverse=True)
        self._entries = entries
        for index, entry in enumerate(entries):
            for form in entry.get("k", []) + entry.get("r", []):
                previous = self._ru_index.get(form)
                if previous is None:
                    self._ru_index[form] = index
                    continue
                # Homonyms: merge missing meanings into the primary entry.
                meanings = self._entries[previous]["s"]
                for gloss in entry.get("s", []):
                    if gloss not in meanings and len(meanings) < 8:
                        meanings.append(gloss)

    # ------------------------------------------------------------------ lookup
    def lookup(self, word: str) -> Optional[DictEntry]:
        """Look up a word, preferring offline Russian data."""
        word = word.strip()
        if not word:
            return None
        if word in self._cache:
            return self._cache[word]

        local = self._local.get(word)
        if local is not None:
            self._cache[word] = local
            return local

        entry = self._lookup_ru(word)
        if entry is None or not entry.russian:
            warodai = self._warodai.lookup(word)
            if warodai:
                entry = DictEntry(
                    word=word,
                    russian=list(warodai),
                    source="warodai",
                )
        if entry is None or (not entry.russian and not entry.english):
            entry = self._lookup_jisho(word)
        self._cache[word] = entry
        return entry

    def _lookup_ru(self, word: str) -> Optional[DictEntry]:
        self._load_ru()
        index = self._ru_index.get(word)
        if index is None:
            return None
        data = self._entries[index]
        kanji = data.get("k") or []
        kana = data.get("r") or []
        return DictEntry(
            word=word,
            reading=kana[0] if kana else "",
            russian=list(data.get("s", [])),
            parts_of_speech=list(data.get("p", [])),
            source="jmdict-ru",
        )

    def russian_meanings(self, word: str) -> List[str]:
        """Fast offline lookup of Russian meanings (no network)."""
        entry = self._local.get(word) or self._lookup_ru(word)
        if entry and entry.russian:
            return entry.russian
        warodai = self._warodai.lookup(word)
        return list(warodai) if warodai else []

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _lookup_jisho(self, word: str) -> Optional[DictEntry]:
        self._throttle()
        try:
            resp = self._session.get(
                _JISHO_URL, params={"keyword": word}, timeout=self.timeout
            )
            resp.raise_for_status()
            rows = resp.json().get("data") or []
        except (requests.RequestException, ValueError):
            return None
        if not rows:
            return None

        row = rows[0]
        for candidate in rows:
            forms = [j.get("word", "") for j in candidate.get("japanese", [])]
            if word in forms:
                row = candidate
                break

        japanese = row.get("japanese") or [{}]
        reading = japanese[0].get("reading", "") or japanese[0].get("word", word)
        english: List[str] = []
        pos: List[str] = []
        for sense in row.get("senses") or []:
            for definition in sense.get("english_definitions", []):
                if definition not in english:
                    english.append(definition)
            for tag in sense.get("parts_of_speech", []):
                if tag not in pos:
                    pos.append(tag)
        return DictEntry(
            word=word,
            reading=reading,
            english=english,
            parts_of_speech=pos,
            jlpt=list(row.get("jlpt") or []),
            source="jisho",
        )

    # ------------------------------------------------------------- tokenization
    def extract_content_words(self, text: str) -> List[str]:
        """Extract vocabulary words (not particles) from Japanese text."""
        found: List[str] = []
        if self.use_tokenizer:
            if self._tagger is None:
                self._tagger = _FugashiTagger()
            for token in self._tagger(text):
                features = token.feature
                if (features[0] if features else "") not in _KEEP_POS:
                    continue
                surface = str(token.surface)
                if not _TOKEN_RE.search(surface):
                    continue
                word = features[7] if len(features) > 7 and features[7] else surface
                if word in _PARTICLES or len(set(word)) <= 1:
                    continue
                if word not in found:
                    found.append(word)
            return found
        for token in _TOKEN_RE.findall(text):
            if token in _PARTICLES or len(set(token)) <= 1:
                continue
            if token not in found:
                found.append(token)
        return found

    def dictionary_size(self) -> int:
        self._load_ru()
        return len(self._entries)

    def warodai_size(self) -> int:
        return self._warodai.size()

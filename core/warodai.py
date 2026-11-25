"""Optional offline fallback dictionary: Warodai Japanese-Russian dictionary.

The original dictionary file is bundled unchanged (dict/warodai_txt.zip) and
parsed at runtime. Warodai is distributed under CC BY-NC-ND 3.0:
https://warodai.ru/ -- attribution is given in the README and the GUI footer.

It adds ~25 000 Japanese headwords that are absent from JMdict.
"""

from __future__ import annotations

import html
import re
import threading
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

_HEAD_RE = re.compile(r"〔\d{3}-\d{2}-\d{2}〕")
_TAG_RE = re.compile(r"<[^>]+>")
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_JAPANESE_RE = re.compile(r"[\u3005-\u30ff\u4e00-\u9fff\uff66-\uff9f]")
_KANJI_RE = re.compile(r"【([^】]+)】")


class WarodaiDictionary:
    """Read-only index over the original Warodai dictionary file."""

    def __init__(self, archive_path: str | Path | None = None) -> None:
        if archive_path is None:
            base = Path(__file__).resolve().parent.parent / "dict"
            archive_path = base / "warodai_txt.zip"
        self.archive_path = Path(archive_path)
        self._index: Dict[str, List[str]] = {}
        self._loaded = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        """Parse the dictionary once, even if several threads ask for it."""
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._index = self._parse()
            self._loaded = True

    def _parse(self) -> Dict[str, List[str]]:
        index: Dict[str, List[str]] = {}
        if not self.archive_path.exists():
            return index
        try:
            with zipfile.ZipFile(self.archive_path) as archive:
                names = [n for n in archive.namelist() if n.endswith(".txt")]
                if not names:
                    return index
                text = archive.read(names[0]).decode("utf-16", errors="replace")
        except (OSError, zipfile.BadZipFile, UnicodeError):
            return index

        lines = text.splitlines()
        i = 0
        total = len(lines)
        while i < total:
            line = lines[i]
            if "〔" not in line or not _HEAD_RE.search(line):
                i += 1
                continue
            headword = re.split(r"[（(〔【]", line, maxsplit=1)[0]
            forms: List[str] = []
            for part in re.split(r"[,、;；]", headword):
                form = part.strip().rstrip("ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVXLCDM0123456789").strip()
                if form:
                    forms.append(form)
            if "【" in line:
                for match in _KANJI_RE.finditer(line):
                    for part in re.split(r"[,、]", match.group(1)):
                        form = part.strip()
                        if form:
                            forms.append(form)

            i += 1
            body: List[str] = []
            while i < total and lines[i].strip():
                body.append(lines[i])
                i += 1

            meanings: List[str] = []
            for raw in body:
                clean = raw
                if "<" in clean:
                    clean = _TAG_RE.sub("", clean)
                if "&" in clean:
                    clean = html.unescape(clean)
                match = _CYRILLIC_RE.search(clean)
                if not match:
                    continue
                fragment = clean[match.start():].strip().rstrip(";").strip()
                if _JAPANESE_RE.search(fragment):
                    fragment = _JAPANESE_RE.sub("", fragment)
                fragment = " ".join(fragment.split())
                if len(fragment) < 2 or fragment.lower().startswith("см."):
                    continue
                if fragment not in meanings:
                    meanings.append(fragment)
                if len(meanings) >= 3:
                    break

            if not meanings or not forms:
                continue
            for form in forms:
                existing = index.get(form)
                if existing is None:
                    index[form] = meanings
                else:
                    for meaning in meanings:
                        if meaning not in existing:
                            existing.append(meaning)
        return index

    # ---------------------------------------------------------------- lookup
    def lookup(self, word: str) -> Optional[List[str]]:
        self._load()
        return self._index.get(word.strip())

    def size(self) -> int:
        self._load()
        return len(self._index)

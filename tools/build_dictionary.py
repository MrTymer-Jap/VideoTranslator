"""Build a full Japanese-Russian dictionary from jmdict-simplified.

Source: https://github.com/scriptin/jmdict-simplified (jmdict-rus release).
Result: dict/jmdict_ru_common.json -- every JMdict entry that has Russian
glosses (69 000+ words), compact JSON ready to be bundled into the app.

The source archive is kept in dict/jmdict-rus.zip so the file can be rebuilt.
"""

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dict" / "jmdict-rus.zip"
OUT = ROOT / "dict" / "jmdict_ru_common.json"
SOURCE_NAME = "jmdict-rus-3.6.2.json"


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"Missing source archive: {SRC}")
    with zipfile.ZipFile(SRC) as archive:
        names = [n for n in archive.namelist() if n.endswith(".json")]
        if not names:
            raise SystemExit(f"No JSON found in {SRC}")
        data = json.loads(archive.read(names[0]))

    entries = []
    for word in data["words"]:
        kanji = word.get("kanji", [])
        kana = word.get("kana", [])
        glosses = []
        for sense in word.get("sense", []):
            for gloss in sense.get("gloss", []):
                if gloss.get("lang") == "rus" and gloss["text"] not in glosses:
                    glosses.append(gloss["text"])
        if not glosses:
            continue
        common = any(item.get("common") for item in kanji + kana)
        entries.append(
            {
                "k": [item["text"] for item in kanji],
                "r": [item["text"] for item in kana],
                "s": glosses[:5],
                "p": word["sense"][0].get("partOfSpeech", []),
                "c": 1 if common else 0,
            }
        )

    payload = {
        "meta": {
            "source": "JMdict (jmdict-simplified), Russian glosses",
            "source_url": "https://github.com/scriptin/jmdict-simplified",
            "count": len(entries),
        },
        "entries": entries,
    }
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Wrote {len(entries)} entries to {OUT} ({OUT.stat().st_size / 1048576:.1f} MB)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

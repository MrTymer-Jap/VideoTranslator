"""Smoke tests that do not require downloading a Whisper model."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from core.audio import extract_audio, get_ffmpeg
from core.dictionary import JapaneseDictionary
from core.subtitles import build_srt, burn_subtitles, format_time
from core.transcribe import Segment
from core.translate import Translator, chunk_text


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        raise AssertionError(label)


def main():
    print("ffmpeg:", get_ffmpeg())
    check("format_time", format_time(61.234) == "00:01:01,234")

    chunks = chunk_text("Hello there. " * 60)
    check("chunking", len(chunks) > 1 and all(len(c) <= 450 for c in chunks))

    d = JapaneseDictionary()
    local = d.lookup("食べる")
    check("curated dictionary", local is not None and local.source == "curated")
    check("JMdict Russian", bool(d.russian_meanings("天気")))
    print("   dictionary size:", d.dictionary_size())
    check("JMdict Russian lookup", bool(d.lookup("素晴らしい").russian))

    t = Translator(japanese_dictionary=d)
    en_ru = t.translate_text("Hello, how are you today?", "en", "ru")
    check("MyMemory en->ru", bool(en_ru) and en_ru != "Hello, how are you today?")
    print("   en->ru:", en_ru)
    ja_ru = t.translate_text("こんにちは、今日はいい天気ですね。", "ja", "ru")
    check("MyMemory ja->ru", bool(ja_ru))
    print("   ja->ru:", ja_ru)

    segments = [Segment(0.0, 2.5, "Hello"), Segment(3.0, 5.0, "World")]
    srt = build_srt(segments, ["Привет", "Мир"])
    check("SRT build", srt.startswith("1\n00:00:00,000 --> 00:00:02,500\nПривет"))

    # Generate a tiny test video with audio, then exercise extraction and burn-in.
    ffmpeg = get_ffmpeg()
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        video = str(Path(tmp) / "test.mp4")
        wav = str(Path(tmp) / "audio.wav")
        srt_path = str(Path(tmp) / "test.srt")
        out = str(Path(tmp) / "out.mp4")
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=3",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", video],
            check=True,
        )
        extract_audio(video, wav, ffmpeg)
        check("audio extraction", Path(wav).stat().st_size > 44)
        Path(srt_path).write_text(srt, encoding="utf-8-sig")
        burn_subtitles(video, srt_path, out, ffmpeg)
        check("subtitle burn-in", Path(out).stat().st_size > 1000)
        print("   output size:", Path(out).stat().st_size)

    print("\nALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()

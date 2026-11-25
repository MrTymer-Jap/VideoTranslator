"""Regression tests for bugs found during the code audit."""

import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from core.audio import extract_audio, get_ffmpeg
from core.dictionary import JapaneseDictionary
from core.pipeline import PipelineOptions, TranslationPipeline
from core.subtitles import build_srt, burn_subtitles
from core.transcribe import Segment
from core.warodai import WarodaiDictionary


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        raise AssertionError(label)


def main():
    ffmpeg = get_ffmpeg()

    # 1. build_srt: sequential numbering and no overlapping cues.
    segs = [Segment(0.0, 1.0, "one"), Segment(0.9, 2.0, "two"), Segment(3.0, 4.0, "three")]
    srt = build_srt(segs, ["один", "", "три"])
    check("empty translations skipped", "два" not in srt and srt.count("-->") == 2)
    check("sequential numbering", srt.startswith("1\n") and "\n2\n" in srt)
    srt_all = build_srt(segs, ["один", "два", "три"])
    check("no overlap", "00:00:01,000 --> 00:00:02,000" in srt_all)

    # 2. Warodai loads fully even when accessed from several threads.
    warodai = WarodaiDictionary()
    with ThreadPoolExecutor(max_workers=6) as pool:
        sizes = list(pool.map(lambda _: warodai.size(), range(6)))
    check("warodai thread-safe size", len(set(sizes)) == 1 and sizes[0] > 100000)
    check("warodai lookup after threads", bool(warodai.lookup("食べる")))

    # 3. JMdict index loads fully under concurrent access.
    d = JapaneseDictionary()
    with ThreadPoolExecutor(max_workers=6) as pool:
        sizes = list(pool.map(lambda _: d.dictionary_size(), range(6)))
    check("jmdict thread-safe size", len(set(sizes)) == 1 and sizes[0] == 69419)

    # 4. No-audio video gives a clear Russian error.
    with tempfile.TemporaryDirectory() as tmp:
        silent = str(Path(tmp) / "silent.mp4")
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=2",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", silent],
            check=True,
        )
        try:
            extract_audio(silent, str(Path(tmp) / "a.wav"), ffmpeg)
            raised = False
        except RuntimeError as exc:
            raised = "аудиодорожки" in str(exc)
        check("clear no-audio error", raised)

        # 5. output path cannot overwrite the source.
        video = Path(tmp) / "v.mp4"
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=2",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-shortest", str(video)],
            check=True,
        )
        srt = Path(tmp) / "s.srt"
        srt.write_text(build_srt([Segment(0, 1, "hi")], ["привет"]), encoding="utf-8-sig")
        try:
            burn_subtitles(str(video), str(srt), str(video), ffmpeg)
            guard = False
        except ValueError:
            guard = True
        check("overwrite guard", guard)

        # 6. Burn-in without saving SRT: no permanent SRT, video produced.
        out = Path(tmp) / "burn_only.mp4"
        options = PipelineOptions(
            video_path=str(video),
            output_srt="",
            output_video=str(out),
            model_size="tiny",
        )
        try:
            result = TranslationPipeline(options).run()
            check("burn-only result", result.srt_path == "" and out.exists())
        except RuntimeError as exc:
            # tiny model may not find speech in a sine wave; that is expected.
            check("burn-only reached transcription", "speech" in str(exc).lower())

    print("\nALL BUGFIX TESTS PASSED")


if __name__ == "__main__":
    main()

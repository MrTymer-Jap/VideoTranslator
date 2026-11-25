"""Full pipeline test using the tiny Whisper model and a generated video."""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from core.audio import get_ffmpeg
from core.dictionary import JapaneseDictionary
from core.pipeline import PipelineOptions, TranslationPipeline


def main():
    ffmpeg = get_ffmpeg()
    with tempfile.TemporaryDirectory() as tmp:
        video = str(Path(tmp) / "input.mp4")
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=4",
             "-i", "tests/speech_en.wav",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", video],
            check=True,
        )
        options = PipelineOptions(
            video_path=video,
            source_lang="en",
            target_lang="ru",
            output_srt=str(Path(tmp) / "out.srt"),
            output_video=str(Path(tmp) / "out.mp4"),
            model_size="tiny",
        )
        pipeline = TranslationPipeline(options, log_cb=print)
        result = pipeline.run()
        assert Path(result.srt_path).exists()
        assert Path(result.video_path).exists()
        print("SRT:\n" + Path(result.srt_path).read_text(encoding="utf-8-sig"))
        print("Video size:", Path(result.video_path).stat().st_size)

    d = JapaneseDictionary()
    words = d.extract_content_words("今日はいい天気ですね。食べるのが好きです。")
    print("Extracted words:", words)
    for word in words:
        print("  ", word, "->", d.russian_meanings(word))
    assert words and any(d.russian_meanings(w) for w in words)
    print("\nPIPELINE TEST PASSED")


if __name__ == "__main__":
    main()

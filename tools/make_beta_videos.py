"""Generate three short test videos with real speech for beta testing."""

import asyncio
import subprocess
import sys
from pathlib import Path

import edge_tts

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")
from core.audio import get_ffmpeg

OUT = Path(__file__).resolve().parent.parent / "tests" / "beta"
OUT.mkdir(parents=True, exist_ok=True)

CASES = [
    (
        "en",
        "en-US-AriaNeural",
        "Hello everyone. Welcome to this short test video. "
        "Today we will see how automatic subtitles work. I hope you enjoy it.",
    ),
    (
        "ja",
        "ja-JP-NanamiNeural",
        "こんにちは。この動画は字幕翻訳のテストです。今日は良い天気ですね。よろしくお願いします。",
    ),
    (
        "es",
        "es-ES-ElviraNeural",
        "Hola a todos. Bienvenidos a este pequeño video de prueba. "
        "Hoy veremos cómo funcionan los subtítulos automáticos.",
    ),
]


async def synthesize(voice: str, text: str, path: Path) -> None:
    await edge_tts.Communicate(text, voice).save(str(path))


def main() -> None:
    ffmpeg = get_ffmpeg()
    for lang, voice, text in CASES:
        audio = OUT / f"{lang}.mp3"
        video = OUT / f"{lang}.mp4"
        asyncio.run(synthesize(voice, text, audio))
        subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc=size=640x360:rate=24:duration=60",
                "-i", str(audio),
                "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-shortest", str(video),
            ],
            check=True,
        )
        print(f"{lang}: {video.name} ({video.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()

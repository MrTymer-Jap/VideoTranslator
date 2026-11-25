"""SRT subtitle generation and optional burn-in with ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Sequence

from .audio import get_ffmpeg


def format_time(seconds: float) -> str:
    """Format seconds as an SRT timestamp: HH:MM:SS,mmm."""
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(segments: Sequence, translations: Sequence[str]) -> str:
    """Build SRT text from timed segments and their translations."""
    blocks: List[str] = []
    previous_end = 0.0
    for seg, text in zip(segments, translations):
        clean = " ".join(str(text).split())
        if not clean:
            continue
        # Whisper segments can overlap slightly; keep SRT cues sequential.
        start = max(float(seg.start), previous_end)
        end = max(float(seg.end), start + 0.5)
        previous_end = end
        blocks.append(
            f"{len(blocks) + 1}\n{format_time(start)} --> {format_time(end)}\n{clean}\n"
        )
    return "\n".join(blocks)


def write_srt(segments: Sequence, translations: Sequence[str], path: str) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig") as fh:
        fh.write(build_srt(segments, translations))
    return path


def burn_subtitles(
    video_path: str,
    srt_path: str,
    output_path: str,
    ffmpeg: str | None = None,
) -> str:
    """Render subtitles into a new video file.

    The subtitle file is copied into a temporary working directory under a
    simple ASCII name to avoid ffmpeg filter-escaping problems with Windows
    paths (colons, backslashes, non-ASCII characters).
    """
    ffmpeg = ffmpeg or get_ffmpeg()
    if Path(video_path).resolve() == Path(output_path).resolve():
        raise ValueError("Output video path must differ from the source video path.")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_subs = Path(tmp) / "subs.srt"
        shutil.copyfile(srt_path, tmp_subs)
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(Path(video_path).resolve()),
            "-vf", "subtitles=subs.srt",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            str(Path(output_path).resolve()),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, errors="replace", cwd=tmp
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg could not burn subtitles: {result.stderr.strip()}")
    return output_path

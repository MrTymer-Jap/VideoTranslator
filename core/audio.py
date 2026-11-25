"""Audio extraction helpers built on ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional


def get_ffmpeg() -> str:
    """Find an ffmpeg executable: system PATH first, then imageio-ffmpeg."""
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - depends on installation
        raise RuntimeError(
            "ffmpeg not found. Install ffmpeg or run: pip install imageio-ffmpeg"
        ) from exc


def extract_audio(video_path: str, wav_path: str, ffmpeg: Optional[str] = None) -> str:
    """Extract mono 16 kHz WAV audio suitable for speech recognition."""
    ffmpeg = ffmpeg or get_ffmpeg()
    Path(wav_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", wav_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "does not contain any stream" in stderr or "no audio" in stderr.lower():
            raise RuntimeError("В видео нет аудиодорожки. Выберите файл со звуком.")
        raise RuntimeError(f"ffmpeg could not extract audio: {stderr}")
    if not Path(wav_path).exists() or Path(wav_path).stat().st_size < 44:
        raise RuntimeError("В видео нет аудиодорожки. Выберите файл со звуком.")
    return wav_path

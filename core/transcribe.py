"""Local speech recognition with faster-whisper (no Google services)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from .audio import get_ffmpeg


@dataclass
class Segment:
    start: float
    end: float
    text: str


class Transcriber:
    """Lazy-loading wrapper around faster-whisper."""

    def __init__(self, model_size: str = "small", device: str = "cpu") -> None:
        self.model_size = model_size
        self.device = device
        self._model = None

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type="int8" if self.device == "cpu" else "float16",
                download_root=None,
            )
        return self._model

    def transcribe(
        self,
        wav_path: str,
        language: Optional[str] = None,
        progress_cb: Optional[Callable[[str], None]] = None,
        cancelled_cb: Optional[Callable[[], bool]] = None,
    ) -> tuple[List[Segment], str]:
        """Transcribe WAV audio.

        Returns (segments, detected_language).
        """
        def log(msg: str) -> None:
            if progress_cb:
                progress_cb(msg)

        log(f"Loading Whisper model '{self.model_size}' (first run downloads it)...")
        model = self._load_model()
        log("Recognizing speech...")

        # Set ffmpeg path so faster-whisper's PyAV can locate it on Windows.
        try:
            import os

            os.environ.setdefault("IMAGEIO_FFMPEG_EXE", get_ffmpeg())
        except RuntimeError:
            pass

        kwargs = dict(
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        if language and language != "auto":
            kwargs["language"] = language

        segment_iter, info = model.transcribe(wav_path, **kwargs)
        detected = language if language and language != "auto" else info.language

        segments: List[Segment] = []
        for seg in segment_iter:
            if cancelled_cb and cancelled_cb():
                raise InterruptedError("Cancelled")
            text = seg.text.strip()
            if text:
                segments.append(Segment(start=float(seg.start), end=float(seg.end), text=text))
                log(f"  recognized {len(segments)} fragments...")
        log(f"Detection complete: {len(segments)} fragments, language={detected}")
        return segments, detected

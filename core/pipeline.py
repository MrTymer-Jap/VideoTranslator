"""End-to-end orchestration of the subtitle translation pipeline."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from .audio import extract_audio, get_ffmpeg
from .dictionary import JapaneseDictionary
from .subtitles import burn_subtitles, write_srt
from .transcribe import Segment, Transcriber
from .translate import Translator


class PipelineCancelled(Exception):
    """Raised when the user cancels a running pipeline."""


@dataclass
class PipelineOptions:
    video_path: str
    source_lang: str = "auto"
    target_lang: str = "ru"
    output_srt: str = ""
    output_video: str = ""
    model_size: str = "small"
    translate_email: Optional[str] = None


@dataclass
class PipelineResult:
    srt_path: str = ""
    video_path: str = ""
    detected_language: str = ""
    segment_count: int = 0


class TranslationPipeline:
    """Run extraction -> transcription -> translation -> subtitle output."""

    def __init__(
        self,
        options: PipelineOptions,
        log_cb: Optional[Callable[[str], None]] = None,
        progress_cb: Optional[Callable[[int], None]] = None,
        cancel_event=None,
    ) -> None:
        self.options = options
        self.log_cb = log_cb or (lambda msg: None)
        self.progress_cb = progress_cb or (lambda pct: None)
        self.cancel_event = cancel_event

    def _log(self, msg: str) -> None:
        self.log_cb(msg)

    def _check_cancel(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise PipelineCancelled("Operation cancelled by user.")

    def run(self) -> PipelineResult:
        opts = self.options
        result = PipelineResult()
        self._check_cancel()

        video = Path(opts.video_path)
        if not video.exists():
            raise FileNotFoundError(f"Video file not found: {video}")

        with tempfile.TemporaryDirectory() as tmp:
            # When only burn-in is requested, keep the SRT in the temp folder.
            srt_path = opts.output_srt or str(Path(tmp) / "subtitles.srt")
            wav_path = str(Path(tmp) / "audio.wav")
            ffmpeg = get_ffmpeg()

            self._log("Extracting audio from video...")
            extract_audio(str(video), wav_path, ffmpeg)
            self.progress_cb(10)
            self._check_cancel()

            transcriber = Transcriber(model_size=opts.model_size)
            segments, detected = transcriber.transcribe(
                wav_path,
                language=None if opts.source_lang == "auto" else opts.source_lang,
                progress_cb=self._log,
                cancelled_cb=lambda: (
                    self.cancel_event.is_set() if self.cancel_event else False
                ),
            )
            result.detected_language = detected
            result.segment_count = len(segments)
            if not segments:
                raise RuntimeError("No speech was detected in the video.")
            self.progress_cb(45)
            self._check_cancel()

            dictionary = JapaneseDictionary()
            translator = Translator(japanese_dictionary=dictionary, email=opts.translate_email)
            source = detected if opts.source_lang == "auto" else opts.source_lang

            self._log(f"Translating {len(segments)} fragments ({source} -> {opts.target_lang})...")
            translations: List[str] = []
            for i, seg in enumerate(segments, start=1):
                self._check_cancel()
                translations.append(translator.translate_text(seg.text, source, opts.target_lang))
                if i % 5 == 0 or i == len(segments):
                    self._log(f"  translated {i}/{len(segments)}")
                    self.progress_cb(45 + int(35 * i / len(segments)))

            write_srt(segments, translations, srt_path)
            if opts.output_srt:
                result.srt_path = srt_path
                self._log(f"Subtitles saved: {srt_path}")
            self.progress_cb(85)
            self._check_cancel()

            if opts.output_video:
                self._log("Burning subtitles into video (this may take a while)...")
                burn_subtitles(str(video), srt_path, opts.output_video, ffmpeg)
                result.video_path = opts.output_video
                self._log(f"Video saved: {opts.output_video}")

            self.progress_cb(100)
            self._log("Done.")
            return result

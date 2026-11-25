#!/usr/bin/env python3
"""Video Translator - modern GUI for translating video speech into subtitles."""

from __future__ import annotations

import os
import queue
import sys
import threading
from pathlib import Path
from typing import Dict

import customtkinter as ctk

from core.audio import get_ffmpeg
from core.dictionary import JapaneseDictionary
from core.pipeline import PipelineCancelled, PipelineOptions, TranslationPipeline

LANGUAGES: Dict[str, str] = {
    "Автоопределение": "auto",
    "Английский": "en",
    "Японский": "ja",
    "Русский": "ru",
    "Испанский": "es",
    "Французский": "fr",
    "Немецкий": "de",
    "Китайский": "zh",
    "Корейский": "ko",
    "Итальянский": "it",
    "Португальский": "pt",
    "Арабский": "ar",
    "Хинди": "hi",
    "Тайский": "th",
    "Вьетнамский": "vi",
}
SOURCE_LANGS = list(LANGUAGES)
TARGET_LANGS = [name for name, code in LANGUAGES.items() if code != "auto"]
MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"]

ACCENT = "#3B82F6"
ACCENT_HOVER = "#2563EB"
CARD = "#1E2029"
CARD_BORDER = "#2E3240"
TEXT_MUTED = "#9AA3B5"
BG = "#12141A"


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Video Translator")
        self.geometry("1000x740")
        self.minsize(880, 620)
        self.configure(fg_color=BG)

        self._queue: queue.Queue = queue.Queue()
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._dictionary = JapaneseDictionary()

        self._build_ui()
        self.after(120, self._drain_queue)
        self.after(1500, self._warm_dictionary)

    # ------------------------------------------------------------------ UI
    def _card(self, parent, number: str, title: str):
        frame = ctk.CTkFrame(
            parent, corner_radius=16, fg_color=CARD,
            border_width=1, border_color=CARD_BORDER,
        )
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(
            header, text=number, width=30, height=30, corner_radius=9,
            fg_color=ACCENT, text_color="#FFFFFF",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text=title, font=ctk.CTkFont(size=15, weight="bold")
        ).pack(side="left", padx=(12, 0))
        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="x", padx=20, pady=(6, 18))
        return frame, body

    def _build_ui(self) -> None:
        header = ctk.CTkFrame(self, height=92, corner_radius=0, fg_color="#191C24")
        header.pack(fill="x")
        header.pack_propagate(False)
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left", padx=(26, 0), pady=16)
        ctk.CTkLabel(
            title_box, text="Video Translator",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box,
            text="Перевод речи в видео в субтитры · распознавание на вашем компьютере",
            font=ctk.CTkFont(size=12), text_color=TEXT_MUTED,
        ).pack(anchor="w", pady=(2, 0))

        self.status_label = ctk.CTkLabel(
            header, text="●  Готов к работе", font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#4ADE80",
        )
        self.status_label.pack(side="right", padx=(0, 26))

        content = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0)
        content.pack(fill="both", expand=True)

        # --- 1. Video
        card, body = self._card(content, "1", "Видеофайл")
        card.grid(row=0, column=0, sticky="ew", padx=26, pady=(18, 12))
        self.video_var = ctk.StringVar()
        ctk.CTkEntry(
            body, textvariable=self.video_var, height=40, corner_radius=10,
            placeholder_text="Выберите видео (MP4, MKV, AVI, MOV ...)",
        ).pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(
            body, text="Обзор", width=104, height=40, corner_radius=10,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._pick_video,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            body, text="Папка", width=88, height=40, corner_radius=10,
            fg_color="#2E3240", hover_color="#3A3F50",
            font=ctk.CTkFont(size=13), command=self._open_folder,
        ).pack(side="left")

        # --- 2. Languages
        card, body = self._card(content, "2", "Языки")
        card.grid(row=1, column=0, sticky="ew", padx=26, pady=(0, 12))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        ctk.CTkLabel(
            body, text="Исходный язык", font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        ctk.CTkLabel(
            body, text="Перевести на", font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
        ).grid(row=0, column=1, sticky="w", pady=(0, 6))
        self.source_var = ctk.StringVar(value="Автоопределение")
        self.target_var = ctk.StringVar(value="Русский")
        combo_font = ctk.CTkFont(size=13)
        ctk.CTkComboBox(
            body, values=SOURCE_LANGS, variable=self.source_var,
            state="readonly", height=40, corner_radius=10, font=combo_font,
            dropdown_font=combo_font,
        ).grid(row=1, column=0, sticky="ew", padx=(0, 12))
        ctk.CTkComboBox(
            body, values=TARGET_LANGS, variable=self.target_var,
            state="readonly", height=40, corner_radius=10, font=combo_font,
            dropdown_font=combo_font,
        ).grid(row=1, column=1, sticky="ew")
        self.lang_hint = ctk.CTkLabel(
            body, text="Автоопределение определит язык по речи",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        )
        self.lang_hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        # --- 3. Settings
        card, body = self._card(content, "3", "Настройки")
        card.grid(row=2, column=0, sticky="ew", padx=26, pady=(0, 12))
        self.srt_var = ctk.BooleanVar(value=True)
        self.burn_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(
            body, text="Сохранить файл субтитров (.srt)",
            variable=self.srt_var, font=ctk.CTkFont(size=13),
            progress_color=ACCENT,
        ).grid(row=0, column=0, sticky="w", padx=(0, 26))
        ctk.CTkSwitch(
            body, text="Впечатать субтитры в видео (.mp4)",
            variable=self.burn_var, font=ctk.CTkFont(size=13),
            progress_color=ACCENT,
        ).grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(
            body, text="Модель распознавания", font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(16, 6))
        self.model_var = ctk.StringVar(value="small")
        ctk.CTkComboBox(
            body, values=MODEL_SIZES, variable=self.model_var,
            state="readonly", height=36, width=150, corner_radius=9,
            font=combo_font, dropdown_font=combo_font,
        ).grid(row=2, column=0, sticky="w")
        ctk.CTkLabel(
            body,
            text="tiny — быстро, small — оптимально, large-v3 — точнее, но медленнее",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        ).grid(row=2, column=1, sticky="w", padx=(16, 0))

        ctk.CTkLabel(
            body, text="Email для MyMemory (необязательно)",
            font=ctk.CTkFont(size=12), text_color=TEXT_MUTED,
        ).grid(row=3, column=0, sticky="w", pady=(14, 6))
        self.email_var = ctk.StringVar()
        ctk.CTkEntry(
            body, textvariable=self.email_var, height=36, corner_radius=9,
            placeholder_text="Увеличивает дневной лимит перевода",
        ).grid(row=4, column=0, columnspan=2, sticky="ew")

        # --- Actions
        actions = ctk.CTkFrame(content, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=26, pady=(2, 12))
        self.start_btn = ctk.CTkButton(
            actions, text="Начать перевод", width=230, height=48,
            corner_radius=12, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=15, weight="bold"), command=self._start,
        )
        self.start_btn.pack(side="left")
        self.cancel_btn = ctk.CTkButton(
            actions, text="Отмена", width=110, height=48, corner_radius=12,
            fg_color="#2E3240", hover_color="#3A3F50",
            font=ctk.CTkFont(size=14), state="disabled",
            command=self._cancel_run,
        )
        self.cancel_btn.pack(side="left", padx=(10, 0))
        self.progress = ctk.CTkProgressBar(
            actions, height=10, corner_radius=6, progress_color=ACCENT,
        )
        self.progress.set(0)
        self.progress.pack(side="left", fill="x", expand=True, padx=(18, 12))
        self.percent_label = ctk.CTkLabel(
            actions, text="0%", width=46, font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_MUTED,
        )
        self.percent_label.pack(side="right")

        # --- Log
        card = ctk.CTkFrame(
            content, corner_radius=16, fg_color="#101218",
            border_width=1, border_color=CARD_BORDER,
        )
        card.grid(row=4, column=0, sticky="ew", padx=26)
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(12, 4))
        ctk.CTkLabel(
            header, text="Ход работы", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="результаты сохраняются рядом с видео",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        ).pack(side="right")
        self.log_text = ctk.CTkTextbox(
            card, height=150, corner_radius=10, fg_color="#0C0E13",
            font=ctk.CTkFont(family="Consolas", size=12), activate_scrollbars=True,
        )
        self.log_text.pack(fill="x", padx=14, pady=(4, 14))
        self.log_text.configure(state="disabled")
        self.log_text.tag_config("error", foreground="#FF6B6B")
        self.log_text.tag_config("success", foreground="#4ADE80")
        self.log_text.tag_config("muted", foreground="#7C8598")

        ctk.CTkLabel(
            content,
            text=(
                "Речь обрабатывается локально · перевод: MyMemory / LibreTranslate · "
                "японские словари: JMdict, Warodai (CC BY-NC-ND 3.0)"
            ),
            font=ctk.CTkFont(size=11), text_color="#6B7280",
        ).grid(row=5, column=0, sticky="w", padx=26, pady=(12, 18))

        content.columnconfigure(0, weight=1)

    # -------------------------------------------------------------- events
    def _warm_dictionary(self) -> None:
        """Parse the large Warodai dictionary in the background."""
        threading.Thread(target=self._dictionary.warodai_size, daemon=True).start()

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.configure(text=text, text_color=color)

    def _pick_video(self) -> None:
        path = ctk.filedialog.askopenfilename(
            title="Выберите видео",
            filetypes=[
                ("Видео", "*.mp4 *.mkv *.avi *.mov *.webm *.m4v *.ts"),
                ("Все файлы", "*.*"),
            ],
        )
        if path:
            self.video_var.set(path)
            self._log(f"Выбрано видео: {path}", "muted")

    def _open_folder(self) -> None:
        path = self.video_var.get().strip()
        folder = str(Path(path).parent) if path else str(Path.cwd())
        if Path(folder).exists():
            os.startfile(folder)  # noqa: S606 - Windows Explorer

    def _cancel_run(self) -> None:
        self._cancel.set()
        self._log("Отмена запрошена...", "muted")
        self.cancel_btn.configure(state="disabled")

    def _start(self) -> None:
        video = self.video_var.get().strip()
        if not video or not Path(video).exists():
            self._log("Сначала выберите существующий видеофайл.", "error")
            self._set_status("●  Нет видео", "#FF6B6B")
            return
        if self._worker and self._worker.is_alive():
            return

        save_srt = self.srt_var.get()
        burn_video = self.burn_var.get()
        if not save_srt and not burn_video:
            self._log(
                "Выберите хотя бы один вариант результата: SRT или видео с субтитрами.",
                "error",
            )
            self._set_status("●  Нет результата", "#FF6B6B")
            return

        source = LANGUAGES[self.source_var.get()]
        target = LANGUAGES[self.target_var.get()]
        base = Path(video).with_suffix("")
        options = PipelineOptions(
            video_path=video,
            source_lang=source,
            target_lang=target,
            output_srt=(str(base) + ".srt") if save_srt else "",
            output_video=(str(base) + ".subbed.mp4") if burn_video else "",
            model_size=self.model_var.get(),
            translate_email=self.email_var.get().strip() or None,
        )

        self._cancel = threading.Event()
        self._queue.put(("progress", 0))
        self._set_status("●  В работе", ACCENT)
        self._log(f"Запуск: {source} → {target}", "muted")
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        cancel_event = self._cancel
        self._worker = threading.Thread(
            target=self._run_pipeline, args=(options, cancel_event), daemon=True
        )
        self._worker.start()

    def _run_pipeline(self, options: PipelineOptions, cancel_event: threading.Event) -> None:
        pipeline = TranslationPipeline(
            options,
            log_cb=lambda msg: self._queue.put(("log", msg)),
            progress_cb=lambda pct: self._queue.put(("progress", pct)),
            cancel_event=cancel_event,
        )
        try:
            self._queue.put(("done", pipeline.run()))
        except (PipelineCancelled, InterruptedError):
            self._queue.put(("cancelled", None))
        except Exception as exc:  # noqa: BLE001 - surfaced in the GUI
            self._queue.put(("error", f"{type(exc).__name__}: {exc}"))

    # ---------------------------------------------------------- queue/UI
    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "progress":
                    self.progress.set(payload / 100)
                    self.percent_label.configure(text=f"{int(payload)}%")
                elif kind == "done":
                    self._on_done(payload)
                elif kind == "cancelled":
                    self._log("Операция отменена.", "muted")
                    self._set_status("●  Отменено", "#F59E0B")
                    self._finish_run()
                elif kind == "error":
                    self._log("ОШИБКА: " + str(payload), "error")
                    self._set_status("●  Ошибка", "#FF6B6B")
                    self._finish_run()
        except queue.Empty:
            pass
        self.after(120, self._drain_queue)

    def _on_done(self, result) -> None:
        self._log(f"Готово! Обработано фрагментов: {result.segment_count}", "success")
        if result.srt_path:
            self._log(f"Субтитры: {result.srt_path}", "success")
        if result.video_path:
            self._log(f"Видео: {result.video_path}", "success")
        self._set_status("●  Готово", "#4ADE80")
        self.progress.set(1)
        self.percent_label.configure(text="100%")
        self._finish_run()

    def _finish_run(self) -> None:
        self.start_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")

    def _log(self, msg: str, tag: str | None = None) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def _selftest() -> None:
    """Check that a frozen build has all its data files and dependencies."""
    import tempfile
    import traceback

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    lines: list[str] = []

    def check(label: str, fn) -> None:
        try:
            lines.append(f"OK   {label}: {fn()}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"FAIL {label}: {type(exc).__name__}: {exc}")
            lines.append(traceback.format_exc())

    def _dict_path() -> Path:
        import core.dictionary as core_dictionary

        base = Path(core_dictionary.__file__).resolve().parent.parent / "dict"
        for name in ("jmdict_ru_common.json", "ja_en_mini.json"):
            if not (base / name).exists():
                raise FileNotFoundError(str(base / name))
        return base

    check("executable", lambda: sys.executable)
    check("bundle dir", lambda: getattr(sys, "_MEIPASS", "not frozen"))
    check("customtkinter", lambda: ctk.__version__)
    check("faster_whisper", lambda: __import__("faster_whisper").__version__)
    check("ctranslate2", lambda: __import__("ctranslate2").__version__)
    check("av", lambda: __import__("av").__version__)
    check("onnxruntime", lambda: __import__("onnxruntime").__version__)
    check("fugashi", lambda: __import__("fugashi").__file__)
    check("imageio_ffmpeg", lambda: get_ffmpeg())
    check("dictionary files", _dict_path)
    dictionary = JapaneseDictionary()
    check("dictionary size", dictionary.dictionary_size)
    check("warodai size", dictionary.warodai_size)
    check("russian lookup", lambda: dictionary.russian_meanings("食べる"))
    check("warodai lookup", lambda: dictionary.russian_meanings("うっちゃる"))
    check("tokenizer", lambda: dictionary.extract_content_words("今日はいい天気ですね。"))
    app = App()
    check("GUI", lambda: "created")
    app.destroy()

    out = Path(tempfile.gettempdir()) / "videotranslator_selftest.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


def _beta(video: str, model: str = "small") -> None:
    """Headless beta run: translate one video and write a report to a file."""
    import tempfile
    import time

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    lines: list[str] = []
    started = time.time()

    def log(msg: str) -> None:
        lines.append(msg)
        print(msg)

    base = Path(video).with_suffix("")
    options = PipelineOptions(
        video_path=str(Path(video).resolve()),
        source_lang="auto",
        target_lang="ru",
        output_srt=str(base) + ".srt",
        output_video=str(base) + ".subbed.mp4",
        model_size=model,
    )
    log(f"BETA: {video} (model={model})")
    try:
        result = TranslationPipeline(options, log_cb=log).run()
        srt = Path(result.srt_path).read_text(encoding="utf-8-sig")
        log(f"detected language: {result.detected_language}")
        log(f"segments: {result.segment_count}")
        log("--- SRT ---")
        log(srt)
        log(f"elapsed: {time.time() - started:.1f}s")
    except Exception as exc:  # noqa: BLE001
        log(f"BETA FAILED: {type(exc).__name__}: {exc}")

    out = Path(tempfile.gettempdir()) / "videotranslator_beta.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport: {out}")


def main() -> None:
    if "--selftest" in sys.argv:
        _selftest()
        return
    if "--beta" in sys.argv:
        index = sys.argv.index("--beta")
        if index + 1 < len(sys.argv):
            model = sys.argv[index + 2] if index + 2 < len(sys.argv) else "small"
            _beta(sys.argv[index + 1], model)
        return
    App().mainloop()


if __name__ == "__main__":
    main()

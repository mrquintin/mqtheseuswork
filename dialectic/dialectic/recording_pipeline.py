"""Post-recording orchestrator — trim → transcribe → title → upload.

Each stage is a stub in this prompt. Prompts 07-10 replace the bodies:

- ``_stage_trim``: prompt 08 (silence trimming)
- ``_stage_transcribe``: prompt 07 (full-session transcription)
- ``_stage_title``: prompt 09 (auto-title via Claude)
- ``_stage_upload``: prompt 10 (Codex upload with credentials)

The modal talks to the pipeline only through Qt signals, so replacements
drop in without touching UI code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal


STAGE_ORDER: tuple[str, ...] = ("trim", "transcribe", "title", "upload")


@dataclass
class RecordingArtifact:
    audio_path: Path
    duration_seconds: float
    sample_rate: int
    channels: int


@dataclass
class PipelineResult:
    trimmed_audio: Optional[Path] = None
    trim_intervals: list = field(default_factory=list)
    original_duration_s: Optional[float] = None
    trimmed_duration_s: Optional[float] = None
    transcript: Optional[str] = None
    transcript_segments: list = field(default_factory=list)
    transcript_language: Optional[str] = None
    transcript_model: Optional[str] = None
    title: Optional[str] = None
    title_method: Optional[str] = None  # "llm" | "fallback"
    recorded_date: Optional[str] = None  # ISO date (YYYY-MM-DD), UTC
    upload_id: Optional[str] = None
    codex_url: Optional[str] = None
    errors: dict = field(default_factory=dict)


class RecordingPipeline(QObject):
    """Runs trim → transcribe → title → upload. Each stage emits a signal
    with its result or error."""

    stage_started = pyqtSignal(str)
    stage_succeeded = pyqtSignal(str, object)
    stage_failed = pyqtSignal(str, str)
    # (stage_name, percent 0-100). Only the upload stage emits this today.
    stage_progress = pyqtSignal(str, int)
    all_done = pyqtSignal(object)

    def __init__(self, artifact: RecordingArtifact, parent: QObject | None = None):
        super().__init__(parent)
        self.artifact = artifact
        self.result = PipelineResult()

    def run(self) -> None:
        stages = (
            ("trim", self._stage_trim),
            ("transcribe", self._stage_transcribe),
            ("title", self._stage_title),
            ("upload", self._stage_upload),
        )
        try:
            for name, fn in stages:
                self.stage_started.emit(name)
                try:
                    value = fn()
                except Exception as exc:
                    self.result.errors[name] = str(exc)
                    self.stage_failed.emit(name, str(exc))
                    return
                self.stage_succeeded.emit(name, value)
        finally:
            self.all_done.emit(self.result)

    def _stage_trim(self):
        from dialectic.auto_trim import auto_trim

        out_path = self.artifact.audio_path.with_suffix(".trimmed.wav")
        result = auto_trim(self.artifact.audio_path, out_path)
        self.result.trimmed_audio = result.output_path
        self.result.trim_intervals = list(result.intervals)
        self.result.original_duration_s = result.original_duration_s
        self.result.trimmed_duration_s = result.trimmed_duration_s
        return result

    def _stage_transcribe(self):
        from dialectic.batch_transcriber import transcribe

        # `trimmed_audio` is populated by `_stage_trim` (prompt 08 replaces
        # its body; prompt 06's stub already assigns the raw path). Fall
        # back to the raw artifact path so this stage also works in
        # isolation — e.g., a test that bypasses trim.
        source = self.result.trimmed_audio or self.artifact.audio_path
        result = transcribe(source)
        self.result.transcript = result.text
        self.result.transcript_segments = list(result.segments)
        self.result.transcript_language = result.language
        self.result.transcript_model = result.model_name
        return result

    def _stage_title(self):
        # Title generation must never fail the whole pipeline. The
        # deterministic fallback inside ``generate_title`` is always
        # available; the outer try/except exists only for unexpected
        # errors above that layer (e.g. an import-time failure).
        from dialectic.auto_title import (
            AutoTitleResult,
            _deterministic_fallback,
            generate_title,
        )

        try:
            duration = (
                self.result.trimmed_duration_s
                or self.artifact.duration_seconds
            )
            result = generate_title(self.result.transcript or "", duration)
        except Exception:
            duration = self.artifact.duration_seconds
            result = AutoTitleResult(
                title=_deterministic_fallback(duration),
                recorded_date="",
                method="fallback",
                warnings=["unexpected error in generate_title"],
            )

        self.result.title = result.title
        self.result.title_method = result.method
        self.result.recorded_date = result.recorded_date
        return result

    def _stage_upload(self):
        # Real Codex upload: prepare → PUT → finalize, with a progress
        # callback for the UI and a pending-queue fallback so a flaky
        # network doesn't lose the recording. The trimmed .wav +
        # transcript stay on disk; a later `drain()` replays them.
        from datetime import datetime, timezone

        from dialectic.codex_upload import UploadError, upload_recording
        from dialectic.credentials import active as active_credentials
        from dialectic.pending_queue import PendingUpload, enqueue

        creds = active_credentials()
        if creds is None or not creds.api_key or not creds.codex_url:
            # No credentials → don't even try; queue for later so the
            # audio isn't lost on the next run of `Retry pending
            # uploads`. Return a result dict so callers can inspect
            # what happened.
            raise RuntimeError(
                "no Codex credentials configured — sign in to upload"
            )

        audio_path = self.result.trimmed_audio or self.artifact.audio_path
        transcript = self.result.transcript or ""
        title = self.result.title or ""
        recorded_date = self.result.recorded_date or ""
        extraction_method = (
            f"dialectic-{self.result.transcript_model or 'faster-whisper'}"
        )

        try:
            upload_result = upload_recording(
                audio_path=audio_path,
                transcript=transcript,
                title=title,
                recorded_date=recorded_date,
                codex_url=creds.codex_url,
                api_key=creds.api_key,
                extraction_method=extraction_method,
                on_progress=lambda sent, total: self.stage_progress.emit(
                    "upload", int(sent * 100 / max(total, 1))
                ),
            )
        except UploadError as e:
            enqueue(
                PendingUpload(
                    audio_path=str(audio_path),
                    transcript=transcript,
                    title=title,
                    recorded_date=recorded_date,
                    extraction_method=extraction_method,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            # Re-raise so the outer run() loop's except branch emits
            # stage_failed with a message explaining the user can retry
            # from the Dialectic menu later.
            raise RuntimeError(
                f"{e} — queued for retry "
                f"(Dialectic menu → 'Retry pending uploads')"
            ) from e

        self.result.upload_id = upload_result.upload_id
        self.result.codex_url = upload_result.codex_url
        return upload_result


class PipelineThread(QThread):
    """Runs a RecordingPipeline off the UI thread so a slow stage can't
    freeze the modal."""

    def __init__(self, pipeline: RecordingPipeline, parent: QObject | None = None):
        super().__init__(parent)
        self.pipeline = pipeline

    def run(self) -> None:  # noqa: D401 — QThread override
        self.pipeline.run()


__all__ = [
    "STAGE_ORDER",
    "RecordingArtifact",
    "PipelineResult",
    "RecordingPipeline",
    "PipelineThread",
]

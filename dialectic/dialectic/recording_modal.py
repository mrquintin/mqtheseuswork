"""Recording modal — capture a session, then hand it to ``RecordingPipeline``.

The modal is a pure UI over local audio capture plus a pipeline object.
No network calls, no transcription, no upload logic live here. Replacements
for the pipeline stages (prompts 07-10) drop in through the pipeline.

State machine::

    IDLE  →  RECORDING  ↔  PAUSED
                  │
                  ├─ Discard  →  DISCARDED (temp wav unlinked, modal closes)
                  │
                  └─ Stop & process  →  PROCESSING  →  DONE | ERROR
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
import wave
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Optional

import numpy as np

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .audio import AudioEngine
from .config import AudioConfig
from .recording_pipeline import (
    STAGE_ORDER,
    PipelineResult,
    PipelineThread,
    RecordingArtifact,
    RecordingPipeline,
)

log = logging.getLogger(__name__)


class RecordingState(Enum):
    IDLE = auto()
    RECORDING = auto()
    PAUSED = auto()
    PROCESSING = auto()
    DONE = auto()
    ERROR = auto()
    DISCARDED = auto()


@dataclass
class _StageRow:
    name: str
    label: QLabel
    status: QLabel
    progress: Optional[QProgressBar] = None


class RecordingModal(QDialog):
    """Drives the record → pause/resume → stop → process flow.

    ``audio_engine_factory`` exists so tests can substitute a fake engine
    that emits synthetic audio chunks without a real mic.
    """

    finished_ok = pyqtSignal(object)  # PipelineResult
    finished_discarded = pyqtSignal()
    finished_error = pyqtSignal(str)

    _STAGE_LABELS = {
        "trim": "Trimming silence",
        "transcribe": "Transcribing",
        "title": "Generating title",
        "upload": "Uploading to Codex",
    }

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        audio_config: Optional[AudioConfig] = None,
        audio_engine_factory=None,
    ):
        super().__init__(parent)
        self._audio_config = audio_config or AudioConfig()
        self._audio_engine_factory = audio_engine_factory or AudioEngine

        self._state: RecordingState = RecordingState.IDLE
        self._tmp_wav: Optional[Path] = None
        self._engine: Optional[AudioEngine] = None

        # Elapsed-time bookkeeping — the displayed clock freezes while
        # paused, but the total count excludes paused intervals.
        self._elapsed_accum: float = 0.0
        self._segment_start: float = 0.0

        self._last_rms: float = 0.0

        self._pipeline: Optional[RecordingPipeline] = None
        self._pipeline_thread: Optional[PipelineThread] = None
        self._stage_rows: dict[str, _StageRow] = {}
        self._final_result: Optional[PipelineResult] = None
        self._error_message: Optional[str] = None

        self.setWindowTitle("Recording session")
        self.setModal(True)
        self.setMinimumSize(480, 320)

        self._build_ui()
        self._install_shortcuts()

        # Start capturing as soon as the modal appears. The user's intent
        # in clicking Record is "start now"; a two-click experience would
        # be friction for no benefit.
        QTimer.singleShot(0, self._start_recording)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(14)

        self._timer_label = QLabel("00:00")
        self._timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._timer_label.setFont(QFont("SF Mono", 28, QFont.Weight.Bold))
        self._timer_label.setObjectName("recordingTimer")
        root.addWidget(self._timer_label)

        self._vu_bar = QProgressBar()
        self._vu_bar.setRange(0, 1000)
        self._vu_bar.setValue(0)
        self._vu_bar.setTextVisible(False)
        self._vu_bar.setFixedHeight(18)
        self._vu_bar.setStyleSheet(
            """
            QProgressBar {
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                background-color: #F2F2F2;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #27AE60, stop:0.7 #D4A017, stop:1 #C0392B
                );
                border-radius: 3px;
            }
            """
        )
        root.addWidget(self._vu_bar)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._pause_btn = QPushButton("Pause")
        self._pause_btn.clicked.connect(self._toggle_pause)
        btn_row.addWidget(self._pause_btn)

        self._discard_btn = QPushButton("Discard")
        self._discard_btn.clicked.connect(self._on_discard_clicked)
        btn_row.addWidget(self._discard_btn)

        btn_row.addStretch()

        self._stop_btn = QPushButton("Stop && process")
        self._stop_btn.setDefault(True)
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        btn_row.addWidget(self._stop_btn)

        root.addLayout(btn_row)

        self._footer = QLabel(
            "When you stop, Dialectic will trim silence, auto-title the "
            "session, and upload it to your Codex."
        )
        self._footer.setWordWrap(True)
        self._footer.setStyleSheet("color: #666666;")
        root.addWidget(self._footer)

        # Processing view — built hidden, shown on Stop & process.
        self._stages_box = QWidget()
        stages_layout = QVBoxLayout(self._stages_box)
        stages_layout.setContentsMargins(0, 6, 0, 0)
        stages_layout.setSpacing(4)
        for name in STAGE_ORDER:
            row = QHBoxLayout()
            label = QLabel(self._STAGE_LABELS[name])
            label.setMinimumWidth(180)
            status = QLabel("…")
            status.setStyleSheet("color: #888888;")
            row.addWidget(label)
            row.addWidget(status, stretch=1)
            progress: Optional[QProgressBar] = None
            if name == "upload":
                # Only the upload stage reports live progress today —
                # the other stages are fast enough that a spinner-style
                # "running…" status is enough. The bar is hidden until
                # the first percent update arrives.
                progress = QProgressBar()
                progress.setRange(0, 100)
                progress.setValue(0)
                progress.setFixedHeight(10)
                progress.setTextVisible(False)
                progress.setVisible(False)
                row.addWidget(progress, stretch=1)
            holder = QWidget()
            holder.setLayout(row)
            stages_layout.addWidget(holder)
            self._stage_rows[name] = _StageRow(
                name=name, label=label, status=status, progress=progress
            )
        root.addWidget(self._stages_box)
        self._stages_box.setVisible(False)

        self._dismiss_btn = QPushButton("Dismiss")
        self._dismiss_btn.clicked.connect(self._close_after_processing)
        self._dismiss_btn.setVisible(False)
        root.addWidget(self._dismiss_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(200)
        self._clock_timer.timeout.connect(self._update_timer)

        self._vu_timer = QTimer(self)
        self._vu_timer.setInterval(50)  # 20 Hz
        self._vu_timer.timeout.connect(self._update_vu)

    def _install_shortcuts(self) -> None:
        # Space → pause/resume. Use QShortcut so focus on buttons doesn't
        # eat the key; Enter activates the default button anyway.
        self._space_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._space_shortcut.activated.connect(self._toggle_pause)
        self._enter_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        self._enter_shortcut.activated.connect(self._on_stop_clicked)
        self._enter_shortcut2 = QShortcut(QKeySequence(Qt.Key.Key_Enter), self)
        self._enter_shortcut2.activated.connect(self._on_stop_clicked)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def state(self) -> RecordingState:
        return self._state

    def _set_state(self, new_state: RecordingState) -> None:
        self._state = new_state

    # ------------------------------------------------------------------
    # Recording lifecycle
    # ------------------------------------------------------------------

    def _start_recording(self) -> None:
        if self._state is not RecordingState.IDLE:
            return
        fd, tmp_path = tempfile.mkstemp(prefix="dialectic_rec_", suffix=".wav")
        os.close(fd)
        self._tmp_wav = Path(tmp_path)

        self._engine = self._audio_engine_factory(
            config=self._audio_config,
            on_audio_chunk=self._on_audio_chunk,
            save_path=self._tmp_wav,
        )
        try:
            self._engine.start()
        except Exception as exc:
            log.exception("RecordingModal: AudioEngine.start failed")
            QMessageBox.critical(self, "Microphone error", str(exc))
            self._cleanup_tmp()
            self._set_state(RecordingState.ERROR)
            self._error_message = str(exc)
            self.reject()
            return

        self._segment_start = time.monotonic()
        self._elapsed_accum = 0.0
        self._set_state(RecordingState.RECORDING)
        self._clock_timer.start()
        self._vu_timer.start()

    def _on_audio_chunk(self, audio: np.ndarray, _timestamp: float) -> None:
        # Runs on the sounddevice callback thread; don't touch widgets.
        if audio.size == 0:
            return
        x = audio.astype(np.float32)
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        if peak > 1.5:  # likely int16 raw
            x = x / 32768.0
        rms = float(np.sqrt(np.mean(x * x))) if x.size else 0.0
        # Soft clip to 0-1, with a gentle ceiling so normal speech is mid-range.
        self._last_rms = min(1.0, rms * 6.0)

    def _toggle_pause(self) -> None:
        if self._state is RecordingState.RECORDING:
            self._pause()
        elif self._state is RecordingState.PAUSED:
            self._resume()

    def _pause(self) -> None:
        if self._engine is None:
            return
        # Freeze the clock; don't tear down the stream — sounddevice input
        # stays open, but the engine's on_audio_chunk keeps feeding RMS.
        # For the wav file, we rely on AudioEngine.stop() at end; "pause"
        # here is a UI-level hold that halts timer accumulation. The
        # actual wav continues silence-like data while paused — trim
        # (prompt 08) will clean that up.
        self._elapsed_accum += time.monotonic() - self._segment_start
        self._set_state(RecordingState.PAUSED)
        self._pause_btn.setText("Resume")

    def _resume(self) -> None:
        self._segment_start = time.monotonic()
        self._set_state(RecordingState.RECORDING)
        self._pause_btn.setText("Pause")

    def _current_elapsed(self) -> float:
        if self._state is RecordingState.RECORDING:
            return self._elapsed_accum + (time.monotonic() - self._segment_start)
        return self._elapsed_accum

    def _update_timer(self) -> None:
        elapsed = int(self._current_elapsed())
        self._timer_label.setText(f"{elapsed // 60:02d}:{elapsed % 60:02d}")

    def _update_vu(self) -> None:
        if self._state is RecordingState.PAUSED:
            target = 0.0
        else:
            target = self._last_rms
        self._vu_bar.setValue(int(max(0.0, min(1.0, target)) * 1000))

    # ------------------------------------------------------------------
    # Stop / discard
    # ------------------------------------------------------------------

    def _on_stop_clicked(self) -> None:
        if self._state not in (RecordingState.RECORDING, RecordingState.PAUSED):
            return
        self._finish_capture_and_process()

    def _on_discard_clicked(self) -> None:
        if self._state not in (RecordingState.RECORDING, RecordingState.PAUSED):
            return
        reply = QMessageBox.question(
            self,
            "Discard recording?",
            "Discard this recording? It cannot be recovered.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._discard()

    def keyPressEvent(self, event) -> None:  # noqa: D401 — Qt override
        if event.key() == Qt.Key.Key_Escape:
            self._on_discard_clicked()
            return
        super().keyPressEvent(event)

    def _discard(self) -> None:
        self._clock_timer.stop()
        self._vu_timer.stop()
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                log.exception("RecordingModal: engine.stop during discard failed")
            self._engine = None
        self._cleanup_tmp()
        self._set_state(RecordingState.DISCARDED)
        self.finished_discarded.emit()
        self.reject()

    def _cleanup_tmp(self) -> None:
        if self._tmp_wav is not None and self._tmp_wav.exists():
            try:
                os.unlink(self._tmp_wav)
            except OSError:
                log.warning("RecordingModal: failed to unlink %s", self._tmp_wav)
        self._tmp_wav = None

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _finish_capture_and_process(self) -> None:
        if self._state is RecordingState.RECORDING:
            self._elapsed_accum += time.monotonic() - self._segment_start
        self._clock_timer.stop()
        self._vu_timer.stop()

        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                log.exception("RecordingModal: engine.stop failed")
            self._engine = None

        assert self._tmp_wav is not None
        duration = self._elapsed_accum
        # If the wav file is missing or empty, surface an error rather
        # than feed the pipeline a bad path.
        if not self._tmp_wav.exists() or self._tmp_wav.stat().st_size == 0:
            self._enter_processing_view()
            self._show_error("no audio was captured")
            return

        artifact = RecordingArtifact(
            audio_path=self._tmp_wav,
            duration_seconds=duration,
            sample_rate=self._audio_config.sample_rate,
            channels=self._audio_config.channels,
        )
        self._set_state(RecordingState.PROCESSING)
        self._enter_processing_view()

        self._pipeline = RecordingPipeline(artifact)
        self._pipeline.stage_started.connect(self._on_stage_started)
        self._pipeline.stage_succeeded.connect(self._on_stage_succeeded)
        self._pipeline.stage_failed.connect(self._on_stage_failed)
        self._pipeline.stage_progress.connect(self._on_stage_progress)
        self._pipeline.all_done.connect(self._on_pipeline_done)

        self._pipeline_thread = PipelineThread(self._pipeline)
        self._pipeline_thread.start()

    def _enter_processing_view(self) -> None:
        self._pause_btn.setEnabled(False)
        self._discard_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
        self._footer.setVisible(False)
        self._stages_box.setVisible(True)
        self._dismiss_btn.setVisible(True)
        self._dismiss_btn.setEnabled(False)
        for row in self._stage_rows.values():
            row.status.setText("…")
            row.status.setStyleSheet("color: #888888;")

    def _on_stage_started(self, name: str) -> None:
        row = self._stage_rows.get(name)
        if row is None:
            return
        row.status.setText("running…")
        row.status.setStyleSheet("color: #2980B9;")

    def _on_stage_succeeded(self, name: str, _value: object) -> None:
        row = self._stage_rows.get(name)
        if row is None:
            return
        row.status.setText("done")
        row.status.setStyleSheet("color: #27AE60;")
        if row.progress is not None:
            row.progress.setValue(100)
            row.progress.setVisible(False)

    def _on_stage_progress(self, name: str, percent: int) -> None:
        row = self._stage_rows.get(name)
        if row is None or row.progress is None:
            return
        if not row.progress.isVisible():
            row.progress.setVisible(True)
        row.progress.setValue(max(0, min(100, int(percent))))
        row.status.setText(f"{int(percent)}%")
        row.status.setStyleSheet("color: #2980B9;")

    def _on_stage_failed(self, name: str, message: str) -> None:
        row = self._stage_rows.get(name)
        if row is not None:
            row.status.setText(f"error: {message}")
            row.status.setStyleSheet("color: #C0392B;")
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        self._error_message = message
        self._set_state(RecordingState.ERROR)
        self._dismiss_btn.setEnabled(True)
        self._dismiss_btn.setText("Dismiss")

    def _on_pipeline_done(self, result: PipelineResult) -> None:
        self._final_result = result
        if self._state is RecordingState.ERROR:
            return
        self._set_state(RecordingState.DONE)
        self._dismiss_btn.setEnabled(True)
        self._dismiss_btn.setText("Close")
        self.finished_ok.emit(result)

    def _close_after_processing(self) -> None:
        if self._pipeline_thread is not None:
            self._pipeline_thread.wait(2000)
            self._pipeline_thread = None
        if self._state is RecordingState.ERROR:
            self.finished_error.emit(self._error_message or "unknown error")
            self.reject()
        else:
            self.accept()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: D401 — Qt override
        if self._state in (RecordingState.RECORDING, RecordingState.PAUSED):
            # Treat window-close-button as Discard (but ask first).
            reply = QMessageBox.question(
                self,
                "Discard recording?",
                "Closing now will discard the in-progress recording. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._discard()
        if self._pipeline_thread is not None:
            self._pipeline_thread.wait(2000)
            self._pipeline_thread = None
        super().closeEvent(event)


__all__ = ["RecordingModal", "RecordingState"]

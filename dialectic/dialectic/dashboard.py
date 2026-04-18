"""Dialectic Dashboard — PyQt6 live-analysis interface.

Layout:
    ┌──────────────────────────────────────────────────┐
    │  DIALECTIC                          [Settings]   │
    │  ─────────────────────────────────────────────── │
    │                                                  │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
    │  │ TOPICS   │  │  [REC]   │  │ QUESTIONS │       │
    │  │          │  │  00:00   │  │           │       │
    │  └──────────┘  └──────────┘  └──────────┘       │
    │                                                  │
    │  ┌────────────── TRANSCRIPT ──────────────────┐  │
    │  │ [Speaker 1] Lorem ipsum dolor sit amet...  │  │
    │  │ [Speaker 2] Consectetur adipiscing elit... │  │
    │  │ ...                                        │  │
    │  └────────────────────────────────────────────┘  │
    │                                                  │
    │  ┌──── CONTRADICTIONS ────┐ ┌──── OPEN LOOPS ──┐│
    │  │                        │ │                   ││
    │  └────────────────────────┘ └───────────────────┘│
    └──────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import datetime
import math
import queue
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import pyqtgraph as pg
    import qasync
except ImportError:  # pragma: no cover
    pg = None  # type: ignore[misc, assignment]
    qasync = None  # type: ignore[misc, assignment]
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QFrame,
    QSizePolicy,
    QGraphicsDropShadowEffect,
    QPlainTextEdit,
    QToolButton,
)

from .config import DialecticConfig, UIConfig
from .audio import AudioEngine, VADRingCapture, list_audio_devices
from .transcriber import (
    SegmentQueueTranscriber,
    TranscriptionEvent,
    WhisperTranscriber,
    TranscriptSegment,
)
from .analyzer import (
    Contradiction,
    ContradictionAlert,
    DialecticSessionAnalyzer,
    LiveAnalyzer,
    OpenLoop,
    SessionEvent,
    SessionEventKind,
    SuggestedQuestion,
    TopicState,
)
from .interlocutor import InterlocutorController, InterlocutorMode
from .tts_sidecar import speak
from .cloud_uploader import (
    is_configured as cloud_is_configured,
    upload_session_async,
)
from .updater import check_for_updates


# ======================================================================
# Signal bridge — thread-safe Qt signals from background threads
# ======================================================================

class AnalysisBridge(QObject):
    """Bridges background-thread callbacks to Qt's signal/slot system."""
    segment_received = pyqtSignal(object)
    contradiction_detected = pyqtSignal(object)
    topic_updated = pyqtSignal(object)
    open_loop_detected = pyqtSignal(object)
    question_generated = pyqtSignal(object)
    interlocutor_suggested = pyqtSignal(object)


# ======================================================================
# Custom Widgets
# ======================================================================

class RecordButton(QPushButton):
    """Large circular record/stop button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recording = False
        self.setFixedSize(80, 80)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Start recording")
        self._update_style()

    @property
    def recording(self) -> bool:
        return self._recording

    @recording.setter
    def recording(self, value: bool):
        self._recording = value
        self.setToolTip("Stop recording" if value else "Start recording")
        self._update_style()

    def _update_style(self):
        if self._recording:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #C0392B;
                    border: 3px solid #922B21;
                    border-radius: 40px;
                    color: white;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #E74C3C; }
            """)
            self.setText("STOP")
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #2E4057;
                    border: 3px solid #1A2636;
                    border-radius: 40px;
                    color: white;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #3D5474; }
            """)
            self.setText("REC")


class FeedPanel(QFrame):
    """A scrollable panel for one analysis feed."""

    def __init__(self, title: str, accent_color: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(f"""
            FeedPanel {{
                background-color: #FFFFFF;
                border: 1px solid #E0E0E0;
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Header
        header = QLabel(title)
        header.setFont(QFont("SF Pro Display", 11, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {accent_color}; border: none; background: transparent;")
        layout.addWidget(header)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {accent_color}; max-height: 2px; border: none;")
        layout.addWidget(sep)

        # Scrollable content area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background: transparent; border: none;")

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(6)
        self._content_layout.addStretch()

        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 30))
        self.setGraphicsEffect(shadow)

    def add_item(self, widget: QWidget) -> None:
        """Insert a widget above the stretch at the bottom."""
        count = self._content_layout.count()
        self._content_layout.insertWidget(count - 1, widget)
        # Auto-scroll to bottom
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def clear_items(self) -> None:
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


def make_card(text: str, subtext: str = "", color: str = "#333") -> QFrame:
    """Create a small card widget for a feed item."""
    card = QFrame()
    card.setStyleSheet(f"""
        QFrame {{
            background-color: #F7F8FA;
            border-radius: 6px;
            border: 1px solid #ECECEC;
            padding: 6px;
        }}
    """)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(2)

    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setFont(QFont("SF Pro Text", 10))
    lbl.setStyleSheet(f"color: {color}; border: none; background: transparent;")
    layout.addWidget(lbl)

    if subtext:
        sub = QLabel(subtext)
        sub.setWordWrap(True)
        sub.setFont(QFont("SF Pro Text", 9))
        sub.setStyleSheet("color: #8B8B9E; border: none; background: transparent;")
        layout.addWidget(sub)

    return card


# ======================================================================
# Interlocutor overlay (SP09) — bottom-right, dismissible
# ======================================================================


class InterventionOverlay(QFrame):
    """Four-line observational prompt; does not claim beliefs."""

    def __init__(self, ui: UIConfig, parent: QWidget):
        super().__init__(parent)
        self._ui = ui
        self.setObjectName("interlocutorOverlay")
        self.setFixedSize(400, 128)
        self.setStyleSheet(
            f"""
            QFrame#interlocutorOverlay {{
                background-color: {ui.panel_bg};
                border: 2px solid {ui.accent_color};
                border-radius: 10px;
            }}
            """
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        self._text = QLabel("")
        self._text.setWordWrap(True)
        self._text.setFont(QFont("SF Pro Text", 10))
        self._text.setStyleSheet(f"color: {ui.text_color};")
        lay.addWidget(self._text)

        row = QHBoxLayout()
        ack = QPushButton("Ack / dismiss")
        ack.setToolTip("Mark dismissed and hide overlay")
        ack.clicked.connect(self._ack_clicked)
        row.addWidget(ack)
        row.addStretch()
        self._on_ack = None
        lay.addLayout(row)

    def set_ack_handler(self, fn) -> None:
        self._on_ack = fn

    def _ack_clicked(self) -> None:
        if self._on_ack:
            self._on_ack()
        self.hide()

    def set_lines(self, lines: tuple[str, str, str, str]) -> None:
        self._text.setText("\n".join(lines))


# ======================================================================
# Main Dashboard Window
# ======================================================================

class DialecticDashboard(QMainWindow):

    def __init__(self, config: DialecticConfig | None = None):
        super().__init__()
        self.cfg = config or DialecticConfig()
        self._bridge = AnalysisBridge()

        # Engines (wired up in _init_engines)
        self._audio: AudioEngine | None = None
        self._transcriber: WhisperTranscriber | None = None
        self._analyzer: LiveAnalyzer | None = None

        self._interlocutor: InterlocutorController | None = None
        self._session_started_id: str = ""
        self._session_writer = None  # SessionJSONLWriter | None (lazy import)
        self._audible_tts = False
        self._pending_intervention_id: str | None = None

        self._init_ui()
        self._init_engines()
        self._connect_signals()

        # Timer for elapsed time display
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_timer)
        self._timer.setInterval(200)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self):
        ui = self.cfg.ui
        self.setWindowTitle(ui.window_title)
        self.setMinimumSize(ui.window_width, ui.window_height)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        central.setStyleSheet(f"background-color: {ui.bg_color};")

        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # ── Header ──
        header_row = QHBoxLayout()
        title = QLabel("DIALECTIC")
        title.setFont(QFont("SF Pro Display", 20, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {ui.accent_color};")
        header_row.addWidget(title)
        header_row.addStretch()

        subtitle = QLabel("Live Epistemological Analysis")
        subtitle.setFont(QFont("SF Pro Text", 11))
        subtitle.setStyleSheet(f"color: {ui.muted_color};")
        header_row.addWidget(subtitle)
        root.addLayout(header_row)

        # ── Top row: Topics | Record | Questions ──
        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        # Topics panel
        self._topics_panel = FeedPanel("TOPIC TRACKER", ui.blue_accent)
        self._topics_panel.setMinimumHeight(180)
        top_row.addWidget(self._topics_panel, stretch=1)

        # Center: Record button + timer
        center_col = QVBoxLayout()
        center_col.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._rec_btn = RecordButton()
        self._rec_btn.clicked.connect(self._toggle_recording)
        center_col.addWidget(self._rec_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._timer_label = QLabel("00:00")
        self._timer_label.setFont(QFont("SF Mono", 16, QFont.Weight.Bold))
        self._timer_label.setStyleSheet(f"color: {ui.accent_color};")
        self._timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_col.addWidget(self._timer_label)

        # Status label
        self._status_label = QLabel("Ready")
        self._status_label.setFont(QFont("SF Pro Text", 10))
        self._status_label.setStyleSheet(f"color: {ui.muted_color};")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_col.addWidget(self._status_label)

        top_row.addLayout(center_col)

        # Questions panel
        self._questions_panel = FeedPanel("SUGGESTED QUESTIONS", ui.green_accent)
        self._questions_panel.setMinimumHeight(180)
        top_row.addWidget(self._questions_panel, stretch=1)

        root.addLayout(top_row)

        # ── Transcript panel (wide, scrolling) ──
        self._transcript_panel = FeedPanel("LIVE TRANSCRIPT", ui.accent_color)
        self._transcript_panel.setMinimumHeight(200)
        self._transcript_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        root.addWidget(self._transcript_panel, stretch=2)

        # ── Bottom row: Contradictions | Open Loops ──
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(16)

        self._contradictions_panel = FeedPanel("CONTRADICTIONS", ui.red_accent)
        self._contradictions_panel.setMinimumHeight(160)
        bottom_row.addWidget(self._contradictions_panel, stretch=1)

        self._loops_panel = FeedPanel("OPEN LOOPS", ui.amber_accent)
        self._loops_panel.setMinimumHeight(160)
        bottom_row.addWidget(self._loops_panel, stretch=1)

        root.addLayout(bottom_row)

        ctrl = QHBoxLayout()
        self._stand_down_btn = QPushButton("Theseus: stand down")
        self._stand_down_btn.setToolTip("Immediately suspend interlocutor interventions for this session")
        self._stand_down_btn.setEnabled(False)
        self._stand_down_btn.clicked.connect(self._on_stand_down_clicked)
        ctrl.addWidget(self._stand_down_btn)
        ctrl.addStretch()
        root.addLayout(ctrl)

        self._central_panel = central
        self._intervention_overlay = InterventionOverlay(ui, central)
        self._intervention_overlay.set_ack_handler(self._dismiss_intervention_overlay)
        self._intervention_overlay.raise_()
        self._intervention_overlay.hide()

    # ------------------------------------------------------------------
    # Engine wiring
    # ------------------------------------------------------------------

    def _init_engines(self):
        # Transcriber
        self._transcriber = WhisperTranscriber(
            config=self.cfg.transcription,
            on_segment=self._bridge.segment_received.emit,
        )

        # Analyzer
        self._analyzer = LiveAnalyzer(
            config=self.cfg.analysis,
            on_contradiction=self._bridge.contradiction_detected.emit,
            on_topic_update=self._bridge.topic_updated.emit,
            on_open_loop=self._bridge.open_loop_detected.emit,
            on_question=self._bridge.question_generated.emit,
        )

        # Audio (feeds transcriber)
        def on_audio_chunk(audio, timestamp):
            self._transcriber.feed_audio(audio, timestamp)

        self._audio = AudioEngine(
            config=self.cfg.audio,
            on_audio_chunk=on_audio_chunk,
        )

    def _connect_signals(self):
        self._bridge.segment_received.connect(self._on_segment)
        self._bridge.contradiction_detected.connect(self._on_contradiction)
        self._bridge.topic_updated.connect(self._on_topic)
        self._bridge.open_loop_detected.connect(self._on_loop)
        self._bridge.question_generated.connect(self._on_question)
        self._bridge.interlocutor_suggested.connect(self._on_interlocutor_suggestion)

    # ------------------------------------------------------------------
    # Recording control
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_intervention_overlay()

    def _position_intervention_overlay(self) -> None:
        if not getattr(self, "_intervention_overlay", None) or not getattr(self, "_central_panel", None):
            return
        margin = 18
        w = min(420, max(280, self._central_panel.width() // 3))
        h = self._intervention_overlay.height()
        x = self._central_panel.width() - w - margin
        y = self._central_panel.height() - h - margin
        self._intervention_overlay.move(max(8, x), max(8, y))

    def _toggle_recording(self):
        if self._audio and self._audio.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _run_interlocutor_consent_dialog(self) -> tuple[InterlocutorMode, bool, bool]:
        d = QDialog(self)
        d.setWindowTitle("Theseus interlocutor — session consent")
        lay = QVBoxLayout(d)
        form = QFormLayout()
        combo = QComboBox()
        self._interlocutor_modes = list(InterlocutorMode)
        for m in self._interlocutor_modes:
            combo.addItem(m.value.replace("_", " ").title())
        form.addRow("Mode", combo)
        opt = QCheckBox("All participants have explicitly opted in to Theseus interventions")
        form.addRow(opt)
        aud = QCheckBox("Allow audible output (TTS) in conversational / tutor modes")
        form.addRow(aud)
        tutor_ack = QCheckBox(
            "Tutor mode only: I acknowledge higher interruption frequency for deliberate practice."
        )
        form.addRow(tutor_ack)
        lay.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(d.accept)
        buttons.rejected.connect(d.reject)
        lay.addWidget(buttons)
        if d.exec() != QDialog.DialogCode.Accepted:
            return InterlocutorMode.SILENT, False, False
        mode = self._interlocutor_modes[combo.currentIndex()]
        if mode == InterlocutorMode.TUTOR and not tutor_ack.isChecked():
            QMessageBox.warning(
                self,
                "Tutor mode",
                "Tutor mode requires acknowledging the higher interruption rate.",
            )
            return InterlocutorMode.SILENT, False, False
        if mode != InterlocutorMode.SILENT and not opt.isChecked():
            QMessageBox.warning(
                self,
                "Consent required",
                "Active modes require explicit participant opt-in. Switching to silent.",
            )
            return InterlocutorMode.SILENT, False, False
        return mode, opt.isChecked(), aud.isChecked()

    def _start_recording(self):
        mode, opted_in, audible = self._run_interlocutor_consent_dialog()
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        wav_path = self.cfg.recordings_dir / f"session_{ts}.wav"

        self._audio._save_path = wav_path

        try:
            self._audio.start()
            self._transcriber.start()
            self._analyzer.start()

            self._session_started_id = f"session_{ts}"

            # Open a session JSONL so every finalized transcript segment can
            # be streamed to disk. Without this the legacy dashboard had no
            # persistent transcript at all, so cloud upload found nothing to
            # send and a crash mid-session meant the whole conversation
            # evaporated.
            from .session_writer import SessionJSONLWriter
            jsonl_path = (
                self.cfg.recordings_dir / f"{self._session_started_id}.jsonl"
            )
            # Touch the file immediately so cloud upload always has at least
            # an empty payload + header to send (good for audit trail).
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            jsonl_path.touch(exist_ok=True)
            self._session_writer = SessionJSONLWriter(jsonl_path)

            self._interlocutor = InterlocutorController(
                self.cfg.interlocutor,
                session_id=self._session_started_id,
                log_dir=self.cfg.recordings_dir,
                on_intervention=lambda c, rid: self._bridge.interlocutor_suggested.emit(
                    {"candidate": c, "id": rid}
                ),
            )
            self._interlocutor.set_mode(mode)
            self._interlocutor.set_participants_opt_in(
                opted_in or mode == InterlocutorMode.SILENT
            )
            self._audible_tts = bool(
                audible
                and mode
                in (InterlocutorMode.CONVERSATIONAL, InterlocutorMode.TUTOR)
            )

            self._rec_btn.recording = True
            self._status_label.setText("Recording...")
            self._status_label.setStyleSheet(f"color: {self.cfg.ui.red_accent};")
            self._timer.start()
            self._stand_down_btn.setEnabled(mode != InterlocutorMode.SILENT)
        except Exception as e:
            # Previously this silently stuffed the error into a small status
            # label and left the UI in a half-started state (button looks idle
            # but audio/transcriber/analyzer may be partially running). Now
            # we show a dialog, log the traceback, and roll back the engines.
            import traceback as _tb
            _tb.print_exc()
            try:
                if self._audio and self._audio.is_recording:
                    self._audio.stop()
                if self._transcriber:
                    self._transcriber.stop()
                if self._analyzer:
                    self._analyzer.stop()
            except Exception:
                pass
            self._rec_btn.recording = False
            self._timer.stop()
            self._status_label.setText("Error — see dialog")
            self._status_label.setStyleSheet(
                f"color: {self.cfg.ui.red_accent};"
            )
            QMessageBox.critical(
                self,
                "Couldn't start recording",
                f"{type(e).__name__}: {e}\n\n"
                "Check microphone permissions (System Settings → Privacy & "
                "Security → Microphone) and try again.",
            )

    def _stop_recording(self):
        sid = self._session_started_id
        if self._intervention_overlay:
            self._intervention_overlay.hide()
        if self._interlocutor:
            self._interlocutor.save_reflection_bundle()
        self._interlocutor = None
        self._pending_intervention_id = None
        self._stand_down_btn.setEnabled(False)

        wav_path = self._audio.stop()
        self._transcriber.stop()
        self._analyzer.stop()
        # Release the session writer reference; file is fully flushed via
        # per-line context managers on append so no explicit close needed.
        self._session_writer = None

        self._rec_btn.recording = False
        self._timer.stop()
        msg = f"Saved: {wav_path.name}" if wav_path else "Stopped"
        if sid:
            msg += f"  |  Transcript: {sid}.jsonl"
            msg += f"  |  Reflection: {sid}_reflection.json"

        # Optional cloud sync — silent no-op unless DIALECTIC_CLOUD_URL and
        # DIALECTIC_CLOUD_API_KEY are set in the environment.
        if sid and cloud_is_configured():
            upload_session_async(sid, self.cfg.recordings_dir)
            msg += "  |  Cloud upload started."

        self._status_label.setText(msg)
        self._status_label.setStyleSheet(f"color: {self.cfg.ui.muted_color};")

    def _on_stand_down_clicked(self) -> None:
        if self._interlocutor:
            self._interlocutor.force_stand_down()
        if self._intervention_overlay:
            self._intervention_overlay.hide()
        self._status_label.setText("Theseus interlocutor stood down for this session.")

    def _dismiss_intervention_overlay(self) -> None:
        if self._interlocutor and self._pending_intervention_id:
            self._interlocutor.apply_rating(
                self._pending_intervention_id, engagement="dismissed"
            )
        self._pending_intervention_id = None
        if self._intervention_overlay:
            self._intervention_overlay.hide()

    def _on_interlocutor_suggestion(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        cand = payload.get("candidate")
        rid = str(payload.get("id", ""))
        if rid and self._intervention_overlay and cand is not None:
            self._pending_intervention_id = rid
            self._intervention_overlay.set_lines(tuple(cand.overlay_lines))
            self._intervention_overlay.show()
            self._position_intervention_overlay()
            if self._audible_tts:
                # Bind `tts_text` and `max_seconds` into default args at
                # schedule time. A bare closure over `cand` would capture
                # the current attribute value lazily, so if a second
                # suggestion landed before the delay fired the TTS would
                # speak the *new* candidate's text, not the one that just
                # came in.
                tts_text = cand.tts_text
                tts_ms = int(self.cfg.interlocutor.min_pause_seconds_tts * 1000)
                tts_seconds = float(self.cfg.interlocutor.tts_max_seconds)
                QTimer.singleShot(
                    tts_ms,
                    lambda t=tts_text, s=tts_seconds: speak(t, max_seconds=s),
                )

    def _update_timer(self):
        if self._audio and self._audio.is_recording:
            secs = int(self._audio.elapsed_seconds)
            m, s = divmod(secs, 60)
            h, m = divmod(m, 60)
            if h > 0:
                self._timer_label.setText(f"{h}:{m:02d}:{s:02d}")
            else:
                self._timer_label.setText(f"{m:02d}:{s:02d}")

    # ------------------------------------------------------------------
    # Slot handlers (called on the Qt main thread via signals)
    # ------------------------------------------------------------------

    def _on_segment(self, segment: TranscriptSegment):
        """New transcript segment arrived."""
        speaker_color = self.cfg.ui.blue_accent if "1" in segment.speaker else self.cfg.ui.accent_color
        time_str = self._format_time(segment.start_time)

        card = make_card(
            f"[{segment.speaker}]  {segment.text}",
            subtext=time_str,
            color=self.cfg.ui.text_color,
        )
        self._transcript_panel.add_item(card)

        # Persist the raw finalized segment to the session JSONL so there is
        # always *something* to cloud-upload even if the analyzer never
        # extracts formal claims (short sessions, noisy audio, etc.).
        # Using the zero embedding sentinel keeps the schema identical to
        # claim-bearing lines; Noosphere treats it as a transcript entry.
        writer = getattr(self, "_session_writer", None)
        if writer is not None and getattr(segment, "is_final", True) and segment.text.strip():
            try:
                import numpy as _np
                writer.append_claim(
                    speaker=segment.speaker,
                    text=segment.text.strip(),
                    embedding=_np.zeros(384, dtype=_np.float32),
                    contradiction_pair_ids=[],
                    topic_cluster_id="",
                )
            except Exception as e:
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "DialecticDashboard: failed to write session JSONL line: %s", e
                )

        if self._interlocutor:
            self._interlocutor.feed_segment(segment)
        self._analyzer.feed_segment(segment)

    def _on_contradiction(self, c: Contradiction):
        """Contradiction detected."""
        card = make_card(
            f"\u26A0  \"{c.statement_a[:60]}...\" vs \"{c.statement_b[:60]}...\"",
            subtext=f"Confidence: {c.score:.0%}  |  {c.speaker_a} vs {c.speaker_b}",
            color=self.cfg.ui.red_accent,
        )
        self._contradictions_panel.add_item(card)
        if self._interlocutor:
            self._interlocutor.feed_contradiction(c)

    def _on_topic(self, t: TopicState):
        """Topic state updated."""
        if self._interlocutor:
            self._interlocutor.mark_topic_activity()
        status = "\u2705 On topic" if t.on_topic else "\u2192 Drifting"
        color = self.cfg.ui.green_accent if t.on_topic else self.cfg.ui.amber_accent

        card = make_card(
            f"{t.current_topic}",
            subtext=f"{status}  {t.drift_direction}".strip(),
            color=color,
        )
        self._topics_panel.add_item(card)

    def _on_loop(self, loop: OpenLoop):
        """Open loop detected or updated."""
        if loop.status == "abandoned":
            card = make_card(
                f"\u26A0 ABANDONED: {loop.description[:80]}...",
                subtext=f"Opened {self._format_time(loop.opened_at)}, last referenced {self._format_time(loop.last_referenced)}",
                color=self.cfg.ui.red_accent,
            )
        else:
            card = make_card(
                f"\u2753 {loop.description[:100]}",
                subtext=f"Opened {self._format_time(loop.opened_at)}",
                color=self.cfg.ui.amber_accent,
            )
        self._loops_panel.add_item(card)
        if self._interlocutor and loop.status == "open":
            self._interlocutor.feed_open_loop(loop)

    def _on_question(self, q: SuggestedQuestion):
        """New question suggested."""
        cat_icon = {
            "deepening": "\U0001F50D",
            "contradiction": "\u26A0",
            "open_loop": "\U0001F504",
            "pivot": "\u27A1",
        }.get(q.category, "\u2753")

        card = make_card(
            f"{cat_icon}  {q.text}",
            subtext=q.rationale,
            color=self.cfg.ui.green_accent,
        )
        self._questions_panel.add_item(card)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_time(seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"


# ======================================================================
# Three-pane live dashboard (qasync + ~1 Hz redraw)
# ======================================================================


class _GraphNode:
    __slots__ = ("cid", "x", "y", "vx", "vy", "text")

    def __init__(self, cid: str, text: str) -> None:
        self.cid = cid
        # Keep the first few words intact for on-graph labelling;
        # the `.text` property is both the hover tooltip AND the
        # visible node label rendered next to each scatter point.
        self.text = text[:64]
        self.x = (hash(cid) % 200) / 10.0 - 10.0
        self.y = (hash(cid[::-1]) % 200) / 10.0 - 10.0
        self.vx = 0.0
        self.vy = 0.0


class _CardList(QScrollArea):
    """Vertical scroll list of dismissible cards.

    Used by TENSIONS (contradictions) and PROMPTS (interlocutor
    suggestions) panels. When there are no cards the placeholder text
    is shown instead so the empty state tells the user what will
    appear.

    Each card is a QFrame with an `objectName` matching one of the
    styles in _DASHBOARD_QSS (`tensionCard` | `promptCard`) so the
    coloured left-border reflects the card's category.
    """

    def __init__(
        self,
        *,
        placeholder: str,
        card_style: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._card_style = card_style
        self._placeholder_text = placeholder
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._placeholder = QLabel(self._placeholder_text)
        self._placeholder.setWordWrap(True)
        self._placeholder.setStyleSheet(
            "color: #8a7352; font-size: 11px; font-style: italic; "
            "line-height: 1.45; padding: 6px 4px;"
        )
        self._layout.addWidget(self._placeholder)

        self.setWidget(self._content)

    def _ensure_placeholder_hidden(self) -> None:
        if self._placeholder.isVisible():
            self._placeholder.setVisible(False)

    def _ensure_placeholder_shown(self) -> None:
        # Called from `remove_card`: if the only remaining child is the
        # placeholder, re-show it.
        if self._layout.count() == 1 and not self._placeholder.isVisible():
            self._placeholder.setVisible(True)

    def add_card(
        self,
        *,
        headline: str,
        body: str,
        meta: str = "",
    ) -> QFrame:
        """Add a new card at the TOP of the list (most recent first).

        Returns the card widget so callers that want a dismiss button
        can wire it up.
        """
        self._ensure_placeholder_hidden()

        card = QFrame()
        card.setObjectName(self._card_style)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(2, 2, 2, 2)
        inner.setSpacing(3)

        hl = QLabel(headline)
        hl.setWordWrap(True)
        hl.setStyleSheet(
            "color: #e3c995; font-size: 12px; font-weight: 600; "
            "font-family: 'SF Pro Text', 'Helvetica Neue', sans-serif;"
        )
        inner.addWidget(hl)

        if body:
            bd = QLabel(body)
            bd.setWordWrap(True)
            bd.setStyleSheet(
                "color: #b8a082; font-size: 11px; "
                "font-family: 'SF Pro Text', 'Helvetica Neue', sans-serif; "
                "line-height: 1.45;"
            )
            inner.addWidget(bd)

        if meta:
            row = QHBoxLayout()
            row.setContentsMargins(0, 2, 0, 0)
            mt = QLabel(meta)
            mt.setStyleSheet(
                "color: #8a7352; font-size: 9px; "
                "font-family: 'IBM Plex Mono', monospace; "
                "letter-spacing: 0.12em; text-transform: uppercase;"
            )
            row.addWidget(mt, stretch=1)

            dismiss = QToolButton()
            dismiss.setText("×")
            dismiss.setToolTip("Dismiss")
            dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
            dismiss.setStyleSheet(
                "QToolButton { background: transparent; color: #8a7352; "
                "border: none; font-size: 16px; padding: 0 6px; }"
                "QToolButton:hover { color: #d4a017; }"
            )
            dismiss.clicked.connect(lambda _=None, c=card: self.remove_card(c))
            row.addWidget(dismiss)
            inner.addLayout(row)

        # insertWidget(0, ...) puts newest at the top.
        self._layout.insertWidget(0, card)
        return card

    def remove_card(self, card: QFrame) -> None:
        self._layout.removeWidget(card)
        card.deleteLater()
        QTimer.singleShot(0, self._ensure_placeholder_shown)


_DASHBOARD_QSS = """
QWidget#centralRoot {
    background-color: #0e0a06;
    color: #e3c995;
}
QWidget#centralRoot QLabel {
    color: #d4a017;
}
QLabel#titleLabel {
    color: #d4a017;
    font-size: 22px;
    font-weight: 600;
    letter-spacing: 6px;
}
QLabel#subtitleLabel {
    color: #a08868;
    font-size: 12px;
    font-style: italic;
}
QLabel#statusBadge {
    color: #7a9a6a;
    font-size: 11px;
    letter-spacing: 3px;
    padding: 4px 10px;
    border: 1px solid #3e2c13;
    border-radius: 4px;
    background-color: #15100a;
}
QLabel#paneHeader {
    color: #d4a017;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 3px;
    padding: 2px 0;
}
QLabel#paneSubheader {
    color: #8a7352;
    font-size: 10px;
    font-style: italic;
    padding: 0 0 4px 0;
}
QFrame#tensionCard {
    background-color: rgba(192, 57, 43, 0.10);
    border-left: 3px solid #c0392b;
    border-radius: 3px;
    padding: 6px 10px;
}
QFrame#promptCard {
    background-color: rgba(212, 160, 23, 0.10);
    border-left: 3px solid #d4a017;
    border-radius: 3px;
    padding: 6px 10px;
}
QLabel#footerLabel {
    color: #5a4218;
    font-size: 10px;
    letter-spacing: 1px;
}
QPlainTextEdit {
    background-color: #15100a;
    color: #e3c995;
    border: 1px solid #3e2c13;
    border-radius: 6px;
    font-family: "SF Mono", "Menlo", "Consolas", monospace;
    font-size: 12px;
    padding: 10px 12px;
    selection-background-color: #5a4218;
    selection-color: #f5e4c5;
}
QFrame#paneFrame {
    background-color: transparent;
    border: none;
}
QPushButton#recordBtn {
    background-color: #d4a017;
    color: #0e0a06;
    border: none;
    border-radius: 8px;
    padding: 14px 40px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 4px;
}
QPushButton#recordBtn:hover { background-color: #efb82a; }
QPushButton#recordBtn:disabled {
    background-color: #5a4218;
    color: #2a1e0c;
}
QPushButton#recordBtn[recording="true"] {
    background-color: #c0392b;
    color: #f5e4c5;
}
QPushButton#recordBtn[recording="true"]:hover {
    background-color: #e04a3b;
}
"""


class ThreePaneDialecticWindow(QMainWindow):
    """Transcript (left), claim graph (center), alerts (right).

    Redesigned for clarity — the window opens instantly, shows a
    beautiful dark-amber UI that matches the Theseus Codex aesthetic,
    runs a preflight diagnostic at startup (audio / torch /
    faster-whisper availability), and gives unmistakable feedback at
    every step: Idle → Initializing → Loading models → Listening →
    Stopped, with errors routed to the Alerts pane (never silent).

    Expensive constructors (VADRingCapture triggers a torch.hub
    Silero VAD load; SegmentQueueTranscriber's first transcribe
    triggers a faster-whisper download) are deferred until the user
    clicks Begin Session, and are run on a worker thread so the
    main event loop stays responsive.
    """

    def __init__(
        self,
        config: DialecticConfig,
        loop: asyncio.AbstractEventLoop,
        *,
        whisper_model: str = "base",
        whisper_device: str = "cpu",
    ) -> None:
        super().__init__()
        self.cfg = config
        self._loop = loop
        self._whisper_model_name = whisper_model
        self._whisper_device = whisper_device

        ui = config.ui
        self.setWindowTitle(ui.window_title + " — Live")
        self.setMinimumSize(1200, 760)

        # Heavy components are NOT created here. Constructing
        # VADRingCapture chains through SileroVADSegmenter, which
        # calls torch.hub.load() — that can block the main thread
        # for tens of seconds on first launch (or minutes on slow
        # networks). Deferring them keeps the window snappy and
        # lets us show a status indicator during init.
        self._segment_q: queue.Queue | None = None
        self._trans_q: asyncio.Queue | None = None
        self._session_q: asyncio.Queue | None = None
        self._cap: VADRingCapture | None = None
        self._transcriber: SegmentQueueTranscriber | None = None
        self._analyzer: DialecticSessionAnalyzer | None = None
        self._interlocutor: InterlocutorController | None = None
        self._session_id: str = ""
        self._nodes: dict[str, _GraphNode] = {}
        self._edges: list[tuple[str, str]] = []
        self._pending_partial: str = ""
        self._transcript_lines: list[str] = []
        self._tasks: list[asyncio.Task] = []
        self._recording = False
        self._initializing = False
        # Preflight results populated by ``_run_preflight`` and shown
        # in the Alerts pane; also used to grey out the Begin button
        # if a critical dependency is missing.
        self._preflight_ok = True

        self._build_ui()
        self._run_preflight()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralRoot")
        central.setStyleSheet(_DASHBOARD_QSS)
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(14)

        # ── Header: title + status badge ───────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("DIALECTIC")
        title.setObjectName("titleLabel")
        header.addWidget(title)
        header.addStretch()
        self._status_label = QLabel("● READY")
        self._status_label.setObjectName("statusBadge")
        header.addWidget(self._status_label)
        root.addLayout(header)

        subtitle = QLabel(
            "Live conversation analysis — transcript, claim graph, and "
            "contradiction alerts. Click BEGIN SESSION to start recording."
        )
        subtitle.setObjectName("subtitleLabel")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        # ── Centered Begin/End button ──────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 6, 0, 6)
        btn_row.addStretch()
        self._rec_btn = QPushButton("BEGIN SESSION")
        self._rec_btn.setObjectName("recordBtn")
        self._rec_btn.setProperty("recording", "false")
        self._rec_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rec_btn.setMinimumHeight(52)
        self._rec_btn.setMinimumWidth(260)
        self._rec_btn.clicked.connect(self._toggle)
        btn_row.addWidget(self._rec_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # ── Three-pane body ────────────────────────────────────────
        body = QHBoxLayout()
        body.setSpacing(14)
        body.setContentsMargins(0, 4, 0, 0)

        # Left: transcript
        self._transcript = QPlainTextEdit()
        self._transcript.setReadOnly(True)
        self._transcript.setPlainText(
            "Waiting for audio input…\n\n"
            "Once you click BEGIN SESSION, speech will appear here line\n"
            "by line. Partial hypotheses appear first and are refined as\n"
            "the transcription model converges on each utterance.\n\n"
            "Recordings are saved to\n"
            f"{self.cfg.recordings_dir}\n"
        )
        left_frame = self._wrap_pane("TRANSCRIPT", self._transcript)
        body.addWidget(left_frame, stretch=2)

        # Middle: claim graph
        self._plot = pg.PlotWidget()
        self._plot.setBackground("#15100a")
        self._plot.showGrid(x=True, y=True, alpha=0.15)
        # Amber-tinted axes to match the dashboard palette.
        for side in ("left", "bottom", "right", "top"):
            axis = self._plot.getAxis(side)
            try:
                axis.setPen(pg.mkPen("#3e2c13"))
                axis.setTextPen(pg.mkPen("#8a7352"))
            except Exception:
                pass
        self._scatter = pg.ScatterPlotItem(
            size=14,
            pen=pg.mkPen("#d4a017"),
            brush=pg.mkBrush(212, 160, 23, 200),
        )
        self._plot.addItem(self._scatter)
        self._line_plot = pg.PlotDataItem(pen=pg.mkPen("#c0392b", width=2))
        self._plot.addItem(self._line_plot)
        # Per-node TextItems rendered next to each scatter point. We
        # cache one TextItem per claim id (created lazily on first draw,
        # repositioned on every tick) — much cheaper than recreating
        # 100 text objects every frame, and still correct when claims
        # move under the force-directed physics.
        self._node_labels: dict[str, "pg.TextItem"] = {}
        center_frame = self._wrap_pane_with_sub(
            "CLAIM GRAPH",
            "Main ideas captured in real time · tensions shown as red edges",
            self._plot,
        )
        body.addWidget(center_frame, stretch=3)

        # Right column: three stacked panes so the three value-bearing
        # events of the session each get dedicated visual real estate
        # instead of being interleaved in one scrolling log:
        #
        #   TENSIONS  — contradictions between claims, card-styled with
        #                a red left-border. This is the single most
        #                important feedback the analyzer produces.
        #   PROMPTS   — follow-up questions the interlocutor suggests
        #                (conversationally: "would you like to specify
        #                resolution criteria for that prediction?").
        #                Amber-left-bordered cards. Each card has its
        #                own dismiss button so you acknowledge as you go.
        #   SYSTEM LOG — diagnostics + preflight + session lifecycle.
        #                The old "Alerts" stream lives here, out of the
        #                way of the analytic output.
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(12)

        # ── TENSIONS ───────────────────────────────────────────────
        self._tensions_list = _CardList(
            placeholder=(
                "No tensions yet. When the analyzer spots two claims "
                "that contradict each other, they appear here with the "
                "severity score and the two statements."
            ),
            card_style="tensionCard",
        )
        right_col.addWidget(
            self._wrap_pane_with_sub(
                "TENSIONS",
                "Contradictions detected in real time",
                self._tensions_list,
            ),
            stretch=3,
        )

        # ── PROMPTS ────────────────────────────────────────────────
        self._prompts_list = _CardList(
            placeholder=(
                "No follow-up questions yet. The interlocutor proposes "
                "one when a high-confidence contradiction lands, when a "
                "prediction-shaped statement needs resolution criteria, "
                "or when an open loop stays unresolved."
            ),
            card_style="promptCard",
        )
        right_col.addWidget(
            self._wrap_pane_with_sub(
                "PROMPTS",
                "Follow-up questions the interlocutor suggests",
                self._prompts_list,
            ),
            stretch=3,
        )

        # ── SYSTEM LOG (collapsed header) ──────────────────────────
        self._alerts = QPlainTextEdit()
        self._alerts.setReadOnly(True)
        right_col.addWidget(
            self._wrap_pane_with_sub(
                "SYSTEM LOG",
                "Preflight checks + session lifecycle",
                self._alerts,
            ),
            stretch=2,
        )

        right_frame = QFrame()
        right_frame.setObjectName("paneFrame")
        right_frame.setLayout(right_col)
        body.addWidget(right_frame, stretch=3)

        root.addLayout(body, stretch=1)

        # ── Footer ─────────────────────────────────────────────────
        footer = QLabel(
            f"Dialectic · recordings → {self.cfg.recordings_dir} · "
            "⌘Q to quit"
        )
        footer.setObjectName("footerLabel")
        footer.setWordWrap(True)
        root.addWidget(footer)

        # 1 Hz redraw timer (physics + partial transcript flush).
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick_ui)

    def _wrap_pane(self, header_text: str, widget: QWidget) -> QFrame:
        frame = QFrame()
        frame.setObjectName("paneFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        header = QLabel(header_text)
        header.setObjectName("paneHeader")
        layout.addWidget(header)
        layout.addWidget(widget, stretch=1)
        return frame

    def _wrap_pane_with_sub(
        self,
        header_text: str,
        subheader_text: str,
        widget: QWidget,
    ) -> QFrame:
        """Pane wrapper with a one-line italic subheader that explains
        what the pane is for. Helps the user recognise "oh, that's where
        contradictions appear" without having to start a session first."""
        frame = QFrame()
        frame.setObjectName("paneFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        header = QLabel(header_text)
        header.setObjectName("paneHeader")
        layout.addWidget(header)
        sub = QLabel(subheader_text)
        sub.setObjectName("paneSubheader")
        sub.setWordWrap(True)
        layout.addWidget(sub)
        layout.addWidget(widget, stretch=1)
        return frame

    # ------------------------------------------------------------------
    # Status + alerts helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str, color: str = "#7a9a6a") -> None:
        """Update the top-right status badge.

        Colors by convention:
          * ``#7a9a6a`` (olive green) — Ready / Listening
          * ``#d4a017`` (amber)       — Initializing / Processing
          * ``#c0392b`` (red)         — Error / Stopped with error
          * ``#8a7352`` (muted)       — Stopped cleanly
        """
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color: {color}; font-size: 11px; letter-spacing: 3px; "
            f"padding: 4px 10px; border: 1px solid #3e2c13; "
            f"border-radius: 4px; background-color: #15100a;"
        )

    def _log_alert(self, message: str, *, level: str = "info") -> None:
        """Append a timestamped line to the Alerts pane.

        Levels: ``info`` (default amber-dim), ``ok`` (olive),
        ``warn`` (amber), ``error`` (red). The QPlainTextEdit uses
        one style for the whole widget, so we mark the severity
        inline with a leading sigil instead.
        """
        sigil = {"info": "·", "ok": "✓", "warn": "⚠", "error": "✕"}.get(
            level, "·"
        )
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._alerts.appendPlainText(f"{ts}  {sigil}  {message}")

    # ------------------------------------------------------------------
    # Preflight diagnostics
    # ------------------------------------------------------------------

    def _run_preflight(self) -> None:
        """Check critical dependencies; write results to the Alerts pane.

        Runs synchronously on startup but every individual check is
        cheap (no model loads). If a *critical* dep is missing we
        disable the Begin Session button and surface instructions.
        """
        self._alerts.setPlainText("")
        self._log_alert("Dialectic startup — running preflight checks")

        critical_ok = True

        # sounddevice + at least one input device
        try:
            import sounddevice as sd  # noqa: F401
            devs = [
                d for d in sd.query_devices()
                if d.get("max_input_channels", 0) > 0
            ]
            if devs:
                default_name = ""
                try:
                    default_idx = sd.default.device[0]
                    if 0 <= default_idx < len(sd.query_devices()):
                        default_name = str(
                            sd.query_devices(default_idx)["name"]
                        )
                except Exception:
                    pass
                self._log_alert(
                    f"audio    · {len(devs)} input device(s) detected"
                    + (f" · default: {default_name}" if default_name else ""),
                    level="ok",
                )
            else:
                critical_ok = False
                self._log_alert(
                    "audio    · no input devices found. On macOS, grant "
                    "Microphone permission in System Settings → Privacy "
                    "& Security → Microphone, then restart Dialectic.",
                    level="error",
                )
        except ImportError as e:
            critical_ok = False
            self._log_alert(
                f"audio    · sounddevice not installed ({e}). "
                "Install with: pip install sounddevice",
                level="error",
            )
        except Exception as e:
            critical_ok = False
            self._log_alert(
                f"audio    · device query failed: {type(e).__name__}: {e}",
                level="error",
            )

        # faster-whisper
        try:
            import faster_whisper  # noqa: F401
            self._log_alert(
                f"whisper  · faster-whisper available "
                f"(model={self._whisper_model_name} device={self._whisper_device})",
                level="ok",
            )
        except ImportError:
            critical_ok = False
            self._log_alert(
                "whisper  · faster-whisper not installed. "
                "Install with: pip install faster-whisper",
                level="error",
            )

        # torch (needed for Silero VAD; energy fallback works without it
        # but quality drops sharply, so warn loudly rather than fail)
        try:
            import torch
            self._log_alert(
                f"vad      · torch {torch.__version__} available for Silero VAD",
                level="ok",
            )
        except ImportError:
            self._log_alert(
                "vad      · torch not installed — will fall back to "
                "RMS-energy segmentation (lower quality). Install torch "
                "for Silero VAD if speech segmentation seems off.",
                level="warn",
            )

        # Cloud upload status — surfaces both the configured/not state
        # and, when configured, who we're signed in as. The credentials
        # come from the login dialog at startup (stored in the OS
        # application-support dir), so the founder always knows which
        # account the session will be uploaded under.
        if cloud_is_configured():
            try:
                from . import credentials as _c
                active = _c.active()
            except Exception:
                active = None
            if active and active.founder_email:
                self._log_alert(
                    f"cloud    · signed in as {active.founder_name or active.founder_email} "
                    f"· {active.codex_url} — sessions auto-upload on stop",
                    level="ok",
                )
            else:
                self._log_alert(
                    "cloud    · DIALECTIC_CLOUD_URL + _API_KEY set — "
                    "sessions will auto-upload to the Codex on stop",
                    level="ok",
                )
        else:
            self._log_alert(
                "cloud    · not signed in. Re-launch Dialectic to log "
                "in and enable cloud upload.",
                level="warn",
            )

        self._preflight_ok = critical_ok
        if critical_ok:
            self._set_status("● READY", color="#7a9a6a")
            self._log_alert(
                "preflight complete — click BEGIN SESSION to start", level="ok"
            )
        else:
            self._set_status("● NOT READY", color="#c0392b")
            self._rec_btn.setEnabled(False)
            self._rec_btn.setToolTip(
                "A critical dependency is missing. See the Alerts pane "
                "for the fix."
            )
            self._log_alert(
                "preflight FAILED — fix the issues above and restart",
                level="error",
            )

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def _toggle(self) -> None:
        if self._initializing:
            return  # already in the middle of a start; ignore clicks
        if not self._recording:
            self._start_session()
        else:
            self._stop_session()

    def _start_session(self) -> None:
        """Kick off a session; heavy construction runs off the UI thread.

        The order of events the user sees:
          1. Click BEGIN SESSION → button disables, status → INITIALIZING
          2. Worker thread instantiates VADRingCapture (triggers Silero VAD
             download on first run) and SegmentQueueTranscriber (triggers
             faster-whisper model download on first use).
          3. Back on the main thread, we start the audio stream, launch
             the pump tasks, and flip status → LISTENING.

        If any step fails, the error goes into the Alerts pane with a
        clear message, status flips to ERROR, and the button reverts
        so the user can retry.
        """
        if not self._preflight_ok:
            self._log_alert(
                "Cannot start — preflight failed. See earlier errors.",
                level="error",
            )
            return

        self._initializing = True
        self._rec_btn.setEnabled(False)
        self._rec_btn.setText("INITIALIZING…")
        self._set_status("● INITIALIZING", color="#d4a017")

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_id = f"session_{ts}"
        self._log_alert(f"starting session {self._session_id}")
        self._log_alert(
            "initializing audio capture + loading models "
            "(first run can take 10–30s)…"
        )

        import threading as _threading

        def _worker() -> None:
            """Heavy one-time construction — runs off the UI thread."""
            try:
                # These constructors can each block for seconds on cold
                # start: VADRingCapture → torch.hub.load Silero VAD;
                # SegmentQueueTranscriber will download faster-whisper
                # weights on first .start().
                segment_q: queue.Queue = queue.Queue(maxsize=256)
                trans_q: asyncio.Queue = asyncio.Queue()
                session_q: asyncio.Queue = asyncio.Queue()
                cap = VADRingCapture(self.cfg.audio, segment_q)
                transcriber = SegmentQueueTranscriber(
                    segment_q,
                    trans_q,
                    self._loop,
                    model=self._whisper_model_name,
                    device=self._whisper_device,
                )
                analyzer = DialecticSessionAnalyzer(
                    self.cfg.analysis, session_q, session_writer=None
                )
            except Exception as exc:
                # Bounce back to UI thread to report failure and reset.
                QTimer.singleShot(
                    0, lambda e=exc: self._on_init_failed(e)
                )
                return

            # Success — hand the freshly constructed components back to
            # the UI thread and finish starting there (Qt objects have
            # thread affinity, and sounddevice is friendliest when its
            # InputStream is opened on the owning thread).
            QTimer.singleShot(
                0,
                lambda: self._finish_start_on_ui_thread(
                    segment_q, trans_q, session_q, cap, transcriber, analyzer
                ),
            )

        _threading.Thread(
            target=_worker, name="DialecticInit", daemon=True
        ).start()

    def _on_init_failed(self, exc: BaseException) -> None:
        """Recover from a failure during session initialization."""
        self._initializing = False
        self._recording = False
        self._rec_btn.setEnabled(True)
        self._rec_btn.setText("BEGIN SESSION")
        self._rec_btn.setProperty("recording", "false")
        self._rec_btn.style().unpolish(self._rec_btn)
        self._rec_btn.style().polish(self._rec_btn)
        self._set_status("● ERROR", color="#c0392b")
        self._log_alert(
            f"init failed: {type(exc).__name__}: {exc}", level="error"
        )
        # Detailed traceback to stderr for developers; the UI already
        # shows the user-friendly version above.
        import traceback as _tb
        _tb.print_exc()

    def _finish_start_on_ui_thread(
        self,
        segment_q: queue.Queue,
        trans_q: asyncio.Queue,
        session_q: asyncio.Queue,
        cap: VADRingCapture,
        transcriber: SegmentQueueTranscriber,
        analyzer: DialecticSessionAnalyzer,
    ) -> None:
        """Final phase of start — runs on the UI/event-loop thread."""
        try:
            self._segment_q = segment_q
            self._trans_q = trans_q
            self._session_q = session_q
            self._cap = cap
            self._transcriber = transcriber
            self._analyzer = analyzer

            from .session_writer import SessionJSONLWriter

            # Always touch the JSONL so cloud-upload has something to
            # send even if the session yields zero formal claims.
            jsonl_path = (
                self.cfg.recordings_dir / f"{self._session_id}.jsonl"
            )
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            jsonl_path.touch(exist_ok=True)
            analyzer.set_session_writer(SessionJSONLWriter(jsonl_path))

            # Wire the interlocutor with an on_intervention callback
            # that routes into the PROMPTS pane. Default mode is
            # PASSIVE — overlay-only suggestions, no TTS — so the user
            # sees what the interlocutor would say without the app
            # ever speaking uninvited. Participants are auto-opted-in
            # because a single-user desktop session effectively IS
            # consent; multi-speaker consent still goes through the
            # legacy Dashboard flow if the user wants finer control.
            try:
                def _on_intervention(cand, rid: str) -> None:
                    # Bounce onto the Qt main thread — the interlocutor
                    # fires this from its analysis worker.
                    QTimer.singleShot(
                        0, lambda c=cand, i=rid: self._append_prompt_card(c, i)
                    )

                self._interlocutor = InterlocutorController(
                    self.cfg.interlocutor,
                    session_id=self._session_id,
                    log_dir=self.cfg.recordings_dir,
                    on_intervention=_on_intervention,
                )
                self._interlocutor.set_mode(InterlocutorMode.PASSIVE)
                self._interlocutor.set_participants_opt_in(True)
            except Exception as e:
                self._log_alert(
                    f"interlocutor construction failed "
                    f"(continuing without): {type(e).__name__}: {e}",
                    level="warn",
                )
                self._interlocutor = None

            cap.start()
            transcriber.start()
            self._tasks.append(
                asyncio.ensure_future(self._pump_transcription())
            )
            self._tasks.append(asyncio.ensure_future(self._pump_session()))
            self._timer.start()

            self._recording = True
            self._initializing = False
            self._rec_btn.setEnabled(True)
            self._rec_btn.setText("END SESSION")
            self._rec_btn.setProperty("recording", "true")
            self._rec_btn.style().unpolish(self._rec_btn)
            self._rec_btn.style().polish(self._rec_btn)
            self._set_status("● LISTENING", color="#7a9a6a")
            self._log_alert("listening — start speaking", level="ok")
            # Replace the idle transcript placeholder with a fresh pane.
            self._transcript.setPlainText("")
            self._transcript_lines = []
        except Exception as exc:
            self._on_init_failed(exc)

    def _stop_session(self) -> None:
        self._set_status("● STOPPING", color="#d4a017")
        self._recording = False

        if self._timer is not None:
            self._timer.stop()

        if self._cap is not None:
            try:
                self._cap.stop()
            except Exception as e:
                self._log_alert(
                    f"audio stop raised: {type(e).__name__}: {e}",
                    level="warn",
                )
        if self._transcriber is not None:
            try:
                self._transcriber.stop()
            except Exception as e:
                self._log_alert(
                    f"transcriber stop raised: {type(e).__name__}: {e}",
                    level="warn",
                )

        for t in self._tasks:
            t.cancel()
        self._tasks.clear()

        sid = self._session_id or ""
        if self._interlocutor is not None:
            try:
                self._interlocutor.save_reflection_bundle()
            except Exception as e:
                self._log_alert(
                    f"reflection save raised: {type(e).__name__}: {e}",
                    level="warn",
                )
            self._interlocutor = None

        self._rec_btn.setText("BEGIN SESSION")
        self._rec_btn.setProperty("recording", "false")
        self._rec_btn.style().unpolish(self._rec_btn)
        self._rec_btn.style().polish(self._rec_btn)
        self._set_status("● STOPPED", color="#8a7352")

        if sid:
            self._log_alert(f"session {sid} stopped", level="ok")
            if cloud_is_configured():
                try:
                    upload_session_async(sid, self.cfg.recordings_dir)
                    self._log_alert(
                        "cloud upload started (background thread)",
                        level="info",
                    )
                except Exception as e:
                    self._log_alert(
                        f"cloud upload failed to start: "
                        f"{type(e).__name__}: {e}",
                        level="warn",
                    )

    async def _pump_transcription(self) -> None:
        while True:
            try:
                ev: TranscriptionEvent = await asyncio.wait_for(
                    self._trans_q.get(), timeout=0.35
                )
            except asyncio.TimeoutError:
                if not self._recording:
                    break
                continue
            await self._analyzer.handle_transcription(ev)
            if ev.kind == "final" and ev.text.strip() and not ev.text.startswith("["):
                self.finalize_partial_line(ev.text)

    async def _pump_session(self) -> None:
        while True:
            try:
                se: SessionEvent = await asyncio.wait_for(
                    self._session_q.get(), timeout=0.35
                )
            except asyncio.TimeoutError:
                if not self._recording:
                    break
                continue
            self._apply_session(se)

    def _apply_session(self, se: SessionEvent) -> None:
        if se.kind == SessionEventKind.PARTIAL_TRANSCRIPT:
            self._pending_partial = se.data.get("text", "")
            return
        if se.kind == SessionEventKind.CLAIM:
            cid = str(se.data["claim_id"])
            self._nodes[cid] = _GraphNode(cid, str(se.data.get("text", "")))
            self._transcript_lines.append(
                f"[claim] {str(se.data.get('text', ''))[:200]}"
            )
            return
        if se.kind == SessionEventKind.CONTRADICTION_ALERT:
            a: ContradictionAlert = se.data["alert"]
            self._edges.append((a.claim_a_id, a.claim_b_id))
            # Render the contradiction as a full card in the TENSIONS
            # pane (previously a single log line; too easy to miss).
            self._tensions_list.add_card(
                headline=f"⚠ Contradiction · {a.score:.0%} severity",
                body=f"A: “{a.text_a}”\nB: “{a.text_b}”",
                meta=datetime.datetime.now().strftime("%H:%M:%S"),
            )
            # Lightweight mirror to the system log so the audit trail
            # stays complete (and the scroll history of contradictions
            # survives dismissals of the cards above).
            self._log_alert(
                f"contradiction ({a.score:.0%}) recorded",
                level="warn",
            )
            # Feed into the interlocutor so PASSIVE mode can surface a
            # follow-up prompt alongside the contradiction card.
            if self._interlocutor is not None:
                try:
                    from types import SimpleNamespace as _NS
                    c_obj = _NS(
                        statement_a=a.text_a,
                        statement_b=a.text_b,
                        score=float(a.score),
                        timestamp=0.0,
                        speaker_a="",
                        speaker_b="",
                    )
                    self._interlocutor.feed_contradiction(c_obj)
                except Exception as e:
                    import logging as _logging
                    _logging.getLogger(__name__).warning(
                        "ThreePane: interlocutor feed_contradiction raised: %s", e
                    )
            return
        if se.kind == SessionEventKind.TOPIC_SHIFT:
            self._log_alert(
                f"topic shift → {se.data.get('topic_cluster_id', '')}",
                level="info",
            )

    def _append_prompt_card(self, candidate, rid: str) -> None:
        """Render a new interlocutor suggestion in the PROMPTS pane.

        `candidate` is an `InterventionCandidate` — we crib the first
        and last lines of its four-line overlay script as the card
        headline + body. The full four lines are the formal artifact
        the interlocutor produced; the headline/body split here is a
        UI concession so the card reads well at a glance.
        """
        try:
            lines = list(getattr(candidate, "overlay_lines", ()))
            kind_ = str(getattr(candidate.kind, "value", candidate.kind))
            # `overlay_lines` is a fixed 4-tuple: [title, context, snippet, ask]
            # The first line is the interlocutor's self-ID ("Theseus
            # (interlocutor)") — we replace it with our own kind label
            # for consistency with the headline styling.
            headline = f"▸ {kind_.replace('_', ' ').title()}"
            body_parts = lines[1:] if len(lines) >= 4 else lines
            body = "\n".join(p for p in body_parts if p)
        except Exception:
            headline = "▸ Suggestion"
            body = str(candidate)

        self._prompts_list.add_card(
            headline=headline,
            body=body,
            meta=datetime.datetime.now().strftime("%H:%M:%S") + " · dismiss →",
        )

    def _tick_ui(self) -> None:
        if self._pending_partial:
            self._transcript.setPlainText(
                "\n".join(self._transcript_lines + [f"[partial] {self._pending_partial}"])
            )
        self._physics()
        self._redraw_graph()

    def _physics(self) -> None:
        nodes = list(self._nodes.values())
        for n in nodes:
            n.vx *= 0.9
            n.vy *= 0.9
        rep = 120.0
        for i, a in enumerate(nodes):
            for b in nodes[i + 1 :]:
                dx, dy = a.x - b.x, a.y - b.y
                d = math.hypot(dx, dy) + 1e-4
                f = rep / (d * d)
                fx, fy = f * dx / d, f * dy / d
                a.vx += fx
                a.vy += fy
                b.vx -= fx
                b.vy -= fy
        spr = 0.04
        for aid, bid in self._edges:
            na, nb = self._nodes.get(aid), self._nodes.get(bid)
            if na is None or nb is None:
                continue
            dx, dy = nb.x - na.x, nb.y - na.y
            na.vx += spr * dx
            na.vy += spr * dy
            nb.vx -= spr * dx
            nb.vy -= spr * dy
        for n in nodes:
            n.x += n.vx
            n.y += n.vy

    def _redraw_graph(self) -> None:
        nodes = list(self._nodes.values())
        if not nodes:
            self._scatter.setData([], [])
            self._line_plot.setData([], [])
            # Clear stale labels so the pane really looks empty when
            # there are no claims.
            for label in list(self._node_labels.values()):
                try:
                    self._plot.removeItem(label)
                except Exception:
                    pass
            self._node_labels.clear()
            return
        xs = [n.x for n in nodes]
        ys = [n.y for n in nodes]
        self._scatter.setData(xs, ys)
        lx: list[float] = []
        ly: list[float] = []
        for aid, bid in self._edges:
            na, nb = self._nodes.get(aid), self._nodes.get(bid)
            if na is None or nb is None:
                continue
            lx.extend([na.x, nb.x, float("nan")])
            ly.extend([na.y, nb.y, float("nan")])
        if lx:
            self._line_plot.setData(lx, ly)
        else:
            self._line_plot.setData([], [])

        # ── Labels: one pg.TextItem per claim ──────────────────────
        # We create the label the first time a claim shows up and
        # simply reposition it on every redraw. That lets the user
        # actually read which idea each dot represents — previously
        # the graph was a constellation of anonymous amber points
        # that moved around interestingly but meant nothing.
        live_ids: set[str] = set()
        for n in nodes:
            live_ids.add(n.cid)
            label = self._node_labels.get(n.cid)
            if label is None:
                short = n.text
                # Break long claims onto two lines at a word boundary
                # so a 50-word claim doesn't stretch off-screen.
                if len(short) > 28:
                    cut = short.rfind(" ", 0, 28)
                    if cut > 14:
                        short = short[:cut] + "\n" + short[cut + 1 : cut + 1 + 28]
                    else:
                        short = short[:28] + "…"
                label = pg.TextItem(
                    text=short,
                    color=(227, 201, 149),  # --parchment
                    anchor=(0, 1),          # position = anchor at bottom-left of text
                )
                # Small font so labels don't overwhelm the dots.
                try:
                    from PyQt6.QtGui import QFont as _QFont
                    label.setFont(_QFont("IBM Plex Mono", 8))
                except Exception:
                    pass
                self._plot.addItem(label)
                self._node_labels[n.cid] = label
            # Offset slightly right + up from the dot.
            label.setPos(n.x + 0.25, n.y + 0.35)
        # Prune labels whose claims have been evicted (shouldn't
        # happen in the current code path — claims are append-only —
        # but defensive so a future cap on node count works cleanly).
        for stale in list(self._node_labels.keys() - live_ids):
            try:
                self._plot.removeItem(self._node_labels[stale])
            except Exception:
                pass
            self._node_labels.pop(stale, None)

    def finalize_partial_line(self, text: str) -> None:
        if text.strip():
            self._transcript_lines.append(text.strip())
            self._pending_partial = ""
            self._transcript.setPlainText("\n".join(self._transcript_lines))


def _schedule_update_check(window: QMainWindow) -> None:
    """Trigger a background update check that shows a non-blocking banner.

    ``updater.check_for_updates`` runs in its own daemon thread; when it
    finds a new version it calls our callback with the manifest dict. We
    bounce the UI work onto the Qt main thread via ``QTimer.singleShot``
    so we don't try to pop a dialog from a worker thread (which would
    silently fail on macOS).
    """

    def _on_new_version(info: dict) -> None:
        def _show() -> None:
            try:
                version = info.get("version", "?")
                url = info.get("download_url", "")
                notes = info.get("release_notes", "")
                body = (
                    f"A new Dialectic release is available: {version}\n\n"
                    f"{notes}\n\n"
                    f"Download: {url}"
                )
                QMessageBox.information(window, "Dialectic update", body)
            except Exception:
                pass

        QTimer.singleShot(0, _show)

    try:
        check_for_updates(callback=_on_new_version)
    except Exception as e:
        print(f"[dialectic] update check skipped: {e}", file=sys.stderr)


def _apply_credentials_to_env(creds) -> None:
    """Push stored credentials into the env vars the cloud uploader
    already knows how to use.

    `cloud_uploader._is_configured()` gates cloud upload on
    DIALECTIC_CLOUD_URL + DIALECTIC_CLOUD_API_KEY. Rather than
    refactor that to read credentials directly, we bridge here —
    set the env vars for the process lifetime so every downstream
    uploader call just works.
    """
    import os as _os

    _os.environ["DIALECTIC_CLOUD_URL"] = creds.codex_url
    _os.environ["DIALECTIC_CLOUD_API_KEY"] = creds.api_key
    if creds.organization_slug:
        _os.environ["DIALECTIC_ORGANIZATION_SLUG"] = creds.organization_slug


def run_dashboard(
    config: DialecticConfig | None = None,
    *,
    legacy: bool = False,
    whisper_model: str | None = None,
    whisper_device: str | None = None,
) -> None:
    """Launch Dialectic UI (three-pane + qasync by default).

    Authentication is the first gate. We run the Codex login flow
    BEFORE bringing up the heavy application window — if the user
    cancels or has no session, we exit cleanly (no captured audio,
    no orphaned processes). The login dialog is skipped when
    `DIALECTIC_CLOUD_URL` + `DIALECTIC_CLOUD_API_KEY` env vars are
    set (CI / script usage) or when a valid stored key exists.
    """
    cfg = config or DialecticConfig()

    # ── Pre-flight: ensure a single QApplication exists BEFORE we
    #    try to open any dialog. PyQt explodes if a QDialog is
    #    constructed with no QApplication in scope.
    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Helvetica Neue", 10))

    # ── Authentication gate ───────────────────────────────────────
    # `ensure_authenticated` tries env → stored creds → login dialog.
    # Returns None only when the user explicitly cancelled; in that
    # case we exit the process rather than falling through to an
    # unauthenticated main window.
    from .login_dialog import ensure_authenticated

    creds = ensure_authenticated()
    if creds is None:
        print(
            "[dialectic] Sign-in cancelled. Exiting.",
            file=sys.stderr,
        )
        sys.exit(0)
    _apply_credentials_to_env(creds)

    # Auto-downgrade to legacy if the live-dashboard deps aren't available.
    # Previously this raised RuntimeError, which in a packaged .app means the
    # user sees the icon bounce once and then nothing — the window never
    # opens. Falling back to the legacy single-pane dashboard is always
    # better than no UI at all.
    if not legacy and (pg is None or qasync is None):
        print(
            "[dialectic] pyqtgraph or qasync not available; "
            "falling back to legacy dashboard.",
            file=sys.stderr,
        )
        legacy = True

    if legacy:
        window = DialecticDashboard(cfg)
        window.show()
        _schedule_update_check(window)
        sys.exit(app.exec())

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    wm = whisper_model or cfg.transcription.whisper_model
    wd = whisper_device or cfg.transcription.whisper_device
    win = ThreePaneDialecticWindow(cfg, loop, whisper_model=wm, whisper_device=wd)
    win.show()
    _schedule_update_check(win)

    # Idiomatic qasync lifecycle: tie the asyncio loop to Qt's aboutToQuit so
    # the loop actually stops when the user closes the window. The old
    # `sys.exit(loop.run_forever())` pattern left orphaned tasks and, on some
    # systems, kept the process alive after window close.
    close_event = asyncio.Event()
    app.aboutToQuit.connect(close_event.set)
    with loop:
        loop.run_until_complete(close_event.wait())


def run_dashboard_legacy(config: DialecticConfig | None = None) -> None:
    run_dashboard(config, legacy=True)

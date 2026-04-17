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

        self._rec_btn.recording = False
        self._timer.stop()
        msg = f"Saved: {wav_path.name}" if wav_path else "Stopped"
        if sid:
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
                QTimer.singleShot(
                    int(self.cfg.interlocutor.min_pause_seconds_tts * 1000),
                    lambda: speak(
                        cand.tts_text, max_seconds=self.cfg.interlocutor.tts_max_seconds
                    ),
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

        if self._interlocutor:
            self._interlocutor.feed_segment(segment)
        # Also feed to analyzer
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
        self.text = text[:48]
        self.x = (hash(cid) % 200) / 10.0 - 10.0
        self.y = (hash(cid[::-1]) % 200) / 10.0 - 10.0
        self.vx = 0.0
        self.vy = 0.0


class ThreePaneDialecticWindow(QMainWindow):
    """Transcript (left), claim graph (center), alerts (right)."""

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
        ui = config.ui
        self.setWindowTitle(ui.window_title + " — Live")
        self.setMinimumSize(1200, 720)

        self._segment_q: queue.Queue = queue.Queue(maxsize=64)
        self._trans_q: asyncio.Queue = asyncio.Queue()
        self._session_q: asyncio.Queue = asyncio.Queue()
        self._cap = VADRingCapture(config.audio, self._segment_q)
        self._transcriber = SegmentQueueTranscriber(
            self._segment_q,
            self._trans_q,
            loop,
            model=whisper_model,
            device=whisper_device,
        )
        self._analyzer = DialecticSessionAnalyzer(
            config.analysis, self._session_q, session_writer=None
        )
        self._nodes: dict[str, _GraphNode] = {}
        self._edges: list[tuple[str, str]] = []
        self._pending_partial: str = ""
        self._transcript_lines: list[str] = []
        self._tasks: list[asyncio.Task] = []

        central = QWidget()
        self.setCentralWidget(central)
        central.setStyleSheet(f"background-color: {ui.bg_color};")
        h = QHBoxLayout(central)
        h.setContentsMargins(10, 10, 10, 10)
        h.setSpacing(10)

        # Left: transcript
        left = QFrame()
        left_l = QVBoxLayout(left)
        left_l.addWidget(QLabel("TRANSCRIPT"))
        self._transcript = QPlainTextEdit()
        self._transcript.setReadOnly(True)
        self._transcript.setStyleSheet("font-family: 'SF Mono', monospace; font-size: 11px;")
        left_l.addWidget(self._transcript)
        h.addWidget(left, stretch=2)

        # Center: graph
        center = QFrame()
        cl = QVBoxLayout(center)
        cl.addWidget(QLabel("CLAIM GRAPH"))
        self._plot = pg.PlotWidget()
        self._plot.showGrid(x=True, y=True, alpha=0.2)
        self._scatter = pg.ScatterPlotItem(size=10, pen=pg.mkPen("b"), brush=pg.mkBrush(80, 120, 200, 200))
        self._plot.addItem(self._scatter)
        self._line_plot = pg.PlotDataItem(pen=pg.mkPen(200, 80, 80, width=2))
        self._plot.addItem(self._line_plot)
        cl.addWidget(self._plot)
        h.addWidget(center, stretch=3)

        # Right: alerts
        right = QFrame()
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("ALERTS"))
        self._alerts = QPlainTextEdit()
        self._alerts.setReadOnly(True)
        self._alerts.setStyleSheet("font-family: 'Helvetica Neue'; font-size: 11px;")
        rl.addWidget(self._alerts)
        h.addWidget(right, stretch=2)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick_ui)
        self._recording = False

        # Record control
        bar = QHBoxLayout()
        self._rec_btn = QPushButton("Start session")
        self._rec_btn.clicked.connect(self._toggle)
        bar.addWidget(self._rec_btn)
        left_l.insertWidget(0, bar)

    def _toggle(self) -> None:
        if not self._recording:
            self._recording = True
            self._rec_btn.setText("Stop session")
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self._session_id = f"session_{ts}"
            from .session_writer import SessionJSONLWriter

            self._analyzer.set_session_writer(
                SessionJSONLWriter(self.cfg.recordings_dir / f"{self._session_id}.jsonl")
            )
            self._cap.start()
            self._transcriber.start()
            self._tasks.append(asyncio.ensure_future(self._pump_transcription()))
            self._tasks.append(asyncio.ensure_future(self._pump_session()))
            self._timer.start()
        else:
            self._recording = False
            self._rec_btn.setText("Start session")
            self._timer.stop()
            self._cap.stop()
            self._transcriber.stop()
            for t in self._tasks:
                t.cancel()
            self._tasks.clear()
            sid = getattr(self, "_session_id", "") or ""
            if sid and cloud_is_configured():
                upload_session_async(sid, self.cfg.recordings_dir)

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
            self._alerts.appendPlainText(
                f"Contradiction ({a.score:.0%}): {a.text_a[:60]}… vs {a.text_b[:60]}…\n"
            )
            return
        if se.kind == SessionEventKind.TOPIC_SHIFT:
            self._alerts.appendPlainText(
                f"Topic shift → {se.data.get('topic_cluster_id', '')}\n"
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

    def finalize_partial_line(self, text: str) -> None:
        if text.strip():
            self._transcript_lines.append(text.strip())
            self._pending_partial = ""
            self._transcript.setPlainText("\n".join(self._transcript_lines))


def run_dashboard(
    config: DialecticConfig | None = None,
    *,
    legacy: bool = False,
    whisper_model: str | None = None,
    whisper_device: str | None = None,
) -> None:
    """Launch Dialectic UI (three-pane + qasync by default)."""
    cfg = config or DialecticConfig()

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
        app = QApplication.instance() or QApplication(sys.argv)
        app.setFont(QFont("Helvetica Neue", 10))
        window = DialecticDashboard(cfg)
        window.show()
        sys.exit(app.exec())

    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Helvetica Neue", 10))
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    wm = whisper_model or cfg.transcription.whisper_model
    wd = whisper_device or cfg.transcription.whisper_device
    win = ThreePaneDialecticWindow(cfg, loop, whisper_model=wm, whisper_device=wd)
    win.show()

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

"""pytest-qt coverage for ``RecordingModal`` state transitions.

A ``FakeAudioEngine`` stands in for ``AudioEngine`` so tests don't need a
microphone. It writes a minimal WAV at ``save_path`` on ``start()`` so
the real-file check in ``_finish_capture_and_process`` passes.
"""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Optional

import numpy as np
import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QMessageBox

from dialectic.config import AudioConfig
from dialectic.recording_modal import RecordingModal, RecordingState


class FakeAudioEngine:
    """Drop-in replacement for ``AudioEngine`` in tests.

    ``start()`` writes a small WAV file and fires one synthetic audio
    chunk so the VU path is exercised without a real mic.
    """

    def __init__(self, config: AudioConfig, on_audio_chunk=None, save_path: Optional[Path] = None):
        self.cfg = config
        self._on_chunk = on_audio_chunk
        self._save_path = save_path
        self.is_recording = False

    def start(self) -> None:
        assert self._save_path is not None
        with wave.open(str(self._save_path), "wb") as wf:
            wf.setnchannels(self.cfg.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.cfg.sample_rate)
            wf.writeframes((np.zeros(self.cfg.sample_rate // 4, dtype=np.int16)).tobytes())
        self.is_recording = True
        if self._on_chunk is not None:
            self._on_chunk(np.ones(256, dtype=np.int16) * 4000, 0.0)

    def stop(self) -> Optional[Path]:
        self.is_recording = False
        return self._save_path


@pytest.fixture
def modal_factory(qtbot, monkeypatch):
    """Returns a builder that opens a RecordingModal with the fake engine."""

    def _make(**kwargs) -> RecordingModal:
        # Silence the confirm dialog on Discard by default; specific tests
        # override this before triggering their action.
        monkeypatch.setattr(
            QMessageBox,
            "question",
            classmethod(lambda cls, *a, **kw: QMessageBox.StandardButton.Yes),
        )
        m = RecordingModal(
            audio_config=AudioConfig(),
            audio_engine_factory=FakeAudioEngine,
            **kwargs,
        )
        qtbot.addWidget(m)
        m.show()
        qtbot.waitUntil(lambda: m.state is RecordingState.RECORDING, timeout=2000)
        return m

    return _make


def test_modal_transitions_to_recording_on_open(modal_factory):
    m = modal_factory()
    assert m.state is RecordingState.RECORDING
    assert m._tmp_wav is not None and m._tmp_wav.exists()


def test_space_toggles_pause_and_resume(modal_factory, qtbot):
    m = modal_factory()

    m._space_shortcut.activated.emit()
    qtbot.waitUntil(lambda: m.state is RecordingState.PAUSED, timeout=1000)
    assert m._pause_btn.text() == "Resume"

    m._space_shortcut.activated.emit()
    qtbot.waitUntil(lambda: m.state is RecordingState.RECORDING, timeout=1000)
    assert m._pause_btn.text() == "Pause"


def test_stop_runs_pipeline_and_reaches_done(modal_factory, qtbot):
    m = modal_factory()
    stages_seen: list[str] = []
    # Wire up a listener *before* stop, so we can assert order.
    # The pipeline is created inside _finish_capture_and_process, so we
    # hook via the stage_rows widgets: their status text changes to "done"
    # only after the success signal fires on the UI thread.

    m._enter_shortcut.activated.emit()
    qtbot.waitUntil(lambda: m.state is RecordingState.PROCESSING, timeout=1000)
    # Collect pipeline stage signals now that the pipeline exists.
    assert m._pipeline is not None
    m._pipeline.stage_started.connect(stages_seen.append)

    qtbot.waitUntil(lambda: m.state is RecordingState.DONE, timeout=5000)
    # All four rows should be marked done.
    for name in ("trim", "transcribe", "title", "upload"):
        assert m._stage_rows[name].status.text() == "done", name
    assert m._dismiss_btn.isEnabled()
    assert m._dismiss_btn.text() == "Close"


def test_discard_unlinks_temp_wav(modal_factory, qtbot):
    m = modal_factory()
    tmp = m._tmp_wav
    assert tmp is not None and tmp.exists()

    m._on_discard_clicked()
    qtbot.waitUntil(lambda: m.state is RecordingState.DISCARDED, timeout=1000)
    assert not tmp.exists()
    assert m._pipeline is None


def test_error_path_shows_dismiss(modal_factory, qtbot, monkeypatch):
    m = modal_factory()

    # Replace the real _on_stop_clicked wiring: stop capture, then point
    # the pipeline's transcribe stub at a failure before run() spins up.
    # We intercept PipelineThread.start so we can monkeypatch the stage
    # on the exact pipeline instance the modal built.
    from dialectic import recording_pipeline as rp

    original_start = rp.PipelineThread.start

    def start_with_failing_transcribe(self, *args, **kwargs):
        def boom():
            raise RuntimeError("synthetic failure")

        self.pipeline._stage_transcribe = boom  # type: ignore[assignment]
        return original_start(self, *args, **kwargs)

    monkeypatch.setattr(rp.PipelineThread, "start", start_with_failing_transcribe)

    m._enter_shortcut.activated.emit()
    qtbot.waitUntil(lambda: m.state is RecordingState.ERROR, timeout=5000)
    assert m._dismiss_btn.isEnabled()
    assert m._dismiss_btn.text() == "Dismiss"
    assert "synthetic failure" in (m._error_message or "")
    assert m._stage_rows["transcribe"].status.text().startswith("error:")

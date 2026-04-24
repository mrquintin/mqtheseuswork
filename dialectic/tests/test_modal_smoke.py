"""Headless modal smoke + optional real-whisper run.

The basic "modal opens, all four stages run to done, closes cleanly"
path is already exercised by ``test_recording_modal.py`` (specifically
``test_stop_runs_pipeline_and_reaches_done``). This file adds:

- A lightweight repeat of that smoke under ``pytest-qt`` so running
  only ``test_modal_smoke.py`` still gives a useful signal if someone
  hard-deletes the richer modal test file.
- An opt-in check that, when ``DIALECTIC_TEST_REAL_WHISPER=1`` is set,
  the 5-second tiny audio fixture actually transcribes end-to-end in
  under 60 s on the current machine. Gated because faster-whisper's
  first run downloads hundreds of MB of model weights.
"""

from __future__ import annotations

import os
import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np
import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QMessageBox

from dialectic.config import AudioConfig
from dialectic.recording_modal import RecordingModal, RecordingState


class _SilentFakeAudioEngine:
    """Minimal audio engine stub. Writes a tiny WAV on start() so the
    stop() path can hand the pipeline a real file."""

    def __init__(
        self,
        config: AudioConfig,
        on_audio_chunk=None,
        save_path: Optional[Path] = None,
    ):
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
            wf.writeframes(
                np.zeros(self.cfg.sample_rate // 4, dtype=np.int16).tobytes()
            )
        self.is_recording = True
        if self._on_chunk is not None:
            self._on_chunk(np.ones(256, dtype=np.int16) * 4000, 0.0)

    def stop(self) -> Optional[Path]:
        self.is_recording = False
        return self._save_path


def test_modal_opens_runs_stages_and_closes(qtbot, monkeypatch):
    """Sanity smoke: modal launches, all four stages tick to done,
    Close dismisses without error.

    All four pipeline stages are stubbed so this runs in < 1 s without
    Silero / faster-whisper / Anthropic / Codex. The point of the test
    is the UI wiring: modal → pipeline → stage_rows → DONE state.
    The real stages are covered by their own unit tests.
    """
    from dialectic.auto_trim import SpeechInterval, TrimResult
    from dialectic.auto_title import AutoTitleResult
    from dialectic.batch_transcriber import TranscriptionResult, TranscriptSegment
    from dialectic.codex_upload import UploadResult
    from dialectic.recording_pipeline import RecordingPipeline

    monkeypatch.setattr(
        QMessageBox,
        "question",
        classmethod(lambda cls, *a, **kw: QMessageBox.StandardButton.Yes),
    )

    # Stub every stage. Each writes its result into PipelineResult as
    # the real stages do, so the modal's signal handlers see a complete
    # payload.
    def fake_trim(self):
        interval = SpeechInterval(0.0, 0.25)
        self.result.trimmed_audio = self.artifact.audio_path
        self.result.trim_intervals = [interval]
        self.result.original_duration_s = 0.25
        self.result.trimmed_duration_s = 0.25
        return TrimResult(
            input_path=self.artifact.audio_path,
            output_path=self.artifact.audio_path,
            original_duration_s=0.25,
            trimmed_duration_s=0.25,
            intervals=[interval],
        )

    def fake_transcribe(self):
        result = TranscriptionResult(
            text="mocked transcript",
            segments=[TranscriptSegment(0.0, 0.25, "mocked transcript")],
            language="en",
            model_name="mocked",
            duration_seconds=0.25,
            elapsed_seconds=0.0,
        )
        self.result.transcript = result.text
        self.result.transcript_segments = list(result.segments)
        self.result.transcript_language = result.language
        self.result.transcript_model = result.model_name
        return result

    def fake_title(self):
        result = AutoTitleResult(
            title="Mocked session title",
            recorded_date="2026-04-24",
            method="fallback",
        )
        self.result.title = result.title
        self.result.title_method = result.method
        self.result.recorded_date = result.recorded_date
        return result

    def fake_upload(self):
        result = UploadResult(
            upload_id="u_test",
            codex_url="http://codex.test/dashboard/uploads/u_test",
            bytes_sent=0,
        )
        self.result.upload_id = result.upload_id
        self.result.codex_url = result.codex_url
        return result

    monkeypatch.setattr(RecordingPipeline, "_stage_trim", fake_trim)
    monkeypatch.setattr(RecordingPipeline, "_stage_transcribe", fake_transcribe)
    monkeypatch.setattr(RecordingPipeline, "_stage_title", fake_title)
    monkeypatch.setattr(RecordingPipeline, "_stage_upload", fake_upload)

    m = RecordingModal(
        audio_config=AudioConfig(),
        audio_engine_factory=_SilentFakeAudioEngine,
    )
    qtbot.addWidget(m)
    m.show()
    qtbot.waitUntil(lambda: m.state is RecordingState.RECORDING, timeout=2000)

    m._enter_shortcut.activated.emit()
    qtbot.waitUntil(lambda: m.state is RecordingState.DONE, timeout=5000)

    for name in ("trim", "transcribe", "title", "upload"):
        assert m._stage_rows[name].status.text() == "done", name
    assert m._dismiss_btn.isEnabled()


@pytest.mark.skipif(
    os.environ.get("DIALECTIC_TEST_REAL_WHISPER") != "1",
    reason="real-whisper smoke is gated by DIALECTIC_TEST_REAL_WHISPER=1",
)
def test_real_whisper_transcribes_tiny_fixture_under_60s():
    """End-to-end with the actual faster-whisper model, not a mock.

    Runs only when a developer explicitly opts in. A cold first run
    downloads model weights (hundreds of MB) — after that it's typically
    a few seconds on Apple Silicon, comfortably inside the 60 s budget.
    """
    from dialectic.batch_transcriber import transcribe

    fixtures = Path(__file__).parent / "fixtures"
    candidates = sorted(fixtures.glob("*.wav")) + sorted(fixtures.glob("*.m4a"))
    if not candidates:
        pytest.skip(
            "no audio fixture under dialectic/tests/fixtures/; "
            "drop a ~5 s clip in there to enable."
        )

    t0 = time.monotonic()
    result = transcribe(candidates[0])
    elapsed = time.monotonic() - t0

    assert result.text.strip(), "real whisper returned an empty transcript"
    assert elapsed < 60.0, (
        f"real-whisper transcription took {elapsed:.1f}s on this machine — "
        "consider a smaller model or a shorter fixture."
    )

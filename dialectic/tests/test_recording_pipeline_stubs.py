"""Tests for ``RecordingPipeline`` stage protocol with stubbed work.

The production stage bodies run VAD, transcription, titling, and Codex upload.
These tests lock in the *protocol* the modal depends on without touching those
network/model paths: four stages fire in order, and ``PipelineResult`` carries a
value for each after a clean run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QCoreApplication

from dialectic.recording_pipeline import (
    STAGE_ORDER,
    PipelineResult,
    RecordingArtifact,
    RecordingPipeline,
)


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


@pytest.fixture
def artifact(tmp_path: Path) -> RecordingArtifact:
    p = tmp_path / "rec.wav"
    p.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")  # shape-only fixture
    return RecordingArtifact(
        audio_path=p,
        duration_seconds=3.14,
        sample_rate=16_000,
        channels=1,
    )


def test_stage_order_constant_matches_pipeline_stages():
    assert STAGE_ORDER == ("trim", "transcribe", "title", "upload")


def _install_success_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_trim(self):
        self.result.trimmed_audio = self.artifact.audio_path
        self.result.original_duration_s = self.artifact.duration_seconds
        self.result.trimmed_duration_s = self.artifact.duration_seconds
        return self.artifact.audio_path

    def fake_transcribe(self):
        self.result.transcript = "A short test transcript."
        self.result.transcript_segments = []
        self.result.transcript_language = "en"
        self.result.transcript_model = "stub"
        return self.result.transcript

    def fake_title(self):
        self.result.title = "Dialectic session — test"
        self.result.title_method = "fallback"
        self.result.recorded_date = "2026-05-02"
        return self.result.title

    def fake_upload(self):
        self.result.upload_id = "upload_test"
        self.result.codex_url = "https://www.theseuscodex.com"
        return {"upload_id": self.result.upload_id}

    monkeypatch.setattr(RecordingPipeline, "_stage_trim", fake_trim)
    monkeypatch.setattr(RecordingPipeline, "_stage_transcribe", fake_transcribe)
    monkeypatch.setattr(RecordingPipeline, "_stage_title", fake_title)
    monkeypatch.setattr(RecordingPipeline, "_stage_upload", fake_upload)


def test_pipeline_runs_all_four_stages_in_order(qapp, artifact, monkeypatch):
    _install_success_stubs(monkeypatch)
    pipeline = RecordingPipeline(artifact)

    started: list[str] = []
    succeeded: list[tuple[str, object]] = []
    done_results: list[PipelineResult] = []

    pipeline.stage_started.connect(started.append)
    pipeline.stage_succeeded.connect(lambda name, val: succeeded.append((name, val)))
    pipeline.all_done.connect(done_results.append)

    pipeline.run()

    assert started == list(STAGE_ORDER)
    assert [name for name, _ in succeeded] == list(STAGE_ORDER)
    assert len(done_results) == 1


def test_pipeline_result_populated_after_stub_run(qapp, artifact, monkeypatch):
    _install_success_stubs(monkeypatch)
    pipeline = RecordingPipeline(artifact)
    pipeline.run()

    r = pipeline.result
    assert r.trimmed_audio == artifact.audio_path
    assert r.transcript is not None and r.transcript.strip() != ""
    assert r.title is not None and "Dialectic session" in r.title
    assert r.upload_id is not None
    assert r.errors == {}


def test_pipeline_failure_halts_remaining_stages(qapp, artifact, monkeypatch):
    _install_success_stubs(monkeypatch)
    pipeline = RecordingPipeline(artifact)

    def boom() -> str:
        raise RuntimeError("transcribe blew up")

    pipeline._stage_transcribe = boom  # type: ignore[assignment]

    started: list[str] = []
    failed: list[tuple[str, str]] = []
    done_results: list[PipelineResult] = []

    pipeline.stage_started.connect(started.append)
    pipeline.stage_failed.connect(lambda n, m: failed.append((n, m)))
    pipeline.all_done.connect(done_results.append)

    pipeline.run()

    # trim ran, transcribe started+failed, title/upload never started.
    assert started == ["trim", "transcribe"]
    assert failed == [("transcribe", "transcribe blew up")]
    assert len(done_results) == 1
    assert pipeline.result.errors == {"transcribe": "transcribe blew up"}

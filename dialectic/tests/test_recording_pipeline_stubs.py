"""Tests for ``RecordingPipeline`` stub stages (prompt 06 scope).

The pipeline's stages are stubs now; prompts 07-10 replace them. These
tests lock in the *protocol* the modal depends on: four stages fire in
order, and ``PipelineResult`` carries a value for each after a clean run.
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


def test_pipeline_runs_all_four_stages_in_order(qapp, artifact):
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


def test_pipeline_result_populated_after_stub_run(qapp, artifact):
    pipeline = RecordingPipeline(artifact)
    pipeline.run()

    r = pipeline.result
    assert r.trimmed_audio == artifact.audio_path
    assert r.transcript is not None and r.transcript.strip() != ""
    assert r.title is not None and "Dialectic session" in r.title
    assert r.upload_id is not None
    assert r.errors == {}


def test_pipeline_failure_halts_remaining_stages(qapp, artifact):
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

"""Five load-bearing invariants for the recording pipeline.

Each of these was a real failure mode during Wave 2 development. If a
refactor accidentally re-opens one, the corresponding test fires.

    (1) Stage order is trim, transcribe, title, upload — modal UX
        depends on it.
    (2) Upload always operates on the trimmed file, never the raw one —
        otherwise a 2-hour recording uploads a 1.2 GB WAV when the
        speech-only cut is 800 MB.
    (3) Title is never empty or None, even when Claude is unavailable —
        the Codex column is NOT NULL and downstream dashboard widgets
        assume a string.
    (4) A failed upload lands in the pending queue — losing audio to
        a flaky network is unacceptable.
    (5) Transcript text on the Dialectic side equals textContent on
        the Codex side — silent divergence means the Codex is
        extracting claims from text the founder never said.

Do NOT 'fix' these tests by loosening assertions. Fix the code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

from dialectic.auto_trim import SpeechInterval, TrimResult
from dialectic.batch_transcriber import TranscriptionResult, TranscriptSegment
from dialectic.codex_upload import UploadError, UploadResult
from dialectic.recording_pipeline import (
    STAGE_ORDER,
    RecordingArtifact,
    RecordingPipeline,
)


CANONICAL_TRANSCRIPT = (
    "We were discussing the purpose of the school. "
    "The claim is that inquiry matters more than credentialing. "
    "A second claim: narrative priced assets overpay by about "
    "eighteen percent, which is a testable prediction."
)


@pytest.fixture(scope="module")
def qapp():
    # QApplication (not QCoreApplication) — a later pytest-qt test in
    # the same session will abort if a QCoreApplication is live when it
    # tries to create a QApplication.
    app = QCoreApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def artifact(tmp_path: Path) -> RecordingArtifact:
    p = tmp_path / "raw.wav"
    # Shape-only bytes — all stages that touch file contents are
    # mocked in these tests.
    p.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    return RecordingArtifact(
        audio_path=p,
        duration_seconds=30.0,
        sample_rate=16_000,
        channels=1,
    )


def _install_trim_stub(monkeypatch, *, trimmed_path: Path):
    """Stub ``_stage_trim`` to return a real TrimResult pointing at
    ``trimmed_path``. Leaves ``_stage_trim`` observable so the stage
    still emits ``stage_started``."""
    # The trimmed file must exist on disk so the upload stage has bytes
    # to read if it ever got that far.
    trimmed_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    def fake_trim(self):
        interval = SpeechInterval(0.0, 28.0)
        result = TrimResult(
            input_path=self.artifact.audio_path,
            output_path=trimmed_path,
            original_duration_s=30.0,
            trimmed_duration_s=28.0,
            intervals=[interval],
        )
        self.result.trimmed_audio = trimmed_path
        self.result.trim_intervals = [interval]
        self.result.original_duration_s = 30.0
        self.result.trimmed_duration_s = 28.0
        return result

    monkeypatch.setattr(
        "dialectic.recording_pipeline.RecordingPipeline._stage_trim",
        fake_trim,
    )


def _install_transcribe_stub(monkeypatch, *, text: str = CANONICAL_TRANSCRIPT):
    def fake_transcribe(self):
        result = TranscriptionResult(
            text=text,
            segments=[TranscriptSegment(0.0, 28.0, text)],
            language="en",
            model_name="mocked",
            duration_seconds=28.0,
            elapsed_seconds=0.01,
        )
        self.result.transcript = result.text
        self.result.transcript_segments = list(result.segments)
        self.result.transcript_language = result.language
        self.result.transcript_model = result.model_name
        return result

    monkeypatch.setattr(
        "dialectic.recording_pipeline.RecordingPipeline._stage_transcribe",
        fake_transcribe,
    )


def _install_env_creds(monkeypatch, base_url: str = "http://codex.test"):
    monkeypatch.setenv("DIALECTIC_CLOUD_URL", base_url)
    monkeypatch.setenv("DIALECTIC_CLOUD_API_KEY", "test-key")


# ─────────────────────────────────────────────────────────────────────────────
# (1) Stage order
# ─────────────────────────────────────────────────────────────────────────────


def test_invariant_stage_order(qapp, artifact, monkeypatch, tmp_path):
    _install_trim_stub(monkeypatch, trimmed_path=tmp_path / "trimmed.wav")
    _install_transcribe_stub(monkeypatch)
    _install_env_creds(monkeypatch)

    # Stub upload so we can observe without network.
    uploaded: list[Path] = []

    def fake_upload_recording(*, audio_path, **kw):
        uploaded.append(Path(audio_path))
        return UploadResult(
            upload_id="u_test",
            codex_url="http://codex.test/dashboard/uploads/u_test",
            bytes_sent=Path(audio_path).stat().st_size,
        )

    monkeypatch.setattr(
        "dialectic.codex_upload.upload_recording", fake_upload_recording
    )

    pipeline = RecordingPipeline(artifact)
    started: list[str] = []
    pipeline.stage_started.connect(started.append)
    pipeline.run()

    assert started == list(STAGE_ORDER) == ["trim", "transcribe", "title", "upload"]


# ─────────────────────────────────────────────────────────────────────────────
# (2) Upload uses the trimmed file, not the raw one
# ─────────────────────────────────────────────────────────────────────────────


def test_invariant_upload_uses_trimmed_file(qapp, artifact, monkeypatch, tmp_path):
    trimmed_path = tmp_path / "trimmed.wav"
    _install_trim_stub(monkeypatch, trimmed_path=trimmed_path)
    _install_transcribe_stub(monkeypatch)
    _install_env_creds(monkeypatch)

    captured: dict = {}

    def fake_upload_recording(*, audio_path, **kw):
        captured["audio_path"] = Path(audio_path)
        return UploadResult(
            upload_id="u_test",
            codex_url="http://codex.test/dashboard/uploads/u_test",
            bytes_sent=Path(audio_path).stat().st_size,
        )

    monkeypatch.setattr(
        "dialectic.codex_upload.upload_recording", fake_upload_recording
    )

    pipeline = RecordingPipeline(artifact)
    pipeline.run()

    assert captured.get("audio_path") == trimmed_path, (
        f"upload stage must receive the trimmed file {trimmed_path!s}, "
        f"got {captured.get('audio_path')!s}"
    )
    # Defense in depth: the trimmed path must not be the raw recording.
    assert captured["audio_path"] != artifact.audio_path


# ─────────────────────────────────────────────────────────────────────────────
# (3) Title is never empty, even when the LLM is unreachable
# ─────────────────────────────────────────────────────────────────────────────


def test_invariant_title_never_empty_even_in_full_fallback(
    qapp, artifact, monkeypatch, tmp_path
):
    _install_trim_stub(monkeypatch, trimmed_path=tmp_path / "trimmed.wav")
    _install_transcribe_stub(monkeypatch)
    _install_env_creds(monkeypatch)

    # Make generate_title blow up so the pipeline's outer fallback has
    # to rescue it. This exercises the "unexpected error above the
    # generate_title layer" branch in ``_stage_title``.
    def boom(*_a, **_kw):
        raise RuntimeError("simulated LLM outage")

    monkeypatch.setattr("dialectic.auto_title.generate_title", boom)

    # Stub upload so the run completes.
    monkeypatch.setattr(
        "dialectic.codex_upload.upload_recording",
        lambda **kw: UploadResult(
            upload_id="u_test",
            codex_url="http://codex.test/dashboard/uploads/u_test",
            bytes_sent=0,
        ),
    )

    pipeline = RecordingPipeline(artifact)
    pipeline.run()

    title = pipeline.result.title
    assert isinstance(title, str) and title.strip(), (
        f"title must never be empty; got {title!r}"
    )
    assert title.startswith("Dialectic session"), (
        f"fallback title should start with 'Dialectic session', got {title!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# (4) Failed upload queues for later retry
# ─────────────────────────────────────────────────────────────────────────────


def test_invariant_offline_upload_queues(
    qapp, artifact, monkeypatch, tmp_path
):
    trimmed_path = tmp_path / "trimmed.wav"
    _install_trim_stub(monkeypatch, trimmed_path=trimmed_path)
    _install_transcribe_stub(monkeypatch)
    _install_env_creds(monkeypatch)

    # Isolate the pending queue to tmp — don't scribble on the
    # developer's real Application Support dir.
    queue_dir = tmp_path / "pending"
    monkeypatch.setenv("DIALECTIC_PENDING_QUEUE_DIR", str(queue_dir))
    from dialectic import pending_queue

    # Flush any cached directory by re-reading via queue_file().
    queue_file = pending_queue.queue_file()
    if queue_file.exists():
        queue_file.unlink()

    # Simulate a Codex 5xx: upload_recording raises UploadError. The
    # pipeline should enqueue and re-raise.
    def fake_upload_recording(**kw):
        raise UploadError("prepare failed: 500 Internal Server Error")

    monkeypatch.setattr(
        "dialectic.codex_upload.upload_recording", fake_upload_recording
    )

    pipeline = RecordingPipeline(artifact)
    failures: list[tuple[str, str]] = []
    pipeline.stage_failed.connect(lambda n, m: failures.append((n, m)))
    pipeline.run()

    # Upload stage should be the one that failed.
    assert len(failures) == 1
    stage, msg = failures[0]
    assert stage == "upload"
    assert "Retry pending uploads" in msg, (
        f"stage_failed message must point the user at the retry menu; got: {msg!r}"
    )

    # Exactly one line should have been written to the queue.
    lines = [
        ln for ln in queue_file.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    assert len(lines) == 1, f"expected 1 queued upload, got {len(lines)}: {lines!r}"
    record = json.loads(lines[0])
    assert Path(record["audio_path"]) == trimmed_path
    assert record["transcript"] == CANONICAL_TRANSCRIPT
    assert record["title"], "queued record must carry a title"
    assert record["extraction_method"].startswith("dialectic-")


# ─────────────────────────────────────────────────────────────────────────────
# (5) Transcript and textContent stay aligned end-to-end
# ─────────────────────────────────────────────────────────────────────────────


def test_invariant_transcript_equals_textcontent(
    qapp, artifact, monkeypatch, tmp_path
):
    trimmed_path = tmp_path / "trimmed.wav"
    _install_trim_stub(monkeypatch, trimmed_path=trimmed_path)
    transcript_text = CANONICAL_TRANSCRIPT
    _install_transcribe_stub(monkeypatch, text=transcript_text)
    _install_env_creds(monkeypatch)

    # Capture whatever transcript the upload stage forwards to Codex.
    forwarded: dict = {}

    def fake_upload_recording(*, transcript, **kw):
        forwarded["transcript"] = transcript
        return UploadResult(
            upload_id="u_test",
            codex_url="http://codex.test/dashboard/uploads/u_test",
            bytes_sent=0,
        )

    monkeypatch.setattr(
        "dialectic.codex_upload.upload_recording", fake_upload_recording
    )

    pipeline = RecordingPipeline(artifact)
    pipeline.run()

    assert pipeline.result.transcript == transcript_text
    assert forwarded.get("transcript") == transcript_text, (
        "the transcript Dialectic stages produced and the transcript Codex "
        "receives must be byte-identical — diverging here is a silent "
        "claim-fabrication failure"
    )

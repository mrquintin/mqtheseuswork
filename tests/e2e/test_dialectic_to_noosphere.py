"""Full cross-wave happy path: Dialectic record → Codex upload → Noosphere ingest.

No UI. No real whisper. No real Supabase. Everything runs in-process:

- Dialectic's ``RecordingPipeline`` walks the four stages. Trim and
  transcribe are monkey-patched so we don't pull down Silero and
  faster-whisper models (hundreds of MB each, CI-hostile).
- The upload stage talks to the mock HTTP server from ``conftest.py``,
  which persists the Upload row into a SQLite DB shaped like the Codex
  schema.
- ``ingest_from_codex`` then reads that same SQLite DB and extracts
  Conclusions — same code path as production, just pointed at sqlite://
  instead of postgres://.

Assertions prove the transcript made it end-to-end: at least one
Conclusion's text contains a substring from the canonical transcript.
That rules out the "ingest fabricated claims on its own" failure mode.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

# Use QApplication (not QCoreApplication) so a later pytest-qt test in
# the same session — which instantiates QApplication itself — doesn't
# hit the "cannot downcast QCoreApplication to QApplication" abort.
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication


_CANONICAL_TRANSCRIPT = (
    "We were discussing the purpose of the school. "
    "The claim is that inquiry matters more than credentialing. "
    "A second claim: narrative priced assets overpay by about "
    "eighteen percent, which is a testable prediction. "
    "Therefore we should build a measurement protocol before we "
    "build more opinions."
)


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance() or QApplication([])
    yield app


@pytest.mark.e2e
def test_recording_lands_as_conclusions_in_codex(
    qapp,
    seed_audio_fixture,
    fake_codex_and_supabase,
    sqlite_codex_with_api_hookup,
    monkeypatch,
    tmp_path,
):
    """Full happy path: fixture wav → trim → transcribe → title →
    upload → Codex (SQLite) → ingest-from-codex → Conclusions."""
    from dialectic.auto_trim import SpeechInterval, TrimResult
    from dialectic.batch_transcriber import TranscriptionResult, TranscriptSegment
    from dialectic.recording_pipeline import RecordingArtifact, RecordingPipeline

    # ── 1. Point Dialectic at the mock Codex (env-var creds path) ──
    monkeypatch.setenv("DIALECTIC_CLOUD_URL", fake_codex_and_supabase.base_url)
    monkeypatch.setenv("DIALECTIC_CLOUD_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # force title fallback

    # ── 2. Build an artifact pointing at the seed wav ──
    artifact = RecordingArtifact(
        audio_path=Path(seed_audio_fixture),
        duration_seconds=30.0,
        sample_rate=16000,
        channels=1,
    )

    # ── 3. Stub the heavy stages. Trim copies the seed file to a
    #      "trimmed" path (so invariant #2 — upload uses trimmed — is
    #      exercised even with trim mocked). Transcribe returns the
    #      canonical transcript.
    trimmed_path = tmp_path / "trimmed.wav"
    trimmed_path.write_bytes(Path(seed_audio_fixture).read_bytes())

    def fake_trim(self):
        self.result.trimmed_audio = trimmed_path
        self.result.trim_intervals = [SpeechInterval(0.0, 28.0)]
        self.result.original_duration_s = 30.0
        self.result.trimmed_duration_s = 28.0
        return TrimResult(
            input_path=self.artifact.audio_path,
            output_path=trimmed_path,
            original_duration_s=30.0,
            trimmed_duration_s=28.0,
            intervals=[SpeechInterval(0.0, 28.0)],
        )

    def fake_transcribe(self):
        result = TranscriptionResult(
            text=_CANONICAL_TRANSCRIPT,
            segments=[
                TranscriptSegment(0.0, 28.0, _CANONICAL_TRANSCRIPT),
            ],
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
        "dialectic.recording_pipeline.RecordingPipeline._stage_trim",
        fake_trim,
    )
    monkeypatch.setattr(
        "dialectic.recording_pipeline.RecordingPipeline._stage_transcribe",
        fake_transcribe,
    )

    # ── 4. Run the pipeline synchronously ──
    pipeline = RecordingPipeline(artifact)
    failures: list[tuple[str, str]] = []
    pipeline.stage_failed.connect(lambda n, m: failures.append((n, m)))
    pipeline.run()

    assert failures == [], f"pipeline stage failure: {failures}"
    assert pipeline.result.upload_id is not None, "upload failed"
    upload_id = pipeline.result.upload_id

    # ── 5. Run ingest-from-codex against the SQLite fake ──
    from noosphere.codex_bridge import ingest_from_codex

    result = ingest_from_codex(
        upload_id=upload_id,
        use_llm=False,
        dry_run=False,
        codex_db_url=sqlite_codex_with_api_hookup.url,
    )
    assert result.num_conclusions_written >= 2

    # ── 6. Conclusions reference the transcript's substantive content ──
    rows = sqlite_codex_with_api_hookup.conn.execute(
        'SELECT text FROM "Conclusion"'
    ).fetchall()
    assert rows, "no Conclusion rows were written"
    texts = [r[0].lower() for r in rows]
    assert any(
        "inquiry" in t or "credentialing" in t or "narrative" in t
        for t in texts
    ), (
        "expected at least one conclusion to reference the transcript's "
        f"substantive content; got: {texts}"
    )

    # ── 7. The Upload row's extractionMethod + status match expectations ──
    r = sqlite_codex_with_api_hookup.conn.execute(
        'SELECT "extractionMethod", status FROM "Upload" WHERE id=?',
        (upload_id,),
    ).fetchone()
    assert r is not None
    assert (r[0] or "").startswith("dialectic-"), (
        f"extractionMethod should start with 'dialectic-' (set by Dialectic "
        f"upload) but got {r[0]!r}"
    )
    assert r[1] == "ingested"

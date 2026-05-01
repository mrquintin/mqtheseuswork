"""Transcript enrichment writes durable blurbs, headings, and chunks."""

from __future__ import annotations

import json

from noosphere.articles.transcript_enrichment import enrich_upload_transcript
from noosphere.currents._llm_client import LLMResponse


class FakeTranscriptClient:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *, system: str, user: str, max_tokens: int, temperature: float = 0.0) -> LLMResponse:
        self.calls += 1
        assert "Return only JSON" in system
        assert "[0]" in user
        return LLMResponse(
            text=json.dumps(
                {
                    "blurb": (
                        "This conversation frames the Codex as a durable memory surface for founder "
                        "judgment. The speakers distinguish raw discussion from publishable reasoning, "
                        "emphasizing that timestamps, speaker attribution, and stable anchors make prior "
                        "work easier to inspect, cite, and turn into firm-level conclusions."
                    ),
                    "sectionMarkers": [
                        {"chunkIndex": 0, "headingHint": "Memory as Infrastructure"},
                        {"chunkIndex": 2, "headingHint": "Publishable Judgment"},
                    ],
                }
            )
        )


def test_transcript_enrichment_persists_blurb_markers_and_chunks(
    fake_codex_db,
    codex_sqlite_url,
    upload_factory,
) -> None:
    upload_id = upload_factory(
        mime="text/plain",
        title="Fixture transcript",
        original_name="fixture.txt",
        text=(
            "[00:00:12] Michael: The Codex needs durable anchors for prior conversations.\n"
            "[00:01:30] Ada: Speaker labels make the reading surface inspectable.\n\n"
            "The publishable layer should summarize the work without hiding the raw transcript."
        ),
    )
    client = FakeTranscriptClient()

    result = enrich_upload_transcript(upload_id, codex_db_url=codex_sqlite_url, client=client)

    assert result.enriched is True
    assert result.chunk_count == 3
    assert result.section_markers == (
        (0, "Memory as Infrastructure"),
        (2, "Publishable Judgment"),
    )
    assert client.calls == 1

    upload = fake_codex_db.execute(
        'SELECT blurb FROM "Upload" WHERE id = ?',
        (upload_id,),
    ).fetchone()
    assert "durable memory surface" in upload["blurb"]

    chunks = fake_codex_db.execute(
        'SELECT id, "index", text, "startMs", "speakerLabel", "headingHint" '
        'FROM "UploadChunk" WHERE "uploadId" = ? ORDER BY "index"',
        (upload_id,),
    ).fetchall()
    assert [row["index"] for row in chunks] == [0, 1, 2]
    assert chunks[0]["startMs"] == 12_000
    assert chunks[0]["speakerLabel"] == "Michael"
    assert chunks[1]["startMs"] == 90_000
    assert chunks[1]["speakerLabel"] == "Ada"
    assert chunks[2]["headingHint"] == "Publishable Judgment"

    ids_before = [row["id"] for row in chunks]
    skipped = enrich_upload_transcript(upload_id, codex_db_url=codex_sqlite_url, client=client)
    ids_after = [
        row["id"]
        for row in fake_codex_db.execute(
            'SELECT id FROM "UploadChunk" WHERE "uploadId" = ? ORDER BY "index"',
            (upload_id,),
        ).fetchall()
    ]
    assert skipped.enriched is False
    assert skipped.skipped_reason == "already_enriched"
    assert client.calls == 1
    assert ids_after == ids_before


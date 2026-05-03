"""Transcript blurb and section-marker enrichment for Codex uploads."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg2.extras

from noosphere.codex_bridge import _db_safe, _open_codex_connection, _resolve_codex_db_url
from noosphere.currents._llm_client import LLMResponse, make_client


MAX_BLURB_CHARS = 900
MAX_HEADING_CHARS = 90
MAX_PROMPT_CHARS = 18_000
DEFAULT_SECTION_MIN = 6
DEFAULT_SECTION_MAX = 12

_TIMED_LINE_RE = re.compile(
    r"^\s*\[?(?P<ts>(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[\.,]\d{1,3})?)\]?\s*(?P<body>.*)$"
)
_VTT_RANGE_RE = re.compile(
    r"^\s*(?P<start>(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[\.,]\d{1,3})?)\s*-->\s*"
    r"(?P<end>(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[\.,]\d{1,3})?)"
)
_SPEAKER_RE = re.compile(r"^\s*(?P<label>[A-Za-z][A-Za-z0-9 ._\-']{0,60}):\s+(?P<body>.+)$")


@dataclass(frozen=True)
class ChunkDraft:
    index: int
    text: str
    start_ms: int | None = None
    end_ms: int | None = None
    speaker_label: str | None = None


@dataclass(frozen=True)
class TranscriptEnrichmentResult:
    upload_id: str
    chunk_count: int
    enriched: bool
    skipped_reason: str | None = None
    blurb: str | None = None
    section_markers: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class TranscriptEnrichmentBatchResult:
    dry_run: bool
    uploads_scanned: int
    uploads_enriched: int
    chunks_found: int
    skipped: dict[str, int]
    errors: tuple[str, ...] = ()
    organization_slug: str | None = None


def _new_cuid() -> str:
    return "c" + uuid.uuid4().hex[:24]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ms(raw: str) -> int | None:
    value = raw.strip().replace(",", ".")
    if not value:
        return None
    parts = value.split(":")
    try:
        seconds = float(parts[-1])
        minutes = int(parts[-2]) if len(parts) >= 2 else 0
        hours = int(parts[-3]) if len(parts) >= 3 else 0
    except (ValueError, IndexError):
        return None
    return int(round(((hours * 60 + minutes) * 60 + seconds) * 1000))


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("LLM response did not contain a JSON object") from None
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM response JSON was not an object")
    return payload


def _split_speaker(text: str) -> tuple[str | None, str]:
    match = _SPEAKER_RE.match(text.strip())
    if not match:
        return None, text.strip()
    return match.group("label").strip(), match.group("body").strip()


def split_upload_text_into_chunks(text: str) -> list[ChunkDraft]:
    """Split raw upload text into stable transcript/essay blocks."""

    chunks: list[ChunkDraft] = []
    paragraph: list[str] = []
    pending_start: int | None = None
    pending_end: int | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph, pending_start, pending_end
        body = " ".join(part.strip() for part in paragraph if part.strip()).strip()
        paragraph = []
        if not body:
            pending_start = None
            pending_end = None
            return
        speaker, clean = _split_speaker(body)
        chunks.append(
            ChunkDraft(
                index=len(chunks),
                text=clean,
                start_ms=pending_start,
                end_ms=pending_end,
                speaker_label=speaker,
            )
        )
        pending_start = None
        pending_end = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue

        range_match = _VTT_RANGE_RE.match(line)
        if range_match:
            flush_paragraph()
            pending_start = _parse_ms(range_match.group("start"))
            pending_end = _parse_ms(range_match.group("end"))
            continue

        timed_match = _TIMED_LINE_RE.match(line)
        if timed_match and timed_match.group("body").strip():
            ts = _parse_ms(timed_match.group("ts"))
            if ts is not None:
                flush_paragraph()
                speaker, clean = _split_speaker(timed_match.group("body"))
                chunks.append(
                    ChunkDraft(
                        index=len(chunks),
                        text=clean,
                        start_ms=ts,
                        end_ms=None,
                        speaker_label=speaker,
                    )
                )
                continue

        paragraph.append(line)

    flush_paragraph()

    if chunks:
        return chunks

    fallback = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
    return [
        ChunkDraft(index=i, text=re.sub(r"\s+", " ", part).strip())
        for i, part in enumerate(fallback)
    ]


def sync_upload_chunks(conn: Any, upload_id: str, text: str) -> list[dict[str, Any]]:
    """Persist chunks while preserving ids for unchanged index/text pairs."""

    drafts = split_upload_text_into_chunks(text)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        '''SELECT id, "index", text, "startMs", "endMs", "speakerLabel", "headingHint"
           FROM "UploadChunk"
           WHERE "uploadId" = %s
           ORDER BY "index" ASC''',
        (upload_id,),
    )
    existing_by_index = {int(row["index"]): row for row in cur.fetchall()}
    now = _utcnow()
    saved: list[dict[str, Any]] = []

    for draft in drafts:
        existing = existing_by_index.get(draft.index)
        same = (
            existing is not None
            and existing["text"] == draft.text
            and existing.get("startMs") == draft.start_ms
            and existing.get("endMs") == draft.end_ms
            and existing.get("speakerLabel") == draft.speaker_label
        )
        if same:
            saved.append(dict(existing))
            continue

        if existing is not None:
            cur.execute(
                'DELETE FROM "UploadChunk" WHERE "uploadId" = %s AND "index" = %s',
                (upload_id, draft.index),
            )

        chunk_id = _new_cuid()
        cur.execute(
            '''INSERT INTO "UploadChunk"
               (id, "uploadId", "index", text, "startMs", "endMs", "speakerLabel",
                "createdAt", "updatedAt")
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            (
                chunk_id,
                upload_id,
                draft.index,
                _db_safe(draft.text, cap=20_000),
                draft.start_ms,
                draft.end_ms,
                _db_safe(draft.speaker_label, cap=80) if draft.speaker_label else None,
                now,
                now,
            ),
        )
        saved.append(
            {
                "id": chunk_id,
                "index": draft.index,
                "text": draft.text,
                "startMs": draft.start_ms,
                "endMs": draft.end_ms,
                "speakerLabel": draft.speaker_label,
                "headingHint": None,
            }
        )

    if drafts:
        cur.execute(
            'DELETE FROM "UploadChunk" WHERE "uploadId" = %s AND "index" >= %s',
            (upload_id, len(drafts)),
        )
    else:
        cur.execute('DELETE FROM "UploadChunk" WHERE "uploadId" = %s', (upload_id,))

    conn.commit()
    return saved


def _llm_configured() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    try:
        from noosphere.config import get_settings

        settings = get_settings()
        return bool(getattr(settings, "llm_api_key", ""))
    except Exception:
        return False


def _chunk_prompt(chunks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for chunk in chunks:
        text = str(chunk["text"]).replace("\n", " ").strip()
        if len(text) > 420:
            text = text[:417].rstrip() + "..."
        prefix = f"[{chunk['index']}]"
        if chunk.get("startMs") is not None:
            prefix += f" @{int(chunk['startMs']) // 1000}s"
        if chunk.get("speakerLabel"):
            prefix += f" {chunk['speakerLabel']}:"
        lines.append(f"{prefix} {text}")
    rendered = "\n".join(lines)
    return rendered[:MAX_PROMPT_CHARS]


def _system_prompt() -> str:
    return (
        "You enrich uploaded transcripts and essays for a public-quality reading surface. "
        "Return only JSON. The blurb must be 60-100 words: concrete, non-promotional, "
        "and faithful to the uploaded piece. Pick the 6-12 most natural section "
        "boundaries unless the piece is shorter; section headings should be concise "
        "navigation labels, not clickbait."
    )


def _user_prompt(upload: dict[str, Any], chunks: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        [
            f"Upload title: {upload.get('title') or upload['id']}",
            f"Source type: {upload.get('sourceType') or ''}",
            "Chunks:",
            _chunk_prompt(chunks),
            (
                "Return JSON with this exact shape: "
                '{"blurb":"60-100 words","sectionMarkers":[{"chunkIndex":0,"headingHint":"Opening"}]}. '
                "Use chunkIndex values from the chunk list."
            ),
        ]
    )


async def _complete(client: Any, *, system: str, user: str) -> LLMResponse:
    result = client.complete(system=system, user=user, max_tokens=900, temperature=0.0)
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, LLMResponse):
        return result
    text = getattr(result, "text", None)
    if isinstance(text, str):
        return LLMResponse(text=text)
    if isinstance(result, str):
        return LLMResponse(text=result)
    raise RuntimeError(f"Unsupported transcript enrichment LLM response: {type(result)!r}")


def _parse_payload(raw: str, chunk_count: int) -> tuple[str, list[tuple[int, str]]]:
    payload = _extract_json_object(raw)
    blurb = str(payload.get("blurb") or "").strip()
    if not blurb:
        raise RuntimeError("transcript enrichment payload missing blurb")
    markers_raw = payload.get("sectionMarkers") or payload.get("sections") or []
    if not isinstance(markers_raw, list):
        raise RuntimeError("transcript enrichment sectionMarkers must be a list")

    markers: list[tuple[int, str]] = []
    seen: set[int] = set()
    for item in markers_raw:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("chunkIndex"))
        except (TypeError, ValueError):
            continue
        heading = str(item.get("headingHint") or item.get("heading") or "").strip()
        if idx < 0 or idx >= chunk_count or not heading or idx in seen:
            continue
        markers.append((idx, heading[:MAX_HEADING_CHARS]))
        seen.add(idx)
    if not markers and chunk_count:
        markers.append((0, "Opening"))
    return blurb[:MAX_BLURB_CHARS], markers[:DEFAULT_SECTION_MAX]


def _fallback_payload(upload: dict[str, Any], chunks: list[dict[str, Any]]) -> tuple[str, list[tuple[int, str]]]:
    text = " ".join(str(chunk["text"]).strip() for chunk in chunks)
    words = text.split()
    blurb = " ".join(words[:95]).strip()
    if len(words) > 95:
        blurb += "..."
    if not blurb:
        blurb = str(upload.get("title") or "Untitled upload")
    step = max(1, len(chunks) // DEFAULT_SECTION_MIN)
    markers = []
    for idx in range(0, len(chunks), step):
        markers.append((idx, "Opening" if idx == 0 else f"Section {len(markers) + 1}"))
        if len(markers) >= min(DEFAULT_SECTION_MIN, len(chunks)):
            break
    return blurb[:MAX_BLURB_CHARS], markers


def enrich_upload_transcript(
    upload_id: str,
    *,
    codex_db_url: Optional[str] = None,
    force: bool = False,
    client: Any | None = None,
) -> TranscriptEnrichmentResult:
    """Seed chunks and persist a blurb plus section heading hints."""

    url = _resolve_codex_db_url(codex_db_url)
    conn = _open_codex_connection(url)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            '''SELECT id, title, "sourceType", "mimeType", "textContent", blurb
               FROM "Upload"
               WHERE id = %s''',
            (upload_id,),
        )
        upload = cur.fetchone()
        if upload is None:
            raise RuntimeError(f"Upload {upload_id} not found in the Codex DB.")
        text = str(upload.get("textContent") or "")
        if not text.strip():
            return TranscriptEnrichmentResult(
                upload_id=upload_id,
                chunk_count=0,
                enriched=False,
                skipped_reason="no_text",
            )

        from noosphere.relevant_text import select_pertinent_text

        pertinent = select_pertinent_text(
            text,
            source_type=upload.get("sourceType") or "written",
            mime_type=upload.get("mimeType") or "",
        )
        text = pertinent.text

        chunks = sync_upload_chunks(conn, upload_id, text)
        if not chunks:
            return TranscriptEnrichmentResult(
                upload_id=upload_id,
                chunk_count=0,
                enriched=False,
                skipped_reason="no_chunks",
            )
        try:
            from noosphere.embedding_pipeline import embed_chunk_with_store
            from noosphere.store import Store

            embedding_store = Store.from_database_url(url)
            embedded_chunks = 0
            for chunk in chunks:
                if embed_chunk_with_store(
                    embedding_store,
                    chunk_id=str(chunk["id"]),
                    text=str(chunk["text"]),
                ):
                    embedded_chunks += 1
            print(
                "transcript_chunk_embeddings "
                f"attempted={len(chunks)} embedded={embedded_chunks}"
            )
        except Exception as embed_exc:
            print(f"transcript_chunk_embedding_followup_failed: {type(embed_exc).__name__}: {embed_exc}")

        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            '''SELECT COUNT(*) AS count
               FROM "UploadChunk"
               WHERE "uploadId" = %s AND "headingHint" IS NOT NULL''',
            (upload_id,),
        )
        heading_count = int(cur.fetchone()["count"])
        if not force and str(upload.get("blurb") or "").strip() and heading_count > 0:
            return TranscriptEnrichmentResult(
                upload_id=upload_id,
                chunk_count=len(chunks),
                enriched=False,
                skipped_reason="already_enriched",
                blurb=str(upload.get("blurb")),
            )

        if client is None and not _llm_configured():
            blurb, markers = _fallback_payload(upload, chunks)
        else:
            client = client or make_client()
            response = asyncio.run(
                _complete(
                    client,
                    system=_system_prompt(),
                    user=_user_prompt(upload, chunks),
                )
            )
            blurb, markers = _parse_payload(response.text, len(chunks))

        cur.execute('UPDATE "Upload" SET blurb = %s WHERE id = %s', (_db_safe(blurb, cap=MAX_BLURB_CHARS), upload_id))
        cur.execute('UPDATE "UploadChunk" SET "headingHint" = NULL WHERE "uploadId" = %s', (upload_id,))
        for chunk_index, heading in markers:
            cur.execute(
                '''UPDATE "UploadChunk"
                   SET "headingHint" = %s, "updatedAt" = %s
                   WHERE "uploadId" = %s AND "index" = %s''',
                (_db_safe(heading, cap=MAX_HEADING_CHARS), _utcnow(), upload_id, chunk_index),
            )
        conn.commit()
        return TranscriptEnrichmentResult(
            upload_id=upload_id,
            chunk_count=len(chunks),
            enriched=True,
            blurb=blurb,
            section_markers=tuple(markers),
        )
    finally:
        conn.close()


def _has_column(cur: Any, table: str, column: str) -> bool:
    try:
        cur.execute(
            '''SELECT 1
               FROM information_schema.columns
               WHERE table_name = %s AND column_name = %s
               LIMIT 1''',
            (table, column),
        )
        return cur.fetchone() is not None
    except Exception:
        try:
            cur.execute(f'PRAGMA table_info("{table}")')
            return any(
                (row["name"] if isinstance(row, dict) else row[1]) == column
                for row in cur.fetchall()
            )
        except Exception:
            return False


def _organization_id_for_slug(cur: Any, slug: str) -> str:
    cur.execute('SELECT id FROM "Organization" WHERE slug = %s', (slug,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"Organization slug not found: {slug}")
    return row["id"] if isinstance(row, dict) else row[0]


def _candidate_query(has_deleted_at: bool) -> str:
    deleted_filter = 'AND "deletedAt" IS NULL' if has_deleted_at else ""
    return f'''SELECT id, title, "sourceType", "mimeType", "textContent"
               FROM "Upload"
               WHERE "textContent" IS NOT NULL
                 AND LENGTH(TRIM("textContent")) >= 40
                 {deleted_filter}
                 AND (%s IS NULL OR "organizationId" = %s)
               ORDER BY "createdAt" ASC
               LIMIT %s'''


def enrich_all_upload_transcripts(
    *,
    codex_db_url: Optional[str] = None,
    organization_slug: Optional[str] = None,
    limit: int = 500,
    force: bool = False,
    dry_run: bool = True,
    client: Any | None = None,
) -> TranscriptEnrichmentBatchResult:
    """Backfill explorable chunks, blurbs, and headings for existing uploads."""

    url = _resolve_codex_db_url(codex_db_url)
    conn = _open_codex_connection(url)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        organization_id = (
            _organization_id_for_slug(cur, organization_slug)
            if organization_slug
            else None
        )
        has_deleted_at = _has_column(cur, "Upload", "deletedAt")
        cur.execute(
            _candidate_query(has_deleted_at),
            (organization_id, organization_id, int(limit)),
        )
        uploads = list(cur.fetchall())
    finally:
        conn.close()

    skipped: dict[str, int] = {}
    errors: list[str] = []
    chunks_found = 0
    uploads_enriched = 0

    if dry_run:
        from noosphere.relevant_text import select_pertinent_text

        for upload in uploads:
            pertinent = select_pertinent_text(
                str(upload.get("textContent") or ""),
                source_type=upload.get("sourceType") or "written",
                mime_type=upload.get("mimeType") or "",
            )
            chunks_found += len(split_upload_text_into_chunks(pertinent.text))
        return TranscriptEnrichmentBatchResult(
            dry_run=True,
            uploads_scanned=len(uploads),
            uploads_enriched=0,
            chunks_found=chunks_found,
            skipped={},
            errors=(),
            organization_slug=organization_slug,
        )

    for upload in uploads:
        upload_id = str(upload["id"])
        try:
            result = enrich_upload_transcript(
                upload_id,
                codex_db_url=url,
                force=force,
                client=client,
            )
            chunks_found += result.chunk_count
            if result.enriched:
                uploads_enriched += 1
            elif result.skipped_reason:
                skipped[result.skipped_reason] = skipped.get(result.skipped_reason, 0) + 1
        except Exception as exc:
            errors.append(f"{upload_id}:{type(exc).__name__}: {exc}")

    return TranscriptEnrichmentBatchResult(
        dry_run=False,
        uploads_scanned=len(uploads),
        uploads_enriched=uploads_enriched,
        chunks_found=chunks_found,
        skipped=skipped,
        errors=tuple(errors),
        organization_slug=organization_slug,
    )

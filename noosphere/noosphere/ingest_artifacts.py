"""
Markdown / plain-text / transcript artifact ingestion (Phase 2).

Imported from `noosphere.ingester` for a single public surface.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from noosphere.ids import artifact_id_from_bytes, artifact_id_from_file, chunk_id
from noosphere.models import Artifact, Chunk, Claim, Speaker
from noosphere.observability import get_logger

logger = get_logger(__name__)

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[misc, assignment]

MIN_CHUNK = 40
MAX_CHUNK = 2000


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _parse_frontmatter_markdown(raw: str) -> tuple[dict[str, Any], str]:
    if not raw.startswith("---\n"):
        return {}, raw
    end = raw.find("\n---\n", 4)
    if end == -1:
        return {}, raw
    fm_block = raw[4:end]
    body = raw[end + 5 :]
    meta: dict[str, Any] = {}
    if yaml is not None:
        try:
            loaded = yaml.safe_load(fm_block)
            if isinstance(loaded, dict):
                meta = loaded
        except yaml.YAMLError:
            meta = {}
    else:
        for line in fm_block.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


def _split_sentences(paragraph: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+", paragraph.strip())


def _pack_paragraph(
    paragraph: str,
    base_meta: dict[str, str],
    offset_base: int,
    artifact_id: str,
    emit: Callable[[Chunk], None],
) -> int:
    """Emit one or more chunks from a paragraph; returns next byte offset."""
    p = paragraph.strip()
    if len(p) < MIN_CHUNK:
        return offset_base + len(paragraph) + 2
    parts: list[str] = []
    if len(p) <= MAX_CHUNK:
        parts = [p]
    else:
        buf = ""
        for sent in _split_sentences(p):
            if not sent:
                continue
            if len(buf) + len(sent) + 1 <= MAX_CHUNK:
                buf = f"{buf} {sent}".strip() if buf else sent
            else:
                if len(buf) >= MIN_CHUNK:
                    parts.append(buf)
                buf = sent
        if len(buf) >= MIN_CHUNK:
            parts.append(buf)
    cursor = offset_base
    for piece in parts:
        if len(piece) < MIN_CHUNK:
            continue
        start = cursor
        end = start + len(piece)
        cid = chunk_id(artifact_id, start, end)
        emit(
            Chunk(
                id=cid,
                artifact_id=artifact_id,
                start_offset=start,
                end_offset=end,
                text=piece,
                metadata=dict(base_meta),
            )
        )
        cursor = end + 1
    return offset_base + len(paragraph) + 2


def _chunk_markdown_body(body: str, artifact_id: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    heading = ""
    offset = 0
    paragraphs = re.split(r"\n\s*\n+", body)
    for para in paragraphs:
        stripped = para.strip()
        if not stripped:
            offset += len(para) + 2
            continue
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            offset += len(para) + 2
            continue
        meta = {"section_heading": heading} if heading else {}

        def emit(ch: Chunk) -> None:
            chunks.append(ch)

        offset = _pack_paragraph(para, meta, offset, artifact_id, emit)
    return chunks


def ingest_markdown(path: str | Path, store: Any | None = None) -> Artifact:
    p = Path(path)
    raw_bytes = _read_bytes(p)
    aid = artifact_id_from_bytes(raw_bytes)
    text = raw_bytes.decode("utf-8", errors="replace")
    meta, body = _parse_frontmatter_markdown(text)
    title = str(meta.get("title", "") or p.stem)
    author = str(meta.get("author", meta.get("authors", "")) or "")
    sd: date | None = None
    for key in ("date", "published", "pub_date"):
        if key in meta and meta[key]:
            try:
                sd = date.fromisoformat(str(meta[key])[:10])
            except ValueError:
                sd = None
            if sd:
                break
    import hashlib

    art = Artifact(
        id=aid,
        uri=str(p.resolve()),
        mime_type="text/markdown",
        byte_length=len(raw_bytes),
        content_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        title=title,
        author=author,
        source_date=sd,
    )
    chunks = _chunk_markdown_body(body, aid)
    if store is not None:
        store.put_artifact(art)
        for c in chunks:
            store.put_chunk(c)
    logger.info("ingest_markdown", artifact_id=aid, num_chunks=len(chunks))
    return art


def ingest_text(path: str | Path, store: Any | None = None) -> Artifact:
    p = Path(path)
    raw_bytes = _read_bytes(p)
    aid = artifact_id_from_file(p)
    body = raw_bytes.decode("utf-8", errors="replace")
    import hashlib

    art = Artifact(
        id=aid,
        uri=str(p.resolve()),
        mime_type="text/plain",
        byte_length=len(raw_bytes),
        content_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        title=p.stem,
    )
    chunks: list[Chunk] = []
    offset = 0
    for para in re.split(r"\n\s*\n+", body):
        if not para.strip():
            offset += len(para) + 2
            continue

        def emit(ch: Chunk) -> None:
            chunks.append(ch)

        offset = _pack_paragraph(para, {}, offset, aid, emit)
    if store is not None:
        store.put_artifact(art)
        for c in chunks:
            store.put_chunk(c)
    logger.info("ingest_text", artifact_id=aid, num_chunks=len(chunks))
    return art


def _parse_webvtt(text: str) -> list[tuple[Optional[float], Optional[float], str, str]]:
    """Return list of (start_s, end_s, cue_text, raw_block)."""
    cues: list[tuple[Optional[float], Optional[float], str, str]] = []
    if "WEBVTT" not in text[:200].upper():
        return cues
    blocks = re.split(r"\n\s*\n+", text.strip())
    ts_re = re.compile(
        r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})"
    )

    def to_sec(h, m, s, ms):
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

    for block in blocks:
        if not block.strip() or block.strip().upper().startswith("WEBVTT"):
            continue
        lines = block.strip().splitlines()
        if not lines:
            continue
        m = ts_re.search(lines[0])
        if not m:
            continue
        t0 = to_sec(m.group(1), m.group(2), m.group(3), m.group(4))
        t1 = to_sec(m.group(5), m.group(6), m.group(7), m.group(8))
        cue_text = "\n".join(lines[1:]).strip()
        cues.append((t0, t1, cue_text, block))
    return cues


def _dialectic_claims_from_jsonl(raw: str) -> list[Claim]:
    claims: list[Claim] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj.get("claims"), list):
            for item in obj["claims"]:
                if isinstance(item, dict) and item.get("text"):
                    claims.append(
                        _claim_from_dialectic_obj(item, obj.get("episode_id", "dialectic"))
                    )
                elif isinstance(item, str):
                    claims.append(
                        Claim(
                            text=item,
                            speaker=Speaker(name="unknown"),
                            episode_id=str(obj.get("session_id", "dialectic")),
                            episode_date=date.today(),
                        )
                    )
        elif obj.get("text") and (
            "speaker" in obj or "role" in obj or "author" in obj
        ):
            claims.append(_claim_from_dialectic_obj(obj, obj.get("episode_id", "dialectic")))
    return claims


def _decode_embedding_b64(obj: dict[str, Any]) -> list[float] | None:
    raw_emb = obj.get("embedding")
    if isinstance(raw_emb, str) and raw_emb.strip():
        try:
            buf = base64.b64decode(raw_emb.encode("ascii"))
            import struct

            n = len(buf) // 4
            return list(struct.unpack(f"{n}f", buf))
        except Exception:
            return None
    if isinstance(raw_emb, list) and raw_emb:
        try:
            return [float(x) for x in raw_emb]
        except (TypeError, ValueError):
            return None
    return None


def _claim_from_dialectic_obj(obj: dict[str, Any], episode_id: str) -> Claim:
    spk = (
        str(obj.get("speaker") or obj.get("author") or obj.get("role") or "unknown")
    )
    when = date.today()
    if obj.get("timestamp"):
        try:
            when = datetime.fromisoformat(str(obj["timestamp"])[:10]).date()
        except ValueError:
            when = date.today()
    emb = _decode_embedding_b64(obj)
    contra = obj.get("contradictions") or obj.get("contradiction_pair_ids") or []
    evp: list[str] = [str(x) for x in contra] if isinstance(contra, list) else []
    cid = obj.get("claim_id")
    if cid is not None and str(cid).strip():
        return Claim(
            id=str(cid).strip(),
            text=str(obj["text"]),
            speaker=Speaker(name=spk),
            episode_id=str(episode_id),
            episode_date=when,
            chunk_id=str(obj.get("chunk_id", "")),
            embedding=emb,
            evidence_pointers=evp,
        )
    return Claim(
        text=str(obj["text"]),
        speaker=Speaker(name=spk),
        episode_id=str(episode_id),
        episode_date=when,
        chunk_id=str(obj.get("chunk_id", "")),
        embedding=emb,
        evidence_pointers=evp,
    )


def ingest_dialectic_session_jsonl(
    path: str | Path,
    store: Any,
    *,
    episode_id: str = "dialectic",
    episode_date: date | None = None,
    embedding_model: str = "all-MiniLM-L6-v2",
) -> tuple[Artifact, int]:
    """
    Ingest a Dialectic ``session.jsonl`` (one claim per line: timestamp, speaker,
    text, base64 float32 embedding, contradictions, topic_cluster_id).

    Persists claims, optional embeddings, and topic membership for Noosphere.
    """
    from noosphere.mitigations.ingestion_guard import apply_ingestion_flags_to_claim

    p = Path(path)
    raw_bytes = p.read_bytes()
    aid = artifact_id_from_file(p)
    art = Artifact(
        id=aid,
        uri=str(p.resolve()),
        mime_type="application/x-ndjson",
        byte_length=len(raw_bytes),
        content_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        title=p.stem,
    )
    store.put_artifact(art)
    n = 0
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not obj.get("text"):
                continue
            obj_ep = str(obj.get("episode_id", episode_id))
            cl = _claim_from_dialectic_obj(obj, obj_ep)
            if episode_date is not None:
                cl = cl.model_copy(update={"episode_date": episode_date})
            apply_ingestion_flags_to_claim(cl)
            store.put_claim(cl)
            if cl.embedding:
                th = hashlib.sha256(cl.text.encode("utf-8")).hexdigest()
                eid = f"emb_{cl.id}"
                store.put_embedding(
                    embedding_id=eid,
                    model_name=embedding_model,
                    text_sha256=th,
                    vector=cl.embedding,
                    ref_claim_id=cl.id,
                )
            tid = str(obj.get("topic_cluster_id", "")).strip()
            if tid:
                store.put_claim_topic(cl.id, tid)
            n += 1
    logger.info(
        "ingest_dialectic_session_jsonl",
        artifact_id=aid,
        num_claims=n,
        path=str(p),
    )
    return art, n


def ingest_transcript(
    path: str | Path, store: Any | None = None
) -> tuple[Artifact, list[Chunk], list[Claim]]:
    """
    Returns (artifact, chunks, dialectic_claims).

    For Dialectic JSONL sessions, `chunks` is empty and `dialectic_claims` is filled.
    """
    p = Path(path)
    raw_bytes = _read_bytes(p)
    aid = artifact_id_from_file(p)
    import hashlib

    text = raw_bytes.decode("utf-8", errors="replace")
    claims: list[Claim] = []
    chunks: list[Chunk] = []

    if p.suffix.lower() == ".jsonl" or "dialectic" in p.name.lower():
        from noosphere.mitigations.ingestion_guard import apply_ingestion_flags_to_claim

        claims = _dialectic_claims_from_jsonl(text)
        art = Artifact(
            id=aid,
            uri=str(p.resolve()),
            mime_type="application/x-ndjson",
            byte_length=len(raw_bytes),
            content_sha256=hashlib.sha256(raw_bytes).hexdigest(),
            title=p.stem,
        )
        if store is not None:
            store.put_artifact(art)
            for cl in claims:
                apply_ingestion_flags_to_claim(cl)
                store.put_claim(cl)
        logger.info("ingest_transcript_dialectic", artifact_id=aid, num_claims=len(claims))
        return art, [], claims

    if p.suffix.lower() == ".vtt" or text.lstrip().upper().startswith("WEBVTT"):
        from noosphere.config import get_settings
        from noosphere.mitigations.embedding_text import (
            normalize_for_embedding,
            zero_width_count,
        )
        from noosphere.mitigations.ingestion_guard import scan_ingestion_text

        cues = _parse_webvtt(text)
        offset = 0
        for t0, t1, cue, _raw in cues:
            if len(cue) < MIN_CHUNK:
                continue
            spk = "unknown"
            if ":" in cue.split("\n", 1)[0]:
                first_line = cue.split("\n", 1)[0]
                if re.match(r"^[A-Za-z0-9 _.-]{1,40}:", first_line):
                    spk, cue_body = first_line.split(":", 1)
                    spk, cue = spk.strip(), cue_body.strip()
            start = offset
            end = start + len(cue)
            cid = chunk_id(aid, start, end)
            md: dict[str, str] = {"speaker": spk}
            if t0 is not None:
                md["start_seconds"] = str(t0)
            if t1 is not None:
                md["end_seconds"] = str(t1)
            if get_settings().ingestion_guard_enabled:
                inj = scan_ingestion_text(normalize_for_embedding(cue), enabled=True)
                if inj.quarantine:
                    md["ingestion_quarantine"] = "1"
                    md["ingestion_guard_signals"] = ",".join(inj.signals)
            if zero_width_count(cue) >= 4:
                md["ingestion_quarantine"] = "1"
                prev = md.get("ingestion_guard_signals", "")
                extra = "zero_width_cluster" if not prev else f"{prev},zero_width_cluster"
                md["ingestion_guard_signals"] = extra
            chunks.append(
                Chunk(
                    id=cid,
                    artifact_id=aid,
                    start_offset=start,
                    end_offset=end,
                    text=cue,
                    metadata=md,
                )
            )
            offset = end + 2
        art = Artifact(
            id=aid,
            uri=str(p.resolve()),
            mime_type="text/vtt",
            byte_length=len(raw_bytes),
            content_sha256=hashlib.sha256(raw_bytes).hexdigest(),
            title=p.stem,
        )
        if store is not None:
            store.put_artifact(art)
            for c in chunks:
                store.put_chunk(c)
        logger.info("ingest_transcript_vtt", artifact_id=aid, num_chunks=len(chunks))
        return art, chunks, []

    # Plain speaker-tagged text: reuse TranscriptParser (lazy import avoids cycles)
    from noosphere.ingester import TranscriptParser

    parser = TranscriptParser()
    segs = parser.parse(text, episode_id=p.stem)
    offset = 0
    for seg in segs:
        body = seg.text.strip()
        if len(body) < MIN_CHUNK:
            offset += len(body) + 20
            continue
        spk = seg.speaker.name

        def emit(ch: Chunk) -> None:
            chunks.append(ch)

        meta = {"speaker": spk}
        if seg.start_time is not None:
            meta["start_seconds"] = str(seg.start_time)
        offset = _pack_paragraph(body, meta, offset, aid, emit)
    art = Artifact(
        id=aid,
        uri=str(p.resolve()),
        mime_type="text/plain",
        byte_length=len(raw_bytes),
        content_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        title=p.stem,
    )
    if store is not None:
        store.put_artifact(art)
        for c in chunks:
            store.put_chunk(c)
    logger.info("ingest_transcript_plain", artifact_id=aid, num_chunks=len(chunks))
    return art, chunks, []

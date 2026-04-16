"""
External literature ingestion — connectors produce ``Artifact`` + ``Chunk`` rows,
``Claim`` rows with ``claim_origin=literature`` (first author as ``Voice``).

Copyright: respect ``license_status``; full text is only stored when access is lawful.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

import requests

from noosphere.ids import artifact_id_from_bytes, chunk_id
from noosphere.models import Artifact, Chunk, Claim, ClaimOrigin, ClaimType, InputSourceType, Speaker
from noosphere.observability import get_logger
from noosphere.store import Store
from noosphere.voices import ensure_voice_profile, register_voice_corpus_artifact

logger = get_logger(__name__)

NS = {"a": "http://www.w3.org/2005/Atom"}


@runtime_checkable
class SourceConnector(Protocol):
    name: str

    def ingest(self, store: Store, **kwargs: Any) -> list[str]:
        """Return list of new artifact ids."""
        ...


def _first_author(author_field: str) -> str:
    s = (author_field or "").strip()
    if not s:
        return "Unknown author"
    part = re.split(r"[,;]|\band\b", s, maxsplit=1, flags=re.I)[0].strip()
    return part or "Unknown author"


def _section_type_for_paragraph(para: str) -> str:
    u = para.strip()[:80].upper()
    if u.startswith("ABSTRACT"):
        return "abstract"
    if u.startswith("INTRODUCTION") or u.startswith("1 INTRODUCTION"):
        return "introduction"
    if "METHOD" in u[:40]:
        return "methods"
    if "RESULT" in u[:40]:
        return "results"
    if "CONCLUSION" in u[:40]:
        return "conclusion"
    if "REFERENCE" in u[:40]:
        return "references"
    return "body"


def extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pypdf is required for PDF ingestion") from e
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text() or ""
        if t.strip():
            parts.append(t)
    return "\n\n".join(parts)


def _chunks_from_text(
    text: str,
    artifact_id: str,
    *,
    max_chars: int = 1800,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    offset = 0
    for para in re.split(r"\n\s*\n+", text):
        p = para.strip()
        if len(p) < 80:
            offset += len(para) + 2
            continue
        section = _section_type_for_paragraph(p)
        while p:
            piece = p[:max_chars]
            p = p[max_chars:]
            start = offset
            end = start + len(piece)
            cid = chunk_id(artifact_id, start, end)
            chunks.append(
                Chunk(
                    id=cid,
                    artifact_id=artifact_id,
                    start_offset=start,
                    end_offset=end,
                    text=piece,
                    metadata={"section_type": section},
                )
            )
            offset = end + 2
        offset += 2
    return chunks


def _claims_from_chunks(
    store: Store,
    chunks: list[Chunk],
    *,
    voice_id: str,
    voice_name: str,
    artifact_id: str,
    pub_date: date,
) -> int:
    spk = Speaker(name=voice_name, role="author")
    n = 0
    for ch in chunks:
        if len(ch.text.strip()) < 60:
            continue
        cid = f"lit_{artifact_id[:8]}_{ch.id}_{uuid.uuid4().hex[:6]}"
        c = Claim(
            id=cid,
            text=ch.text.strip()[:4000],
            speaker=spk,
            episode_id=f"literature:{artifact_id}",
            episode_date=pub_date,
            claim_type=ClaimType.METHODOLOGICAL,
            chunk_id=ch.id,
            segment_context=ch.text[:500],
            claim_origin=ClaimOrigin.LITERATURE,
            voice_id=voice_id,
            source_type=InputSourceType.EXTERNAL,
            source_id=artifact_id,
            source_span_start=ch.start_offset,
            source_span_end=ch.end_offset,
        )
        store.put_claim(c)
        n += 1
    return n


@dataclass
class LiteratureIngestResult:
    artifact_id: str
    voice_id: str
    claims_written: int


def ingest_literature_text(
    store: Store,
    *,
    title: str,
    author: str,
    body: str,
    connector: str,
    license_status: str,
    pub_date: Optional[date] = None,
    uri: str = "",
    mime_type: str = "text/plain",
) -> LiteratureIngestResult:
    raw = body.encode("utf-8", errors="replace")
    if not raw.strip():
        raw = f"{title}|{uri}|{connector}".encode("utf-8", errors="replace")
    aid = artifact_id_from_bytes(raw)
    voice_name = _first_author(author)
    voice = ensure_voice_profile(store, voice_name, copyright_status=f"literature:{connector}")
    voice = register_voice_corpus_artifact(store, voice, aid)
    pd = pub_date or date.today()
    art = Artifact(
        id=aid,
        uri=uri or f"literature:{connector}:{aid}",
        mime_type=mime_type,
        byte_length=len(raw),
        content_sha256=hashlib.sha256(raw).hexdigest(),
        title=title,
        author=author,
        source_date=pd,
        license_status=license_status,
        literature_connector=connector,
    )
    store.put_artifact(art)
    chunks = _chunks_from_text(body, aid)
    for ch in chunks:
        store.put_chunk(ch)
    n = _claims_from_chunks(store, chunks, voice_id=voice.id, voice_name=voice.canonical_name, artifact_id=aid, pub_date=pd)
    logger.info("literature_ingested", artifact_id=aid, connector=connector, claims=n)
    return LiteratureIngestResult(aid, voice.id, n)


class LocalPDFConnector:
    name = "local_pdf"

    def ingest(
        self,
        store: Store,
        *,
        path: str | Path,
        license_status: str = "firm_licensed",
        title: str = "",
        author: str = "",
        pub_date: Optional[date] = None,
    ) -> list[str]:
        p = Path(path)
        text = extract_pdf_text(p)
        if license_status == "restricted_metadata_only":
            text = text[:0]
        meta_path = p.with_suffix(".json")
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                title = str(meta.get("title", title or p.stem))
                author = str(meta.get("author", author or ""))
                if meta.get("date"):
                    pub_date = date.fromisoformat(str(meta["date"])[:10])
            except (json.JSONDecodeError, ValueError):
                pass
        if not title:
            title = p.stem
        res = ingest_literature_text(
            store,
            title=title,
            author=author or "Unknown",
            body=text or "(no extractable text — add OCR or text layer)",
            connector=self.name,
            license_status=license_status,
            pub_date=pub_date,
            uri=str(p.resolve()),
            mime_type="application/pdf",
        )
        return [res.artifact_id]


class ManualConnector:
    name = "manual"

    def ingest(
        self,
        store: Store,
        *,
        path: str | Path,
        license_status: str = "firm_licensed",
        title: str = "",
        author: str = "",
        pub_date: Optional[date] = None,
    ) -> list[str]:
        p = Path(path)
        suf = p.suffix.lower()
        if suf == ".pdf":
            return LocalPDFConnector().ingest(
                store, path=p, license_status=license_status, title=title, author=author, pub_date=pub_date
            )
        body = p.read_text(encoding="utf-8", errors="replace")
        res = ingest_literature_text(
            store,
            title=title or p.stem,
            author=author or "Unknown",
            body=body,
            connector=self.name,
            license_status=license_status,
            pub_date=pub_date,
            uri=str(p.resolve()),
            mime_type="text/markdown" if suf in {".md", ".markdown"} else "text/plain",
        )
        return [res.artifact_id]


class ArxivConnector:
    name = "arxiv"

    def ingest(
        self,
        store: Store,
        *,
        search_query: str = "cat:physics.soc-ph",
        max_results: int = 5,
        full_text: bool = False,
    ) -> list[str]:
        """Fetch arXiv Atom API; stores abstract (and optional PDF text when ``full_text``)."""
        url = "https://export.arxiv.org/api/query"
        r = requests.get(
            url,
            params={"search_query": search_query, "start": 0, "max_results": max_results},
            timeout=60,
        )
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ids_out: list[str] = []
        for entry in root.findall("a:entry", NS):
            title_el = entry.find("a:title", NS)
            title = (title_el.text or "").strip().replace("\n", " ")
            published = entry.find("a:published", NS)
            pd: Optional[date] = None
            if published is not None and published.text:
                try:
                    pd = date.fromisoformat(published.text[:10])
                except ValueError:
                    pd = None
            authors = [a.find("a:name", NS).text or "" for a in entry.findall("a:author", NS) if a.find("a:name", NS) is not None]
            author = "; ".join(authors) if authors else ""
            summary_el = entry.find("a:summary", NS)
            summary = (summary_el.text or "").strip() if summary_el is not None else ""
            id_el = entry.find("a:id", NS)
            arxiv_url = (id_el.text or "").strip() if id_el is not None else ""
            body = f"URL: {arxiv_url}\n\nAbstract:\n{summary}"
            if full_text and arxiv_url:
                m = re.search(r"arxiv\.org/abs/([^/]+)", arxiv_url)
                if m:
                    aid_pdf = m.group(1)
                    pdf_url = f"https://arxiv.org/pdf/{aid_pdf}.pdf"
                    try:
                        pr = requests.get(pdf_url, timeout=120)
                        pr.raise_for_status()
                        tmp = Path(tempfile.gettempdir()) / f"arxiv_{aid_pdf}.pdf"
                        tmp.write_bytes(pr.content)
                        body = extract_pdf_text(tmp)
                    except Exception as e:
                        logger.warning("arxiv_pdf_fetch_failed", error=str(e))
            res = ingest_literature_text(
                store,
                title=title or "arXiv item",
                author=author,
                body=body,
                connector=self.name,
                license_status="open_access",
                pub_date=pd,
                uri=arxiv_url,
                mime_type="application/pdf" if full_text else "text/plain",
            )
            ids_out.append(res.artifact_id)
        return ids_out


class PhilPapersConnector:
    name = "philpapers"

    def ingest(self, store: Store, *, query: str = "", max_items: int = 5, api_key: str = "") -> list[str]:
        key = api_key or __import__("os").environ.get("PHILPAPERS_API_KEY", "")
        if not key:
            logger.warning("philpapers_no_api_key", hint="Set PHILPAPERS_API_KEY for live search.")
            return []
        logger.warning("philpapers_stub", query=query, max_items=max_items)
        return []

"""Bound-PDF export of every published article in a window.

Powers ``noosphere docs export-articles --since DATE --format pdf``.

The export reads the same public ``PublishedConclusion`` table that
serves the live blog. Visibility is therefore identical to the public
site: only rows that have been promoted into ``PublishedConclusion``
land in the bundle. The founder running the CLI on their workstation
cannot leak private content this way, because the visibility filter is
the schema itself — private rows simply do not exist in this table.

Output formats:
    html   single self-contained HTML file with a TOC. Each article
           starts on a fresh page (CSS ``page-break-before: always``)
           and gets the same print-style metadata block + endnotes
           that the web stylesheet uses.
    pdf    the same HTML run through WeasyPrint when available.
           WeasyPrint is an optional dependency; if it's missing we
           still emit the HTML next to the requested ``--out`` path
           and tell the founder to install WeasyPrint, instead of
           silently failing.

Tests exercise the HTML composition (``compose_articles_html``) so
no PDF binary is needed in CI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Iterable

from sqlmodel import select

from noosphere.models import PublicationSignature, PublishedConclusion


# ── Public types ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ArticleEndnote:
    """One endnote row in the printed article."""

    label: str
    title: str
    kind: str | None = None
    url: str | None = None
    bibliographic: str | None = None


@dataclass(frozen=True)
class ArticleForExport:
    """A single article projected into print-ready shape."""

    slug: str
    version: int
    title: str
    byline: str
    published_at: datetime
    body_markdown: str
    methodology: str | None
    confidence: float | None
    confidence_context: str | None
    mqs_composite: float | None
    canonical_url: str
    signature_fingerprint: str | None
    endnotes: tuple[ArticleEndnote, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExportManifest:
    """Result of one batch run; useful for logs + tests."""

    article_count: int
    out_path: Path
    html_path: Path
    pdf_path: Path | None
    skipped_pdf_reason: str | None


# ── Selection ───────────────────────────────────────────────────────────────


def _public_site_base(env_overrides: dict[str, str] | None = None) -> str:
    import os

    src = env_overrides if env_overrides is not None else os.environ
    raw = (src.get("THESEUS_PUBLIC_SITE_URL") or "").strip()
    if raw:
        return raw.rstrip("/")
    return "https://theseuscodex.com"


def _as_utc_naive(dt: datetime) -> datetime:
    """Project an aware-or-naive datetime to a naive UTC datetime.

    SQLite stores datetimes without tz info (the SQLAlchemy column is
    ``DateTime`` not ``DateTime(timezone=True)``). To keep comparisons
    well-defined regardless of how the caller passes ``since``/``until``
    we drop tz info after converting to UTC.
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def fetch_articles_since(
    store: Any,
    *,
    since: datetime,
    until: datetime | None = None,
    site_base: str | None = None,
) -> list[ArticleForExport]:
    """Return print-ready article rows from the public table.

    The selection mirrors the web's "what's published" rule: ``kind ==
    'ARTICLE'`` and ``published_at >= since``. Anything outside that
    window or hidden in private tables is filtered at the SQL level —
    not in Python — so this CLI can never expand its visibility by
    accident.
    """
    base = (site_base or _public_site_base()).rstrip("/")
    since_naive = _as_utc_naive(since)
    until_naive = _as_utc_naive(until) if until is not None else None
    with store.session() as session:
        rows: list[PublishedConclusion] = list(
            session.exec(
                select(PublishedConclusion)
                .where(PublishedConclusion.kind == "ARTICLE")
                .where(PublishedConclusion.published_at >= since_naive)
                .order_by(PublishedConclusion.published_at)
            ).all()
        )
        if until_naive is not None:
            rows = [
                r for r in rows if _as_utc_naive(r.published_at) <= until_naive
            ]

        # One sweep for signatures so we don't N+1 the table when an
        # operator exports a quarter's worth of work.
        slugs = sorted({r.slug for r in rows})
        signatures: dict[tuple[str, int], str] = {}
        if slugs:
            for sig in session.exec(
                select(PublicationSignature).where(
                    PublicationSignature.slug.in_(slugs)  # type: ignore[attr-defined]
                )
            ).all():
                signatures[(sig.slug, sig.version)] = sig.key_fingerprint

    out: list[ArticleForExport] = []
    for row in rows:
        payload = _safe_payload(row.payload_json)
        article_payload = payload.get("article") if isinstance(payload, dict) else {}
        body_markdown = ""
        endnotes: list[ArticleEndnote] = []
        if isinstance(article_payload, dict):
            body_markdown = str(article_payload.get("bodyMarkdown") or "")
            for c in article_payload.get("citations") or []:
                if not isinstance(c, dict):
                    continue
                public_url = c.get("public_url") or c.get("publicUrl")
                title = (
                    str(c.get("source_conclusion_text") or "").strip()
                    or str(c.get("quoted_span") or "").strip()
                    or str(c.get("source_id") or "").strip()
                    or str(c.get("label") or "").strip()
                )
                endnotes.append(
                    ArticleEndnote(
                        label=str(c.get("label") or ""),
                        title=title or "Source",
                        kind=str(c.get("source_kind") or "") or None,
                        url=str(public_url).strip() or None
                        if public_url
                        else None,
                    )
                )
        for block in payload.get("citations") or []:
            if not isinstance(block, dict):
                continue
            fmt = str(block.get("format") or "").upper()
            text = str(block.get("block") or "").strip()
            if not text:
                continue
            endnotes.append(
                ArticleEndnote(
                    label=fmt or "REF",
                    title=f"{fmt or 'REF'} citation",
                    bibliographic=text,
                )
            )

        title = (
            str(payload.get("conclusionText") or "").strip()
            if isinstance(payload, dict)
            else ""
        ) or row.slug
        methodology = None
        if isinstance(payload, dict):
            method_block = payload.get("methodology") or {}
            if isinstance(method_block, dict):
                profiles = method_block.get("profiles") or []
                if profiles and isinstance(profiles[0], dict):
                    methodology = str(profiles[0].get("patternType") or "") or None

        confidence = (
            float(row.discounted_confidence)
            if row.discounted_confidence is not None
            else None
        )
        confidence_context = None
        if row.stated_confidence:
            confidence_context = (
                f"stated {int(round(float(row.stated_confidence) * 100))}%"
            )

        canonical_url = f"{base}/c/{row.slug}"
        out.append(
            ArticleForExport(
                slug=row.slug,
                version=row.version,
                title=title,
                byline="Theseus",
                published_at=row.published_at,
                body_markdown=body_markdown,
                methodology=methodology,
                confidence=confidence,
                confidence_context=confidence_context,
                mqs_composite=None,
                canonical_url=canonical_url,
                signature_fingerprint=signatures.get((row.slug, row.version)),
                endnotes=tuple(endnotes),
            )
        )
    return out


def _safe_payload(payload_json: str | None) -> dict[str, Any]:
    if not payload_json:
        return {}
    try:
        value = json.loads(payload_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


# ── HTML composition ────────────────────────────────────────────────────────


_BOUND_CSS = """
@page { size: Letter; margin: 0.85in 0.9in 0.95in; }
html, body {
  background: #fff; color: #111;
  font-family: 'EB Garamond', Georgia, serif;
  font-size: 11pt; line-height: 1.55;
}
.toc { page-break-after: always; }
.toc h1 { font-size: 22pt; margin: 0 0 0.6em; }
.toc ol { padding-left: 1.4em; }
.toc li { margin-bottom: 0.35em; }
.toc a { color: #000; text-decoration: none; }
.toc a:hover { text-decoration: underline; }
.bound-article { page-break-before: right; }
.bound-article:first-of-type { page-break-before: auto; }
.bound-article h1 { font-size: 22pt; margin: 0 0 0.4em; page-break-after: avoid; }
.bound-article h2 { font-size: 14pt; margin: 1.4em 0 0.4em; page-break-after: avoid; }
.bound-article p { margin: 0 0 0.75em; orphans: 3; widows: 3; text-align: justify; page-break-inside: avoid; }
.print-metadata-block { border-bottom: 0.5pt solid #333; margin: 0 0 1.2em; padding: 0 0 0.7em; }
.print-metadata-block dl { display: grid; grid-template-columns: max-content 1fr; grid-column-gap: 1em; grid-row-gap: 0.15em; font-size: 9.5pt; margin: 0; }
.print-metadata-block dt { color: #444; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
.print-metadata-block dd { margin: 0; }
.print-metadata-block .fingerprint { font-family: 'IBM Plex Mono', Menlo, monospace; font-size: 8.5pt; word-break: break-all; }
.print-endnotes { border-top: 0.5pt solid #333; margin-top: 2em; padding-top: 0.7em; }
.print-endnotes h2 { font-size: 13pt; margin: 0 0 0.5em; }
.print-endnotes ol { padding-left: 1.6em; }
.print-endnotes li { font-size: 10pt; line-height: 1.4; margin: 0 0 0.45em; }
.print-endnotes .url { color: #222; font-family: 'IBM Plex Mono', Menlo, monospace; font-size: 9pt; word-break: break-all; }
"""


def _format_pct(value: float | None) -> str | None:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n:  # NaN
        return None
    n = max(0.0, min(1.0, n))
    return f"{int(round(n * 100))}%"


def _slug_anchor(slug: str) -> str:
    return "art-" + "".join(c if c.isalnum() else "-" for c in slug).strip("-").lower()


def _markdown_to_html(text: str) -> str:
    """Tiny markdown projection — paragraphs and ## headings only.

    The web app uses react-markdown; here we deliberately avoid pulling
    in a Python markdown dependency so this CLI keeps working in any
    minimal environment. Articles in this codebase are paragraph-prose
    with the occasional ``## subhead``, which is what we render.
    """
    out: list[str] = []
    for raw_block in (b.strip() for b in text.split("\n\n")):
        if not raw_block:
            continue
        if raw_block.startswith("## "):
            out.append(f"<h2>{escape(raw_block[3:].strip())}</h2>")
        elif raw_block.startswith("# "):
            out.append(f"<h1>{escape(raw_block[2:].strip())}</h1>")
        else:
            out.append(f"<p>{escape(raw_block)}</p>")
    return "\n".join(out)


def _render_metadata_block(article: ArticleForExport) -> str:
    rows: list[str] = []

    def row(label: str, value: str, *, klass: str = "") -> None:
        rows.append(f"<dt>{escape(label)}</dt>")
        rows.append(
            f"<dd{' class=' + chr(34) + klass + chr(34) if klass else ''}>"
            f"{escape(value)}</dd>"
        )

    if article.methodology:
        row("Method", article.methodology)
    mqs = _format_pct(article.mqs_composite)
    if mqs:
        row("MQS", f"{mqs} composite")
    confidence = _format_pct(article.confidence)
    if confidence:
        suffix = f" · {article.confidence_context}" if article.confidence_context else ""
        row("Confidence", f"{confidence}{suffix}")
    row(
        "Signed",
        article.signature_fingerprint or "(unsigned)",
        klass="fingerprint",
    )
    row("Source", article.canonical_url, klass="url")

    return (
        '<aside class="print-metadata-block">'
        f'<h1>{escape(article.title)}</h1>'
        f'<p>{escape(article.byline)} · '
        f'{escape(article.published_at.strftime("%B %d, %Y"))}</p>'
        f'<dl>{"".join(rows)}</dl>'
        "</aside>"
    )


def _render_endnotes(article: ArticleForExport) -> str:
    if not article.endnotes:
        return ""
    items: list[str] = []
    for note in article.endnotes:
        parts = [f"<span>{escape(note.title)}</span>"]
        if note.kind:
            parts.append(f' <span class="meta">({escape(note.kind)})</span>')
        if note.url and note.url.lower().startswith(("http://", "https://")):
            parts.append(
                f' <a class="url" href="{escape(note.url, quote=True)}">'
                f'{escape(note.url)}</a>'
            )
        if note.bibliographic:
            parts.append(f'<div class="url">{escape(note.bibliographic)}</div>')
        items.append(f'<li>{"".join(parts)}</li>')
    return (
        '<section class="print-endnotes"><h2>Endnotes</h2><ol>'
        + "".join(items)
        + "</ol></section>"
    )


def _render_article(article: ArticleForExport) -> str:
    anchor = _slug_anchor(article.slug)
    return (
        f'<article class="bound-article" id="{anchor}">'
        + _render_metadata_block(article)
        + _markdown_to_html(article.body_markdown)
        + _render_endnotes(article)
        + "</article>"
    )


def _render_toc(articles: Iterable[ArticleForExport]) -> str:
    items: list[str] = []
    for art in articles:
        anchor = _slug_anchor(art.slug)
        date = art.published_at.strftime("%Y-%m-%d")
        items.append(
            f'<li><a href="#{anchor}">{escape(art.title)}</a>'
            f' <span class="muted">({escape(date)})</span></li>'
        )
    return (
        '<section class="toc"><h1>Contents</h1><ol>'
        + "".join(items)
        + "</ol></section>"
    )


def compose_articles_html(
    articles: list[ArticleForExport],
    *,
    title: str = "Theseus Codex — Bound Articles",
    generated_at: datetime | None = None,
) -> str:
    """Compose the final bound HTML document.

    The output is a complete, standalone document (no external CSS) so
    a founder can hand the file to anyone — including a printer — and
    get the same rendering.
    """
    when = generated_at or datetime.now(timezone.utc)
    body_parts = [_render_toc(articles)]
    for art in articles:
        body_parts.append(_render_article(art))
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>{escape(title)}</title>"
        f"<style>{_BOUND_CSS}</style>"
        f'<meta name="generator" content="noosphere docs export-articles">'
        f'<meta name="generated-at" content="{when.isoformat()}">'
        "</head><body>"
        + "".join(body_parts)
        + "</body></html>"
    )


def export_articles(
    store: Any,
    *,
    since: datetime,
    out_path: Path,
    fmt: str = "pdf",
    until: datetime | None = None,
    site_base: str | None = None,
    title: str = "Theseus Codex — Bound Articles",
    generated_at: datetime | None = None,
) -> ExportManifest:
    """Run the full export and write the result to disk.

    For ``fmt='html'`` we just write the composed document. For
    ``fmt='pdf'`` we additionally pipe through WeasyPrint when it's
    available; if it isn't, the HTML is still on disk and we report
    why the PDF was skipped (so the operator can install the
    dependency and re-run).
    """
    fmt = fmt.lower().strip()
    if fmt not in {"html", "pdf"}:
        raise ValueError(f"Unsupported format: {fmt!r}")

    articles = fetch_articles_since(
        store, since=since, until=until, site_base=site_base
    )
    html_doc = compose_articles_html(
        articles, title=title, generated_at=generated_at
    )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "html":
        out_path.write_text(html_doc, encoding="utf-8")
        return ExportManifest(
            article_count=len(articles),
            out_path=out_path,
            html_path=out_path,
            pdf_path=None,
            skipped_pdf_reason=None,
        )

    # fmt == "pdf"
    html_path = out_path.with_suffix(".html")
    html_path.write_text(html_doc, encoding="utf-8")

    pdf_path: Path | None = None
    skipped_reason: str | None = None
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]

        HTML(string=html_doc).write_pdf(str(out_path))
        pdf_path = out_path
    except ImportError:
        skipped_reason = (
            "weasyprint is not installed; wrote HTML next to --out and "
            "skipped PDF rendering. Install with: pip install weasyprint"
        )
    except Exception as exc:  # pragma: no cover - environment-specific
        skipped_reason = f"weasyprint rendering failed: {exc}"

    return ExportManifest(
        article_count=len(articles),
        out_path=out_path,
        html_path=html_path,
        pdf_path=pdf_path,
        skipped_pdf_reason=skipped_reason,
    )

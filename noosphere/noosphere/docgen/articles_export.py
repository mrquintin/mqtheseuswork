"""Bound-PDF export of every published article in a window.

Powers ``noosphere docs export-articles --since DATE --format pdf``.

The export reads the same public ``PublishedConclusion`` table that
serves the live blog. Visibility is therefore identical to the public
site: only rows that have been promoted into ``PublishedConclusion``
land in the bundle. The founder running the CLI on their workstation
cannot leak private content this way, because the visibility filter is
the schema itself — private rows simply do not exist in this table.

Output formats:
    html   single self-contained HTML file. Each article starts on a
           fresh page and gets the same print-style metadata block +
           endnotes that the web stylesheet uses.
    pdf    the same HTML run through WeasyPrint when available.
           WeasyPrint is an optional dependency; if it's missing we
           still emit the HTML next to the requested ``--out`` path
           and tell the founder to install WeasyPrint, instead of
           silently failing.

Composition switches (``compose_articles_html`` / ``export_articles``,
exposed on the CLI as ``--cover``, ``--toc/--no-toc``,
``--start-each-on-right`` and ``--privacy strict|tolerant``):

    cover                a single generated cover page, prepended.
    toc                  a clickable table of contents (default on).
    start_each_on_right  open each article on a right-hand page, for
                         two-sided binding.
    privacy              ``strict`` (default) omits the consolidated
                         private-source appendix entirely; ``tolerant``
                         renders it. Per-article endnotes are never
                         affected — the switch governs only the
                         appendix.

The bound stylesheet also carries a running header (the current
article title) and a numbered footer that begins on page 2, matching
the numbering style of the firm's existing LaTeX PDFs in ``docs/``.

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
    """One endnote row in the printed article.

    ``credibility`` is the source-credibility score (Round 17 prompt
    19) as a 0–100 strip value (``BetaPosterior.score_100``), shown
    inline after the source name. ``None`` when the cited source is
    not in the credibility ledger.
    """

    label: str
    title: str
    kind: str | None = None
    url: str | None = None
    bibliographic: str | None = None
    credibility: float | None = None

    @property
    def is_public(self) -> bool:
        """True when the source carries a real public ``http(s)`` URL.

        The inverse — ``not is_public`` and no ``bibliographic`` block —
        is what the export treats as a *private source*: an internal
        firm citation with no externally addressable URL. Those are the
        rows the ``--privacy`` switch governs in the appendix.
        """

        return bool(self.url and self.url.lower().startswith(("http://", "https://")))


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
    # Composition switches that produced this bundle, echoed back so a
    # log / the CLI can report exactly what was bound.
    cover: bool = False
    toc: bool = True
    start_each_on_right: bool = False
    privacy: str = "strict"


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
                        credibility=_citation_credibility(c),
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


def _citation_credibility(citation: dict[str, Any]) -> float | None:
    """Pull a 0–100 source-credibility score off a citation payload.

    The publish payload may carry the source-credibility (Round 17
    prompt 19) posterior in a couple of shapes depending on when the
    article was published: a bare numeric ``credibility`` /
    ``credibility_score`` field, or the full ``source_credibility``
    display payload (which has ``score_100``). We accept either and
    fall back to ``None`` — a missing score is not an error, it just
    means the cited source has no ledger entry yet.
    """
    raw: Any = None
    block = citation.get("source_credibility")
    if isinstance(block, dict):
        raw = block.get("score_100")
        if raw is None and block.get("mean") is not None:
            try:
                raw = float(block["mean"]) * 100.0
            except (TypeError, ValueError):
                raw = None
    if raw is None:
        raw = citation.get("credibility_score")
    if raw is None:
        raw = citation.get("credibility")
    if raw is None:
        return None
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return None
    if score != score:  # NaN
        return None
    return max(0.0, min(100.0, score))


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
/*
 * Bound-export stylesheet. This mirrors the web `print.css` but is
 * self-contained (the bundle ships with no external CSS). It targets
 * WeasyPrint/Prince — the engines the PDF path runs through — so it
 * leans on CSS paged-media features (margin boxes, named strings,
 * target-counter) that those engines implement.
 */
@page {
  size: Letter;
  margin: 0.85in 0.9in 0.95in;
  /* Running header (current article title) + numbered footer. The
   * footer style — a small, plain arabic numeral on the outside edge,
   * no "page X of Y" — matches the firm's existing LaTeX PDFs in
   * `docs/` (`\\fancyhead[R]{\\small\\thepage}`). */
  @top-left {
    content: string(doc-running-title);
    font-family: 'EB Garamond', Georgia, serif;
    font-size: 8.5pt; color: #555; letter-spacing: 0.02em;
  }
  @bottom-right {
    content: counter(page);
    font-family: 'EB Garamond', Georgia, serif;
    font-size: 9pt; color: #333;
  }
}
/* Page 1 (the cover, or the TOC when there is no cover) carries no
 * running header and no page number — numbering begins on page 2. */
@page :first {
  @top-left { content: ''; }
  @bottom-right { content: ''; }
}
html, body {
  background: #fff; color: #111;
  font-family: 'EB Garamond', Georgia, serif;
  font-size: 11pt; line-height: 1.55;
}

/* ── Cover page ───────────────────────────────────────────────────── */
.print-cover { page-break-after: always; padding: 2.2in 0 0; text-align: center; }
.print-cover .print-cover-imprint {
  color: #555; font-size: 10pt; letter-spacing: 0.26em;
  margin: 0 0 3em; text-transform: uppercase;
}
.print-cover .print-cover-title { font-size: 30pt; font-weight: 600; line-height: 1.15; margin: 0 0 0.4em; }
.print-cover .print-cover-subtitle { color: #333; font-size: 13pt; font-style: italic; margin: 0 0 2.5em; }
.print-cover .print-cover-meta { color: #555; font-size: 9.5pt; line-height: 1.7; }

/* ── Table of contents ───────────────────────────────────────────── */
.toc { page-break-after: always; }
.toc h1 { font-size: 22pt; margin: 0 0 0.6em; }
.toc ol { list-style: none; margin: 0; padding: 0; }
.toc li { margin-bottom: 0.4em; font-size: 10.5pt; }
.toc a { color: #000; text-decoration: none; }
.toc a:hover { text-decoration: underline; }
/* Dotted leader + destination page number for each entry; engines
 * without target-counter support just drop the ::after. */
.toc a::after {
  content: leader('. ') target-counter(attr(href), page);
  color: #555; font-size: 9.5pt;
}
.toc .muted { color: #777; font-size: 9pt; }

/* ── Articles ─────────────────────────────────────────────────────── */
/* Default: each article opens on a fresh page. With the `bind-right`
 * body class (the --start-each-on-right switch) it opens on a
 * right-hand page instead, for two-sided binding. */
.bound-article { page-break-before: always; }
.bound-article:first-of-type { page-break-before: auto; }
.bind-right .bound-article { page-break-before: right; }
.bind-right .bound-article:first-of-type { page-break-before: auto; }
.bound-article h1 { font-size: 22pt; margin: 0 0 0.4em; page-break-after: avoid; break-after: avoid; }
.bound-article h2 { font-size: 14pt; margin: 1.4em 0 0.4em; page-break-after: avoid; break-after: avoid; }
.bound-article p { margin: 0 0 0.75em; orphans: 3; widows: 3; text-align: justify; page-break-inside: avoid; }
.print-metadata-block { border-bottom: 0.5pt solid #333; margin: 0 0 1.2em; padding: 0 0 0.7em; }
/* Publish the current article title into the running header. */
.print-metadata-block h1 { font-size: 22pt; margin: 0 0 0.4em; string-set: doc-running-title content(); }
.print-metadata-block .print-metadata-pill {
  display: inline-block; border: 0.75pt solid #444; border-radius: 999px;
  font-size: 8pt; font-variant: small-caps; letter-spacing: 0.06em;
  margin: 0 0 0.6em; padding: 0.18em 0.8em;
}
.print-metadata-block dl { display: grid; grid-template-columns: max-content 1fr; grid-column-gap: 1em; grid-row-gap: 0.15em; font-size: 9.5pt; margin: 0; }
.print-metadata-block dt { color: #444; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
.print-metadata-block dd { margin: 0; }
.print-metadata-block .fingerprint { font-family: 'IBM Plex Mono', Menlo, monospace; font-size: 8.5pt; word-break: break-all; }

/* ── Endnotes ─────────────────────────────────────────────────────── */
.print-endnotes { border-top: 0.5pt solid #333; margin-top: 2em; padding-top: 0.7em; }
.print-endnotes h2 { font-size: 13pt; margin: 0 0 0.5em; page-break-after: avoid; break-after: avoid; }
.print-endnotes ol { padding-left: 1.6em; }
/* Each endnote is kept whole across a page break so a source name
 * never strands; the list still breaks freely between notes. */
.print-endnotes li { font-size: 10pt; line-height: 1.4; margin: 0 0 0.45em; page-break-inside: avoid; break-inside: avoid; }
/* Source names print in small caps — the bibliographic convention. */
.print-endnotes .print-endnote-title { font-variant: small-caps; letter-spacing: 0.01em; }
.print-endnotes .meta { color: #555; }
/* Source-credibility score (Round 17 prompt 19), inline after the name. */
.print-endnotes .cred { color: #555; font-size: 8.5pt; white-space: nowrap; }
.print-endnotes .url {
  color: #222; font-family: 'IBM Plex Mono', Menlo, monospace; font-size: 9pt;
  /* Wrap URLs at sensible characters: the renderer inserts <wbr>
   * break opportunities after `/ . ? & = -`; overflow-wrap is the
   * fallback for one unbroken giant token. We avoid word-break:
   * break-all, which breaks mid-token at an arbitrary letter. */
  word-break: normal; overflow-wrap: break-word;
}

/* ── Appendix: private sources ────────────────────────────────────── */
.print-appendix { page-break-before: always; border-top: 0.5pt solid #333; padding-top: 0.7em; }
.print-appendix h1 { font-size: 18pt; margin: 0 0 0.3em; }
.print-appendix .appendix-note { color: #555; font-size: 9.5pt; font-style: italic; margin: 0 0 0.9em; }
.print-appendix ol { padding-left: 1.6em; }
.print-appendix li { font-size: 10pt; line-height: 1.4; margin: 0 0 0.4em; page-break-inside: avoid; break-inside: avoid; }
.print-appendix .print-endnote-title { font-variant: small-caps; letter-spacing: 0.01em; }
.print-appendix .meta { color: #555; }
.print-appendix .cred { color: #555; font-size: 8.5pt; white-space: nowrap; }
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


def _soft_break_url(url: str) -> str:
    """HTML-escape a URL and insert ``<wbr>`` break opportunities.

    Breaks go in after the structural characters ``/ . ? & = -`` so a
    long endnote URL wraps at sensible boundaries in the rendered PDF
    instead of overflowing the column or breaking mid-token at an
    arbitrary letter. Returns ready-to-embed HTML.
    """
    out: list[str] = []
    for ch in url:
        out.append(escape(ch))
        if ch in "/.?&=-":
            out.append("<wbr>")
    return "".join(out)


def _format_credibility(score: float | None) -> str | None:
    """Render a 0–100 source-credibility score as ``cred NN/100``."""
    if score is None:
        return None
    try:
        n = float(score)
    except (TypeError, ValueError):
        return None
    if n != n:  # NaN
        return None
    n = max(0.0, min(100.0, n))
    return f"cred {int(round(n))}/100"


def _render_metadata_block(article: ArticleForExport) -> str:
    rows: list[str] = []

    def row(label: str, value: str, *, klass: str = "") -> None:
        rows.append(f"<dt>{escape(label)}</dt>")
        rows.append(
            f"<dd{' class=' + chr(34) + klass + chr(34) if klass else ''}>"
            f"{escape(value)}</dd>"
        )

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

    # Methodology renders as a bordered small-caps pill — the print
    # echo of the on-screen methodology pill — not as a `dl` row.
    pill = (
        f'<p class="print-metadata-pill">{escape(article.methodology)}</p>'
        if article.methodology
        else ""
    )
    return (
        '<aside class="print-metadata-block">'
        f'<h1>{escape(article.title)}</h1>'
        f'<p>{escape(article.byline)} · '
        f'{escape(article.published_at.strftime("%B %d, %Y"))}</p>'
        f"{pill}"
        f'<dl>{"".join(rows)}</dl>'
        "</aside>"
    )


def _render_endnotes(article: ArticleForExport) -> str:
    if not article.endnotes:
        return ""
    items: list[str] = []
    for note in article.endnotes:
        parts = [
            f'<span class="print-endnote-title">{escape(note.title)}</span>'
        ]
        if note.kind:
            parts.append(f' <span class="meta">({escape(note.kind)})</span>')
        cred = _format_credibility(note.credibility)
        if cred:
            parts.append(f' <span class="cred">· {escape(cred)}</span>')
        # A URL is emitted only for genuinely public sources — private
        # sources have no `http(s)` URL and never get a link, so a
        # private link cannot leak into the printed document.
        if note.is_public and note.url:
            parts.append(
                f' <a class="url" href="{escape(note.url, quote=True)}">'
                f"{_soft_break_url(note.url)}</a>"
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


def _render_cover(
    *,
    title: str,
    subtitle: str | None,
    generated_at: datetime,
    article_count: int,
) -> str:
    """Render the single prepended cover page for a bound run."""
    meta_lines = [
        f"{article_count} {'article' if article_count == 1 else 'articles'}",
        f"Compiled {generated_at.strftime('%B %d, %Y')}",
    ]
    meta = "".join(f"<div>{escape(line)}</div>" for line in meta_lines)
    subtitle_html = (
        f'<p class="print-cover-subtitle">{escape(subtitle)}</p>'
        if subtitle
        else ""
    )
    return (
        '<section class="print-cover">'
        '<p class="print-cover-imprint">Theseus Codex</p>'
        f'<h1 class="print-cover-title">{escape(title)}</h1>'
        f"{subtitle_html}"
        f'<div class="print-cover-meta">{meta}</div>'
        "</section>"
    )


def _render_toc(articles: Iterable[ArticleForExport]) -> str:
    """Render the clickable table of contents.

    Each entry is a real in-document anchor link; ``_BOUND_CSS``
    additionally appends a dotted leader + destination page number via
    ``target-counter`` in print engines that support it.
    """
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


def _render_appendix(
    articles: Iterable[ArticleForExport], privacy: str
) -> str:
    """Consolidated appendix of private (non-public-URL) cited sources.

    ``privacy`` governs whether this section is produced at all:

    * ``strict`` — the appendix is omitted entirely; private sources
      are not consolidated anywhere in the bound document.
    * ``tolerant`` — the appendix lists every distinct private source
      cited across the bundle, by title + kind + credibility. It never
      emits a URL: private sources have none by definition, and the
      export will not invent one.

    Either way, per-article endnotes are untouched — they already list
    private sources inline by title with no link, exactly as the web
    print view does. The switch governs only the *consolidated*
    appendix.
    """
    if privacy != "tolerant":
        return ""
    seen: set[tuple[str, str | None]] = set()
    rows: list[str] = []
    for art in articles:
        for note in art.endnotes:
            # A private source: no public URL, and not one of the
            # APA/BibTeX bibliographic blocks (those are not sources).
            if note.is_public or note.bibliographic:
                continue
            key = (note.title, note.kind)
            if key in seen:
                continue
            seen.add(key)
            parts = [
                f'<span class="print-endnote-title">{escape(note.title)}</span>'
            ]
            if note.kind:
                parts.append(f' <span class="meta">({escape(note.kind)})</span>')
            cred = _format_credibility(note.credibility)
            if cred:
                parts.append(f' <span class="cred">· {escape(cred)}</span>')
            rows.append(f'<li>{"".join(parts)}</li>')
    if not rows:
        return ""
    return (
        '<section class="print-appendix" id="appendix-private-sources">'
        "<h1>Appendix &middot; Private sources</h1>"
        '<p class="appendix-note">Internal firm sources cited above that '
        "have no public URL. Listed for provenance; not externally "
        "addressable.</p>"
        "<ol>" + "".join(rows) + "</ol></section>"
    )


def _fmt_day(dt: datetime) -> str:
    """``Mon D, YYYY`` — `%-d` is POSIX-only, so fall back defensively."""
    naive = _as_utc_naive(dt)
    try:
        return naive.strftime("%b %-d, %Y")
    except ValueError:  # pragma: no cover - platform-specific
        return naive.strftime("%b %d, %Y")


def _window_label(since: datetime, until: datetime | None) -> str:
    """Human window string for the cover page subtitle."""
    start = _fmt_day(since)
    if until is None:
        return f"Published since {start}"
    return f"Published {start} – {_fmt_day(until)}"


def compose_articles_html(
    articles: list[ArticleForExport],
    *,
    title: str = "Theseus Codex — Bound Articles",
    generated_at: datetime | None = None,
    include_toc: bool = True,
    include_cover: bool = False,
    cover_subtitle: str | None = None,
    start_each_on_right: bool = False,
    privacy: str = "strict",
) -> str:
    """Compose the final bound HTML document.

    The output is a complete, standalone document (no external CSS) so
    a founder can hand the file to anyone — including a printer — and
    get the same rendering.

    Composition switches:

    * ``include_cover`` — prepend a single generated cover page. Being
      page 1, the cover carries no running header / page number
      (``@page :first``); numbering starts on the page after it.
    * ``include_toc`` — emit a clickable table of contents (on by
      default). Entries link to in-document anchors and, in print
      engines with paged-media target counters, carry a dotted leader
      to the destination page number.
    * ``start_each_on_right`` — open each article on a right-hand page
      (for two-sided binding) rather than simply the next page.
    * ``privacy`` — ``strict`` | ``tolerant``; governs whether the
      consolidated private-source appendix is produced (see
      ``_render_appendix``). Defaults to ``strict``.
    """
    privacy = (privacy or "strict").lower().strip()
    if privacy not in {"strict", "tolerant"}:
        raise ValueError(f"Unsupported privacy mode: {privacy!r}")

    when = generated_at or datetime.now(timezone.utc)
    body_parts: list[str] = []
    if include_cover:
        body_parts.append(
            _render_cover(
                title=title,
                subtitle=cover_subtitle,
                generated_at=when,
                article_count=len(articles),
            )
        )
    if include_toc:
        body_parts.append(_render_toc(articles))
    for art in articles:
        body_parts.append(_render_article(art))
    body_parts.append(_render_appendix(articles, privacy))

    body_class = ' class="bind-right"' if start_each_on_right else ""
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>{escape(title)}</title>"
        f"<style>{_BOUND_CSS}</style>"
        f'<meta name="generator" content="noosphere docs export-articles">'
        f'<meta name="generated-at" content="{when.isoformat()}">'
        f"</head><body{body_class}>"
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
    include_cover: bool = False,
    include_toc: bool = True,
    start_each_on_right: bool = False,
    privacy: str = "strict",
) -> ExportManifest:
    """Run the full export and write the result to disk.

    For ``fmt='html'`` we just write the composed document. For
    ``fmt='pdf'`` we additionally pipe through WeasyPrint when it's
    available; if it isn't, the HTML is still on disk and we report
    why the PDF was skipped (so the operator can install the
    dependency and re-run).

    The composition switches — ``include_cover``, ``include_toc``,
    ``start_each_on_right``, ``privacy`` — back the CLI's ``--cover``,
    ``--toc/--no-toc``, ``--start-each-on-right`` and
    ``--privacy strict|tolerant`` options; see ``compose_articles_html``.
    """
    fmt = fmt.lower().strip()
    if fmt not in {"html", "pdf"}:
        raise ValueError(f"Unsupported format: {fmt!r}")
    privacy = (privacy or "strict").lower().strip()
    if privacy not in {"strict", "tolerant"}:
        raise ValueError(f"Unsupported privacy mode: {privacy!r}")

    articles = fetch_articles_since(
        store, since=since, until=until, site_base=site_base
    )
    html_doc = compose_articles_html(
        articles,
        title=title,
        generated_at=generated_at,
        include_toc=include_toc,
        include_cover=include_cover,
        cover_subtitle=_window_label(since, until) if include_cover else None,
        start_each_on_right=start_each_on_right,
        privacy=privacy,
    )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def _manifest(
        *,
        html_path: Path,
        pdf_path: Path | None,
        skipped_pdf_reason: str | None,
    ) -> ExportManifest:
        return ExportManifest(
            article_count=len(articles),
            out_path=out_path,
            html_path=html_path,
            pdf_path=pdf_path,
            skipped_pdf_reason=skipped_pdf_reason,
            cover=include_cover,
            toc=include_toc,
            start_each_on_right=start_each_on_right,
            privacy=privacy,
        )

    if fmt == "html":
        out_path.write_text(html_doc, encoding="utf-8")
        return _manifest(
            html_path=out_path, pdf_path=None, skipped_pdf_reason=None
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

    return _manifest(
        html_path=html_path,
        pdf_path=pdf_path,
        skipped_pdf_reason=skipped_reason,
    )

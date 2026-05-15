"""Tests for the print-view polish on the bound-article export.

Round 17 prompt 38 turned articles into clean PDFs; this round
(prompt 28) refines the rough edges: a true title-page metadata
block, small-caps endnotes with inline source-credibility, numbered
footers from page 2, and the batch-export switches ``--cover``,
``--toc``, ``--start-each-on-right`` and ``--privacy``.

The 50-page long-form check renders an actual PDF only when WeasyPrint
is installed; the structural guarantees (TOC links resolve, numbering
is continuous, headings are kept with their bodies, fingerprints match
the canonical record) are asserted on the composed HTML so they run in
CI regardless.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from noosphere.docgen.articles_export import (
    ArticleEndnote,
    ArticleForExport,
    _citation_credibility,
    _format_credibility,
    _soft_break_url,
    compose_articles_html,
    export_articles,
    fetch_articles_since,
)
from noosphere.models import PublicationSignature, PublishedConclusion
from noosphere.store import Store

ORG_ID = "org_export_polish"
NOW = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)


# ── Fixtures / builders ─────────────────────────────────────────────────────


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _article(
    *,
    slug: str,
    title: str = "A Considered Title",
    body: str = "First paragraph.\n\nSecond paragraph.",
    endnotes: tuple[ArticleEndnote, ...] = (),
    methodology: str | None = "six_layer_coherence",
    confidence: float | None = 0.81,
    confidence_context: str | None = "stated 86%",
    mqs_composite: float | None = 0.72,
    fingerprint: str | None = "fp-default",
    when: datetime = NOW,
) -> ArticleForExport:
    return ArticleForExport(
        slug=slug,
        version=1,
        title=title,
        byline="Theseus",
        published_at=when,
        body_markdown=body,
        methodology=methodology,
        confidence=confidence,
        confidence_context=confidence_context,
        mqs_composite=mqs_composite,
        canonical_url=f"https://theseus.test/c/{slug}",
        signature_fingerprint=fingerprint,
        endnotes=endnotes,
    )


# Three article lengths for the print-stylesheet snapshot.
_SHORT_BODY = "A single tight paragraph that states the claim and stops."
_MEDIUM_BODY = "\n\n".join(
    ["## A subhead"] + [f"Medium body paragraph number {i}." for i in range(6)]
)
_LONG_BODY = "\n\n".join(
    ["## Opening"]
    + [f"Long body paragraph {i}, several clauses deep, for paper." for i in range(40)]
)


def _seed_article(
    store: Store,
    *,
    slug: str,
    title: str,
    body: str,
    when: datetime,
    citations: list[dict[str, object]] | None = None,
    fingerprint: str | None = None,
) -> None:
    payload = {
        "schema": "theseus.publicConclusion.v1",
        "conclusionText": title,
        "rationale": "",
        "topicHint": "",
        "evidenceSummary": "",
        "exitConditions": [],
        "strongestObjection": {"objection": "", "firmAnswer": ""},
        "openQuestionsAdjacent": [],
        "voiceComparisons": [],
        "methodology": {
            "schema": "theseus.methodology.v1",
            "reviewerNarrative": "",
            "profiles": [
                {
                    "patternType": "six_layer_coherence",
                    "title": "demo",
                    "summary": "",
                    "reasoningMoves": [],
                    "transferTargets": [],
                    "assumptions": [],
                    "failureModes": [],
                    "evidenceAnchors": [],
                    "confidence": 0.7,
                }
            ],
        },
        "timeline": [],
        "whatWouldChangeOurMind": [],
        "citations": [],
        "article": {
            "kind": "thematic",
            "bodyMarkdown": body,
            "sourceIds": [],
            "citations": citations or [],
        },
    }
    row = PublishedConclusion(
        organization_id=ORG_ID,
        source_conclusion_id=f"src_{slug}",
        slug=slug,
        version=1,
        kind="ARTICLE",
        discounted_confidence=0.81,
        stated_confidence=0.86,
        calibration_discount_reason="",
        payload_json=json.dumps(payload),
        doi="",
        zenodo_record_id="",
        published_at=when,
    )
    with store.session() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
    if fingerprint:
        sig = PublicationSignature(
            published_conclusion_id=row.id,
            slug=slug,
            version=1,
            canonical_hash="0" * 64,
            signature_hex="dead",
            key_fingerprint=fingerprint,
            signed_at=when.isoformat(),
        )
        with store.session() as session:
            session.add(sig)
            session.commit()


# ── A. Metadata block — a true title page ───────────────────────────────────


def test_metadata_block_carries_full_title_page_content() -> None:
    art = _article(slug="title-page", title="The Title Page Article")
    html = compose_articles_html([art], generated_at=NOW)

    # Title, byline + publication date.
    assert "<h1>The Title Page Article</h1>" in html
    assert "Theseus · May 01, 2026" in html
    # Methodology renders as a pill, not a plain dl row.
    assert 'class="print-metadata-pill">six_layer_coherence<' in html
    assert "<dt>Method</dt>" not in html
    # MQS + confidence (with calibration context).
    assert "72% composite" in html
    assert "81% · stated 86%" in html
    # Signature fingerprint + canonical URL.
    assert '<dd class="fingerprint">fp-default</dd>' in html
    assert '<dd class="url">https://theseus.test/c/title-page</dd>' in html


def test_metadata_block_marks_unsigned_articles() -> None:
    art = _article(slug="unsigned", fingerprint=None)
    html = compose_articles_html([art], generated_at=NOW)
    assert '<dd class="fingerprint">(unsigned)</dd>' in html


def test_print_css_makes_metadata_block_a_title_page() -> None:
    """The web stylesheet gives page 1 over to the metadata block and
    suppresses the running header + footer there (`@page :first`)."""
    css = Path(__file__).resolve().parents[2] / "theseus-codex" / "src" / "app" / "print.css"
    text = css.read_text(encoding="utf-8")
    block = re.search(r"\.print-metadata-block\s*\{[^}]*\}", text)
    assert block is not None
    assert "page-break-after: always" in block.group(0)
    # Footer numbering + first-page suppression.
    assert "@page :first" in text
    assert "counter(page)" in text
    assert "string(doc-running-title)" in text


# ── B. Endnotes — small caps, credibility, page breaks, URL wrapping ─────────


def test_endnotes_use_small_caps_and_inline_credibility() -> None:
    art = _article(
        slug="endnotes",
        endnotes=(
            ArticleEndnote(
                label="S1",
                title="Major Newspaper Report",
                kind="news",
                url="https://example.com/report",
                credibility=72.0,
            ),
        ),
    )
    html = compose_articles_html([art], generated_at=NOW)
    # Source name carries the small-caps class.
    assert '<span class="print-endnote-title">Major Newspaper Report</span>' in html
    # Source-credibility score is inline.
    assert '<span class="cred">· cred 72/100</span>' in html
    # The bound stylesheet renders the title in small caps.
    assert "font-variant: small-caps" in html


def test_endnote_urls_wrap_at_sensible_characters() -> None:
    long_url = "https://example.com/section/sub/page?id=42&ref=print-view"
    art = _article(
        slug="wrap",
        endnotes=(
            ArticleEndnote(label="S1", title="Deep Link", url=long_url),
        ),
    )
    html = compose_articles_html([art], generated_at=NOW)
    # The href is intact (HTML-escaped) and the visible URL carries
    # <wbr> break opportunities after the structural characters.
    assert 'href="https://example.com/section/sub/page?id=42&amp;ref=print-view"' in html
    assert "page?<wbr>id=<wbr>42&amp;<wbr>ref=<wbr>print-<wbr>view" in html
    # The endnote-URL rule wraps on word boundaries — never break-all,
    # which would break mid-token at an arbitrary letter.
    url_rule = re.search(r"\.print-endnotes \.url\s*\{[^}]*\}", html)
    assert url_rule is not None
    assert "word-break: break-all" not in url_rule.group(0)
    assert "overflow-wrap: break-word" in url_rule.group(0)


def test_endnotes_kept_whole_across_page_breaks() -> None:
    art = _article(
        slug="break",
        endnotes=(ArticleEndnote(label="S1", title="Source"),),
    )
    html = compose_articles_html([art], generated_at=NOW)
    li_rule = re.search(r"\.print-endnotes li\s*\{[^}]*\}", html)
    assert li_rule is not None
    assert "page-break-inside: avoid" in li_rule.group(0)
    # The "Endnotes" heading is never left stranded at a page foot.
    h2_rule = re.search(r"\.print-endnotes h2\s*\{[^}]*\}", html)
    assert h2_rule is not None and "page-break-after: avoid" in h2_rule.group(0)


def test_private_source_endnote_never_emits_a_url() -> None:
    art = _article(
        slug="private",
        endnotes=(
            ArticleEndnote(label="S1", title="Internal Firm Memo", kind="conclusion"),
        ),
    )
    html = compose_articles_html([art], generated_at=NOW)
    chunk = html.split("Internal Firm Memo", 1)[1].split("</li>", 1)[0]
    assert "http" not in chunk


def test_soft_break_url_inserts_breaks_after_structural_chars() -> None:
    out = _soft_break_url("https://a.com/b?c=d")
    # A <wbr> follows each of `/ . ? & = -` but not ordinary letters.
    assert out.startswith("https:/<wbr>/<wbr>")
    assert "a.<wbr>com/<wbr>b?<wbr>c=<wbr>d" in out
    assert _soft_break_url("plainword") == "plainword"


# ── C. Page numbering ───────────────────────────────────────────────────────


def test_bound_css_numbers_footers_from_page_two() -> None:
    html = compose_articles_html([_article(slug="num")], generated_at=NOW)
    # A numbered footer (small plain arabic numeral, outside edge) —
    # matching the firm's existing LaTeX PDFs in docs/.
    assert "@bottom-right" in html
    assert "content: counter(page)" in html
    # Page 1 (cover / first metadata page) is suppressed; numbering
    # therefore starts on page 2.
    assert "@page :first" in html
    # Numbering is continuous: nothing resets the page counter.
    assert "counter-reset: page" not in html


# ── D. Batch export switches ────────────────────────────────────────────────


def test_cover_option_prepends_a_single_cover_page() -> None:
    arts = [_article(slug="a"), _article(slug="b")]
    with_cover = compose_articles_html(
        arts, generated_at=NOW, include_cover=True, cover_subtitle="Published in May"
    )
    without = compose_articles_html(arts, generated_at=NOW, include_cover=False)
    assert with_cover.count('class="print-cover"') == 1
    assert without.count('class="print-cover"') == 0
    assert "Published in May" in with_cover
    assert "2 articles" in with_cover
    assert "Compiled May 1, 2026" in with_cover or "Compiled May 01, 2026" in with_cover


def test_toc_is_clickable_and_can_be_disabled() -> None:
    arts = [_article(slug="alpha", title="Alpha"), _article(slug="beta", title="Beta")]
    with_toc = compose_articles_html(arts, generated_at=NOW)  # default on
    no_toc = compose_articles_html(arts, generated_at=NOW, include_toc=False)
    assert '<section class="toc">' in with_toc
    assert 'href="#art-alpha"' in with_toc and 'href="#art-beta"' in with_toc
    # Clickable TOC gets a leader + destination page number in engines
    # that support paged-media target counters.
    assert "target-counter(attr(href), page)" in with_toc
    assert '<section class="toc">' not in no_toc


def test_start_each_on_right_toggles_binding_class() -> None:
    arts = [_article(slug="a")]
    bound = compose_articles_html(arts, generated_at=NOW, start_each_on_right=True)
    plain = compose_articles_html(arts, generated_at=NOW, start_each_on_right=False)
    assert '<body class="bind-right">' in bound
    assert '<body class="bind-right">' not in plain
    assert "<body>" in plain
    # The right-hand-page rule exists in the stylesheet for the class.
    assert ".bind-right .bound-article { page-break-before: right; }" in bound


def test_privacy_switch_governs_the_private_source_appendix() -> None:
    arts = [
        _article(
            slug="with-private",
            endnotes=(
                ArticleEndnote(label="S1", title="Public Wire", url="https://ex.com/x"),
                ArticleEndnote(label="S2", title="Internal Dossier", kind="conclusion"),
            ),
        )
    ]
    strict = compose_articles_html(arts, generated_at=NOW, privacy="strict")
    tolerant = compose_articles_html(arts, generated_at=NOW, privacy="tolerant")

    # strict: no consolidated appendix section at all.
    assert '<section class="print-appendix"' not in strict
    # tolerant: the appendix lists the private source — but still with
    # no URL, because private sources have none.
    assert 'class="print-appendix"' in tolerant
    appendix = tolerant.split('class="print-appendix"', 1)[1]
    assert "Internal Dossier" in appendix
    assert "http" not in appendix
    # Either way, per-article endnotes are unchanged: the private
    # source is still listed inline by title.
    assert strict.count("Internal Dossier") == 1
    assert tolerant.count("Internal Dossier") == 2  # endnote + appendix


def test_privacy_switch_default_is_strict() -> None:
    arts = [
        _article(
            slug="default-priv",
            endnotes=(ArticleEndnote(label="S1", title="Internal Only"),),
        )
    ]
    assert '<section class="print-appendix"' not in compose_articles_html(
        arts, generated_at=NOW
    )


def test_invalid_privacy_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="privacy"):
        compose_articles_html([_article(slug="x")], generated_at=NOW, privacy="loose")


def test_export_articles_threads_switches_into_the_manifest(tmp_path: Path) -> None:
    store = _store()
    _seed_article(
        store, slug="bound-one", title="Bound One", body="Body.", when=NOW,
        fingerprint="fp-bound-one",
    )
    out = tmp_path / "bundle.html"
    manifest = export_articles(
        store,
        since=NOW - timedelta(days=7),
        until=NOW + timedelta(days=1),
        out_path=out,
        fmt="html",
        site_base="https://theseus.test",
        include_cover=True,
        include_toc=True,
        start_each_on_right=True,
        privacy="tolerant",
    )
    assert manifest.cover is True
    assert manifest.toc is True
    assert manifest.start_each_on_right is True
    assert manifest.privacy == "tolerant"
    text = out.read_text(encoding="utf-8")
    assert 'class="print-cover"' in text
    assert '<body class="bind-right">' in text


def test_export_articles_rejects_bad_privacy(tmp_path: Path) -> None:
    store = _store()
    with pytest.raises(ValueError, match="privacy"):
        export_articles(
            store,
            since=NOW - timedelta(days=7),
            out_path=tmp_path / "x.html",
            fmt="html",
            privacy="open",
        )


# ── Source-credibility plumbing (Round 17 prompt 19) ────────────────────────


def test_citation_credibility_reads_multiple_payload_shapes() -> None:
    assert _citation_credibility({"credibility": 64}) == 64.0
    assert _citation_credibility({"credibility_score": 88.5}) == 88.5
    assert _citation_credibility({"source_credibility": {"score_100": 41.0}}) == 41.0
    # `mean` is accepted as a 0-1 fraction and scaled.
    assert _citation_credibility({"source_credibility": {"mean": 0.5}}) == 50.0
    # Out-of-range is clamped; junk yields None.
    assert _citation_credibility({"credibility": 250}) == 100.0
    assert _citation_credibility({"credibility": "n/a"}) is None
    assert _citation_credibility({}) is None


def test_fetch_articles_carries_citation_credibility_into_endnotes() -> None:
    store = _store()
    _seed_article(
        store,
        slug="cred-article",
        title="Credibility Article",
        body="Body.",
        when=NOW,
        citations=[
            {
                "label": "S1",
                "source_kind": "news",
                "source_id": "n_1",
                "quoted_span": "quoted",
                "public_url": "https://example.com/n/1",
                "credibility_score": 73.0,
            }
        ],
    )
    rows = fetch_articles_since(
        store, since=NOW - timedelta(days=7), until=NOW + timedelta(days=1)
    )
    assert len(rows) == 1
    assert rows[0].endnotes[0].credibility == 73.0
    html = compose_articles_html(rows, generated_at=NOW)
    assert "cred 73/100" in html


def test_format_credibility_rounds_and_clamps() -> None:
    assert _format_credibility(72.4) == "cred 72/100"
    assert _format_credibility(72.6) == "cred 73/100"
    assert _format_credibility(-5) == "cred 0/100"
    assert _format_credibility(140) == "cred 100/100"
    assert _format_credibility(None) is None
    assert _format_credibility(float("nan")) is None


# ── F. Print-stylesheet snapshot at three article lengths ───────────────────


@pytest.mark.parametrize(
    "length,body",
    [("short", _SHORT_BODY), ("medium", _MEDIUM_BODY), ("long", _LONG_BODY)],
)
def test_print_stylesheet_snapshot_holds_at_three_lengths(length: str, body: str) -> None:
    art = _article(
        slug=f"len-{length}",
        title=f"{length.title()} Article",
        body=body,
        endnotes=(
            ArticleEndnote(
                label="S1",
                title="Cited Source",
                kind="news",
                url="https://example.com/s",
                credibility=70.0,
            ),
        ),
    )
    html = compose_articles_html([art], generated_at=NOW)

    # Composition is deterministic — the same input snapshots identically
    # on every run (no render-time state leaks into the document).
    assert html == compose_articles_html([art], generated_at=NOW)

    # Invariants that must hold regardless of body length:
    assert html.startswith("<!doctype html>")
    assert html.count('class="print-metadata-block"') == 1
    assert html.count('class="print-endnotes"') == 1
    assert f"<h1>{length.title()} Article</h1>" in html
    assert 'id="art-len-' + length + '"' in html
    assert 'href="#art-len-' + length + '"' in html
    # The print stylesheet ships embedded and keeps headings with bodies.
    assert "@media print" not in html  # bound doc uses bare @page, not @media
    assert "page-break-after: avoid" in html


# ── E. Long-form: a synthetic ~50-page bound export ─────────────────────────


def _slug_anchor(slug: str) -> str:
    return "art-" + "".join(c if c.isalnum() else "-" for c in slug).strip("-").lower()


def test_fifty_page_bound_export_is_structurally_sound(tmp_path: Path) -> None:
    """Build a synthetic ~50-page bound export and confirm the long-form
    guarantees: TOC entries link, numbering is continuous, headings are
    kept with their bodies, and signature fingerprints match the
    canonical (signature-table) record."""
    store = _store()
    article_count = 28
    long_body = "\n\n".join(
        ["## Section heading"]
        + [
            f"Paragraph {i} of a deliberately long article so the bound "
            f"document spans many pages under print layout."
            for i in range(22)
        ]
    )
    expected_fingerprints: dict[str, str] = {}
    for n in range(article_count):
        slug = f"longform-{n:02d}"
        fingerprint = f"fp-longform-{n:02d}"
        expected_fingerprints[slug] = fingerprint
        _seed_article(
            store,
            slug=slug,
            title=f"Long-form Article {n:02d}",
            body=long_body,
            when=NOW + timedelta(hours=n),
            fingerprint=fingerprint,
        )

    articles = fetch_articles_since(
        store,
        since=NOW - timedelta(days=1),
        until=NOW + timedelta(days=2),
        site_base="https://theseus.test",
    )
    assert len(articles) == article_count

    html = compose_articles_html(
        articles,
        generated_at=NOW,
        include_cover=True,
        include_toc=True,
        start_each_on_right=True,
        privacy="strict",
    )

    # TOC entries link: every TOC href resolves to a real article id.
    toc_section = html.split('<section class="toc">', 1)[1].split("</section>", 1)[0]
    toc_hrefs = set(re.findall(r'href="#(art-[^"]+)"', toc_section))
    body_ids = set(re.findall(r'id="(art-[^"]+)"', html))
    assert len(toc_hrefs) == article_count
    assert toc_hrefs <= body_ids

    # Page numbers continue across articles: a single continuous page
    # counter, never reset between articles.
    assert "content: counter(page)" in html
    assert "counter-reset: page" not in html
    # Numbering starts on page 2 — page 1 (the cover) is suppressed.
    assert "@page :first" in html

    # No orphaned headings: every heading level is kept with what
    # follows it (page-break-after: avoid).
    for selector in (
        r"\.bound-article h1",
        r"\.bound-article h2",
        r"\.print-endnotes h2",
    ):
        rule = re.search(selector + r"\s*\{[^}]*\}", html)
        assert rule is not None, selector
        assert "page-break-after: avoid" in rule.group(0), selector

    # Signature fingerprints match the canonical web record: the
    # fingerprint shown in each article's metadata block is exactly the
    # one stored in the PublicationSignature table.
    for slug, fingerprint in expected_fingerprints.items():
        anchor = _slug_anchor(slug)
        section = html.split(f'id="{anchor}"', 1)[1].split("</article>", 1)[0]
        assert f'<dd class="fingerprint">{fingerprint}</dd>' in section

    # When WeasyPrint is available, render the real PDF and confirm the
    # bound document genuinely spans ~50 pages. Skipped in minimal CI.
    weasyprint = pytest.importorskip("weasyprint")
    out = tmp_path / "longform.pdf"
    document = weasyprint.HTML(string=html).render()
    assert len(document.pages) >= 45
    document.write_pdf(str(out))
    assert out.exists() and out.stat().st_size > 0
    assert out.read_bytes().startswith(b"%PDF")

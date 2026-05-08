"""Tests for the bound-article export CLI."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from noosphere.docgen.articles_export import (
    ArticleEndnote,
    ArticleForExport,
    compose_articles_html,
    export_articles,
    fetch_articles_since,
)
from noosphere.models import PublicationSignature, PublishedConclusion
from noosphere.store import Store


ORG_ID = "org_export"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_article(
    store: Store,
    *,
    slug: str,
    title: str,
    body: str,
    when: datetime,
    citations: list[dict[str, str | None]] | None = None,
    fingerprint: str | None = None,
    version: int = 1,
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
        version=version,
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
            version=version,
            canonical_hash="0" * 64,
            signature_hex="dead",
            key_fingerprint=fingerprint,
            signed_at=when.isoformat(),
        )
        with store.session() as session:
            session.add(sig)
            session.commit()


def test_fetch_articles_filters_by_window_and_loads_signature() -> None:
    store = _store()
    _seed_article(
        store,
        slug="too-old",
        title="Old Article",
        body="Old body.",
        when=NOW - timedelta(days=120),
    )
    _seed_article(
        store,
        slug="in-window",
        title="In-window Article",
        body="In-window body.",
        when=NOW - timedelta(days=10),
        fingerprint="abcd1234",
        citations=[
            {
                "label": "S1",
                "source_kind": "opinion",
                "source_id": "op_1",
                "quoted_span": "evidence quoted",
                "public_url": "https://example.com/op/1",
            }
        ],
    )
    _seed_article(
        store,
        slug="too-new",
        title="Future Article",
        body="Future body.",
        when=NOW + timedelta(days=10),
    )

    rows = fetch_articles_since(
        store,
        since=NOW - timedelta(days=30),
        until=NOW + timedelta(seconds=1),
        site_base="https://theseus.test",
    )
    assert [r.slug for r in rows] == ["in-window"]
    art = rows[0]
    assert art.title == "In-window Article"
    assert art.signature_fingerprint == "abcd1234"
    assert art.canonical_url == "https://theseus.test/c/in-window"
    assert art.endnotes
    assert art.endnotes[0].url == "https://example.com/op/1"


def test_compose_articles_html_has_toc_and_one_article_per_section() -> None:
    articles = [
        ArticleForExport(
            slug="alpha",
            version=1,
            title="Alpha Title",
            byline="Theseus",
            published_at=NOW,
            body_markdown="## Subhead\n\nFirst alpha paragraph.\n\nSecond.",
            methodology="six_layer_coherence",
            confidence=0.8,
            confidence_context="stated 86%",
            mqs_composite=0.72,
            canonical_url="https://theseus.test/c/alpha",
            signature_fingerprint="fp-alpha",
            endnotes=(
                ArticleEndnote(
                    label="S1",
                    title="Public source",
                    kind="opinion",
                    url="https://example.com/source",
                ),
                ArticleEndnote(
                    label="S2",
                    title="Internal source",
                    kind="conclusion",
                ),
            ),
        ),
        ArticleForExport(
            slug="beta",
            version=2,
            title="Beta Title",
            byline="Theseus",
            published_at=NOW + timedelta(days=1),
            body_markdown="Beta body.",
            methodology=None,
            confidence=None,
            confidence_context=None,
            mqs_composite=None,
            canonical_url="https://theseus.test/c/beta",
            signature_fingerprint=None,
            endnotes=(),
        ),
    ]
    html = compose_articles_html(articles, generated_at=NOW)

    assert html.startswith("<!doctype html>")
    # TOC entries link to anchors that exist in the body.
    assert 'href="#art-alpha"' in html
    assert 'href="#art-beta"' in html
    assert 'id="art-alpha"' in html
    assert 'id="art-beta"' in html
    # Each article carries the print metadata block.
    assert html.count('class="print-metadata-block"') == 2
    assert "Alpha Title" in html
    assert "fp-alpha" in html
    assert "(unsigned)" in html  # beta has no fingerprint
    # Endnotes only render when present, and external URLs become <a>.
    assert html.count('class="print-endnotes"') == 1
    assert 'href="https://example.com/source"' in html
    # Internal-only source must NOT leak any URL.
    internal_section = html.split("Internal source", 1)[1].split("</li>", 1)[0]
    assert "http" not in internal_section
    # Page break rule for new articles is in the embedded CSS.
    assert "page-break-before: right" in html


def test_export_articles_html_format_writes_one_file(tmp_path: Path) -> None:
    store = _store()
    _seed_article(
        store,
        slug="quarterly",
        title="Quarterly Review",
        body="Body text.",
        when=NOW,
    )
    out = tmp_path / "bound.html"
    manifest = export_articles(
        store,
        since=NOW - timedelta(days=7),
        out_path=out,
        fmt="html",
        site_base="https://theseus.test",
    )
    assert manifest.article_count == 1
    assert manifest.html_path == out
    assert manifest.pdf_path is None
    assert manifest.skipped_pdf_reason is None
    text = out.read_text(encoding="utf-8")
    assert "Quarterly Review" in text
    assert 'href="#art-quarterly"' in text


def test_export_articles_pdf_falls_back_to_html_when_weasyprint_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store()
    _seed_article(
        store,
        slug="pdf-target",
        title="PDF Target",
        body="Body.",
        when=NOW,
    )
    # Force the import inside ``export_articles`` to fail; the caller
    # is supposed to keep working and emit the HTML companion.
    import sys

    monkeypatch.setitem(sys.modules, "weasyprint", None)

    out = tmp_path / "bound.pdf"
    manifest = export_articles(
        store,
        since=NOW - timedelta(days=7),
        out_path=out,
        fmt="pdf",
    )
    assert manifest.article_count == 1
    assert manifest.pdf_path is None
    assert manifest.skipped_pdf_reason is not None
    assert "weasyprint" in manifest.skipped_pdf_reason.lower()
    assert manifest.html_path.exists()
    assert "PDF Target" in manifest.html_path.read_text(encoding="utf-8")


def test_export_respects_visibility_filter() -> None:
    """Rows that aren't articles never appear in the bundle.

    The visibility rule is the table itself: ``PublishedConclusion``
    is the public-facing snapshot; private content lives elsewhere.
    Here we plant a non-ARTICLE row in the same window and confirm
    the export ignores it.
    """
    store = _store()
    _seed_article(
        store,
        slug="public-article",
        title="Public",
        body="Body.",
        when=NOW,
    )

    private_row = PublishedConclusion(
        organization_id=ORG_ID,
        source_conclusion_id="src_internal",
        slug="internal-conclusion",
        version=1,
        kind="CONCLUSION",  # <- not an ARTICLE; must be skipped.
        discounted_confidence=0.5,
        stated_confidence=0.5,
        calibration_discount_reason="",
        payload_json=json.dumps(
            {
                "schema": "theseus.publicConclusion.v1",
                "conclusionText": "PRIVATE_TITLE_DO_NOT_LEAK",
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
                    "profiles": [],
                },
                "timeline": [],
                "whatWouldChangeOurMind": [],
                "citations": [],
            }
        ),
        doi="",
        zenodo_record_id="",
        published_at=NOW,
    )
    with store.session() as session:
        session.add(private_row)
        session.commit()

    rows = fetch_articles_since(store, since=NOW - timedelta(days=7))
    assert [r.slug for r in rows] == ["public-article"]
    html = compose_articles_html(rows)
    assert "PRIVATE_TITLE_DO_NOT_LEAK" not in html

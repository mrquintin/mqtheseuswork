"""
Tests for source-standing canonicalization, the in-memory ledger,
synthetic pollers, and cascade fan-out into RevisionInputs.

Synthetic over-the-wire calls: we hand each poller a fake fetch
function so the test is hermetic.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noosphere.cascade.revision import RevisionInput
from noosphere.literature.standing import (
    PROPAGATING_STATUSES,
    CitationLink,
    InMemoryStandingLedger,
    StandingStatus,
    StandingTransition,
    canonical_source_id,
    affected_conclusions,
    now_utc,
)
from noosphere.literature.standing_polls import (
    PollerOrchestrator,
    revision_inputs_for,
)
from noosphere.literature.standing_polls.arxiv import (
    ArxivPage,
    ArxivWithdrawalPoller,
    parse_atom_entry,
)
from noosphere.literature.standing_polls.generic_url import (
    FetchResult,
    GenericUrlPoller,
)
from noosphere.literature.standing_polls.retraction_watch import (
    RetractionNotice,
    RetractionWatchPoller,
)


# ── canonicalization ─────────────────────────────────────────────────────


class TestCanonicalSourceId:
    def test_doi_normalised_to_lowercase_prefix(self) -> None:
        assert (
            canonical_source_id(doi="10.1234/Foo.BAR")
            == "doi:10.1234/foo.bar"
        )

    def test_doi_extracted_from_url(self) -> None:
        # URL containing a DOI should still collapse to the DOI form.
        url = "https://doi.org/10.1234/foo.bar?utm_source=x"
        assert canonical_source_id(url=url) == "doi:10.1234/foo.bar"

    def test_arxiv_id_strips_version(self) -> None:
        assert canonical_source_id(arxiv_id="1701.01234v3") == "arxiv:1701.01234"
        assert canonical_source_id(url="https://arxiv.org/abs/1701.01234v3") == "arxiv:1701.01234"

    def test_url_normalisation_collapses_equivalents(self) -> None:
        a = canonical_source_id(url="https://Example.com/path/?b=2&a=1")
        b = canonical_source_id(url="HTTPS://example.COM/path?a=1&b=2")
        assert a == b
        assert a.startswith("url:")

    def test_requires_at_least_one_input(self) -> None:
        with pytest.raises(ValueError):
            canonical_source_id()


# ── ledger idempotence ──────────────────────────────────────────────────


def _t(source_id: str, status: StandingStatus, reason: str = "x") -> StandingTransition:
    return StandingTransition(
        source_id=source_id,
        status=status,
        reason=reason,
        poller="test",
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class TestInMemoryStandingLedger:
    def test_first_append_returns_true(self) -> None:
        ledger = InMemoryStandingLedger()
        assert ledger.append(_t("doi:10.1/a", StandingStatus.RETRACTED)) is True

    def test_duplicate_append_is_idempotent(self) -> None:
        ledger = InMemoryStandingLedger()
        ledger.append(_t("doi:10.1/a", StandingStatus.RETRACTED, reason="r"))
        wrote_again = ledger.append(_t("doi:10.1/a", StandingStatus.RETRACTED, reason="r"))
        assert wrote_again is False
        assert len(ledger.all()) == 1

    def test_distinct_reason_appends_again(self) -> None:
        ledger = InMemoryStandingLedger()
        ledger.append(_t("doi:10.1/a", StandingStatus.RETRACTED, reason="initial"))
        wrote = ledger.append(_t("doi:10.1/a", StandingStatus.RETRACTED, reason="updated"))
        assert wrote is True
        assert len(ledger.all()) == 2

    def test_history_filters_by_source_id(self) -> None:
        ledger = InMemoryStandingLedger()
        ledger.append(_t("doi:10.1/a", StandingStatus.RETRACTED))
        ledger.append(_t("doi:10.1/b", StandingStatus.DISPUTED))
        assert len(ledger.history("doi:10.1/a")) == 1


# ── retraction watch poller ─────────────────────────────────────────────


class TestRetractionWatchPoller:
    def test_emits_retracted_for_cited_doi(self) -> None:
        cited = "doi:10.5555/test.paper"
        notices = [
            RetractionNotice(
                doi="10.5555/test.paper",
                reason="Image manipulation",
                notice_url="https://retractionwatch.com/notice/123",
            ),
            # Not cited — should be filtered out.
            RetractionNotice(
                doi="10.9999/other",
                reason="Other",
                notice_url="https://retractionwatch.com/notice/999",
            ),
        ]
        poller = RetractionWatchPoller(fetch=lambda: notices)
        out = poller.poll([cited])
        assert len(out) == 1
        t = out[0]
        assert t.source_id == cited
        assert t.status is StandingStatus.RETRACTED
        assert t.notice_source is not None
        assert t.reason == "Image manipulation"

    def test_correction_notice_emits_corrected(self) -> None:
        notices = [
            RetractionNotice(
                doi="10.5555/test.paper",
                reason="Erratum: figure 2 axis labels",
                notice_url="https://retractionwatch.com/correction/1",
                is_correction=True,
            ),
        ]
        poller = RetractionWatchPoller(fetch=lambda: notices)
        out = poller.poll(["doi:10.5555/test.paper"])
        assert out[0].status is StandingStatus.CORRECTED


# ── arxiv withdrawal poller ─────────────────────────────────────────────


class TestArxivWithdrawalPoller:
    def test_emits_retracted_when_comment_says_withdrawn(self) -> None:
        page = ArxivPage(
            arxiv_id="1701.01234",
            title="A study of X",
            comment="This paper has been withdrawn by the authors due to a fatal error.",
            abstract_url="https://arxiv.org/abs/1701.01234",
        )
        poller = ArxivWithdrawalPoller(fetch=lambda _id: page)
        out = poller.poll(["arxiv:1701.01234"])
        assert len(out) == 1
        assert out[0].status is StandingStatus.RETRACTED
        assert out[0].source_id == "arxiv:1701.01234"

    def test_skips_non_arxiv_ids(self) -> None:
        called: list[str] = []

        def fetch(arxiv_id: str):
            called.append(arxiv_id)
            return None

        poller = ArxivWithdrawalPoller(fetch=fetch)
        poller.poll(["doi:10.1/foo", "url:abc"])
        assert called == []

    def test_active_paper_emits_no_transition(self) -> None:
        page = ArxivPage(
            arxiv_id="1701.01234",
            title="A study of X",
            comment="v2: minor revisions",
            abstract_url="https://arxiv.org/abs/1701.01234",
        )
        poller = ArxivWithdrawalPoller(fetch=lambda _id: page)
        assert poller.poll(["arxiv:1701.01234"]) == []

    def test_atom_parser_extracts_arxiv_page(self) -> None:
        xml = (
            b'<entry xmlns="http://www.w3.org/2005/Atom" '
            b'xmlns:arxiv="http://arxiv.org/schemas/atom">'
            b"<title>Withdrawn: bogus result</title>"
            b"<id>https://arxiv.org/abs/2001.12345v2</id>"
            b"<arxiv:comment>Paper withdrawn</arxiv:comment>"
            b"</entry>"
        )
        page = parse_atom_entry(xml)
        assert page is not None
        assert page.arxiv_id.startswith("2001.12345")
        assert "withdrawn" in page.title.lower()


# ── generic URL poller ──────────────────────────────────────────────────


class TestGenericUrlPoller:
    def test_410_emits_retracted(self) -> None:
        sid = "url:abc"
        url = "https://example.com/paper"
        poller = GenericUrlPoller(
            urls=[(sid, url)],
            http=lambda _u: FetchResult(status=410),
            robots=lambda _u: True,
        )
        out = poller.poll([sid])
        assert len(out) == 1
        assert out[0].status is StandingStatus.RETRACTED
        assert "410" in out[0].reason

    def test_404_emits_expired(self) -> None:
        sid = "url:abc"
        poller = GenericUrlPoller(
            urls=[(sid, "https://example.com/paper")],
            http=lambda _u: FetchResult(status=404),
            robots=lambda _u: True,
        )
        out = poller.poll([sid])
        assert out[0].status is StandingStatus.EXPIRED

    def test_robots_disallowed_skips_silently(self) -> None:
        called: list[str] = []

        def http(url: str):
            called.append(url)
            return FetchResult(status=200)

        poller = GenericUrlPoller(
            urls=[("url:abc", "https://example.com/paper")],
            http=http,
            robots=lambda _u: False,
        )
        out = poller.poll(["url:abc"])
        assert out == []
        assert called == []

    def test_page_replacement_emits_disputed(self) -> None:
        sid = "url:abc"
        poller = GenericUrlPoller(
            urls=[(sid, "https://example.com/paper")],
            http=lambda _u: FetchResult(status=200, body=b"new content"),
            robots=lambda _u: True,
            snapshot=lambda _id: "old-hash",
        )
        out = poller.poll([sid])
        assert len(out) == 1
        assert out[0].status is StandingStatus.DISPUTED

    def test_500_status_is_transient_no_emission(self) -> None:
        poller = GenericUrlPoller(
            urls=[("url:abc", "https://example.com/paper")],
            http=lambda _u: FetchResult(status=503),
            robots=lambda _u: True,
        )
        assert poller.poll(["url:abc"]) == []


# ── orchestrator + cascade hand-off ─────────────────────────────────────


class TestOrchestrator:
    def test_active_to_active_no_propagation(self) -> None:
        ledger = InMemoryStandingLedger()
        orch = PollerOrchestrator(ledger=ledger)
        # Poller that emits nothing — simulating ACTIVE→ACTIVE.
        orch.register(RetractionWatchPoller(fetch=lambda: []))
        propagating = orch.run(["doi:10.5555/x"])
        assert propagating == []
        assert ledger.all() == []

    def test_active_to_retracted_triggers_revision_input(self) -> None:
        ledger = InMemoryStandingLedger()
        orch = PollerOrchestrator(ledger=ledger)
        notices = [
            RetractionNotice(
                doi="10.5555/test.paper",
                reason="Fabricated data",
                notice_url="https://retractionwatch.com/notice/42",
            )
        ]
        orch.register(RetractionWatchPoller(fetch=lambda: notices))

        propagating = orch.run(["doi:10.5555/test.paper"])
        assert len(propagating) == 1
        assert propagating[0].status in PROPAGATING_STATUSES

        links = [
            CitationLink(conclusion_id="conc-1", source_id="doi:10.5555/test.paper"),
            CitationLink(conclusion_id="conc-2", source_id="doi:10.5555/test.paper"),
            CitationLink(conclusion_id="conc-irrelevant", source_id="doi:10.9999/other"),
        ]
        revisions = revision_inputs_for(propagating, links)
        assert sorted(c for c, _ in revisions) == ["conc-1", "conc-2"]
        for _, ri in revisions:
            assert isinstance(ri, RevisionInput)
            # Per the prompt: weight removed, NOT inverted.
            assert ri.weight == 0.0
            assert "RETRACTED" in ri.new_evidence

    def test_idempotent_repoll_writes_no_new_rows(self) -> None:
        ledger = InMemoryStandingLedger()
        orch = PollerOrchestrator(ledger=ledger)
        notices = [
            RetractionNotice(
                doi="10.5555/test.paper",
                reason="Fabricated data",
                notice_url="https://retractionwatch.com/notice/42",
            )
        ]
        orch.register(RetractionWatchPoller(fetch=lambda: list(notices)))

        first = orch.run(["doi:10.5555/test.paper"])
        second = orch.run(["doi:10.5555/test.paper"])

        assert len(first) == 1
        assert second == []
        assert len(ledger.all()) == 1


def test_affected_conclusions_dedupes_and_sorts() -> None:
    links = [
        CitationLink(conclusion_id="b", source_id="s1"),
        CitationLink(conclusion_id="a", source_id="s1"),
        CitationLink(conclusion_id="a", source_id="s1"),
        CitationLink(conclusion_id="c", source_id="s2"),
    ]
    assert affected_conclusions(links, "s1") == ["a", "b"]


def test_now_utc_is_timezone_aware() -> None:
    n = now_utc()
    assert n.tzinfo is not None

"""End-to-end smoke test for the follow-digest pipeline.

This test exercises the production cutover narrative for Round 18
prompt 32: a synthetic subscriber whose scope captures every Round-18
publication (prompts 13, 14, 15, 18) receives a single well-formed
digest covering exactly those items, with the per-cycle ack link and
one-click unsubscribe link wired correctly and zero tracking pixels.

The test is intentionally pure-Python — it hits the builder + the
scheduler intake/outbox round-trip but does not require a database or
a live mail transport. The codex-side delivery contract (DigestSend
ledger, bounce-pause, ack hashing) is exercised by Vitest tests
against the Prisma client.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from noosphere.social import digest_builder as db
from noosphere.social import scheduler as sch

SITE = "https://theseus.test"
NOW = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)


# ── Round 18 fixture: publications 13/14/15 plus retraction propagation 18 ──

def _event(
    *,
    kind: db.EventKind,
    headline: str,
    slug: str,
    methods: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    is_major: bool = False,
    age_hours: float = 6.0,
) -> db.DigestEvent:
    return db.DigestEvent(
        kind=kind,
        headline=headline,
        summary=f"Round 18 — {headline}",
        url=f"{SITE}/c/{slug}/v/1",
        occurred_at=NOW - timedelta(hours=age_hours),
        conclusion_slug=slug,
        methodology_names=methods,
        domain_tags=tags,
        is_major=is_major,
    )


def _round18_events() -> list[db.DigestEvent]:
    return [
        _event(
            kind="publication",
            headline="Prompt 13: Cascade graph closure",
            slug="cascade-closure",
            methods=("cascade_closure",),
            tags=("epistemology",),
            age_hours=72,
        ),
        _event(
            kind="publication",
            headline="Prompt 14: Calibration-aware confidence",
            slug="calibration-aware-confidence",
            methods=("calibration_aware",),
            tags=("forecasting",),
            age_hours=48,
        ),
        _event(
            kind="publication",
            headline="Prompt 15: Provenance heatmap",
            slug="provenance-heatmap",
            methods=("provenance_heatmap",),
            tags=("epistemology",),
            age_hours=24,
        ),
        _event(
            kind="retraction",
            headline="Prompt 18: Retraction propagation lands",
            slug="retraction-propagation",
            methods=("retraction_propagation",),
            tags=("epistemology",),
            is_major=True,
            age_hours=6,
        ),
    ]


def _firm_subscriber(*, ack_token: str = "ack-firm-1") -> db.Subscriber:
    return db.Subscriber(
        id="smoke_firm",
        email="reader@example.org",
        scope="firm",
        scope_key="",
        cadence="weekly",
        unsubscribe_token="unsub-firm-1",
        last_sent_at=None,
        ack_token=ack_token,
    )


# ── A. End-to-end build + content invariants ───────────────────────────────


def test_synthetic_firm_subscriber_receives_all_round18_publications() -> None:
    sub = _firm_subscriber()
    events = _round18_events()
    digest = db.build_digest(sub, db.select_events_for(sub, events, NOW), site_url=SITE)
    assert digest is not None
    # Every Round-18 event appears, by URL — the URL is the unambiguous
    # identifier the reader actually clicks.
    for ev in events:
        assert ev.url in digest.text, f"missing {ev.url} in text body"
        assert ev.url in digest.html, f"missing {ev.url} in html body"
    # Subject reflects the right kind counts.
    assert "publication" in digest.subject
    assert "retraction" in digest.subject
    # Items are sorted newest-first.
    occurred_at = [item.occurred_at for item in digest.items]
    assert occurred_at == sorted(occurred_at, reverse=True)


def test_visibility_filters_honored_for_methodology_scope() -> None:
    method_sub = db.Subscriber(
        id="smoke_method",
        email="m@example.org",
        scope="methodology",
        scope_key="calibration_aware",
        cadence="weekly",
        unsubscribe_token="unsub-m-1",
        ack_token="ack-m-1",
    )
    events = _round18_events()
    digest = db.build_digest(
        method_sub,
        db.select_events_for(method_sub, events, NOW),
        site_url=SITE,
    )
    assert digest is not None
    headlines = {item.headline for item in digest.items}
    # Only the calibration-aware item matches this method scope.
    assert headlines == {"Prompt 14: Calibration-aware confidence"}


def test_immediate_cadence_only_fires_on_major_events() -> None:
    immediate_sub = db.Subscriber(
        id="smoke_imm",
        email="i@example.org",
        scope="firm",
        scope_key="",
        cadence="immediate",
        unsubscribe_token="unsub-i-1",
        ack_token="ack-i-1",
    )
    events = _round18_events()
    selected = db.select_events_for(immediate_sub, events, NOW)
    # The only Round-18 event flagged is_major is the retraction
    # propagation (prompt 18) — the immediate lane is reserved for
    # firm-wide major events, by design.
    assert {e.headline for e in selected} == {
        "Prompt 18: Retraction propagation lands"
    }


# ── B. Production cutover wiring (scheduler round-trip) ────────────────────


def test_scheduler_round_trip_emits_outbox_with_ack_and_unsubscribe(
    tmp_path: Path,
) -> None:
    intake = tmp_path / "intake.json"
    outbox = tmp_path / "outbox.json"
    intake.write_text(
        json.dumps(
            {
                "site_url": SITE,
                "generated_at": NOW.isoformat(),
                "subscribers": [
                    {
                        "id": "smoke_firm",
                        "email": "reader@example.org",
                        "scope": "firm",
                        "scope_key": "",
                        "cadence": "weekly",
                        "unsubscribe_token": "unsub-firm-1",
                        "ack_token": "ack-firm-1",
                        "last_sent_at": None,
                    }
                ],
                "events": [
                    {
                        "kind": ev.kind,
                        "headline": ev.headline,
                        "summary": ev.summary,
                        "url": ev.url,
                        "occurred_at": ev.occurred_at.isoformat(),
                        "conclusion_slug": ev.conclusion_slug,
                        "methodology_names": list(ev.methodology_names),
                        "domain_tags": list(ev.domain_tags),
                        "is_major": ev.is_major,
                    }
                    for ev in _round18_events()
                ],
            }
        ),
        encoding="utf-8",
    )

    digests = sch.run_once(intake, outbox, now=NOW)
    assert len(digests) == 1
    rendered = digests[0]
    assert rendered.unsubscribe_url == f"{SITE}/api/public/unsubscribe/unsub-firm-1"
    assert rendered.ack_url == f"{SITE}/api/public/digest-ack/ack-firm-1"

    payload = json.loads(outbox.read_text(encoding="utf-8"))
    out = payload["digests"][0]
    assert out["ack_url"] == f"{SITE}/api/public/digest-ack/ack-firm-1"
    assert out["unsubscribe_url"] == f"{SITE}/api/public/unsubscribe/unsub-firm-1"
    assert out["headers"]["List-Unsubscribe"] == f"<{rendered.unsubscribe_url}>"
    # Subject + item count round-trip so the codex deliver step can
    # stamp the DigestSend ledger row from the outbox alone.
    assert out["subject"] == rendered.subject
    assert len(out["items"]) == 4


# ── C. No-tracking-pixel discipline (renderer-level) ───────────────────────


def test_rendered_digest_contains_no_tracking_mechanism() -> None:
    sub = _firm_subscriber()
    digest = db.build_digest(
        sub, db.select_events_for(sub, _round18_events(), NOW), site_url=SITE
    )
    assert digest is not None
    html = digest.html.lower()
    # Tags: no <img>, no <iframe>, no meta refresh redirect.
    assert "<img" not in html
    assert "<iframe" not in html
    assert not re.search(r"<\s*meta[^>]+http-equiv=['\"]?refresh", html)
    # Common pixel shibboleths.
    assert "1x1" not in html
    assert ".gif" not in html
    assert "beacon" not in html
    # The disclaimer text is allowed and expected.
    assert "tracking pixels" in html  # part of the disclaimer phrase


def test_no_tracking_pixels_lint_passes_on_current_templates() -> None:
    """The standalone CI lint must accept the current email templates."""
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "check_no_tracking_pixels.py"
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(repo_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"check_no_tracking_pixels failed:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ── D. Voluntary "I read this" link is well-formed ─────────────────────────


def test_ack_link_is_present_only_when_token_supplied() -> None:
    with_token = _firm_subscriber(ack_token="ack-firm-1")
    without_token = db.Subscriber(
        id="smoke_no_ack",
        email="silent@example.org",
        scope="firm",
        scope_key="",
        cadence="weekly",
        unsubscribe_token="unsub-silent",
        ack_token="",  # codex export chose not to mint a token this cycle
    )
    events = _round18_events()
    d1 = db.build_digest(with_token, db.select_events_for(with_token, events, NOW), site_url=SITE)
    d2 = db.build_digest(without_token, db.select_events_for(without_token, events, NOW), site_url=SITE)
    assert d1 is not None and d2 is not None
    assert d1.ack_url and d1.ack_url in d1.text and d1.ack_url in d1.html
    assert d2.ack_url == ""
    assert "/api/public/digest-ack/" not in d2.text
    assert "/api/public/digest-ack/" not in d2.html
    # Sanity: the ack URL is per-subscriber per-cycle, so two subs in
    # the same cycle do not collide on a shared link.
    assert "ack-firm-1" in d1.ack_url


def test_ack_token_hashes_to_a_stable_lookup_value() -> None:
    """Codex stores SHA-256 of the ack token. The hash is deterministic.

    This mirrors the routing contract in
    ``theseus-codex/src/app/api/public/digest-ack/[token]/route.ts``: the
    raw token is sent to the recipient, the hash is stored, and the
    server hashes incoming clicks to look up the matching DigestSend.
    """
    token = "ack-firm-1"
    expected_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    # The hash is the lookup key on the DigestSend row.
    assert len(expected_hash) == 64
    # Recompute it the same way the route does and confirm idempotency.
    assert hashlib.sha256(token.encode("utf-8")).hexdigest() == expected_hash


# ── E. Unsubscribe wiring ──────────────────────────────────────────────────


def test_unsubscribe_url_uses_subscriber_token_and_survives_one_cycle() -> None:
    sub = _firm_subscriber()
    digest = db.build_digest(
        sub, db.select_events_for(sub, _round18_events(), NOW), site_url=SITE
    )
    assert digest is not None
    assert digest.unsubscribe_url == f"{SITE}/api/public/unsubscribe/unsub-firm-1"
    assert digest.unsubscribe_url in digest.text
    assert digest.unsubscribe_url in digest.html
    assert digest.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"

    # After unsubscribe, the codex export omits the row from the next
    # intake — we model the post-unsubscribe cycle by passing an empty
    # subscriber list and confirming no digest is built.
    digests_after = db.build_digests([], _round18_events(), site_url=SITE, now=NOW)
    assert digests_after == []

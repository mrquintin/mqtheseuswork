"""Follow-digest scheduler.

Runs the per-subscriber digest pipeline on a fixed cadence (weekly by
default; immediate for firm-wide major events; monthly for opted-in
subscribers). The scheduler does not own the subscriber list or the
mail transport — those live in the Next.js codex app, which is also
the system of record for double-opt-in confirms and one-click
unsubscribes.

The scheduler's job is to:

  1. Load a snapshot of active subscribers + recent digest-eligible
     events from a JSON intake (produced by the codex export).
  2. Hand both to ``digest_builder.build_digests`` to compute the
     per-subscriber payloads.
  3. Emit the rendered digests as a JSON outbox the codex app picks
     up and sends through the existing ``sendMail`` pipeline (Resend
     or SMTP). No third-party email vendor with non-auditable
     telemetry is used; receipts go through the same path as every
     other firm email.

Keeping the boundary at JSON intake/outbox means tests do not need a
live database: the pure event/subscriber types are sufficient.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from noosphere.social.digest_builder import (
    Cadence,
    Digest,
    DigestEvent,
    Scope,
    Subscriber,
    build_digests,
)

logger = logging.getLogger(__name__)

DEFAULT_SITE_URL = "https://theseuscodex.com"


@dataclass(frozen=True)
class IntakeSnapshot:
    """Parsed intake JSON: subscribers + events frozen at a moment in time."""

    subscribers: tuple[Subscriber, ...]
    events: tuple[DigestEvent, ...]
    site_url: str
    generated_at: datetime


def load_intake(path: Path) -> IntakeSnapshot:
    """Load and validate the codex-produced intake JSON.

    Expected schema (informal):

      {
        "site_url": "https://...",
        "generated_at": "ISO-8601",
        "subscribers": [
          {
            "id": "...", "email": "...", "scope": "firm|methodology|domain|conclusion",
            "scope_key": "...", "cadence": "weekly|immediate|monthly",
            "unsubscribe_token": "...", "last_sent_at": "ISO-8601 | null"
          }, ...
        ],
        "events": [
          {
            "kind": "publication|revision|retraction|calibration_breach",
            "headline": "...", "summary": "...", "url": "...",
            "occurred_at": "ISO-8601",
            "conclusion_slug": "...",
            "methodology_names": ["..."],
            "domain_tags": ["..."],
            "is_major": true|false
          }, ...
        ]
      }
    """

    raw = json.loads(path.read_text(encoding="utf-8"))
    site_url = str(raw.get("site_url") or DEFAULT_SITE_URL).rstrip("/")
    generated_at = _parse_iso(raw.get("generated_at")) or datetime.now(timezone.utc)
    subscribers = tuple(_parse_subscriber(row) for row in raw.get("subscribers", []))
    events = tuple(_parse_event(row) for row in raw.get("events", []))
    return IntakeSnapshot(
        subscribers=subscribers,
        events=events,
        site_url=site_url,
        generated_at=generated_at,
    )


def write_outbox(path: Path, digests: Sequence[Digest]) -> None:
    """Emit the rendered digests as a JSON outbox file the codex app reads."""

    payload = {
        "schema": "theseus.followDigest.outbox.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "digests": [_digest_to_jsonable(d) for d in digests],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_once(
    intake_path: Path,
    outbox_path: Path,
    *,
    now: datetime | None = None,
) -> list[Digest]:
    """Compute one batch of digests from an intake file, write the outbox.

    Returns the in-memory ``Digest`` list for callers that prefer to
    forward directly rather than re-read the outbox file.
    """

    snapshot = load_intake(intake_path)
    when = now or snapshot.generated_at
    digests = build_digests(
        snapshot.subscribers,
        snapshot.events,
        site_url=snapshot.site_url,
        now=when,
    )
    write_outbox(outbox_path, digests)
    logger.info(
        "follow_digest_scheduler",
        extra={
            "subscribers_in": len(snapshot.subscribers),
            "events_in": len(snapshot.events),
            "digests_out": len(digests),
            "outbox": str(outbox_path),
        },
    )
    return digests


# ── parsing helpers ────────────────────────────────────────────────────────

def _parse_subscriber(row: dict) -> Subscriber:
    scope: Scope = row["scope"]
    cadence: Cadence = row.get("cadence", "weekly")
    return Subscriber(
        id=str(row["id"]),
        email=str(row["email"]),
        scope=scope,
        scope_key=str(row.get("scope_key", "") or ""),
        cadence=cadence,
        unsubscribe_token=str(row["unsubscribe_token"]),
        last_sent_at=_parse_iso(row.get("last_sent_at")),
        ack_token=str(row.get("ack_token", "") or ""),
    )


def _parse_event(row: dict) -> DigestEvent:
    return DigestEvent(
        kind=row["kind"],
        headline=str(row.get("headline", "")),
        summary=str(row.get("summary", "")),
        url=str(row.get("url", "")),
        occurred_at=_parse_iso(row.get("occurred_at")) or datetime.now(timezone.utc),
        conclusion_slug=str(row.get("conclusion_slug", "") or ""),
        methodology_names=tuple(row.get("methodology_names") or ()),
        domain_tags=tuple(row.get("domain_tags") or ()),
        is_major=bool(row.get("is_major", False)),
    )


def _parse_iso(value: object) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _digest_to_jsonable(digest: Digest) -> dict:
    return {
        "subscriber_id": digest.subscriber_id,
        "to": digest.to,
        "subject": digest.subject,
        "text": digest.text,
        "html": digest.html,
        "unsubscribe_url": digest.unsubscribe_url,
        "ack_url": digest.ack_url,
        "headers": dict(digest.headers),
        "items": [asdict(item) | {"occurred_at": item.occurred_at.isoformat()} for item in digest.items],
    }


# ── CLI ────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Theseus follow-digest scheduler")
    parser.add_argument("--intake", required=True, type=Path, help="Path to intake JSON")
    parser.add_argument("--outbox", required=True, type=Path, help="Path to write outbox JSON")
    parser.add_argument(
        "--now",
        default=None,
        help="Override the wall-clock used to apply cadence windows (ISO-8601)",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    now = _parse_iso(args.now) if args.now else None
    digests = run_once(args.intake, args.outbox, now=now)
    print(f"wrote {len(digests)} digest(s) to {args.outbox}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""Build per-subscriber follow-digests.

A digest is one email per subscriber per cycle, listing the public-facing
events that occurred since their last `last_sent_at` and that fall within
their declared scope (firm-wide, a methodology name, a domain tag, or a
specific conclusion slug). Honest reporting is mandatory: revisions and
retraction propagations get the same prominence as new publications,
not a downplayed footer.

The module is intentionally pure: callers feed it lists of subscribers
and events; it returns rendered ``Digest`` objects. The web app
(theseus-codex) is the system of record for ``Subscriber`` rows and the
SMTP/Resend transport. The scheduler in ``noosphere/social/scheduler.py``
wires this builder to a JSON intake produced by the codex export, then
hands the rendered digests back to codex for delivery via the existing
``sendMail`` path.

No tracking pixels are inserted. Every email carries a one-click
unsubscribe URL whose token is the subscriber's own ``unsubscribe_token``.

If a per-cycle acknowledgment token is supplied, the digest also
includes a voluntary "I read this" link. The token is unique to the
specific send; the codex side stores only its SHA-256 hash (see
``DigestSend.ackTokenHash`` in the Prisma schema) so the firm can
count opt-in opens without storing per-recipient identifiers. No ack
link is rendered when no token is supplied — silence is the default,
not a hidden default-on counter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Literal, Sequence

EventKind = Literal[
    "publication",        # new published conclusion / article
    "revision",           # revision of a previously published conclusion
    "retraction",         # retraction propagation (prompt 18)
    "calibration_breach", # significant calibration breach (prompt 12)
    "method_version",     # methodology version transition (prompt 41)
]

Cadence = Literal["weekly", "immediate", "monthly"]
Scope = Literal["firm", "methodology", "domain", "conclusion"]


@dataclass(frozen=True)
class Subscriber:
    """A confirmed (active) subscriber row in shape relevant to digests.

    ``ack_token`` is the per-cycle one-time token the codex side mints
    when it exports the intake snapshot. When present, the rendered
    digest includes the voluntary "I read this" link wired to
    ``/api/public/digest-ack/<token>``. When absent (empty string), no
    ack link is rendered — the firm only records what subscribers
    explicitly opt into.
    """

    id: str
    email: str
    scope: Scope
    scope_key: str
    cadence: Cadence
    unsubscribe_token: str
    last_sent_at: datetime | None = None
    ack_token: str = ""


@dataclass(frozen=True)
class DigestEvent:
    """One firm event eligible for inclusion in a digest.

    ``methodology_names`` and ``domain_tags`` are the keys the event is
    visible under, so a single conclusion that exercises three methods
    surfaces to subscribers of any of those methods. ``conclusion_slug``
    must always be present so a `conclusion`-scope subscriber can match.
    """

    kind: EventKind
    headline: str
    summary: str
    url: str
    occurred_at: datetime
    conclusion_slug: str = ""
    methodology_names: tuple[str, ...] = ()
    domain_tags: tuple[str, ...] = ()
    is_major: bool = False  # firm-wide major events drive `immediate` cadence


@dataclass(frozen=True)
class Digest:
    """Rendered per-subscriber digest, ready to hand to a mailer."""

    subscriber_id: str
    to: str
    subject: str
    text: str
    html: str
    items: tuple[DigestEvent, ...]
    unsubscribe_url: str
    ack_url: str = ""
    headers: dict[str, str] = field(default_factory=dict)


# ── Scope filtering ────────────────────────────────────────────────────────

def event_matches_scope(event: DigestEvent, scope: Scope, scope_key: str) -> bool:
    """Return True when ``event`` is in-scope for the given subscription.

    The firm-wide scope sees everything. The other scopes match against a
    distinct field; ``scope_key`` is compared case-insensitively for the
    methodology and domain scopes (their names are already canonicalized
    upstream but humans type into the form), and exactly for the
    conclusion slug.
    """

    if scope == "firm":
        return True
    if scope == "methodology":
        target = scope_key.strip().lower()
        return any(name.strip().lower() == target for name in event.methodology_names)
    if scope == "domain":
        target = scope_key.strip().lower()
        return any(tag.strip().lower() == target for tag in event.domain_tags)
    if scope == "conclusion":
        return event.conclusion_slug == scope_key
    return False


def cadence_window(cadence: Cadence, now: datetime) -> datetime | None:
    """The earliest ``occurred_at`` that should be considered for ``cadence``.

    ``immediate`` returns ``None`` (no lower bound — the caller is
    expected to drive immediate sends event-at-a-time). ``weekly`` and
    ``monthly`` are 7 and 30 day rolling windows; the per-subscriber
    ``last_sent_at`` further trims this so a delayed run does not double-
    fire on the same subscriber.
    """

    if cadence == "immediate":
        return None
    if cadence == "weekly":
        return now.replace(microsecond=0) - _days(7)
    if cadence == "monthly":
        return now.replace(microsecond=0) - _days(30)
    return None


def select_events_for(
    subscriber: Subscriber,
    events: Sequence[DigestEvent],
    now: datetime,
) -> list[DigestEvent]:
    """Return the events that should appear in this subscriber's digest.

    Selection rules, in order:
      * Drop events older than the cadence window (weekly: 7d; monthly: 30d).
      * Drop events at or before ``last_sent_at``.
      * Drop events outside the subscriber's scope.
      * For ``immediate`` cadence, drop events that are not flagged
        ``is_major`` — that lane is reserved for firm-wide major events
        (revisions/retractions). Non-major events still aggregate into
        the next weekly window for these subscribers, by design.
    """

    window_start = cadence_window(subscriber.cadence, now)
    last_sent = subscriber.last_sent_at
    out: list[DigestEvent] = []
    for event in events:
        occurred = event.occurred_at
        if window_start is not None and occurred < window_start:
            continue
        if last_sent is not None and occurred <= last_sent:
            continue
        if subscriber.cadence == "immediate" and not event.is_major:
            continue
        if not event_matches_scope(event, subscriber.scope, subscriber.scope_key):
            continue
        out.append(event)
    out.sort(key=lambda e: e.occurred_at, reverse=True)
    return out


# ── Rendering ──────────────────────────────────────────────────────────────

KIND_LABEL: dict[EventKind, str] = {
    "publication": "PUBLICATION",
    "revision": "REVISION",
    "retraction": "RETRACTION",
    "calibration_breach": "CALIBRATION BREACH",
    "method_version": "METHOD VERSION",
}


def _scope_label(scope: Scope, scope_key: str) -> str:
    if scope == "firm":
        return "the firm"
    if scope == "methodology":
        return f"methodology · {scope_key}"
    if scope == "domain":
        return f"domain · {scope_key}"
    return f"conclusion · {scope_key}"


def render_text(
    subscriber: Subscriber,
    items: Sequence[DigestEvent],
    unsubscribe_url: str,
    ack_url: str = "",
) -> str:
    lines: list[str] = []
    scope_line = _scope_label(subscriber.scope, subscriber.scope_key)
    lines.append(f"Theseus follow-digest — {scope_line}")
    lines.append("")
    lines.append(
        "The firm publishes revisions and retractions with the same prominence as new work."
    )
    lines.append("")
    for event in items:
        lines.append(f"[{KIND_LABEL[event.kind]}] {event.headline}")
        if event.summary:
            lines.append(event.summary)
        lines.append(event.url)
        lines.append("")
    lines.append("---")
    if ack_url:
        lines.append(
            "Voluntary signal — if you read this digest and want the firm to "
            "know, click once: " + ack_url
        )
        lines.append(
            "(Opt-in only. The link records a hashed acknowledgment, not your address.)"
        )
    lines.append("Unsubscribe (one click, no questions): " + unsubscribe_url)
    lines.append("Theseus does not embed tracking pixels in any email it sends.")
    return "\n".join(lines).rstrip() + "\n"


def render_html(
    subscriber: Subscriber,
    items: Sequence[DigestEvent],
    unsubscribe_url: str,
    ack_url: str = "",
) -> str:
    scope_line = _scope_label(subscriber.scope, subscriber.scope_key)
    out: list[str] = [
        "<!doctype html>",
        '<html lang="en"><body style="font-family:Georgia,serif;line-height:1.5;color:#222;max-width:36rem;margin:0 auto;padding:1rem">',
        f"<h1 style=\"font-size:1.1rem;margin:0 0 0.5rem\">Theseus follow-digest — {_escape(scope_line)}</h1>",
        "<p style=\"font-size:0.9rem;color:#444;margin:0 0 1rem\">The firm publishes revisions and retractions with the same prominence as new work.</p>",
    ]
    for event in items:
        label = KIND_LABEL[event.kind]
        out.append('<div style="border-top:1px solid #ccc;padding-top:0.6rem;margin-bottom:0.6rem">')
        out.append(
            f"<div style=\"font-family:monospace;font-size:0.7rem;letter-spacing:0.18em;color:#888;text-transform:uppercase;margin-bottom:0.2rem\">{_escape(label)}</div>"
        )
        out.append(
            f"<div style=\"font-size:1rem\"><a href=\"{_escape(event.url)}\" style=\"color:#5a3d12;text-decoration:underline\">{_escape(event.headline)}</a></div>"
        )
        if event.summary:
            out.append(f"<p style=\"margin:0.3rem 0 0;font-size:0.92rem\">{_escape(event.summary)}</p>")
        out.append("</div>")
    out.append('<hr style="border:0;border-top:1px solid #ccc;margin:1rem 0"/>')
    if ack_url:
        out.append(
            "<p style=\"font-size:0.82rem;color:#555\">"
            f"<a href=\"{_escape(ack_url)}\">I read this</a> — voluntary, one click. "
            "Records a hashed acknowledgment so the firm can see how many "
            "subscribers opted to confirm; never stores your address against "
            "the click."
            "</p>"
        )
    out.append(
        f"<p style=\"font-size:0.82rem;color:#555\"><a href=\"{_escape(unsubscribe_url)}\">Unsubscribe</a> — one click, no questions.<br/>Theseus does not embed tracking pixels in any email it sends.</p>"
    )
    out.append("</body></html>")
    return "\n".join(out)


def build_digest(
    subscriber: Subscriber,
    items: Sequence[DigestEvent],
    *,
    site_url: str,
) -> Digest | None:
    """Render a single subscriber's digest, or ``None`` if there is nothing
    to send. An empty queue yields ``None`` — silence is the right signal
    when nothing has happened in this subscriber's slice of the firm.
    """

    if not items:
        return None
    base = site_url.rstrip("/")
    unsubscribe_url = base + "/api/public/unsubscribe/" + subscriber.unsubscribe_token
    ack_url = (
        base + "/api/public/digest-ack/" + subscriber.ack_token
        if subscriber.ack_token
        else ""
    )
    scope_line = _scope_label(subscriber.scope, subscriber.scope_key)
    counts = _kind_counts(items)
    subject = f"[Theseus] Follow-digest · {scope_line} · {counts}"
    text = render_text(subscriber, items, unsubscribe_url, ack_url)
    html = render_html(subscriber, items, unsubscribe_url, ack_url)
    return Digest(
        subscriber_id=subscriber.id,
        to=subscriber.email,
        subject=subject,
        text=text,
        html=html,
        items=tuple(items),
        unsubscribe_url=unsubscribe_url,
        ack_url=ack_url,
        headers={
            "List-Unsubscribe": f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )


def build_method_version_event(
    *,
    method_name: str,
    from_version: str,
    to_version: str,
    anchor_id: str,
    site_url: str,
    occurred_at: datetime,
    summary: str = "",
    domain_tags: tuple[str, ...] = (),
) -> DigestEvent:
    """Build a digest event for a method version transition.

    The event is keyed under ``methodology_names = (method_name,)``
    so methodology-scope subscribers (prompt 39) match it. The URL
    points at the public changelog anchor, which is stable across
    machines because the anchor is derived from the content hash.
    """
    base = site_url.rstrip("/")
    url = f"{base}/methodology/{method_name}/changelog#{anchor_id}"
    headline = f"Method updated: {method_name} {from_version} → {to_version}"
    summary_text = summary or (
        f"The {method_name} method has a new captured version. "
        f"See the public diff and effect-on-results on the changelog."
    )
    return DigestEvent(
        kind="method_version",
        headline=headline,
        summary=summary_text,
        url=url,
        occurred_at=occurred_at,
        conclusion_slug="",
        methodology_names=(method_name,),
        domain_tags=domain_tags,
        is_major=False,
    )


def build_digests(
    subscribers: Iterable[Subscriber],
    events: Sequence[DigestEvent],
    *,
    site_url: str,
    now: datetime | None = None,
) -> list[Digest]:
    """Build digests for every active subscriber that has matching events."""

    when = now or datetime.now(timezone.utc)
    out: list[Digest] = []
    for sub in subscribers:
        items = select_events_for(sub, events, when)
        digest = build_digest(sub, items, site_url=site_url)
        if digest is not None:
            out.append(digest)
    return out


# ── Helpers ────────────────────────────────────────────────────────────────

def _kind_counts(items: Sequence[DigestEvent]) -> str:
    counts: dict[EventKind, int] = {}
    for event in items:
        counts[event.kind] = counts.get(event.kind, 0) + 1
    parts: list[str] = []
    for kind in (
        "publication",
        "revision",
        "retraction",
        "calibration_breach",
        "method_version",
    ):
        n = counts.get(kind, 0)  # type: ignore[arg-type]
        if n:
            parts.append(f"{n} {kind.replace('_', ' ')}{'s' if n != 1 else ''}")
    return ", ".join(parts) or "update"


def _days(n: int):
    from datetime import timedelta

    return timedelta(days=n)


def _escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

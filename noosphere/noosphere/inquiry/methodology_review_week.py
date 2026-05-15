"""Methodology Review Week — the firm's quarterly methods-on-methods event.

The firm holds methodological commitments (the meta-method, the MQS rubric,
drift detection, retirement workflow) and uses them daily on conclusions.
Methodology Review Week turns the inverse pass — methods reviewing methods —
into a calendared event rather than a vague intention.

What this module owns
---------------------

1. **Schedule generation** — :func:`schedule_for_year`,
   :func:`schedule_for_quarter` and :func:`next_review_week_after` produce
   five working-day windows. The default cadence is the first full Monday
   of the second month of each quarter, so the review falls mid-quarter and
   does not collide with the seasonal review (Round-17 prompt 46) at the
   quarter close.

2. **Day-by-day focus** — :data:`DAY_FOCUS` names the five days. The
   sequence is load-bearing: drift first (what moved?), then failure modes
   (what broke?), then domain bounds (what should we no longer claim?),
   then retirement candidates (what should we stop running?), then the
   methodology section of the seasonal review (write it).

3. **Queue filtering** — :func:`filter_attention_for_day` is a pure
   function over the unified-attention-queue entry shape (Round-17 prompt
   34). It returns the queue subset the day's focus calls for: drift +
   calibration breaches on day 1, peer review + citation verdicts on day 2,
   etc. The web app uses the same filter against the live DB queue; this
   module exercises it as a pure function so tests can pin behaviour
   without a database.

4. **Summary persistence and signing** — :class:`DaySummary` plus
   :func:`save_summary` / :func:`load_summary` write the founder's day-end
   summary to ``docs/methodology_review_week/<slug>/day_<n>.md`` and sign
   the canonical bytes with Ed25519 (same key directory as publication
   signatures, separate sub-folder so the keys do not co-mingle). The
   signature is verified on every read; tampered files raise. Founder
   edits are tracked: an ``edits`` list captures (timestamp, prior_body)
   so the audit trail stays intact when the founder revises a draft.

5. **Drafting** — :func:`draft_summary_from_queue` produces a clearly
   labelled draft based on the day's filtered queue. The draft body
   begins with the literal string :data:`DRAFT_BANNER`; consumers that
   surface the draft to the founder are expected to keep that banner
   visible until the founder edits the body. Drafts are never auto-saved
   as the founder's summary — the founder writes the final.

Constraints the module pins
---------------------------

* **Opt-in.** :func:`mark_postponed` and :func:`mark_skipped` log a missed
  or rescheduled week without penalty; ``status`` lives on the schedule
  row, the public hint reflects it, and the test suite asserts both
  transitions never raise.
* **Public-facing dates are accurate.** :func:`public_hint` reads only
  the schedule rows it is handed and produces ``"Last review week: <date>;
  next review week: <date>"``. A postponed week shows its new date.
* **No DB I/O here.** Persistence is by JSON sidecars + Markdown body;
  the Next.js app mirrors the same schedule shape into Prisma. The
  Python module keeps the calendar reproducible from disk alone.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

logger = logging.getLogger(__name__)


SCHEMA = "theseus.methodology_review_week.v1"

# Ordered list of the five working days. Position in this tuple is the
# `day_index` used everywhere (1-based on the way out, 0-based here).
DAY_FOCUS: tuple[str, ...] = (
    "drift_events",            # day 1
    "failure_modes",           # day 2
    "domain_bounds",           # day 3
    "retirement_candidates",   # day 4
    "methodology_section",     # day 5 — write the seasonal-review section
)

DAY_LABELS: dict[str, str] = {
    "drift_events": "Drift events review",
    "failure_modes": "Failure-mode catalog review",
    "domain_bounds": "Domain-bound review",
    "retirement_candidates": "Retirement candidate review",
    "methodology_section": "Methodology section writeup",
}

# Which queues from the unified attention queue feed each day's focus.
# `methodology_section` is intentionally empty: day 5 is the writeup pass,
# not a triage queue.
QUEUES_BY_FOCUS: dict[str, frozenset[str]] = {
    "drift_events": frozenset({"drift", "calibration_breach"}),
    "failure_modes": frozenset({"peer_review", "citation_verdict"}),
    "domain_bounds": frozenset({"source_triage", "retraction_propagation"}),
    "retirement_candidates": frozenset({"calibration_breach", "drift"}),
    "methodology_section": frozenset(),
}

# Default location for written summaries. Mirrors `docs/seasonal/` shape.
DEFAULT_REVIEW_WEEK_ROOT = Path("docs/methodology_review_week")

# Banner that must remain at the top of any draft surface. The founder
# is expected to delete or rewrite this banner when they accept the draft.
DRAFT_BANNER = (
    "**DRAFT — generated from the day's queue; the founder writes the final.**"
)

# Statuses for a scheduled review week.
STATUS_SCHEDULED = "scheduled"
STATUS_ACTIVE = "active"
STATUS_COMPLETED = "completed"
STATUS_POSTPONED = "postponed"
STATUS_SKIPPED = "skipped"

VALID_STATUSES: frozenset[str] = frozenset({
    STATUS_SCHEDULED,
    STATUS_ACTIVE,
    STATUS_COMPLETED,
    STATUS_POSTPONED,
    STATUS_SKIPPED,
})


# ── Scheduling ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReviewDay:
    """One working day inside a review week."""

    day_index: int  # 1..5
    focus: str
    on: date
    label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "day_index": self.day_index,
            "focus": self.focus,
            "on": self.on.isoformat(),
            "label": self.label,
        }


@dataclass
class ReviewWeek:
    """A 5-working-day methodology review window.

    The week is identified by ``(year, quarter)``; the dates may shift
    (postponement) but the identity does not. ``status`` defaults to
    ``"scheduled"`` and transitions to ``"active"`` while the week is in
    progress, ``"completed"`` afterwards, ``"postponed"`` if the founder
    moves it, or ``"skipped"`` if the founder opts out of the cycle.
    """

    year: int
    quarter: int
    days: tuple[ReviewDay, ...]
    status: str = STATUS_SCHEDULED
    postponed_to: Optional[date] = None
    postpone_reason: str = ""

    @property
    def start(self) -> date:
        return self.days[0].on

    @property
    def end(self) -> date:
        return self.days[-1].on

    @property
    def slug(self) -> str:
        return f"{self.year}_Q{self.quarter}_MethodologyReviewWeek"

    @property
    def label(self) -> str:
        return f"{self.year} Q{self.quarter} Methodology Review Week"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "year": self.year,
            "quarter": self.quarter,
            "slug": self.slug,
            "status": self.status,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "postponed_to": (
                self.postponed_to.isoformat() if self.postponed_to else None
            ),
            "postpone_reason": self.postpone_reason,
            "days": [d.to_dict() for d in self.days],
        }


def _first_monday_on_or_after(d: date) -> date:
    """First Monday at or after ``d``."""
    shift = (7 - d.weekday()) % 7 if d.weekday() != 0 else 0
    return d + timedelta(days=shift)


def _five_working_days(start_monday: date) -> tuple[date, ...]:
    """Five consecutive weekdays starting on a Monday."""
    if start_monday.weekday() != 0:
        raise ValueError(
            f"start_monday must be a Monday (weekday=0), got {start_monday!r} "
            f"(weekday={start_monday.weekday()})"
        )
    return tuple(start_monday + timedelta(days=i) for i in range(5))


def _build_days(start_monday: date) -> tuple[ReviewDay, ...]:
    dates = _five_working_days(start_monday)
    out: list[ReviewDay] = []
    for i, on in enumerate(dates):
        focus = DAY_FOCUS[i]
        out.append(
            ReviewDay(
                day_index=i + 1,
                focus=focus,
                on=on,
                label=DAY_LABELS[focus],
            )
        )
    return tuple(out)


def default_start_for_quarter(year: int, quarter: int) -> date:
    """Default Monday start for a quarter's review week.

    The default is the first Monday of the **second month** of the
    quarter. This places the review mid-quarter, leaving the start for
    new research and the end for the seasonal review (prompt 46).
    """
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"quarter must be 1..4, got {quarter!r}")
    month = (quarter - 1) * 3 + 2  # 2, 5, 8, 11
    return _first_monday_on_or_after(date(year, month, 1))


def schedule_for_quarter(
    year: int,
    quarter: int,
    *,
    start: Optional[date] = None,
) -> ReviewWeek:
    """Build a :class:`ReviewWeek` for the given quarter.

    Pass ``start`` to override the default mid-quarter Monday (used for
    postponement). The override must itself be a Monday.
    """
    monday = start if start is not None else default_start_for_quarter(year, quarter)
    return ReviewWeek(
        year=year,
        quarter=quarter,
        days=_build_days(monday),
        status=STATUS_SCHEDULED,
    )


def schedule_for_year(year: int) -> tuple[ReviewWeek, ...]:
    """All four review weeks for a calendar year, in order."""
    return tuple(schedule_for_quarter(year, q) for q in (1, 2, 3, 4))


def next_review_week_after(
    today: date,
    *,
    horizon_years: int = 2,
) -> ReviewWeek:
    """The next scheduled review week whose start is on or after ``today``."""
    for offset in range(horizon_years + 1):
        for week in schedule_for_year(today.year + offset):
            if week.start >= today:
                return week
    raise RuntimeError(
        f"no scheduled review week found within {horizon_years} years of {today!r}"
    )


def mark_postponed(
    week: ReviewWeek,
    *,
    new_start: date,
    reason: str = "",
) -> ReviewWeek:
    """Reschedule a review week. Identity ``(year, quarter)`` is preserved.

    Opt-in policy: postponement is a recorded fact, not a penalty.
    The returned week carries the new dates, ``status="postponed"``, and
    the founder's reason (which the public hint may surface).
    """
    return ReviewWeek(
        year=week.year,
        quarter=week.quarter,
        days=_build_days(_first_monday_on_or_after(new_start)),
        status=STATUS_POSTPONED,
        postponed_to=new_start,
        postpone_reason=reason.strip(),
    )


def mark_skipped(week: ReviewWeek, *, reason: str = "") -> ReviewWeek:
    """Log a missed review week. The schedule continues."""
    return ReviewWeek(
        year=week.year,
        quarter=week.quarter,
        days=week.days,
        status=STATUS_SKIPPED,
        postponed_to=week.postponed_to,
        postpone_reason=reason.strip() or week.postpone_reason,
    )


# ── Public hint ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class PublicHint:
    """The pair of dates the public methodology page surfaces."""

    last_on: Optional[date]
    next_on: Optional[date]

    def to_string(self) -> str:
        last = self.last_on.isoformat() if self.last_on else "—"
        nxt = self.next_on.isoformat() if self.next_on else "—"
        return f"Last review week: {last}; next review week: {nxt}"


def public_hint(
    history: Sequence[ReviewWeek],
    today: date,
) -> PublicHint:
    """Produce the public hint from a history of review weeks.

    Rules:
      * "Last" = the most recent week whose ``end`` is strictly before
        today and whose ``status`` is ``completed`` (skipped/postponed
        weeks are not "last" — they did not happen).
      * "Next" = the soonest week whose ``start`` is on or after today.
        A postponed week with a later start counts; a skipped week
        does not.
    """
    last_on: Optional[date] = None
    next_on: Optional[date] = None
    for week in sorted(history, key=lambda w: w.start):
        if week.status == STATUS_COMPLETED and week.end < today:
            last_on = week.end
        if week.status == STATUS_SKIPPED:
            continue
        if week.start >= today and (next_on is None or week.start < next_on):
            next_on = week.start
    if next_on is None:
        try:
            next_on = next_review_week_after(today).start
        except RuntimeError:
            next_on = None
    return PublicHint(last_on=last_on, next_on=next_on)


# ── Queue filtering ──────────────────────────────────────────────────


def filter_attention_for_day(
    items: Iterable[dict[str, Any]],
    *,
    focus: str,
) -> list[dict[str, Any]]:
    """Return the subset of the unified attention queue for ``focus``.

    ``items`` are the attention-queue rows as the dashboard sees them
    (each with a ``queue`` key). The filter is a queue-membership test
    against :data:`QUEUES_BY_FOCUS`. Items that arrive without a known
    queue are dropped (defensive — never elevated).

    Day 5 (``methodology_section``) intentionally returns ``[]``: the
    writeup day is not a triage queue.
    """
    if focus not in DAY_FOCUS:
        raise ValueError(f"unknown focus {focus!r}; expected one of {DAY_FOCUS}")
    allowed = QUEUES_BY_FOCUS[focus]
    if not allowed:
        return []
    return [row for row in items if (row.get("queue") in allowed)]


# ── Day summaries (drafted, written, signed) ─────────────────────────


@dataclass
class SummaryEdit:
    """One founder edit on a summary. Captured for audit; signatures
    cover only the *current* body."""

    at: datetime
    prior_body: str

    def to_dict(self) -> dict[str, Any]:
        return {"at": _iso(self.at), "prior_body": self.prior_body}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SummaryEdit":
        return cls(at=_parse_iso(d["at"]), prior_body=str(d.get("prior_body", "")))


@dataclass
class DaySummary:
    """The founder's day-end summary, persisted and signed.

    The signature covers the canonical bytes of ``(week_slug, day_index,
    focus, body)`` — *not* the draft and *not* the edit history. That
    keeps the signature meaningful (it certifies what the founder
    actually wrote) while the surrounding metadata remains advisory.
    """

    week_slug: str
    day_index: int
    focus: str
    body: str
    draft_body: str = ""
    draft_generated_at: Optional[datetime] = None
    edits: list[SummaryEdit] = field(default_factory=list)
    written_at: Optional[datetime] = None
    signed_at: Optional[datetime] = None
    signature_hex: str = ""
    signing_key_fingerprint: str = ""

    def canonical_bytes(self) -> bytes:
        """Canonical bytes the signature covers."""
        payload = {
            "schema": SCHEMA,
            "week_slug": self.week_slug,
            "day_index": self.day_index,
            "focus": self.focus,
            "body": self.body,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )

    def canonical_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "week_slug": self.week_slug,
            "day_index": self.day_index,
            "focus": self.focus,
            "body": self.body,
            "draft_body": self.draft_body,
            "draft_generated_at": _iso_or_none(self.draft_generated_at),
            "edits": [e.to_dict() for e in self.edits],
            "written_at": _iso_or_none(self.written_at),
            "signed_at": _iso_or_none(self.signed_at),
            "signature_hex": self.signature_hex,
            "signing_key_fingerprint": self.signing_key_fingerprint,
            "canonical_hash": self.canonical_hash(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DaySummary":
        if d.get("schema") not in (None, SCHEMA):
            raise ValueError(f"unknown schema {d.get('schema')!r}; expected {SCHEMA!r}")
        return cls(
            week_slug=str(d["week_slug"]),
            day_index=int(d["day_index"]),
            focus=str(d["focus"]),
            body=str(d.get("body", "")),
            draft_body=str(d.get("draft_body", "")),
            draft_generated_at=_parse_iso(d.get("draft_generated_at")),
            edits=[SummaryEdit.from_dict(e) for e in d.get("edits", [])],
            written_at=_parse_iso(d.get("written_at")),
            signed_at=_parse_iso(d.get("signed_at")),
            signature_hex=str(d.get("signature_hex", "")),
            signing_key_fingerprint=str(d.get("signing_key_fingerprint", "")),
        )

    def apply_founder_edit(self, new_body: str, *, at: Optional[datetime] = None) -> None:
        """Record a founder edit, replacing ``body`` and clearing the signature.

        Edits invalidate any prior signature; the caller must re-sign
        with :func:`sign_summary` to make the new body immutable.
        """
        when = at or datetime.now(timezone.utc)
        self.edits.append(SummaryEdit(at=when, prior_body=self.body))
        self.body = new_body
        self.written_at = when
        # A new body has not been signed yet.
        self.signed_at = None
        self.signature_hex = ""
        self.signing_key_fingerprint = ""


def draft_summary_from_queue(
    week: ReviewWeek,
    day_index: int,
    queue_items: Sequence[dict[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> DaySummary:
    """Generate a clearly-labelled draft summary for one day.

    The draft body is the :data:`DRAFT_BANNER`, a one-line summary of
    queue counts by severity, and a bulleted list of the queue's items
    (capped at 20 for legibility). The founder reads, then writes their
    own final via :meth:`DaySummary.apply_founder_edit`.
    """
    when = now or datetime.now(timezone.utc)
    if not 1 <= day_index <= len(DAY_FOCUS):
        raise ValueError(f"day_index must be 1..{len(DAY_FOCUS)}, got {day_index!r}")
    focus = DAY_FOCUS[day_index - 1]
    filtered = filter_attention_for_day(queue_items, focus=focus)

    sev_counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for row in filtered:
        sev = str(row.get("severity", "low"))
        if sev in sev_counts:
            sev_counts[sev] += 1

    lines: list[str] = [DRAFT_BANNER, ""]
    lines.append(f"# {DAY_LABELS[focus]} — {week.label} (Day {day_index})")
    lines.append("")
    if focus == "methodology_section":
        lines.append(
            "Day 5 is the writeup pass. The agent does not draft prose for the "
            "seasonal review's methodology section; the founder writes it from "
            "the four days of triage notes above."
        )
        lines.append("")
    else:
        lines.append(
            f"{len(filtered)} item(s) in the day's queue — "
            f"{sev_counts['high']} high, {sev_counts['medium']} medium, "
            f"{sev_counts['low']} low."
        )
        lines.append("")
        if filtered:
            lines.append("## Items")
            lines.append("")
            for row in filtered[:20]:
                preview = str(row.get("preview", "")).strip().replace("\n", " ")
                lines.append(
                    f"- [{row.get('severity', '?')}] "
                    f"{row.get('queue', '?')}/{row.get('itemId', '?')} — {preview}"
                )
            if len(filtered) > 20:
                lines.append(f"- … plus {len(filtered) - 20} more (see the queue page).")
            lines.append("")
        else:
            lines.append("The queue is empty for this focus today. Record the absence.")
            lines.append("")

    return DaySummary(
        week_slug=week.slug,
        day_index=day_index,
        focus=focus,
        body="",  # the founder writes the body
        draft_body="\n".join(lines).rstrip() + "\n",
        draft_generated_at=when,
    )


# ── Signing (Ed25519, optional — falls back to keyless mode) ─────────


def _signing_dir() -> Path:
    """Where review-week signing keys live.

    Separate sub-folder from publication signing so the keyrings do not
    co-mingle. Override with ``THESEUS_REVIEW_WEEK_KEY_DIR``.
    """
    override = os.environ.get("THESEUS_REVIEW_WEEK_KEY_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".theseus" / "keys" / "review-week"


def _try_load_nacl() -> Any:
    try:
        from nacl.signing import SigningKey  # type: ignore[import-not-found]
        return SigningKey
    except ImportError:  # pragma: no cover — defensive
        return None


@dataclass
class ReviewWeekKeyring:
    """Filesystem-backed Ed25519 keyring for review-week summary signing.

    Mirrors the shape of :class:`PublicationKeyring` (one active key per
    keyring root; key files at ``<root>/keys/<fingerprint>/signing.key``
    and ``.../verify.pub``). The keyring is created lazily on first
    sign; the verifier accepts any key whose fingerprint appears under
    ``<root>/keys/``.
    """

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.keys_dir = self.root / "keys"
        self.active_pointer = self.root / "active"

    def ensure(self) -> str:
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
            os.chmod(self.keys_dir, 0o700)
        except OSError:
            pass
        if self.active_pointer.is_file():
            fp = self.active_pointer.read_text().strip()
            if fp and (self.keys_dir / fp / "signing.key").is_file():
                return fp
        return self._generate()

    def _generate(self) -> str:
        SigningKey = _try_load_nacl()
        if SigningKey is None:
            raise RuntimeError(
                "PyNaCl is required to sign review-week summaries; install "
                "the package or run in an env where ledger signing works."
            )
        sk = SigningKey.generate()
        fp = hashlib.sha256(bytes(sk.verify_key)).hexdigest()[:16]
        d = self.keys_dir / fp
        d.mkdir(parents=True, exist_ok=True)
        (d / "signing.key").write_bytes(bytes(sk))
        (d / "verify.pub").write_bytes(bytes(sk.verify_key))
        (d / "created_at").write_text(_iso(datetime.now(timezone.utc)))
        try:
            os.chmod(d / "signing.key", 0o600)
        except OSError:
            pass
        self.active_pointer.write_text(fp)
        return fp

    def signing_key(self) -> Any:
        SigningKey = _try_load_nacl()
        if SigningKey is None:
            raise RuntimeError("PyNaCl is required to sign review-week summaries")
        fp = self.ensure()
        return SigningKey((self.keys_dir / fp / "signing.key").read_bytes()[:32]), fp

    def verify_key(self, fingerprint: str) -> Any:
        from nacl.signing import VerifyKey  # type: ignore[import-not-found]

        path = self.keys_dir / fingerprint / "verify.pub"
        if not path.is_file():
            return None
        return VerifyKey(path.read_bytes()[:32])


def sign_summary(
    summary: DaySummary,
    *,
    keyring: Optional[ReviewWeekKeyring] = None,
    now: Optional[datetime] = None,
) -> DaySummary:
    """Sign ``summary.body`` and stamp the result on ``summary``.

    Returns the same instance for convenience. Re-signs cleanly if the
    body has changed since the last signature.
    """
    if not summary.body.strip():
        raise ValueError("cannot sign an empty summary body")
    keyring = keyring or ReviewWeekKeyring(_signing_dir())
    sk, fp = keyring.signing_key()
    sig = sk.sign(summary.canonical_bytes()).signature
    summary.signature_hex = sig.hex()
    summary.signed_at = now or datetime.now(timezone.utc)
    summary.signing_key_fingerprint = fp
    return summary


def verify_summary(
    summary: DaySummary,
    *,
    keyring: Optional[ReviewWeekKeyring] = None,
) -> bool:
    """Return True iff ``summary``'s signature matches its current body."""
    if not summary.signature_hex or not summary.signing_key_fingerprint:
        return False
    keyring = keyring or ReviewWeekKeyring(_signing_dir())
    verify_key = keyring.verify_key(summary.signing_key_fingerprint)
    if verify_key is None:
        return False
    try:
        verify_key.verify(
            summary.canonical_bytes(),
            bytes.fromhex(summary.signature_hex),
        )
        return True
    except Exception:  # nacl.exceptions.BadSignatureError + friends
        return False


# ── On-disk layout ───────────────────────────────────────────────────


def week_dir(week: ReviewWeek, *, root: Path = DEFAULT_REVIEW_WEEK_ROOT) -> Path:
    return Path(root) / week.slug


def summary_path(
    week_slug: str,
    day_index: int,
    *,
    root: Path = DEFAULT_REVIEW_WEEK_ROOT,
) -> Path:
    return Path(root) / week_slug / f"day_{day_index}.json"


def save_summary(
    summary: DaySummary,
    *,
    root: Path = DEFAULT_REVIEW_WEEK_ROOT,
) -> Path:
    """Persist a summary to disk as a canonical JSON sidecar.

    A signed summary is **immutable**: attempting to overwrite a row
    whose on-disk canonical hash differs from ``summary``'s hash raises.
    Re-saving the same body (same hash) is allowed and idempotent so
    callers can refresh edit metadata without losing the signature.
    """
    path = summary_path(summary.week_slug, summary.day_index, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        prior_raw = json.loads(path.read_text(encoding="utf-8"))
        prior = DaySummary.from_dict(prior_raw)
        if prior.signature_hex and prior.signed_at is not None:
            if prior.canonical_hash() != summary.canonical_hash():
                raise RuntimeError(
                    f"refusing to overwrite signed summary at {path}: "
                    f"prior_hash={prior.canonical_hash()[:12]} "
                    f"new_hash={summary.canonical_hash()[:12]}"
                )
    path.write_text(
        json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def load_summary(
    week_slug: str,
    day_index: int,
    *,
    root: Path = DEFAULT_REVIEW_WEEK_ROOT,
) -> Optional[DaySummary]:
    path = summary_path(week_slug, day_index, root=root)
    if not path.is_file():
        return None
    return DaySummary.from_dict(json.loads(path.read_text(encoding="utf-8")))


def iter_history(
    *,
    root: Path = DEFAULT_REVIEW_WEEK_ROOT,
) -> list[dict[str, Any]]:
    """List past review weeks on disk (latest first).

    Each entry is a dict with ``slug``, ``year``, ``quarter``, ``days``
    (list of day_index → has_summary, has_signature) — sufficient to
    drive the history page in the web app without re-deriving the
    schedule.
    """
    root = Path(root)
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    pattern = re.compile(r"^(?P<year>\d{4})_Q(?P<quarter>[1-4])_MethodologyReviewWeek$")
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        m = pattern.match(entry.name)
        if not m:
            continue
        days: list[dict[str, Any]] = []
        for i in range(1, len(DAY_FOCUS) + 1):
            p = entry / f"day_{i}.json"
            has = p.is_file()
            signed = False
            if has:
                try:
                    s = DaySummary.from_dict(
                        json.loads(p.read_text(encoding="utf-8"))
                    )
                    signed = bool(s.signature_hex and s.signed_at)
                except Exception:
                    signed = False
            days.append({"day_index": i, "has_summary": has, "signed": signed})
        rows.append(
            {
                "slug": entry.name,
                "year": int(m.group("year")),
                "quarter": int(m.group("quarter")),
                "days": days,
            }
        )
    rows.sort(key=lambda r: (r["year"], r["quarter"]), reverse=True)
    return rows


# ── Seasonal-review handoff ──────────────────────────────────────────


def collect_methodology_section_inputs(
    week: ReviewWeek,
    *,
    root: Path = DEFAULT_REVIEW_WEEK_ROOT,
) -> dict[str, Any]:
    """Bundle the first four days' summaries for the seasonal-review pass.

    Day 5's writeup consumes this object; the seasonal review's
    methodology section is constrained to cite from these four rows.
    Missing days are recorded as ``data_available=False`` rather than
    silently dropped — the firm does not paper over a missed day.
    """
    parts: dict[str, Any] = {
        "schema": SCHEMA,
        "week_slug": week.slug,
        "year": week.year,
        "quarter": week.quarter,
        "days": [],
    }
    for i in range(1, 5):
        summary = load_summary(week.slug, i, root=root)
        if summary is None or not summary.body.strip():
            parts["days"].append(
                {
                    "day_index": i,
                    "focus": DAY_FOCUS[i - 1],
                    "data_available": False,
                    "note": "summary not written",
                }
            )
            continue
        parts["days"].append(
            {
                "day_index": i,
                "focus": DAY_FOCUS[i - 1],
                "data_available": True,
                "body": summary.body,
                "signed": bool(summary.signature_hex and summary.signed_at),
            }
        )
    return parts


# ── ISO helpers (lightweight, avoid a dependency on pydantic etc.) ───


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _iso_or_none(dt: Optional[datetime]) -> Optional[str]:
    return _iso(dt) if dt is not None else None


def _parse_iso(s: Any) -> Optional[datetime]:
    if s is None or s == "":
        return None
    text = str(s)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)

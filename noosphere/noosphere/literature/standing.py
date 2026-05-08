"""
Source-standing model + canonicalization.

The firm cites external sources (papers, posts, datasets). When a source
gets retracted, corrected, disputed, or simply disappears off the open
web, every downstream conclusion that cites it inherits the credibility
hit. This module is the *append-only* ledger that records those status
transitions, and the canonicalization rule that lets two URLs pointing
at the same paper resolve to a single source identity.

The Prisma side stores the row of record (`SourceStanding`). The Python
side is the data model + ledger primitives that pollers and the cascade
revision wiring read and write.

Canonicalization rule (deterministic, documented):

    1. If the source publishes a DOI → ``doi:10.xxxx/yyyy`` (lowercased
       prefix, exact-case suffix per DOI handbook).
    2. Else if it's an arXiv id (with or without version) → ``arxiv:1234.56789``
       (version suffix dropped — withdrawal applies to the work, not a
       single revision).
    3. Else → ``url:<sha256(normalized_url)>`` where the URL has been
       lowercased on host, stripped of fragments, sorted query params,
       and trailing slashes removed.

Two different URLs that point at the same DOI or the same arXiv id
collapse to the same canonical id. Two URLs that don't expose a DOI or
arXiv id but normalize identically also collapse. A change in DOI or
arXiv id (e.g. a journal re-issues a corrected paper under a new DOI)
is treated as a *new* source — the old one is marked CORRECTED with a
pointer to the new one in the reason.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Optional, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class StandingStatus(str, Enum):
    """States a cited source can be in.

    ACTIVE is the implicit default for every newly-seen source; pollers
    only write rows when they observe a transition. A source can move
    from ACTIVE to any non-ACTIVE state and back (e.g. a paper marked
    DISPUTED on social media but later cleared); transitions are
    append-only — the latest row wins for a given canonical id.
    """

    ACTIVE = "ACTIVE"
    RETRACTED = "RETRACTED"
    CORRECTED = "CORRECTED"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"


# Statuses that *remove* evidence weight from cited claims. RETRACTED
# and CORRECTED are the propagation triggers per the prompt: a retracted
# paper does not become evidence for the opposite claim, it simply
# stops counting. DISPUTED is a softer signal — surfaced in the UI but
# not auto-propagated. EXPIRED (404 / DNS death) is treated like
# RETRACTED for propagation purposes since the citation no longer
# verifiably resolves to the original content.
PROPAGATING_STATUSES: frozenset[StandingStatus] = frozenset(
    {StandingStatus.RETRACTED, StandingStatus.CORRECTED, StandingStatus.EXPIRED}
)


_ARXIV_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/)?(?P<id>\d{4}\.\d{4,5})(?:v\d+)?",
    re.IGNORECASE,
)
_DOI_RE = re.compile(r"10\.\d{4,9}/[\-._;()/:A-Z0-9]+", re.IGNORECASE)


def _normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, path, query, ""))


def canonical_source_id(
    *,
    doi: Optional[str] = None,
    arxiv_id: Optional[str] = None,
    url: Optional[str] = None,
) -> str:
    """Resolve the canonical id for a source.

    Precedence: DOI > arXiv id > URL hash. Inputs are inspected for
    embedded ids before falling back — e.g. a URL that contains a DOI
    will collapse to ``doi:...`` rather than ``url:...``.

    Raises ``ValueError`` if none of the inputs are usable.
    """
    if doi:
        m = _DOI_RE.search(doi)
        if m:
            return f"doi:{m.group(0).lower()}"

    if arxiv_id:
        m = _ARXIV_RE.search(arxiv_id)
        if m:
            return f"arxiv:{m.group('id').lower()}"

    if url:
        # Try to lift a DOI or arXiv id out of the URL first.
        m = _DOI_RE.search(url)
        if m:
            return f"doi:{m.group(0).lower()}"
        m = _ARXIV_RE.search(url)
        if m:
            return f"arxiv:{m.group('id').lower()}"
        normalized = _normalize_url(url)
        h = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"url:{h[:32]}"

    raise ValueError("canonical_source_id requires at least one of doi/arxiv_id/url")


@dataclass(frozen=True)
class StandingTransition:
    """A single append-only event in the standing ledger.

    ``notice_source`` is the canonical id of the *retraction notice* (or
    correction notice, etc.) — a retraction is itself a source, and we
    keep the chain explicit so a future audit can re-derive who said
    what when. ``observed_at`` is the time we *learned* of the
    transition (poll time), not necessarily when it was issued.
    """

    source_id: str
    status: StandingStatus
    reason: str
    poller: str
    observed_at: datetime
    notice_source: Optional[str] = None
    raw_payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "status": self.status.value,
            "reason": self.reason,
            "poller": self.poller,
            "observed_at": self.observed_at.isoformat(),
            "notice_source": self.notice_source,
            "raw_payload": dict(self.raw_payload),
        }


class StandingLedger(Protocol):
    """Pluggable storage for standing transitions.

    Production wires this to the Prisma SourceStanding table; tests use
    the in-memory implementation below. The contract is intentionally
    narrow so polling code never has to know about the ORM:

      * ``current_status`` returns the most recent transition for a
        canonical id, or None if we've never seen it (which is treated
        as ACTIVE by callers).
      * ``append`` is idempotent on (source_id, status, reason): a
        re-poll that produces the same transition writes nothing new.
    """

    def append(self, transition: StandingTransition) -> bool: ...
    def current_status(self, source_id: str) -> Optional[StandingTransition]: ...
    def history(self, source_id: str) -> list[StandingTransition]: ...
    def all(self) -> list[StandingTransition]: ...


class InMemoryStandingLedger:
    def __init__(self) -> None:
        self._rows: list[StandingTransition] = []

    def append(self, transition: StandingTransition) -> bool:
        latest = self.current_status(transition.source_id)
        if (
            latest is not None
            and latest.status == transition.status
            and latest.reason == transition.reason
        ):
            return False
        self._rows.append(transition)
        return True

    def current_status(self, source_id: str) -> Optional[StandingTransition]:
        for row in reversed(self._rows):
            if row.source_id == source_id:
                return row
        return None

    def history(self, source_id: str) -> list[StandingTransition]:
        return [r for r in self._rows if r.source_id == source_id]

    def all(self) -> list[StandingTransition]:
        return list(self._rows)


@dataclass(frozen=True)
class CitationLink:
    """Records that a conclusion cites a canonical source.

    The cascade engine queries this when a transition fires: every
    conclusion whose ``conclusion_id`` appears here for the affected
    ``source_id`` gets fed into the revision pipeline.
    """

    conclusion_id: str
    source_id: str
    citation_url: str = ""


def affected_conclusions(
    links: Iterable[CitationLink],
    source_id: str,
) -> list[str]:
    out = sorted({l.conclusion_id for l in links if l.source_id == source_id})
    return out


def now_utc() -> datetime:
    return datetime.now(timezone.utc)

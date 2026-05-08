"""
Retraction Watch poller.

Retraction Watch publishes a CSV/JSON feed of retraction notices keyed
on DOI. We treat each notice as a *source itself* (its public URL) so
the ``notice_source`` field on the StandingTransition points at the
record-of-record for the retraction event, not at the retracted paper.

We don't bundle a hard-coded feed URL into the code; the caller passes
``fetch`` to perform the HTTP call (or a fake in tests). The poller
here is the parsing + matching logic: it filters the feed down to
sources we currently cite, and emits a transition only for those.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Sequence

from noosphere.literature.standing import (
    StandingStatus,
    StandingTransition,
    canonical_source_id,
    now_utc,
)


# A row from the feed. Real feed has more columns (journal, country,
# etc.); we keep what we need to write a transition.
@dataclass(frozen=True)
class RetractionNotice:
    doi: str
    reason: str
    notice_url: str
    is_correction: bool = False


FetchFn = Callable[[], Iterable[RetractionNotice]]


@dataclass
class RetractionWatchPoller:
    name: str = "retraction_watch"
    fetch: Optional[FetchFn] = None

    def poll(self, source_ids: Sequence[str]) -> list[StandingTransition]:
        if self.fetch is None:
            return []
        cited = set(source_ids)
        out: list[StandingTransition] = []
        observed = now_utc()
        for notice in self.fetch():
            try:
                src_id = canonical_source_id(doi=notice.doi)
            except ValueError:
                continue
            if src_id not in cited:
                continue
            try:
                notice_id = canonical_source_id(url=notice.notice_url)
            except ValueError:
                notice_id = None
            status = (
                StandingStatus.CORRECTED if notice.is_correction else StandingStatus.RETRACTED
            )
            out.append(
                StandingTransition(
                    source_id=src_id,
                    status=status,
                    reason=notice.reason.strip()[:500] or "Retraction notice received",
                    poller=self.name,
                    observed_at=observed,
                    notice_source=notice_id,
                    raw_payload={"doi": notice.doi, "notice_url": notice.notice_url},
                )
            )
        return out

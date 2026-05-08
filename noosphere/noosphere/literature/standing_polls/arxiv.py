"""
arXiv withdrawal poller.

arXiv exposes a paper's withdrawal status through the Atom abstract
page: a withdrawn paper has a ``<arxiv:comment>`` of "withdrawn" or a
title prefix "Withdrawn:". We treat that as RETRACTED for cascade
purposes; arXiv corrections (a v2 supersedes v1) are NOT treated as
RETRACTED — they're a normal version bump and the canonical id strips
the version, so the citation still resolves.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from noosphere.literature.standing import (
    StandingStatus,
    StandingTransition,
    canonical_source_id,
    now_utc,
)

NS = {"a": "http://www.w3.org/2005/Atom"}

_WITHDRAWN_RE = re.compile(r"\bwithdrawn\b", re.IGNORECASE)


@dataclass(frozen=True)
class ArxivPage:
    """A snapshot of an arXiv abstract page sufficient to detect a
    withdrawal. ``title`` and ``comment`` may be empty if the upstream
    feed omitted them; the poller treats absence as not-withdrawn.
    """

    arxiv_id: str
    title: str
    comment: str
    abstract_url: str


FetchFn = Callable[[str], Optional[ArxivPage]]


@dataclass
class ArxivWithdrawalPoller:
    name: str = "arxiv_withdrawals"
    fetch: Optional[FetchFn] = None

    def poll(self, source_ids: Sequence[str]) -> list[StandingTransition]:
        if self.fetch is None:
            return []
        out: list[StandingTransition] = []
        observed = now_utc()
        for src_id in source_ids:
            if not src_id.startswith("arxiv:"):
                continue
            arxiv_id = src_id.split(":", 1)[1]
            page = self.fetch(arxiv_id)
            if page is None:
                continue
            if not (
                _WITHDRAWN_RE.search(page.title or "")
                or _WITHDRAWN_RE.search(page.comment or "")
            ):
                continue
            try:
                notice_id = canonical_source_id(url=page.abstract_url)
            except ValueError:
                notice_id = None
            out.append(
                StandingTransition(
                    source_id=src_id,
                    status=StandingStatus.RETRACTED,
                    reason=(page.comment or page.title or "withdrawn").strip()[:500],
                    poller=self.name,
                    observed_at=observed,
                    notice_source=notice_id,
                    raw_payload={"arxiv_id": arxiv_id, "title": page.title},
                )
            )
        return out


def parse_atom_entry(xml_bytes: bytes) -> Optional[ArxivPage]:
    """Helper for the live integration: parse an arXiv Atom entry into
    an ArxivPage. Kept here so tests can exercise the parser without
    spinning up the network."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    entry = root.find("a:entry", NS) if root.tag.endswith("feed") else root
    if entry is None:
        return None
    title_el = entry.find("a:title", NS)
    id_el = entry.find("a:id", NS)
    comment_el = entry.find(
        "{http://arxiv.org/schemas/atom}comment"
    )
    title = (title_el.text or "").strip() if title_el is not None else ""
    abs_url = (id_el.text or "").strip() if id_el is not None else ""
    comment = (comment_el.text or "").strip() if comment_el is not None else ""
    m = re.search(r"abs/([^/?#]+)", abs_url)
    arxiv_id = m.group(1) if m else ""
    return ArxivPage(
        arxiv_id=arxiv_id, title=title, comment=comment, abstract_url=abs_url
    )

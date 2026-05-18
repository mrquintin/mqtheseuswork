"""End-to-end test for the auto-accept principles + conclusions path.

Per founder direction (2026-05-17): a principle extracted from an
artifact is immediately available for internal reasoning AND surfaced
on /principles. There is no triage gate between extraction and
publication — the founder remediates a bad extraction post-hoc by
flipping ``status='rejected'`` rather than approving each new row.

This test covers the three points the prompt calls out:

  (a) ``PrincipleExtractor`` returns Conclusions with ``principle_kind``
      already set when the extractor produced a principle.
  (b) ``sync_drafts_to_codex`` lands the resulting draft as
      ``status='accepted'`` with ``publicVisible=true``.
  (c) the public ``listPublicPrinciples`` shape — i.e. rows the
      `/principles` page reads — includes the row immediately, without
      any intermediate UI action.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from noosphere.claim_extractor import PrincipleExtractor
from noosphere.codex_bridge import _open_codex_connection
from noosphere.distillation import (
    DraftPrinciple,
    PrincipleStatus,
    sync_drafts_to_codex,
)
from noosphere.llm import MockLLMClient
from noosphere.models import Chunk, PrincipleKind


ORG = "org_auto_accept"


_SCHEMA = """
CREATE TABLE "Organization" (
  id TEXT PRIMARY KEY,
  slug TEXT,
  name TEXT
);
CREATE TABLE "Principle" (
  id TEXT PRIMARY KEY,
  "organizationId" TEXT NOT NULL,
  text TEXT NOT NULL,
  "domainsJson" TEXT NOT NULL DEFAULT '[]',
  "clusterConclusionIds" TEXT NOT NULL DEFAULT '[]',
  "citedConclusionIds" TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'draft',
  "triageReason" TEXT NOT NULL DEFAULT '',
  "mergedIntoId" TEXT,
  "convictionScore" REAL NOT NULL DEFAULT 0.0,
  "domainBreadth" INTEGER NOT NULL DEFAULT 0,
  "clusterCentroidSimilarity" REAL NOT NULL DEFAULT 0.0,
  "publicVisible" INTEGER NOT NULL DEFAULT 0,
  "driftReason" TEXT,
  "reviewedByFounderId" TEXT,
  "createdAt" TEXT,
  "updatedAt" TEXT,
  "reviewedAt" TEXT,
  "publishedAt" TEXT
);
"""


@pytest.fixture
def codex_url(tmp_path: Path) -> str:
    path = tmp_path / "codex.db"
    setup = sqlite3.connect(str(path))
    setup.executescript(_SCHEMA)
    setup.execute(
        'INSERT INTO "Organization" (id, slug, name) VALUES (?, ?, ?)',
        (ORG, "auto-accept-org", "Auto-Accept Org"),
    )
    setup.commit()
    setup.close()
    return f"sqlite://{path}"


def _extractor_response(text: str, source_span: str, kind: str) -> MockLLMClient:
    payload = json.dumps(
        {
            "principles": [
                {
                    "text": text,
                    "source_span": source_span,
                    "principle_kind": kind,
                    "domain_of_applicability": "venture investing under uncertainty",
                    "quantifiable_proxies": ["months_of_runway", "burn_multiple"],
                    "decision_examples": ["cut headcount before raising"],
                }
            ],
            "refusals": [],
        }
    )
    return MockLLMClient(responses=[payload])


def test_extractor_emits_principle_kind_set_on_conclusion() -> None:
    """(a) PrincipleExtractor returns a Conclusion with principle_kind."""
    span = (
        "When a portfolio company is below product-market-fit and burning under 12 "
        "months of runway, cut spend before raising."
    )
    extractor = PrincipleExtractor(
        llm=_extractor_response(
            "When runway dips below 12 months at sub-PMF, cut spend before raising.",
            span,
            "RULE",
        )
    )
    chunk = Chunk(id="auto-accept-chunk", text=span, metadata={"speaker": "Founder"})
    conclusions, refusals = extractor.extract(chunk)

    assert refusals == []
    assert len(conclusions) == 1
    c = conclusions[0]
    # No triage UI sits between extraction and persistence — the
    # principle-shape fields are populated here, not later.
    assert c.principle_kind == PrincipleKind.RULE
    assert c.domain_of_applicability
    assert c.quantifiable_proxies
    assert c.decision_examples
    assert c.source_span == span


def test_sync_auto_accepts_draft_into_publicly_visible_row(codex_url: str) -> None:
    """(b) sync_drafts_to_codex lands the principle as accepted + public."""
    draft = DraftPrinciple(
        text="When runway dips below 12 months at sub-PMF, cut spend before raising.",
        domains=["Venture", "Finance"],
        cited_conclusion_ids=["c1"],
        cluster_conclusion_ids=["c1", "c2", "c3", "c4"],
        conviction_score=0.7,
        domain_breadth=2,
        cluster_centroid_similarity=0.88,
    )
    conn = _open_codex_connection(codex_url)
    counts = sync_drafts_to_codex(
        conn, organization_id=ORG, drafts=[draft]
    )
    conn.close()
    assert counts["inserted"] == 1
    assert counts["accepted"] == 1

    conn = _open_codex_connection(codex_url)
    cur = conn.cursor()
    cur.execute(
        'SELECT status, "publicVisible", "reviewedAt", "publishedAt" '
        'FROM "Principle" WHERE "organizationId" = %s',
        (ORG,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == PrincipleStatus.ACCEPTED
    assert row["publicVisible"]
    assert row["reviewedAt"] is not None
    assert row["publishedAt"] is not None


def test_public_principles_read_path_includes_auto_accepted_row(
    codex_url: str,
) -> None:
    """(c) The shape the /principles page reads includes the new row.

    The TS read filter is ``publicVisible = true AND status != 'rejected'``.
    Mirror that filter against the SQLite shim so we exercise the same
    selection without needing the TS runtime.
    """
    draft = DraftPrinciple(
        text="A thesis is admissible only if it carries a falsification clause within 24 months.",
        domains=["Epistemology"],
        cited_conclusion_ids=["c5"],
        cluster_conclusion_ids=["c5", "c6", "c7", "c8"],
        conviction_score=0.65,
        domain_breadth=1,
        cluster_centroid_similarity=0.9,
    )
    conn = _open_codex_connection(codex_url)
    sync_drafts_to_codex(conn, organization_id=ORG, drafts=[draft])
    conn.close()

    conn = _open_codex_connection(codex_url)
    cur = conn.cursor()
    # Same filter as theseus-codex/src/lib/principlesApi.ts:listPublicPrinciples.
    cur.execute(
        'SELECT id, text, status, "publicVisible" '
        'FROM "Principle" '
        'WHERE "organizationId" = %s '
        '  AND "publicVisible" = 1 '
        '  AND status != %s',
        (ORG, PrincipleStatus.REJECTED),
    )
    public_rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    assert len(public_rows) == 1
    assert public_rows[0]["text"].startswith("A thesis is admissible")


def test_rejected_row_still_hides_from_public_read(codex_url: str) -> None:
    """Founder remediation path: flipping status='rejected' hides the row."""
    draft = DraftPrinciple(
        text="A bad principle that the founder wants to suppress.",
        domains=["Misc"],
        cited_conclusion_ids=["c9"],
        cluster_conclusion_ids=["c9", "c10", "c11", "c12"],
        conviction_score=0.4,
        domain_breadth=1,
        cluster_centroid_similarity=0.7,
    )
    conn = _open_codex_connection(codex_url)
    sync_drafts_to_codex(conn, organization_id=ORG, drafts=[draft])
    conn.close()

    # Founder rejects.
    conn = _open_codex_connection(codex_url)
    cur = conn.cursor()
    cur.execute(
        'UPDATE "Principle" SET status = %s WHERE "organizationId" = %s',
        (PrincipleStatus.REJECTED, ORG),
    )
    conn.commit()
    conn.close()

    # Public read filter excludes rejected rows even when publicVisible
    # is still set — that is the safety net.
    conn = _open_codex_connection(codex_url)
    cur = conn.cursor()
    cur.execute(
        'SELECT id FROM "Principle" '
        'WHERE "organizationId" = %s '
        '  AND "publicVisible" = 1 '
        '  AND status != %s',
        (ORG, PrincipleStatus.REJECTED),
    )
    rows = list(cur.fetchall())
    conn.close()
    assert rows == []

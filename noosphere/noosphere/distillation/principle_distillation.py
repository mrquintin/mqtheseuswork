"""
Principle distillation pipeline.

Surfaces stable cross-domain principles the firm keeps re-deriving by:

  1. Pulling firm conclusions and their embeddings.
  2. Hierarchical clustering on the embedding-space neighborhood
     with a conservative threshold (the firm prefers fewer, more
     defensible principles over many narrow ones).
  3. Generating a candidate principle per cluster — single-sentence
     claim, conclusions-only context, citations required.
  4. Computing a conservative conviction score that rewards
     cross-domain convergence over single-conclusion centrality.
  5. Re-distillation diff: flagging existing accepted principles whose
     underlying cluster has shifted (new conclusions, retractions).

The output is a list of `DraftPrinciple` rows the founder triage UI
consumes; nothing here writes to the Codex (Prisma) directly — the CLI
or a sync step is responsible for persistence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence

from anthropic import Anthropic

from noosphere.models import Conclusion
from noosphere.observability import get_logger
from noosphere.ontology import OntologyGraph, PrincipleDistiller

logger = get_logger(__name__)


# ── Types ────────────────────────────────────────────────────────────────────


class PrincipleStatus:
    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_REREVIEW = "needs_rereview"


@dataclass
class DraftPrinciple:
    """A candidate principle the founder triage UI shows in the queue."""

    text: str
    domains: list[str]
    cited_conclusion_ids: list[str]
    cluster_conclusion_ids: list[str]
    conviction_score: float
    domain_breadth: int
    cluster_centroid_similarity: float
    status: str = PrincipleStatus.DRAFT
    existing_principle_id: Optional[str] = None
    drift_reason: Optional[str] = None
    drafted_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "domains": list(self.domains),
            "cited_conclusion_ids": list(self.cited_conclusion_ids),
            "cluster_conclusion_ids": list(self.cluster_conclusion_ids),
            "conviction_score": self.conviction_score,
            "domain_breadth": self.domain_breadth,
            "cluster_centroid_similarity": self.cluster_centroid_similarity,
            "status": self.status,
            "existing_principle_id": self.existing_principle_id,
            "drift_reason": self.drift_reason,
            "drafted_at": self.drafted_at.isoformat(),
        }


@dataclass
class PrincipleCandidate:
    """Internal cluster summary before LLM drafting."""

    indices: list[int]
    conclusions: list[Conclusion]
    centroid_similarities: list[float]
    domains: list[str]


# ── Conviction scoring ───────────────────────────────────────────────────────


def compute_conviction(
    *,
    cluster_size: int,
    domain_breadth: int,
    centrality_scores: Sequence[float],
) -> float:
    """
    Conservative conviction score in [0, 1].

    A single high-centrality conclusion does not produce conviction. The
    score multiplies three saturating components so each must be
    non-trivial:

      * size: log-saturating count of conclusions in the cluster
      * breadth: log-saturating count of distinct domains
      * centrality: mean centrality across the cluster

    Convergence across domains is the dominant lever — a 5-conclusion
    cluster spanning 4 domains scores higher than a 5-conclusion
    cluster all in one domain.
    """
    if cluster_size <= 0:
        return 0.0

    size_term = math.log1p(cluster_size) / math.log1p(8)
    breadth_term = math.log1p(max(0, domain_breadth)) / math.log1p(4)
    if centrality_scores:
        centrality_mean = sum(centrality_scores) / len(centrality_scores)
    else:
        centrality_mean = 0.0
    centrality_term = max(0.0, min(1.0, centrality_mean))

    if domain_breadth < 2:
        # Single-domain principles cannot reach high conviction; cap
        # them to keep the queue honest about narrowness.
        breadth_term = min(breadth_term, 0.4)

    score = size_term * breadth_term * centrality_term
    return max(0.0, min(1.0, score))


# ── Pipeline ─────────────────────────────────────────────────────────────────


class PrincipleDistillationPipeline:
    """Run principle distillation across the firm's full conclusion corpus."""

    def __init__(
        self,
        *,
        graph: Optional[OntologyGraph] = None,
        embedder: Any,
        distiller: Optional[Any] = None,
        anthropic_client: Optional[Anthropic] = None,
        clustering_threshold: float = 0.18,
        min_cluster_size: int = 4,
        min_domain_breadth: int = 2,
    ) -> None:
        """
        Args:
            graph: OntologyGraph that owns the LLM-backed distiller.
                Optional when ``distiller`` is supplied directly (the
                test path).
            embedder: anything with ``.encode(list[str]) -> list[list[float]]``.
            distiller: optional pre-built distiller; defaults to a fresh
                ``PrincipleDistiller`` over ``graph``.  We reuse the
                existing principle distillation primitive rather than
                reinventing it.
            anthropic_client: optional shared Anthropic client.
            clustering_threshold: cosine distance threshold for the
                agglomerative cluster cut.  Default 0.18 is deliberately
                conservative — neighbors must be very close to merge.
            min_cluster_size: min conclusions per cluster.  Default 4
                so a single recurring claim cannot become a principle.
            min_domain_breadth: min distinct domains per cluster.  The
                firm avoids universal-sounding principles whose
                evidence is domain-narrow.
        """
        if distiller is None:
            if graph is None:
                graph = OntologyGraph()
            distiller = PrincipleDistiller(graph=graph, client=anthropic_client)
        self.embedder = embedder
        self.distiller = distiller
        self.clustering_threshold = clustering_threshold
        self.min_cluster_size = min_cluster_size
        self.min_domain_breadth = min_domain_breadth

    # ── Public API ───────────────────────────────────────────────────────

    def run(
        self,
        conclusions: Sequence[Conclusion],
        *,
        existing_principles: Optional[Iterable[dict[str, Any]]] = None,
    ) -> list[DraftPrinciple]:
        """
        Run distillation across the firm's conclusion corpus.

        Returns the founder-triage queue — drafts plus any existing
        accepted principles whose underlying cluster has shifted.
        """
        if not conclusions:
            return []

        usable, embeddings = self._embed_conclusions(list(conclusions))
        if len(usable) < self.min_cluster_size:
            logger.info("not enough conclusions to distill (%d)", len(usable))
            return []

        clusters = self.distiller.cluster_conclusions(
            conclusions=usable,
            embeddings=embeddings,
            clustering_threshold=self.clustering_threshold,
            min_cluster_size=self.min_cluster_size,
        )
        logger.info(
            "clustered %d conclusions into %d clusters",
            len(usable),
            len(clusters),
        )

        candidates = [
            self._summarize_cluster(usable, embeddings, idxs)
            for idxs in clusters
        ]

        drafts: list[DraftPrinciple] = []
        for cand in candidates:
            if len(set(cand.domains)) < self.min_domain_breadth:
                # Domain-narrow clusters are dropped from the public
                # path; they may still surface as founder-only drafts
                # below.
                logger.debug(
                    "skipping cluster with %d distinct domains "
                    "(min=%d)",
                    len(set(cand.domains)),
                    self.min_domain_breadth,
                )
            draft = self._draft_from_candidate(cand)
            if draft is not None:
                drafts.append(draft)

        if existing_principles:
            drafts.extend(
                redistill(
                    drafts,
                    existing_principles=list(existing_principles),
                )
            )

        # Conviction-weighted ordering — the highest-conviction drafts
        # rise to the top of the founder queue.
        drafts.sort(key=lambda d: d.conviction_score, reverse=True)
        return drafts

    # ── Internals ────────────────────────────────────────────────────────

    def _embed_conclusions(
        self, conclusions: list[Conclusion]
    ) -> tuple[list[Conclusion], list[list[float]]]:
        usable: list[Conclusion] = []
        texts: list[str] = []
        for c in conclusions:
            if not c.text or not c.text.strip():
                continue
            usable.append(c)
            texts.append(c.text)
        if not usable:
            return [], []
        embeddings = self.embedder.encode(texts)
        return usable, embeddings

    def _summarize_cluster(
        self,
        conclusions: list[Conclusion],
        embeddings: list[list[float]],
        indices: list[int],
    ) -> PrincipleCandidate:
        cluster_concls = [conclusions[i] for i in indices]
        cluster_vecs = [embeddings[i] for i in indices]

        # Compute mean vector and per-member cosine similarity.  No
        # external dependency required — keeps tests light.
        dim = len(cluster_vecs[0]) if cluster_vecs else 0
        mean = [0.0] * dim
        for v in cluster_vecs:
            for j, val in enumerate(v):
                mean[j] += float(val)
        if cluster_vecs:
            mean = [x / len(cluster_vecs) for x in mean]
        sims = [_cosine(v, mean) for v in cluster_vecs]

        domains: list[str] = []
        for c in cluster_concls:
            for d in c.disciplines:
                # Discipline is an Enum — its .value is the domain
                # string; fall back to str() for exotic shapes.
                domains.append(getattr(d, "value", str(d)))

        return PrincipleCandidate(
            indices=indices,
            conclusions=cluster_concls,
            centroid_similarities=sims,
            domains=domains,
        )

    def _draft_from_candidate(
        self, cand: PrincipleCandidate
    ) -> Optional[DraftPrinciple]:
        if not cand.conclusions:
            return None

        drafted = self.distiller.draft_principle_for_conclusions(cand.conclusions)
        if drafted is None or not drafted.get("text"):
            return None

        # Use the LLM-emitted domains where present, else fall back to
        # the cluster's own discipline tags.
        emitted_domains = drafted.get("domains") or []
        domains = list(dict.fromkeys(emitted_domains or cand.domains))
        domain_breadth = len(set(domains))

        cluster_size = len(cand.conclusions)
        avg_centroid_sim = (
            sum(cand.centroid_similarities) / len(cand.centroid_similarities)
            if cand.centroid_similarities
            else 0.0
        )

        conviction = compute_conviction(
            cluster_size=cluster_size,
            domain_breadth=domain_breadth,
            centrality_scores=cand.centroid_similarities,
        )

        return DraftPrinciple(
            text=drafted["text"],
            domains=domains,
            cited_conclusion_ids=drafted["cited_conclusion_ids"],
            cluster_conclusion_ids=[c.id for c in cand.conclusions],
            conviction_score=conviction,
            domain_breadth=domain_breadth,
            cluster_centroid_similarity=avg_centroid_sim,
        )


# ── Re-derivation diff ───────────────────────────────────────────────────────


def redistill(
    new_drafts: Sequence[DraftPrinciple],
    *,
    existing_principles: Sequence[dict[str, Any]],
) -> list[DraftPrinciple]:
    """
    Compare a fresh distillation pass against accepted principles and
    surface those whose underlying cluster has shifted enough to merit
    re-validation.

    `existing_principles` rows are expected to expose:
      - id: stable principle id
      - cluster_conclusion_ids: list[str]

    A principle is flagged when:
      * a fresh draft overlaps its cluster but adds new conclusions, OR
      * a fresh draft drops conclusions it previously generalized, OR
      * its cluster has no overlapping fresh draft at all (full drift).
    """
    flagged: list[DraftPrinciple] = []
    consumed_existing: set[str] = set()

    for existing in existing_principles:
        ex_id = str(existing.get("id", ""))
        ex_ids = set(existing.get("cluster_conclusion_ids", []) or [])
        if not ex_id or not ex_ids:
            continue

        best_overlap = 0
        best_draft: Optional[DraftPrinciple] = None
        for draft in new_drafts:
            overlap = len(ex_ids & set(draft.cluster_conclusion_ids))
            if overlap > best_overlap:
                best_overlap = overlap
                best_draft = draft

        if best_draft is None:
            flagged.append(
                DraftPrinciple(
                    text=str(existing.get("text", "")),
                    domains=list(existing.get("domains", []) or []),
                    cited_conclusion_ids=list(
                        existing.get("cited_conclusion_ids", []) or []
                    ),
                    cluster_conclusion_ids=sorted(ex_ids),
                    conviction_score=float(
                        existing.get("conviction_score", 0.0)
                    ),
                    domain_breadth=len(
                        set(existing.get("domains", []) or [])
                    ),
                    cluster_centroid_similarity=0.0,
                    status=PrincipleStatus.NEEDS_REREVIEW,
                    existing_principle_id=ex_id,
                    drift_reason="cluster_dissolved",
                )
            )
            continue

        new_ids = set(best_draft.cluster_conclusion_ids)
        added = new_ids - ex_ids
        dropped = ex_ids - new_ids
        if not added and not dropped:
            consumed_existing.add(ex_id)
            continue

        # Mark the matching draft as a re-review of this principle so
        # the founder UI shows it next to the prior text.
        consumed_existing.add(ex_id)
        best_draft.status = PrincipleStatus.NEEDS_REREVIEW
        best_draft.existing_principle_id = ex_id
        if added and dropped:
            best_draft.drift_reason = "cluster_added_and_retracted"
        elif added:
            best_draft.drift_reason = "cluster_grew"
        else:
            best_draft.drift_reason = "cluster_shrunk"

    return flagged


# ── Math helper ──────────────────────────────────────────────────────────────


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += float(x) * float(y)
        na += float(x) * float(x)
        nb += float(y) * float(y)
    denom = math.sqrt(na) * math.sqrt(nb)
    if denom <= 0.0:
        return 0.0
    return dot / denom

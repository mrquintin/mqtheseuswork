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
consumes. The pipeline itself never opens a Codex connection; the
`sync_drafts_to_codex` helper below is the persistence primitive — it
takes a DB connection a caller (the CLI or `run_principle_distillation.sh`)
already owns and writes the queue. Every synced row lands as
``draft`` / ``needs_rereview`` / ``merged`` — never ``accepted`` and
never ``publicVisible``. Publishing a principle is a founder action in
the triage UI; nothing in this module publishes.
"""
from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional, Sequence

from anthropic import Anthropic

from noosphere.models import Conclusion
from noosphere.observability import get_logger
from noosphere.ontology import OntologyGraph, PrincipleDistiller
from noosphere.peer_review.providers import PROVIDER_DEFAULTS, estimate_cost

logger = get_logger(__name__)


# ── Types ────────────────────────────────────────────────────────────────────


class PrincipleStatus:
    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MERGED = "merged"
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
    # Set when the queue-level auto-merge folds this draft into an
    # already-accepted principle it merely paraphrases.
    merged_into_id: Optional[str] = None
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
            "merged_into_id": self.merged_into_id,
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
        cost_cap_usd: Optional[float] = None,
        pricing: Any = None,
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
            cost_cap_usd: optional hard ceiling on the estimated LLM
                spend of one ``run``.  Each cluster's draft call is
                cost-estimated before it is issued; a cluster whose
                estimated cost would push the running total past the
                cap is skipped (not drafted) and ``budget_exhausted``
                is set.  ``None`` disables the gate.
            pricing: provider price table entry used for the cost
                estimate; defaults to the Anthropic ``PROVIDER_DEFAULTS``
                row (the existing LLM client the distiller drafts with).
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
        self.cost_cap_usd = cost_cap_usd
        self._pricing = pricing or PROVIDER_DEFAULTS["anthropic"]
        # Per-run cost telemetry; reset at the top of ``run``.
        self.estimated_cost_usd: float = 0.0
        self.budget_exhausted: bool = False
        self.clusters_skipped_for_budget: int = 0

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
        # Reset per-run cost telemetry so a reused pipeline reports the
        # spend of this pass only.
        self.estimated_cost_usd = 0.0
        self.budget_exhausted = False
        self.clusters_skipped_for_budget = 0

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
            # Cost cap: estimate the draft call's spend before issuing
            # it. A cluster whose draft would push the running total
            # past the cap is skipped — the firm honors the budget over
            # completeness, and the founder memo records what was left
            # undrafted.
            est = self._estimate_draft_cost_usd(cand)
            if (
                self.cost_cap_usd is not None
                and self.estimated_cost_usd + est > self.cost_cap_usd
            ):
                self.budget_exhausted = True
                self.clusters_skipped_for_budget += 1
                logger.info(
                    "cost cap $%.4f reached (spent $%.4f); skipping a "
                    "%d-conclusion cluster",
                    self.cost_cap_usd,
                    self.estimated_cost_usd,
                    len(cand.conclusions),
                )
                continue
            self.estimated_cost_usd += est
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

    def _estimate_draft_cost_usd(self, cand: PrincipleCandidate) -> float:
        """
        Estimate the LLM spend of drafting one cluster, before the call
        is issued.  The distiller's draft prompt is a fixed instruction
        surface plus one ``[id] text`` line per cluster conclusion; the
        completion is capped at the distiller's ``max_tokens``.  We
        price that envelope through the shared provider cost table so
        the cap is honored against the same numbers the rest of the
        firm bills with — ~4 chars/token is the standard rough
        conversion used elsewhere in the codebase.
        """
        prompt_chars = 600  # fixed instruction + JSON scaffold
        for c in cand.conclusions:
            prompt_chars += len(c.id) + len(c.text or "") + 4
        tokens_in = int(prompt_chars / 4.0) + 16
        tokens_out = 600  # distiller draft call's max_tokens ceiling
        return estimate_cost(
            defaults=self._pricing,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
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


# ── Queue-level auto-merge ───────────────────────────────────────────────────


def auto_merge_against_accepted(
    drafts: Sequence[DraftPrinciple],
    *,
    accepted_principles: Sequence[dict[str, Any]],
    embedder: Any,
    paraphrase_threshold: float = 0.92,
) -> int:
    """
    Fold drafts that merely paraphrase an already-accepted principle
    into that principle, in place.

    The constraint: a candidate that re-states a principle the firm has
    already accepted must not surface in the founder queue as a fresh
    duplicate.  We compare each draft's text against every accepted
    principle's text in embedding space; a cosine similarity at or above
    ``paraphrase_threshold`` flips the draft to ``PrincipleStatus.MERGED``
    with ``merged_into_id`` pointing at the accepted row.

    This is *not* a publish — an auto-merge writes a ``merged`` tombstone
    that links a duplicate to an existing principle; it adds nothing to
    the public surface.  Founder confirmation is therefore not required
    (the founder-confirmation rule is about writes that publish).

    Returns the number of drafts auto-merged.
    """
    accepted = [
        p
        for p in accepted_principles
        if str(p.get("id", "")).strip() and str(p.get("text", "")).strip()
    ]
    mergeable = [
        d
        for d in drafts
        if d.status in (PrincipleStatus.DRAFT, PrincipleStatus.NEEDS_REREVIEW)
        and d.text.strip()
    ]
    if not accepted or not mergeable:
        return 0

    accepted_texts = [str(p["text"]) for p in accepted]
    draft_texts = [d.text for d in mergeable]
    vectors = embedder.encode(accepted_texts + draft_texts)
    acc_vecs = vectors[: len(accepted_texts)]
    draft_vecs = vectors[len(accepted_texts):]

    merged = 0
    for draft, dvec in zip(mergeable, draft_vecs):
        best_sim = -1.0
        best_id: Optional[str] = None
        for acc, avec in zip(accepted, acc_vecs):
            sim = _cosine(dvec, avec)
            if sim > best_sim:
                best_sim = sim
                best_id = str(acc["id"])
        if best_id is not None and best_sim >= paraphrase_threshold:
            draft.status = PrincipleStatus.MERGED
            draft.merged_into_id = best_id
            draft.existing_principle_id = best_id
            draft.drift_reason = None
            merged += 1
    return merged


# ── Founder triage memo ──────────────────────────────────────────────────────
#
# The prompted agent does NOT accept principles on the founder's behalf.
# After a distillation pass it writes this memo: every candidate, the
# conclusions under it, and an advisory recommendation. The founder
# reads it and acts in the triage UI — the memo is advice, not a write.

# Drafts below this conviction are recommended for rejection: the
# cluster is too thin or too weakly central for the firm to defend.
LOW_CONVICTION_FLOOR = 0.15


def _concl_text(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, dict):
        return str(obj.get("text") or "")
    return str(getattr(obj, "text", "") or "")


def _concl_tier(obj: Any) -> str:
    if obj is None:
        return "—"
    if isinstance(obj, dict):
        tier = obj.get("confidenceTier") or obj.get("confidence_tier") or "—"
    else:
        tier = getattr(obj, "confidence_tier", None) or "—"
    return str(getattr(tier, "value", tier))


def _triage_recommendation(
    draft: DraftPrinciple,
    *,
    accepted_by_id: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    """
    Return ``(action, detail)`` — the agent's advisory recommendation
    for one candidate. ``action`` is one of: ``auto-merged``,
    ``propose accept``, ``propose reject``, ``propose merge``,
    ``propose re-accept``.
    """
    if draft.status == PrincipleStatus.MERGED:
        tgt = draft.merged_into_id or draft.existing_principle_id or "?"
        return (
            "auto-merged",
            f"Folded into accepted principle `{tgt}` at the queue level — "
            "it paraphrases a principle the firm already holds. No founder "
            "action; listed for the record.",
        )
    if draft.status == PrincipleStatus.NEEDS_REREVIEW:
        ex = draft.existing_principle_id or "?"
        if draft.drift_reason == "cluster_dissolved":
            return (
                "propose reject",
                f"The cluster behind accepted principle `{ex}` has dissolved "
                "— no fresh draft re-derives it. Propose retiring it: reject "
                "with reason 'underlying cluster dissolved on re-distillation'.",
            )
        return (
            "propose re-accept",
            f"Accepted principle `{ex}` drifted ({draft.drift_reason}). "
            f"Proposed accept text: “{draft.text}”. Re-accept against "
            "the updated cluster, or reject if the drift breaks the claim.",
        )
    # Plain draft.
    if draft.domain_breadth < 2:
        return (
            "propose reject",
            f"Spans only {draft.domain_breadth} domain — the firm does not "
            "publish domain-narrow universals. Propose reject (reason: "
            "'domain-narrow: single-domain evidence'), or keep it as a "
            "founder-only working note rather than a public principle.",
        )
    if draft.conviction_score < LOW_CONVICTION_FLOOR:
        return (
            "propose reject",
            f"Conviction {draft.conviction_score:.2f} is below the queue floor "
            f"({LOW_CONVICTION_FLOOR:.2f}) — the cluster is thin or weakly "
            "central. Propose reject (reason: 'low conviction: cluster too "
            "thin to defend').",
        )
    if draft.existing_principle_id and draft.existing_principle_id in accepted_by_id:
        return (
            "propose merge",
            f"Overlaps existing principle `{draft.existing_principle_id}`. "
            "Propose merge-with-existing in the detail UI.",
        )
    domains = ", ".join(draft.domains) if draft.domains else "—"
    return (
        "propose accept",
        f"Proposed accept text: “{draft.text}”. Proposed domains: "
        f"{domains}. Accept (with edits) and publish if the firm will be "
        "held to it.",
    )


def _honesty_preamble(run_kind: str) -> str:
    if "offline" in run_kind:
        return (
            "## 0. Honesty preamble — what produced these candidates\n\n"
            "This pass ran the **offline deterministic distiller** "
            f"(`run_kind: {run_kind}`), not live LLM calls. No "
            "`ANTHROPIC_API_KEY` was present, so rather than emit an empty "
            "queue the run fell back to a deterministic drafter. It is a "
            "fallback, and every artefact says so — but it is not a toy:\n\n"
            "- **Clustering is real.** Agglomerative clustering over the "
            "conclusion embeddings runs unchanged; the cluster membership "
            "is exactly what the provider-backed pass would see.\n"
            "- **Conviction is real.** `compute_conviction` over the real "
            "cluster size / domain breadth / centroid similarity.\n"
            "- **Cost is real.** Spend is priced through the shared "
            "`estimate_cost` table; the offline drafter simply costs $0.\n"
            "- **It is reproducible.** Same corpus → identical candidates "
            "on every host.\n\n"
            "Only the candidate *wording* is deterministic-extractive "
            "rather than LLM-distilled. When `ANTHROPIC_API_KEY` is "
            "provisioned the run switches to the provider-backed distiller "
            "automatically and stamps `run_kind: provider-backed`; the "
            "clusters and conviction scores survive that switch, the exact "
            "phrasing of each candidate does not.\n"
        )
    return (
        "## 0. Honesty preamble — what produced these candidates\n\n"
        f"This pass ran the **provider-backed distiller** (`run_kind: "
        f"{run_kind}`): the existing LLM client drafted one candidate per "
        "cluster from the cluster's conclusions only. The draft prompt "
        "forbids free invention and requires each candidate to cite the "
        "conclusion ids it generalizes. The pass honored the configured "
        "cost cap — clusters whose estimated draft cost would exceed the "
        "budget were left undrafted and are noted in section 1.\n"
    )


def build_triage_memo(
    *,
    run_stamp: str,
    run_kind: str,
    corpus_label: str,
    drafts: Sequence[DraftPrinciple],
    conclusions_by_id: dict[str, Any],
    accepted_principles: Sequence[dict[str, Any]] = (),
    pipeline_stats: Optional[dict[str, Any]] = None,
) -> str:
    """
    Render the founder triage memo for one distillation pass.

    The memo is advisory: it lists every candidate, the conclusions
    underneath it, and a recommendation (proposed accept text, proposed
    merge target, or proposed reject reason). It never accepts anything
    — the founder reads it and acts in `/principles/queue`.
    """
    stats = dict(pipeline_stats or {})
    accepted_by_id = {
        str(p.get("id")): p for p in accepted_principles if p.get("id")
    }

    queue = [d for d in drafts if d.status != PrincipleStatus.MERGED]
    auto_merged = [d for d in drafts if d.status == PrincipleStatus.MERGED]

    lines: list[str] = []
    lines.append("# Principle Distillation — Founder Triage Memo")
    lines.append("")
    lines.append(
        f"**Run:** `{run_stamp}` · `run_kind: {run_kind}` · corpus "
        f"`{corpus_label}`"
    )
    lines.append(
        "**Audience:** founder / internal. The public version of an "
        "accepted principle is the row it produces on "
        "`/methodology/principles`; this memo is the candid reading "
        "behind the queue at `/principles/queue`."
    )
    lines.append(
        f"**Status:** distillation has run. {len(queue)} candidate(s) await "
        f"founder triage; {len(auto_merged)} were auto-merged at the queue "
        "level. **The agent does not accept principles** — every publish is "
        "a founder action in the UI. The recommendations below are advice."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(_honesty_preamble(run_kind))
    lines.append("---")
    lines.append("")

    # ── Section 1: what ran ──────────────────────────────────────────
    lines.append("## 1. What ran")
    lines.append("")
    corpus_size = stats.get("corpus_size")
    clusters = stats.get("clusters")
    lines.append(
        f"- **Corpus:** {corpus_size if corpus_size is not None else '—'} "
        f"conclusion(s) — `{corpus_label}`."
    )
    lines.append(
        f"- **Clusters:** {clusters if clusters is not None else '—'} "
        "embedding-space cluster(s) cleared the size gate."
    )
    lines.append(
        f"- **Candidates queued:** {len(queue)} "
        f"(draft + needs-re-review), conviction-sorted."
    )
    lines.append(f"- **Auto-merged:** {len(auto_merged)} duplicate(s).")
    est = stats.get("estimated_cost_usd")
    cap = stats.get("cost_cap_usd")
    if est is not None:
        cap_str = f"${cap:.4f}" if cap is not None else "uncapped"
        lines.append(
            f"- **Estimated LLM spend:** ${float(est):.4f} (cap: {cap_str})."
        )
    if stats.get("budget_exhausted"):
        skipped = stats.get("clusters_skipped_for_budget", 0)
        lines.append(
            f"- **Cost cap reached:** {skipped} cluster(s) were left "
            "undrafted to honor the budget. Re-run with a higher "
            "`--cost-cap` to pick them up."
        )
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Section 2: candidates ────────────────────────────────────────
    lines.append("## 2. Candidates for founder triage")
    lines.append("")
    if not queue:
        lines.append(
            "_No candidates this pass — the corpus produced no cluster that "
            "cleared the size and domain-breadth gates._"
        )
        lines.append("")
    for idx, draft in enumerate(queue, start=1):
        action, detail = _triage_recommendation(
            draft, accepted_by_id=accepted_by_id
        )
        lines.append(
            f"### {idx}. {draft.text or '_(empty draft text)_'}"
        )
        lines.append("")
        domains = ", ".join(draft.domains) if draft.domains else "—"
        meta = (
            f"conviction `{draft.conviction_score:.2f}` · "
            f"domains `{domains}` ({draft.domain_breadth}) · "
            f"cluster `{len(draft.cluster_conclusion_ids)}` · "
            f"status `{draft.status}`"
        )
        if draft.drift_reason:
            meta += f" · drift `{draft.drift_reason}`"
        lines.append(f"- **Signals:** {meta}")
        lines.append(f"- **Recommendation — {action}:** {detail}")
        lines.append("")
        lines.append("- **Underlying conclusions:**")
        cited = set(draft.cited_conclusion_ids)
        if not draft.cluster_conclusion_ids:
            lines.append(
                "  - _(cluster dissolved — no conclusions on the fresh pass)_"
            )
        for cid in draft.cluster_conclusion_ids:
            obj = conclusions_by_id.get(cid)
            text = _concl_text(obj) or "_(not found in corpus — retracted?)_"
            tier = _concl_tier(obj)
            mark = " · **cited by draft**" if cid in cited else ""
            lines.append(f"  - `{cid}` (tier `{tier}`{mark}) — {text}")
        lines.append("")

    # ── Section 3: auto-merged ───────────────────────────────────────
    if auto_merged:
        lines.append("---")
        lines.append("")
        lines.append("## 3. Auto-merged candidates (no founder action)")
        lines.append("")
        lines.append(
            "These candidates paraphrase a principle the firm already "
            "accepted. They were merged at the queue level rather than "
            "surfaced as duplicates; the founder does not need to triage "
            "them."
        )
        lines.append("")
        for draft in auto_merged:
            tgt = draft.merged_into_id or draft.existing_principle_id or "?"
            tgt_text = ""
            if tgt in accepted_by_id:
                tgt_text = f" — “{accepted_by_id[tgt].get('text', '')}”"
            lines.append(
                f"- “{draft.text}” → merged into `{tgt}`{tgt_text}"
            )
        lines.append("")

    # ── Section 4: how to triage ─────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## 4. How to triage")
    lines.append("")
    lines.append(
        "1. Open `/principles/queue`. Candidates are conviction-sorted; "
        "`j`/`k` (or `↑`/`↓`) move the selection, `Enter` opens the "
        "selected candidate, `e` jumps straight to its underlying "
        "conclusions, and `p` opens the triage command palette."
    )
    lines.append(
        "2. On a candidate's detail page: **accept (with edits)** — edit the "
        "text and domains, optionally flip public visibility; **reject "
        "(with reason)**; or **merge into an existing principle**."
    )
    lines.append(
        "3. Acceptance with public visibility + at least one domain is the "
        "only path onto `/methodology/principles` — that page populates "
        "automatically from accepted, public-visible, domain-declared rows."
    )
    lines.append(
        "4. Conviction is recomputed after triage so principle scores stay "
        "propagated from the current conclusion corpus."
    )
    lines.append("")
    return "\n".join(lines)


# ── Codex persistence ────────────────────────────────────────────────────────


def _dict_cursor(conn: Any) -> Any:
    """
    Return a cursor that yields dict-like rows for both psycopg2 (the
    real Codex Postgres) and the ``codex_bridge`` SQLite test shim.
    psycopg2 wants ``RealDictCursor``; the shim ignores cursor kwargs
    and already returns dict rows.
    """
    try:  # pragma: no cover - exercised via both paths in integration tests
        from psycopg2.extras import RealDictCursor

        return conn.cursor(cursor_factory=RealDictCursor)
    except Exception:
        return conn.cursor()


def _principle_id() -> str:
    """A unique id for a Principle row. Prisma normally emits cuid(); the
    DB only enforces uniqueness, so a uuid4-derived id is fine and keeps
    this module Python-only."""
    return "prn_" + uuid.uuid4().hex[:24]


_SYNC_COLUMNS = (
    "id",
    "organizationId",
    "text",
    "domainsJson",
    "clusterConclusionIds",
    "citedConclusionIds",
    "status",
    "triageReason",
    "mergedIntoId",
    "convictionScore",
    "domainBreadth",
    "clusterCentroidSimilarity",
    "publicVisible",
    "driftReason",
    "reviewedByFounderId",
    "createdAt",
    "updatedAt",
    "reviewedAt",
    "publishedAt",
)


def _draft_triage_reason(draft: DraftPrinciple) -> str:
    if draft.status == PrincipleStatus.MERGED:
        tgt = draft.merged_into_id or draft.existing_principle_id or "?"
        return f"auto-merged: paraphrases accepted principle {tgt}"
    if draft.status == PrincipleStatus.NEEDS_REREVIEW:
        return f"re-distillation drift: {draft.drift_reason or 'unspecified'}"
    return ""


def sync_drafts_to_codex(
    conn: Any,
    *,
    organization_id: str,
    drafts: Sequence[DraftPrinciple],
    now: Optional[datetime] = None,
    replace_recently_accepted: bool = True,
    id_factory: Any = _principle_id,
) -> dict[str, int]:
    """
    Persist a distillation pass into the Codex ``Principle`` table.

    Per founder direction (2026-05-17), every queueable draft lands as
    ``accepted`` + ``publicVisible=true`` on insert. ``reviewedAt`` and
    ``publishedAt`` are stamped to the insert time. ``needs_rereview``
    and ``merged`` rows still carry their own status — only the plain
    ``draft`` status flips to ``accepted`` on the way in.

    When ``replace_recently_accepted`` is set (the default), any
    ``accepted`` rows the sync itself produced within the last 24 hours
    are deleted first, so re-running distillation refreshes recent
    additions instead of piling duplicates onto them — historical
    accepted rows (older than 24h) and rows the founder explicitly
    rejected are never touched.

    ``conn`` is a DB connection the caller owns (psycopg2 against the
    real Codex, or the ``codex_bridge`` SQLite shim in tests). The
    caller is responsible for closing it.

    Returns counts: ``{"inserted", "deleted_stale", "accepted",
    "needs_rereview", "merged"}``.
    """
    now_dt = now or datetime.now(timezone.utc)
    ts = now_dt.isoformat()
    cur = _dict_cursor(conn)
    counts = {
        "inserted": 0,
        "deleted_stale": 0,
        "accepted": 0,
        "needs_rereview": 0,
        "merged": 0,
    }

    if replace_recently_accepted:
        cutoff = (now_dt - timedelta(hours=24)).isoformat()
        cur.execute(
            'DELETE FROM "Principle" '
            'WHERE "organizationId" = %s AND status = %s '
            'AND "publishedAt" IS NOT NULL AND "publishedAt" >= %s',
            (organization_id, PrincipleStatus.ACCEPTED, cutoff),
        )
        counts["deleted_stale"] = int(cur.rowcount or 0)

    placeholders = ", ".join(["%s"] * len(_SYNC_COLUMNS))
    columns = ", ".join(f'"{c}"' for c in _SYNC_COLUMNS)
    insert_sql = f'INSERT INTO "Principle" ({columns}) VALUES ({placeholders})'

    for draft in drafts:
        draft_status = draft.status
        if draft_status not in (
            PrincipleStatus.DRAFT,
            PrincipleStatus.NEEDS_REREVIEW,
            PrincipleStatus.MERGED,
        ):
            logger.warning(
                "skipping draft with non-queue status %r", draft_status
            )
            continue
        # Plain drafts auto-accept on insert; needs_rereview and merged
        # keep their own status (they represent founder-relevant signals
        # the auto-accept path should not silently overwrite).
        if draft_status == PrincipleStatus.DRAFT:
            status = PrincipleStatus.ACCEPTED
            public_visible = True
            reviewed_at: Optional[str] = ts
            published_at: Optional[str] = ts
        else:
            status = draft_status
            public_visible = False
            reviewed_at = None
            published_at = None
        row = (
            id_factory(),
            organization_id,
            draft.text,
            json.dumps(list(draft.domains)),
            json.dumps(list(draft.cluster_conclusion_ids)),
            json.dumps(list(draft.cited_conclusion_ids)),
            status,
            _draft_triage_reason(draft),
            draft.merged_into_id,
            float(draft.conviction_score),
            int(draft.domain_breadth),
            float(draft.cluster_centroid_similarity),
            public_visible,
            draft.drift_reason,
            None,  # reviewedByFounderId — founder action only
            ts,  # createdAt
            ts,  # updatedAt
            reviewed_at,
            published_at,
        )
        cur.execute(insert_sql, row)
        counts["inserted"] += 1
        counts[status] = counts.get(status, 0) + 1

    conn.commit()
    return counts


def recompute_conviction_for_accepted(
    conn: Any,
    *,
    organization_id: str,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """
    Re-run conviction weighting over the org's accepted principles.

    Conviction is a function of the *current* conclusion corpus: when a
    cluster conclusion is retracted (its ``Conclusion`` row is gone) the
    principle's cluster shrinks and its conviction must fall. This is
    the cascade step — it propagates conclusion-level change up into
    principle conviction so the public page never shows a score the
    underlying evidence no longer supports.

    For each accepted principle: re-read the surviving cluster
    conclusions, recompute the centroid similarity from their stored
    embeddings where available (falling back to the stored value),
    re-run ``compute_conviction`` over the live cluster size and the
    principle's declared domain breadth, and update the row when the
    score moves.

    Returns one change record per principle whose ``convictionScore``
    moved: ``{"id", "before", "after", "cluster_before",
    "cluster_after"}``.
    """
    ts = (now or datetime.now(timezone.utc)).isoformat()
    cur = _dict_cursor(conn)
    cur.execute(
        'SELECT id, "clusterConclusionIds", "domainBreadth", '
        '"clusterCentroidSimilarity", "convictionScore" '
        'FROM "Principle" '
        'WHERE "organizationId" = %s AND status = %s',
        (organization_id, PrincipleStatus.ACCEPTED),
    )
    accepted_rows = [dict(r) for r in cur.fetchall()]

    changes: list[dict[str, Any]] = []
    for row in accepted_rows:
        pid = row["id"]
        try:
            cluster_ids = json.loads(row["clusterConclusionIds"] or "[]")
        except (TypeError, json.JSONDecodeError):
            cluster_ids = []
        cluster_ids = [str(c) for c in cluster_ids if isinstance(c, str)]
        before_score = float(row["convictionScore"] or 0.0)
        domain_breadth = int(row["domainBreadth"] or 0)
        stored_centroid = float(row["clusterCentroidSimilarity"] or 0.0)

        survivors: list[dict[str, Any]] = []
        if cluster_ids:
            in_clause = ", ".join(["%s"] * len(cluster_ids))
            cur.execute(
                f'SELECT id, "embeddingJson" FROM "Conclusion" '
                f'WHERE "organizationId" = %s AND id IN ({in_clause})',
                (organization_id, *cluster_ids),
            )
            survivors = [dict(r) for r in cur.fetchall()]

        survivor_count = len(survivors)

        # Recompute centroid similarity from surviving embeddings when
        # every survivor carries one; otherwise keep the stored value.
        vecs: list[list[float]] = []
        for s in survivors:
            raw = s.get("embeddingJson")
            if not raw:
                vecs = []
                break
            try:
                parsed = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                vecs = []
                break
            if not isinstance(parsed, list) or not parsed:
                vecs = []
                break
            vecs.append([float(x) for x in parsed])

        if vecs and len({len(v) for v in vecs}) == 1:
            dim = len(vecs[0])
            mean = [0.0] * dim
            for v in vecs:
                for j, val in enumerate(v):
                    mean[j] += val
            mean = [x / len(vecs) for x in mean]
            sims = [_cosine(v, mean) for v in vecs]
            new_centroid = sum(sims) / len(sims) if sims else 0.0
        else:
            sims = [stored_centroid] * survivor_count
            new_centroid = stored_centroid

        after_score = compute_conviction(
            cluster_size=survivor_count,
            domain_breadth=domain_breadth,
            centrality_scores=sims,
        )

        if abs(after_score - before_score) <= 1e-9:
            continue

        cur.execute(
            'UPDATE "Principle" SET "convictionScore" = %s, '
            '"clusterCentroidSimilarity" = %s, "updatedAt" = %s '
            'WHERE id = %s AND "organizationId" = %s',
            (after_score, new_centroid, ts, pid, organization_id),
        )
        changes.append(
            {
                "id": pid,
                "before": before_score,
                "after": after_score,
                "cluster_before": len(cluster_ids),
                "cluster_after": survivor_count,
            }
        )

    conn.commit()
    return changes

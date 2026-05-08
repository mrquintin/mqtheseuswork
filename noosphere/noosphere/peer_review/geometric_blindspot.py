"""Geometric blindspot reviewer.

Where :mod:`noosphere.peer_review.blindspot` priors objections off the
firm's curated failure-mode catalogs, this reviewer uses the firm's
distinctive geometric capability — embedding-space contradiction
detection — to surface neighboring claims the conclusion's argument
fails to engage.

Algorithm:

1. Build the embedding-space neighborhood of the conclusion's core
   claim within radius ``r`` (and an upper-bound ``k``).
2. Drop claims the conclusion already cites as supports / evidence /
   dissent. Those are *engaged*; a blindspot is what the conclusion
   walks past without comment.
3. For each surviving neighbor, run the contradiction-direction probe.
   The probe scores Hoyer sparsity of the difference vector and the
   distance to the predicted contradiction location. Sparsity is the
   firm's primary contradiction signal (Quintin Hypothesis); the
   prediction-distance is the secondary geometric prior.
4. Rank by ``contradiction_score × cascade_weight`` of the unengaged
   claim's own basis — a structurally load-bearing nearby claim that
   the conclusion didn't cite is a more serious blindspot than a
   floating one.
5. Score severity through :mod:`noosphere.peer_review.severity` so the
   product feeds the same rubric the rest of the swarm uses; high
   product → high severity by construction.

The reviewer coexists with the prompt-driven :class:`BlindspotReviewer`.
Their outputs are *not* merged: each surfaces under its own reviewer
name so provenance survives downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

import numpy as np

from noosphere.methods import get_method, register_method
from noosphere.methods import contradiction_probe as _registered_contradiction_probe  # noqa: F401
from noosphere.methods.contradiction_probe import (
    ContradictionProbeInput,
)
from noosphere.models import Conclusion, Finding, MethodType, ReviewReport
from noosphere.peer_review import reviewers as _registry
from noosphere.peer_review.reviewer import BiasProfile, Reviewer
from noosphere.peer_review.severity import (
    SeverityInputs,
    score_objection as _score_severity,
)


# Defaults are tuned for cosine-distance embeddings: a 0.35 radius is
# the same envelope :mod:`noosphere.coherence.engine` uses for local
# coherence, so the blindspot detector sees the same neighborhood the
# coherence pass already considers in-domain.
DEFAULT_RADIUS = 0.35
DEFAULT_K = 32
DEFAULT_SPARSITY_FLOOR = 0.45
DEFAULT_MAX_FINDINGS = 8


# Severity label → Finding severity vocabulary, mirroring the swarm's
# `_LABEL_TO_FINDING_SEVERITY`. We keep our own copy rather than import
# to avoid a circular dependency with :mod:`peer_review.swarm`.
_LABEL_TO_FINDING = {"low": "minor", "medium": "major", "high": "blocker"}


def _clamp01(x: float) -> float:
    if x != x:
        return 0.0
    return max(0.0, min(1.0, float(x)))


@dataclass(frozen=True)
class GeometricBlindspot:
    """One unengaged neighbor surfaced by the geometric detector."""

    proposition_id: str
    sparsity: float
    cosine_similarity: float
    predicted_distance: float
    cascade_weight: float
    contradiction_score: float
    combined_score: float
    severity_value: float
    severity_label: str

    def evidence_lines(self) -> list[str]:
        return [
            f"unengaged_claim_id={self.proposition_id}",
            f"sparsity={self.sparsity:.4f}",
            f"cosine_similarity={self.cosine_similarity:.4f}",
            f"predicted_distance={self.predicted_distance:.4f}",
            f"cascade_weight={self.cascade_weight:.4f}",
            f"contradiction_score={self.contradiction_score:.4f}",
            f"combined_score={self.combined_score:.4f}",
            f"severity={self.severity_label}:{self.severity_value:.4f}",
        ]


def _engaged_ids(conclusion: Conclusion) -> set[str]:
    """The set of claim/principle ids the conclusion already cites.

    Anything in here is *engaged* — a citation, a piece of evidence, or
    an explicitly noted dissent. A blindspot is by definition outside
    this set.
    """

    engaged: set[str] = {conclusion.id}
    engaged.update(str(x) for x in conclusion.evidence_chain_claim_ids or ())
    engaged.update(str(x) for x in conclusion.supporting_principle_ids or ())
    engaged.update(str(x) for x in conclusion.claims_used or ())
    engaged.update(str(x) for x in conclusion.principles_used or ())
    engaged.update(str(x) for x in conclusion.dissent_claim_ids or ())
    return engaged


def _resolve_query_embedding(
    conclusion: Conclusion,
    locality: Any,
    context: dict[str, Any],
) -> Optional[np.ndarray]:
    """Recover the conclusion's embedding from the locality index.

    Falls back to ``context["query_embedding"]`` when the conclusion
    is not yet indexed (e.g. a freshly-synthesized conclusion that has
    not been persisted).
    """

    explicit = context.get("query_embedding")
    if explicit is not None:
        try:
            arr = np.asarray(explicit, dtype=float).reshape(-1)
            if arr.size:
                return arr
        except (TypeError, ValueError):
            pass

    if locality is None or not hasattr(locality, "vector_for"):
        return None
    vec = locality.vector_for(conclusion.id)
    if vec is None:
        return None
    return np.asarray(vec, dtype=float).reshape(-1)


def _contradiction_score(sparsity: float, predicted_distance: float) -> float:
    """Combine the two probe signals into a single contradiction score.

    Sparsity is the primary Quintin-Hypothesis signal (Hoyer sparsity
    of the difference vector). The probe also returns a distance to the
    predicted contradiction location; closer = more likely. We weight
    sparsity heavier because distance saturates quickly inside the
    cosine ball but the geometry signal keeps discriminating.
    """

    # Distance is in [0, 2] for cosine; clamp to [0, 1] before flipping
    # so the prior is monotonic and bounded.
    closeness = 1.0 - _clamp01(predicted_distance)
    return _clamp01(0.65 * _clamp01(sparsity) + 0.35 * closeness)


def _default_cascade_weight_lookup(
    context: dict[str, Any],
) -> Callable[[str], float]:
    """Build a cascade-weight resolver from the review context.

    Resolution order:

    1. ``context["cascade_weight_lookup"]`` if the caller wired one.
    2. ``context["cascade_weights"]`` mapping ``claim_id -> float``.
    3. Sum of incoming cascade-edge confidences via the store, when a
       ``store`` is present in the context.
    4. Fall back to ``0.5`` — a neutral prior so a missing cascade
       graph does not silently zero-out every blindspot's severity.
    """

    explicit = context.get("cascade_weight_lookup")
    if callable(explicit):
        return lambda pid: _clamp01(float(explicit(pid)))

    table = context.get("cascade_weights")
    if isinstance(table, dict):
        return lambda pid: _clamp01(float(table.get(pid, 0.5)))

    store = context.get("store")
    if store is not None and hasattr(store, "iter_cascade_edges"):
        from noosphere.models import CascadeEdgeRelation

        supportive = {
            CascadeEdgeRelation.SUPPORTS,
            CascadeEdgeRelation.EXTRACTED_FROM,
            CascadeEdgeRelation.AGGREGATES,
            CascadeEdgeRelation.DEPENDS_ON,
        }

        def _lookup(pid: str) -> float:
            try:
                edges = list(
                    store.iter_cascade_edges(dst=pid, include_retracted=False)
                )
            except Exception:
                return 0.5
            total = 0.0
            for edge in edges:
                if edge.relation in supportive:
                    total += float(getattr(edge, "confidence", 0.0))
            if total <= 0.0:
                return 0.5
            return _clamp01(total)

        return _lookup

    return lambda _pid: 0.5


def _default_centrality_lookup(
    context: dict[str, Any],
) -> Callable[[str], float]:
    explicit = context.get("claim_centrality_lookup")
    if callable(explicit):
        return lambda pid: _clamp01(float(explicit(pid)))
    table = context.get("claim_centralities")
    if isinstance(table, dict):
        return lambda pid: _clamp01(float(table.get(pid, 0.5)))
    return lambda _pid: 0.5


def detect_geometric_blindspots(
    conclusion: Conclusion,
    *,
    locality_index: Any,
    context: Optional[dict[str, Any]] = None,
    radius: float = DEFAULT_RADIUS,
    k: int = DEFAULT_K,
    sparsity_floor: float = DEFAULT_SPARSITY_FLOOR,
    max_findings: int = DEFAULT_MAX_FINDINGS,
) -> list[GeometricBlindspot]:
    """Run the geometric blindspot algorithm against ``conclusion``.

    Returns up to ``max_findings`` candidates, sorted by combined score
    descending. The reviewer wraps this; tests call it directly.
    """

    ctx = context or {}
    if locality_index is None:
        return []

    query = _resolve_query_embedding(conclusion, locality_index, ctx)
    if query is None or query.size == 0:
        return []

    engaged = _engaged_ids(conclusion)
    exemplar_pairs = ctx.get("contradiction_exemplar_pairs")

    _, contradiction_probe_method = get_method("contradiction_probe")
    probe_output = contradiction_probe_method(
        ContradictionProbeInput(
            embedding=query.tolist(),
            locality_index=locality_index,
            k=max(1, int(k)),
            radius=float(radius),
            exclude_ids=sorted(engaged),
            exemplar_pairs=exemplar_pairs,
        )
    )

    cascade_lookup = _default_cascade_weight_lookup(ctx)
    centrality_lookup = _default_centrality_lookup(ctx)
    centrality_for_conclusion = _clamp01(centrality_lookup(conclusion.id))

    blindspots: list[GeometricBlindspot] = []
    for cand in probe_output.candidates:
        sparsity = _clamp01(cand.sparsity)
        if sparsity < sparsity_floor:
            continue
        predicted_distance = _clamp01(cand.predicted_distance)
        contradiction_score = _contradiction_score(sparsity, predicted_distance)
        cw = _clamp01(cascade_lookup(cand.proposition_id))
        combined = _clamp01(contradiction_score * cw)

        sev = _score_severity(
            SeverityInputs(
                cascade_weight=cw,
                claim_centrality=centrality_for_conclusion,
                # The geometry signal is treated as a curated prior:
                # the firm has staked the QH benchmark on it being
                # informative, so it counts toward the structural
                # ceiling rather than just being a "judge" score.
                failure_mode_severity=contradiction_score,
                # The combined product is what the spec asks the
                # severity rubric to feed on. We pass it as the judge
                # estimate so the structural inputs above bracket it
                # — high product without structural support cannot
                # promote into the high bracket.
                judge_severity=combined,
            ),
            rationale=(
                f"geometric blindspot: cw={cw:.2f} × "
                f"contradiction={contradiction_score:.2f}"
            ),
        )

        blindspots.append(
            GeometricBlindspot(
                proposition_id=cand.proposition_id,
                sparsity=sparsity,
                cosine_similarity=float(cand.cosine_similarity),
                predicted_distance=predicted_distance,
                cascade_weight=cw,
                contradiction_score=contradiction_score,
                combined_score=combined,
                severity_value=float(sev.value),
                severity_label=str(sev.label),
            )
        )

    blindspots.sort(
        key=lambda b: (
            -b.combined_score,
            -b.severity_value,
            b.proposition_id,
        )
    )
    return blindspots[: max(0, int(max_findings))]


def _findings_from_blindspots(
    spots: Iterable[GeometricBlindspot],
) -> list[Finding]:
    findings: list[Finding] = []
    for spot in spots:
        finding_severity = _LABEL_TO_FINDING.get(spot.severity_label, "major")
        detail = (
            f"Embedding-space neighbor {spot.proposition_id} sits inside "
            f"the conclusion's predicted contradiction direction "
            f"(sparsity={spot.sparsity:.2f}, "
            f"predicted-distance={spot.predicted_distance:.2f}) and the "
            f"conclusion does not cite it as a support, evidence, or "
            f"dissenting claim."
        )
        findings.append(
            Finding(
                severity=finding_severity,
                category="geometric_blindspot",
                detail=detail,
                evidence=spot.evidence_lines(),
                suggested_action=(
                    "Engage the unengaged claim: cite it, refute it, or "
                    "explain why the conclusion's argument is "
                    "indifferent to it."
                ),
            )
        )
    return findings


def _verdict(findings: list[Finding]) -> dict[str, Any]:
    has_blocker = any(f.severity == "blocker" for f in findings)
    has_major = any(f.severity == "major" for f in findings)
    actionable = [f for f in findings if f.severity != "info"]
    return {
        "findings": [f.model_dump() for f in findings],
        "verdict": "reject"
        if has_blocker
        else "revise"
        if (has_major or actionable)
        else "accept",
        "confidence": max(0.5, 0.9 - 0.05 * len(actionable)),
    }


@register_method(
    name="review_geometric_blindspot",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema={"type": "object"},
    output_schema={"type": "object"},
    description=(
        "Geometric blindspot detector: surfaces embedding-space "
        "neighbors of a conclusion that score high on the contradiction "
        "direction but are not cited as supports, evidence, or dissent."
    ),
    rationale=(
        "Prompt-driven blindspot reviewers rediscover known failure "
        "modes by keyword. The geometric detector uses the firm's "
        "actual unique capability — Hoyer sparsity of difference "
        "vectors plus a learned contradiction direction — to surface "
        "structurally-engaged neighbors the argument walks past."
    ),
    owner="founder",
    nondeterministic=False,
)
def _execute(input_data: dict[str, Any]) -> dict[str, Any]:
    conclusion: Conclusion = input_data["conclusion"]
    context: dict[str, Any] = input_data.get("context", {})
    spots = detect_geometric_blindspots(
        conclusion,
        locality_index=context.get("locality_index"),
        context=context,
        radius=float(context.get("geometric_blindspot_radius", DEFAULT_RADIUS)),
        k=int(context.get("geometric_blindspot_k", DEFAULT_K)),
        sparsity_floor=float(
            context.get("geometric_blindspot_sparsity_floor", DEFAULT_SPARSITY_FLOOR)
        ),
        max_findings=int(
            context.get("geometric_blindspot_max_findings", DEFAULT_MAX_FINDINGS)
        ),
    )
    return _verdict(_findings_from_blindspots(spots))


class GeometricBlindspotReviewer(Reviewer):
    name = "geometric_blindspot"
    bias_profile = BiasProfile(
        name="geometric_blindspot",
        prior=(
            "Are there embedding-space neighbors of this conclusion "
            "that the contradiction direction puts inside its "
            "predicted-negation neighborhood, that the conclusion "
            "fails to engage as either support or dissent?"
        ),
        known_blindspots=[
            "Inherits the embedding model's bias: claims that the "
            "embedder collapses together cannot be separated by this "
            "detector, so a paraphrase-collision is invisible.",
            "Cascade weight is read from the locality-index's view of "
            "the cascade graph; if the unengaged claim has no recorded "
            "support edges yet, the prior falls back to neutral and "
            "the severity bracket caps mid-band.",
            "Detector only surfaces *embedding-space* unengagement; a "
            "logically critical claim that the embedder places far "
            "from the conclusion is invisible here and must be caught "
            "by the prompt-driven blindspot reviewer or human review.",
        ],
    )

    def review(
        self, conclusion: Conclusion, context: dict[str, Any]
    ) -> ReviewReport:
        result = _execute({"conclusion": conclusion, "context": context})
        findings = [Finding(**f) for f in result["findings"]]
        inv_ids = (
            [_execute.__method_spec__.method_id]
            if hasattr(_execute, "__method_spec__")
            else []
        )
        return ReviewReport(
            report_id=f"{self.name}-{conclusion.id}",
            reviewer=self.name,
            conclusion_id=conclusion.id,
            findings=findings,
            overall_verdict=result["verdict"],
            confidence=result["confidence"],
            completed_at=datetime.now(timezone.utc),
            method_invocation_ids=inv_ids,
        )


_registry.register(GeometricBlindspotReviewer)


__all__ = [
    "DEFAULT_K",
    "DEFAULT_MAX_FINDINGS",
    "DEFAULT_RADIUS",
    "DEFAULT_SPARSITY_FLOOR",
    "GeometricBlindspot",
    "GeometricBlindspotReviewer",
    "detect_geometric_blindspots",
]

"""Inverse inference engine: back-propagate from a resolved event to corpus claims."""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np

from noosphere.models import (
    BlindspotReport,
    CascadeEdgeRelation,
    CorpusSelector,
    Implication,
    InverseQuery,
    InverseResult,
    MethodType,
    TemporalCut,
)
from noosphere.methods import register_method
from noosphere.methods.nli_scorer import NLIInput, nli_scorer as _nli_scorer
from noosphere.evaluation.slicer import CorpusSlicer
from noosphere.inference.blindspot import compute_blindspot


def _softmax(scores: list[float]) -> list[float]:
    if not scores:
        return []
    max_s = max(scores)
    exps = [math.exp(s - max_s) for s in scores]
    total = sum(exps)
    if total == 0:
        return [0.0] * len(scores)
    return [e / total for e in exps]


def _cosine(a: list[float], b: list[float]) -> float:
    a_arr = np.asarray(a, dtype=np.float64)
    b_arr = np.asarray(b, dtype=np.float64)
    norm_a = float(np.linalg.norm(a_arr))
    norm_b = float(np.linalg.norm(b_arr))
    if norm_a < 1e-10 or norm_b < 1e-10:
        return 0.0
    return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))


def _severity(impact: float) -> str:
    if impact >= 0.7:
        return "severe"
    if impact >= 0.4:
        return "moderate"
    return "mild"


class InverseInferenceEngine:
    """Back-propagate a resolved event through the corpus to find
    supporting/refuting claims and blindspots."""

    def __init__(
        self,
        store: Any,
        embed_client: Any,
        llm_client: Any = None,
        nli_fn: Any = None,
    ) -> None:
        self._store = store
        self._embed = embed_client
        self._llm = llm_client
        self._nli = nli_fn or _nli_scorer

    def run(self, query: InverseQuery) -> InverseResult:
        cut = TemporalCut(
            cut_id=f"inverse-{query.event.event_id}",
            as_of=query.as_of,
            corpus_slice=CorpusSelector(as_of=query.as_of),
            embargoed=CorpusSelector(as_of=query.as_of),
            embedding_version_pin="default",
            outcomes=[],
        )
        slicer = CorpusSlicer(self._store, cut)

        claim_ids = slicer.list_claim_ids()
        claims = []
        for cid in claim_ids:
            claim = slicer.get_claim(cid)
            if claim is not None:
                claims.append(claim)

        if not claims:
            blindspot = compute_blindspot(
                event=query.event,
                sliced_store=slicer,
                embed_client=self._embed,
                llm_client=self._llm,
            )
            return InverseResult(
                supporting=[],
                refuted=[],
                irrelevant=[],
                blindspot=blindspot,
            )

        event_embedding = self._embed.encode([query.event.description])[0]

        scored: list[dict[str, Any]] = []
        for claim in claims:
            claim_emb = (
                claim.embedding
                if claim.embedding is not None
                else self._embed.encode([claim.text])[0]
            )

            nli_result = self._nli(NLIInput(
                premise=claim.text,
                hypothesis=query.event.description,
            ))

            cos_sim = _cosine(claim_emb, event_embedding)

            scored.append({
                "claim": claim,
                "entailment": nli_result.entailment,
                "contradiction": nli_result.contradiction,
                "cosine": cos_sim,
            })

        cosines = [s["cosine"] for s in scored]
        weights = _softmax(cosines)

        for i, s in enumerate(scored):
            s["relevance_weight"] = weights[i]
            s["impact"] = weights[i] * max(s["entailment"], s["contradiction"])

        scored.sort(key=lambda s: s["impact"], reverse=True)

        top_k = scored[: query.k]
        supporting: list[Implication] = []
        refuted: list[Implication] = []
        irrelevant: list[str] = []

        for s in top_k:
            impl = Implication(
                corpus_ref=s["claim"].id,
                entailment_score=s["entailment"],
                refutation_score=s["contradiction"],
                relevance_weight=s["relevance_weight"],
                severity=_severity(s["impact"]),
            )

            if s["entailment"] > s["contradiction"]:
                supporting.append(impl)
            elif s["contradiction"] > s["entailment"]:
                refuted.append(impl)
            else:
                irrelevant.append(s["claim"].id)

        blindspot = compute_blindspot(
            event=query.event,
            sliced_store=slicer,
            embed_client=self._embed,
            llm_client=self._llm,
        )

        return InverseResult(
            supporting=supporting,
            refuted=refuted,
            irrelevant=irrelevant,
            blindspot=blindspot,
        )


_engine_instance: Optional[InverseInferenceEngine] = None


def configure_engine(
    store: Any,
    embed_client: Any,
    llm_client: Any = None,
) -> None:
    global _engine_instance
    _engine_instance = InverseInferenceEngine(store, embed_client, llm_client)


@register_method(
    name="inverse_inference",
    version="1.0.0",
    method_type=MethodType.AGGREGATION,
    input_schema=InverseQuery,
    output_schema=InverseResult,
    description=(
        "Back-propagates from a resolved real-world event through the corpus "
        "to identify supporting and refuting claims with blindspot analysis."
    ),
    rationale=(
        "Uses NLI scoring, embedding cosine similarity, and temporal slicing "
        "to produce a structured inverse inference result."
    ),
    owner="founder",
    status="active",
    nondeterministic=True,
    emits_edges=[CascadeEdgeRelation.SUPPORTS, CascadeEdgeRelation.REFUTES],
)
def run_inverse(query: InverseQuery) -> InverseResult:
    if _engine_instance is None:
        raise RuntimeError(
            "InverseInferenceEngine not configured. "
            "Call inference.inverse.configure_engine() first."
        )
    return _engine_instance.run(query)

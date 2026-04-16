"""
Six-layer coherence aggregator: layers 1–5 + LLM judge, voting, overrides, payloads.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

from noosphere.coherence.argumentation import ArgumentationResult, evaluate_pair_with_neighbors
from noosphere.coherence.geometry import GeometryLayerResult, geometry_from_claims
from noosphere.coherence.information import InformationLayerResult, score_claim_information
from noosphere.coherence.judge import run_llm_judge
from noosphere.mitigations.coherence_judge_guard import judge_cited_scores_match_prior
from noosphere.coherence.nli import NLIScorer
from noosphere.coherence.probabilistic import ProbabilisticAudit, check_kolmogorov_for_pair
from noosphere.config import NoosphereSettings, get_settings
from noosphere.conclusions import ConclusionsRegistry, OpenQuestionCandidate
from noosphere.llm import LLMClient, llm_client_from_settings
from noosphere.models import (
    Claim,
    CoherenceEvaluationPayload,
    CoherenceVerdict,
    ReviewItem,
    SixLayerScore,
    LLMJudgeVerdictPacket,
)
from noosphere.observability import get_logger
from noosphere.store import Store

logger = get_logger(__name__)


@dataclass(frozen=True)
class CoherenceModelVersions:
    nli: str
    argumentation: str
    probabilistic: str
    geometry: str
    information: str
    judge: str

    @classmethod
    def from_settings(cls, s: Optional[NoosphereSettings] = None) -> CoherenceModelVersions:
        s = s or get_settings()
        return cls(
            nli=s.coherence_ver_nli,
            argumentation=s.coherence_ver_argumentation,
            probabilistic=s.coherence_ver_probabilistic,
            geometry=s.coherence_ver_geometry,
            information=s.coherence_ver_information,
            judge=s.coherence_ver_judge,
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "nli": self.nli,
                "argumentation": self.argumentation,
                "probabilistic": self.probabilistic,
                "geometry": self.geometry,
                "information": self.information,
                "judge": self.judge,
            },
            sort_keys=True,
        )


def pair_content_hash(a: Claim, b: Claim) -> str:
    blob = f"{a.id}|{a.text}|{b.id}|{b.text}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def evaluation_cache_key(
    claim_a_id: str, claim_b_id: str, versions_json: str, content_hash: str
) -> str:
    lo, hi = sorted([claim_a_id, claim_b_id])
    base = f"{lo}|{hi}|{versions_json}|{content_hash}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _verdict_argumentation(res: ArgumentationResult) -> CoherenceVerdict:
    if res.jointly_acceptable:
        return CoherenceVerdict.COHERE
    if res.attack_edges:
        return CoherenceVerdict.CONTRADICT
    return CoherenceVerdict.UNRESOLVED


def _verdict_probabilistic(audit: ProbabilisticAudit) -> CoherenceVerdict:
    if audit.violations:
        return CoherenceVerdict.CONTRADICT
    if audit.kolmogorov_ok:
        return CoherenceVerdict.COHERE
    return CoherenceVerdict.UNRESOLVED


def _verdict_from_geo(info: GeometryLayerResult) -> CoherenceVerdict:
    return info.verdict


def _verdict_from_info(info: InformationLayerResult) -> CoherenceVerdict:
    return info.verdict


def majority_of_six(verdicts: list[CoherenceVerdict]) -> CoherenceVerdict:
    ctab: dict[CoherenceVerdict, int] = {v: 0 for v in CoherenceVerdict}
    for v in verdicts:
        ctab[v] = ctab.get(v, 0) + 1
    if ctab[CoherenceVerdict.CONTRADICT] >= 4:
        return CoherenceVerdict.CONTRADICT
    if ctab[CoherenceVerdict.COHERE] >= 4:
        return CoherenceVerdict.COHERE
    return CoherenceVerdict.UNRESOLVED


def build_unresolved_reason(
    layer_names: list[str], verdicts: list[CoherenceVerdict]
) -> str:
    tally = "; ".join(f"{n}={v.value}" for n, v in zip(layer_names, verdicts))
    return (
        "Fewer than four of six layers agreed on cohere or contradict. "
        f"Layer tally: {tally}. Final stance left unresolved pending review."
    )


def strong_layer_disagreement(verdicts: list[CoherenceVerdict]) -> bool:
    return CoherenceVerdict.CONTRADICT in verdicts and CoherenceVerdict.COHERE in verdicts


@dataclass
class AggregationResult:
    payload: CoherenceEvaluationPayload
    judge_packet: Optional[LLMJudgeVerdictPacket]


class CoherenceAggregator:
    """
    Runs NLI, argumentation, probabilistic, geometry, information, LLM judge;
    aggregates with 4/6 voting; supports judge override with audit trail.
    """

    def __init__(
        self,
        *,
        llm: Optional[LLMClient] = None,
        nli: Optional[NLIScorer] = None,
        versions: Optional[CoherenceModelVersions] = None,
        skip_llm_judge: bool = False,
        skip_probabilistic_llm: bool = False,
    ) -> None:
        self.llm = llm or llm_client_from_settings()
        self._nli = nli or NLIScorer()
        self.versions = versions or CoherenceModelVersions.from_settings()
        self.skip_llm_judge = skip_llm_judge
        self.skip_probabilistic_llm = skip_probabilistic_llm

    def evaluate_pair(
        self,
        a: Claim,
        b: Claim,
        *,
        neighbors: Optional[list[Claim]] = None,
        neighbor_contra_scores: Optional[dict[tuple[str, str], float]] = None,
        conclusions_registry: Optional[ConclusionsRegistry] = None,
        store: Optional[Store] = None,
        on_override: Optional[Callable[[AggregationResult], None]] = None,
    ) -> AggregationResult:
        neighbors = neighbors or []
        neighbor_contra_scores = neighbor_contra_scores or {}

        _, partial_nli, v_nli = self._nli.score_claim_pair(a, b)
        s1 = float(partial_nli.s1_consistency)

        arg_res = evaluate_pair_with_neighbors(
            a, b, neighbors, neighbor_contra_scores
        )
        s2 = 1.0 if arg_res.jointly_acceptable else 0.35

        if self.skip_probabilistic_llm:
            prob = ProbabilisticAudit(
                kolmogorov_ok=True, violations=[], extracted={"a": {}, "b": {}}
            )
            s3 = 0.5
        else:
            try:
                prob = check_kolmogorov_for_pair(a, b, self.llm)
            except Exception as e:  # pragma: no cover
                logger.warning("probabilistic_layer_failed", error=str(e))
                prob = ProbabilisticAudit(
                    kolmogorov_ok=False,
                    violations=["layer_error"],
                    extracted={"a": {}, "b": {}},
                )
            s3 = 1.0 if prob.kolmogorov_ok and not prob.violations else 0.2

        geo = geometry_from_claims(a, b)
        s4 = geo.score

        info = score_claim_information(a, b)
        s5 = info.score

        lv_nli = v_nli
        lv_arg = _verdict_argumentation(arg_res)
        lv_prob = _verdict_probabilistic(prob)
        lv_geo = _verdict_from_geo(geo)
        lv_info = _verdict_from_info(info)

        prior = SixLayerScore(
            s1_consistency=s1,
            s2_argumentation=s2,
            s3_probabilistic=s3,
            s4_geometric=s4,
            s5_compression=s5,
            s6_llm_judge=0.0,
        )

        layer_names = ["nli", "argumentation", "probabilistic", "geometry", "information", "judge"]
        judge_pkt: Optional[LLMJudgeVerdictPacket] = None
        lv_judge = CoherenceVerdict.UNRESOLVED
        if self.skip_llm_judge:
            prior = SixLayerScore(
                s1_consistency=s1,
                s2_argumentation=s2,
                s3_probabilistic=s3,
                s4_geometric=s4,
                s5_compression=s5,
                s6_llm_judge=0.0,
            )
            lv_judge = CoherenceVerdict.UNRESOLVED
        else:
            try:
                judge_pkt = run_llm_judge(self.llm, a, b, prior)
                if judge_pkt is not None and not judge_cited_scores_match_prior(
                    judge_pkt, prior
                ):
                    logger.warning(
                        "llm_judge_rejected",
                        reason="cited_scores_mismatch_prior",
                        claim_pair=(a.id, b.id),
                    )
                    judge_pkt = None
            except Exception as e:  # pragma: no cover
                logger.warning("llm_judge_failed", error=str(e))
                judge_pkt = None
            if judge_pkt is not None:
                prior = SixLayerScore(
                    s1_consistency=s1,
                    s2_argumentation=s2,
                    s3_probabilistic=s3,
                    s4_geometric=s4,
                    s5_compression=s5,
                    s6_llm_judge=float(judge_pkt.confidence),
                )
                lv_judge = judge_pkt.verdict
            else:
                prior = SixLayerScore(
                    s1_consistency=s1,
                    s2_argumentation=s2,
                    s3_probabilistic=s3,
                    s4_geometric=s4,
                    s5_compression=s5,
                    s6_llm_judge=0.0,
                )
                lv_judge = CoherenceVerdict.UNRESOLVED

        layer_verdicts_list = [lv_nli, lv_arg, lv_prob, lv_geo, lv_info, lv_judge]
        agg = majority_of_six(layer_verdicts_list)

        final = agg
        judge_override = False
        judge_override_rationale = ""
        if judge_pkt is not None and judge_pkt.verdict != agg:
            if judge_pkt.explanation.strip():
                final = judge_pkt.verdict
                judge_override = True
                judge_override_rationale = judge_pkt.explanation.strip()
                logger.info(
                    "coherence_judge_override",
                    aggregator_verdict=agg.value,
                    judge_verdict=judge_pkt.verdict.value,
                    claim_pair=(a.id, b.id),
                )

        unresolved_reason = ""
        if final == CoherenceVerdict.UNRESOLVED:
            unresolved_reason = build_unresolved_reason(layer_names, layer_verdicts_list)

        cited_layers = (
            [x.layer for x in judge_pkt.cited_prior_scores] if judge_pkt else []
        )
        payload = CoherenceEvaluationPayload(
            final_verdict=final,
            aggregator_verdict=agg,
            prior_scores=prior,
            layer_verdicts={k: v.value for k, v in zip(layer_names, layer_verdicts_list)},
            confidence=float(judge_pkt.confidence) if judge_pkt else 0.0,
            explanation=judge_pkt.explanation if judge_pkt else "",
            unresolved_reason=unresolved_reason,
            judge_override=judge_override,
            judge_override_rationale=judge_override_rationale,
            judge_cited_layers=cited_layers,
        )
        result = AggregationResult(payload=payload, judge_packet=judge_pkt)
        if judge_override and on_override is not None:
            on_override(result)

        if (
            conclusions_registry is not None
            and final == CoherenceVerdict.UNRESOLVED
            and unresolved_reason
        ):
            summary = f"Unresolved coherence between claims {a.id} and {b.id}."
            oq = OpenQuestionCandidate(
                summary=summary,
                claim_a_id=a.id,
                claim_b_id=b.id,
                unresolved_reason=unresolved_reason,
                layer_disagreement_summary=tally_layer_disagreement(
                    layer_names, layer_verdicts_list
                ),
            )
            conclusions_registry.register_open_question(oq)

        if store is not None and strong_layer_disagreement(layer_verdicts_list):
            reason = "Strong cross-layer disagreement (cohere vs contradict present)."
            if lv_nli == CoherenceVerdict.CONTRADICT and lv_arg == CoherenceVerdict.COHERE:
                reason = (
                    "NLI indicates contradict while abstract argumentation treats the "
                    "pair as jointly acceptable — high-value review case."
                )
            ri = ReviewItem(
                claim_a_id=a.id,
                claim_b_id=b.id,
                reason=reason,
                layer_verdicts=payload.layer_verdicts,
                severity=0.85,
            )
            store.put_review_item(ri)

        return result


def tally_layer_disagreement(
    names: list[str], verdicts: list[CoherenceVerdict]
) -> str:
    return ", ".join(f"{n}={v.value}" for n, v in zip(names, verdicts))


def aggregate_claim_pair(
    a: Claim,
    b: Claim,
    *,
    aggregator: Optional[CoherenceAggregator] = None,
    **kwargs: Any,
) -> AggregationResult:
    """Thin API for `from noosphere.coherence import aggregate_claim_pair`."""
    ag = aggregator or CoherenceAggregator()
    return ag.evaluate_pair(a, b, **kwargs)

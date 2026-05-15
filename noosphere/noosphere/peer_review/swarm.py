from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from noosphere.models import Conclusion, Finding, ReviewReport, SwarmReport
from noosphere.peer_review.providers import (
    NLIScoreFn,
    ObjectionResult,
    ProviderAdapter,
    ProviderDisagreement,
    available_providers,
    detect_disagreements,
)
from noosphere.peer_review.reviewer import LLMProviderReviewer, Reviewer
from noosphere.peer_review.reviewers import all_reviewers
from noosphere.peer_review.severity import (
    ObjectionSeverity,
    SeverityAggregate,
    SeverityInputs,
    aggregate as aggregate_severity,
    score_objection as score_objection_severity,
)
from noosphere.store import Store

logger = logging.getLogger(__name__)


# ── Multi-provider result types ──────────────────────────────────────


@dataclass
class MultiProviderRun:
    """The full result of a single multi-provider swarm pass.

    Lives next to the existing :class:`SwarmReport` rather than
    replacing it: the legacy heuristic reviewers still produce
    :class:`ReviewReport` objects, while this aggregate captures the
    provider-rotation layer and the cross-provider disagreement
    signal.
    """

    conclusion_id: str
    objections: list[ObjectionResult]
    disagreements: list[ProviderDisagreement]
    total_cost_usd: float
    spent_providers: list[str]
    skipped_providers: list[str] = field(default_factory=list)
    monoculture: bool = False
    partial: bool = False
    partial_reason: Optional[str] = None
    weights: dict[str, float] = field(default_factory=dict)
    requires_human_escalation: bool = False
    severities: list[ObjectionSeverity] = field(default_factory=list)
    severity_aggregate: Optional[SeverityAggregate] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    # Pre-review agreement prediction + routing decision. Populated when
    # ``run_multi_provider`` is handed an agreement model; ``None`` when
    # it is not (the legacy path). The prediction is a *predictive aid*
    # — it never gates the run, it only (optionally) reshapes the
    # roster, and the founder can override it entirely.
    agreement_prediction: Optional[float] = None
    routing_decision: Optional[dict[str, Any]] = None


# Map severity labels onto the existing Finding severity vocabulary.
# The mapping is lossy by design: there is no "info" equivalent for a
# scored objection (info findings are reserved for provider errors).
# `high` lands at "blocker" so the existing `RebuttalRegistry`
# publication gate fires on a high-severity unresolved objection.
_LABEL_TO_FINDING_SEVERITY: dict[str, str] = {
    "low": "minor",
    "medium": "major",
    "high": "blocker",
}


def severity_inputs_from_context(
    conclusion: Conclusion, context: dict[str, Any]
) -> SeverityInputs:
    """Best-effort extraction of severity rubric inputs from the swarm context.

    The orchestrator's context is intentionally loose — callers may
    pass cascade weight / centrality / matched failure-mode severity
    when they have it (for example, the blindspot reviewer can stamp
    `matched_failure_severity`). Anything missing falls back to a
    neutral default that the rubric can still bracket.
    """

    severity_ctx = context.get("severity") or {}

    # Cascade weight: prefer an explicit value; fall back to the
    # conclusion's own confidence as a coarse upstream-support proxy.
    cascade_weight = float(
        severity_ctx.get("cascade_weight", conclusion.confidence or 0.5)
    )
    centrality = float(severity_ctx.get("claim_centrality", 0.5))
    fm_severity = float(severity_ctx.get("failure_mode_severity", 0.0))
    src_cred = severity_ctx.get("source_credibility")
    if src_cred is not None:
        src_cred = float(src_cred)
    judge = severity_ctx.get("judge_severity")
    if judge is not None:
        judge = float(judge)

    return SeverityInputs(
        cascade_weight=cascade_weight,
        claim_centrality=centrality,
        failure_mode_severity=fm_severity,
        source_credibility=src_cred,
        judge_severity=judge,
    )


# ── Orchestrator ─────────────────────────────────────────────────────


class SwarmOrchestrator:
    def __init__(self, store: Store) -> None:
        self._store = store

    def run(
        self,
        conclusion_id: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> SwarmReport:
        conclusion = self._store.get_conclusion(conclusion_id)
        if conclusion is None:
            raise ValueError(f"Conclusion {conclusion_id} not found")

        reviewers: list[Reviewer] = [cls() for cls in all_reviewers()]
        ctx = self._bootstrap_review_context(context)
        reports = self._run_reviews(reviewers, conclusion, ctx)

        for report in reports:
            self._store.insert_review_report(report)

        return SwarmReport(
            conclusion_id=conclusion_id,
            reviews=reports,
            rebuttals=[],
        )

    def run_multi_provider(
        self,
        conclusion_id: str,
        *,
        context: dict[str, Any] | None = None,
        adapters: Optional[list[ProviderAdapter]] = None,
        weights: Optional[dict[str, float]] = None,
        max_cost_usd: float = 1.0,
        max_tokens: int = 512,
        temperature: float = 0.2,
        seed: Optional[int] = None,
        nli_score: Optional[NLIScoreFn] = None,
        disagreement_threshold: float = 0.55,
        persist_findings: bool = True,
        agreement_model: Optional[Any] = None,
        routing_policy: Optional[Any] = None,
        apply_routing: bool = False,
        founder_override_full_swarm: bool = False,
        prompt_variant: str = "default",
        persist_prediction: bool = True,
    ) -> MultiProviderRun:
        """Rotate the swarm across architecturally distinct providers.

        Skips providers without an env-var key. Honours ``max_cost_usd``
        — if the budget runs out before every available provider has
        responded, the run is flagged ``partial`` so downstream
        consumers do not treat it as a complete swarm.

        Pre-review agreement prediction (optional). When ``agreement_model``
        is supplied (an :class:`~noosphere.peer_review.agreement_model.AgreementModel`),
        the swarm predicts how tightly the reviewers will agree on this
        conclusion *before* spending a token, and:

        * records the prediction + routing decision on the returned
          :class:`MultiProviderRun`,
        * persists a per-conclusion prediction artifact the review page
          reads to render its "expected contention" pill,
        * and, only when ``apply_routing`` is set **and** the caller did
          not pin ``adapters``, lets the routing policy reshape the
          roster — expanding it for a contested conclusion, shrinking it
          for a consensus one.

        The prediction is a *predictive aid, not a gate*: it never
        blocks a run, and ``founder_override_full_swarm=True`` keeps the
        full default swarm regardless of what the model predicted.
        """
        conclusion = self._store.get_conclusion(conclusion_id)
        if conclusion is None:
            raise ValueError(f"Conclusion {conclusion_id} not found")

        ctx = context or {}

        # Pre-review agreement prediction + routing decision.
        predicted_agreement: Optional[float] = None
        decision = None
        top_drivers: list[dict[str, Any]] = []
        if agreement_model is not None:
            predicted_agreement, decision, top_drivers = self._predict_and_route(
                conclusion,
                ctx,
                agreement_model=agreement_model,
                routing_policy=routing_policy,
                temperature=temperature,
                prompt_variant=prompt_variant,
                founder_override_full_swarm=founder_override_full_swarm,
            )
            if persist_prediction and decision is not None:
                self._persist_agreement_prediction(
                    conclusion_id,
                    agreement_model=agreement_model,
                    decision=decision,
                    top_drivers=top_drivers,
                )

        # The routing policy may reshape the roster — but only when the
        # caller asked for it and did not pin an explicit adapter list.
        # An explicit ``adapters`` argument always wins; routing is an
        # aid, not an override of the caller's intent.
        if apply_routing and adapters is None and decision is not None:
            wanted = set(decision.provider_mix)
            roster = [a for a in available_providers() if a.name in wanted]
        else:
            roster = adapters if adapters is not None else available_providers()
        roster = list(roster)

        if not roster:
            logger.warning(
                "Multi-provider swarm has no available providers; check "
                "API key environment variables."
            )
            return MultiProviderRun(
                conclusion_id=conclusion_id,
                objections=[],
                disagreements=[],
                total_cost_usd=0.0,
                spent_providers=[],
                skipped_providers=[],
                monoculture=False,
                partial=True,
                partial_reason="no_available_providers",
                weights=weights or {},
                requires_human_escalation=False,
                completed_at=datetime.now(timezone.utc),
                agreement_prediction=predicted_agreement,
                routing_decision=decision.to_dict() if decision else None,
            )

        if len(roster) == 1:
            warning_msg = (
                "monoculture review: only one provider available "
                f"({roster[0].name}); swarm diversity guarantees do not "
                "hold for this run."
            )
            logger.warning(
                warning_msg,
            )
            logging.getLogger().warning(warning_msg)

        # Provider order: highest weight first, ties broken by the
        # roster's insertion order so callers can pin order without
        # specifying every weight.
        w = weights or {}
        roster.sort(key=lambda a: -w.get(a.name, 1.0))

        objections: list[ObjectionResult] = []
        spent: list[str] = []
        skipped: list[str] = []
        total_cost = 0.0
        partial = False
        partial_reason: Optional[str] = None

        reviewers = [
            LLMProviderReviewer(
                adapter=a,
                max_tokens=max_tokens,
                temperature=temperature,
                seed=seed,
            )
            for a in roster
        ]

        for reviewer in reviewers:
            if total_cost >= max_cost_usd:
                skipped.append(reviewer.adapter.name)
                partial = True
                partial_reason = "budget_exhausted"
                logger.warning(
                    "swarm budget %.4f exhausted; skipping %s",
                    max_cost_usd,
                    reviewer.adapter.name,
                )
                continue
            result = reviewer.produce_objection(conclusion, ctx)
            objections.append(result)
            if result.ok:
                spent.append(reviewer.adapter.name)
                total_cost += result.cost_usd
                if total_cost > max_cost_usd:
                    partial = True
                    partial_reason = "budget_overrun"
            else:
                # Provider failures still count as spent attempts but
                # do not consume budget; we mark partial so downstream
                # treats the run as incomplete.
                partial = True
                if partial_reason is None:
                    partial_reason = "provider_error"

        disagreements = detect_disagreements(
            objections,
            threshold=disagreement_threshold,
            nli_score=nli_score,
        )

        # Severity-score every successful objection. The rubric inputs
        # come from `context["severity"]` if the caller populated them
        # (cascade weight, claim centrality, matched failure-mode
        # severity, source credibility, judge estimate); otherwise the
        # rubric falls back to neutral defaults and the structural
        # ceiling alone defines the score.
        severities: list[ObjectionSeverity] = []
        sev_inputs = severity_inputs_from_context(conclusion, ctx)
        for o in objections:
            if not o.ok:
                continue
            sev = score_objection_severity(sev_inputs)
            severities.append(sev)
            o.extra["severity"] = sev.to_dict()

        sev_agg = aggregate_severity(severities)

        run = MultiProviderRun(
            conclusion_id=conclusion_id,
            objections=objections,
            disagreements=disagreements,
            total_cost_usd=total_cost,
            spent_providers=spent,
            skipped_providers=skipped,
            monoculture=len(roster) == 1,
            partial=partial,
            partial_reason=partial_reason,
            weights={a.name: w.get(a.name, 1.0) for a in roster},
            requires_human_escalation=bool(disagreements)
            or sev_agg.response_required_high,
            severities=severities,
            severity_aggregate=sev_agg,
            completed_at=datetime.now(timezone.utc),
            agreement_prediction=predicted_agreement,
            routing_decision=decision.to_dict() if decision else None,
        )

        if persist_findings:
            for report in self._objections_as_reports(conclusion, run):
                try:
                    self._store.insert_review_report(report)
                except Exception:  # pragma: no cover - store-specific
                    logger.exception(
                        "failed to persist multi-provider review for %s",
                        report.reviewer,
                    )

        return run

    # ── helpers ──────────────────────────────────────────────────────

    def _bootstrap_review_context(
        self, context: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Inject the heavy collaborators reviewers need into the context.

        ``store`` and ``locality_index`` are not part of the public
        review API — but the geometric blindspot reviewer needs both
        to do its job. Rather than make every caller wire them in by
        hand, the orchestrator fills them when missing so legacy
        callers keep working unchanged.
        """

        ctx: dict[str, Any] = dict(context or {})
        ctx.setdefault("store", self._store)
        if "locality_index" not in ctx:
            try:
                from noosphere.coherence.locality import DomainLocalityIndex

                ctx["locality_index"] = DomainLocalityIndex(
                    store=self._store, autosave=False
                )
            except Exception:  # pragma: no cover - defensive
                logger.exception(
                    "failed to bootstrap DomainLocalityIndex; geometric "
                    "blindspot reviewer will return no findings"
                )
        return ctx

    def _predict_and_route(
        self,
        conclusion: Conclusion,
        ctx: dict[str, Any],
        *,
        agreement_model: Any,
        routing_policy: Optional[Any],
        temperature: float,
        prompt_variant: str,
        founder_override_full_swarm: bool,
    ) -> tuple[float, Any, list[dict[str, Any]]]:
        """Predict pre-review agreement and derive a routing decision.

        Builds the pre-review feature row from the conclusion (text,
        reasoning, domain, confidence) and its structural severity
        inputs — every input here is knowable before a provider is
        called — then runs it through the agreement model and the
        routing policy. The feature row's ``provider_mix`` is the
        policy's *base* mix: the prediction answers "how will the
        default swarm do on this conclusion?", and routing decides
        whether to deviate from that default.
        """

        from noosphere.peer_review.agreement_features import (
            FeatureInputs,
            feature_dict,
        )
        from noosphere.peer_review.swarm_router import default_policy, route

        policy = routing_policy or default_policy()
        domain = (
            getattr(conclusion, "domain", None)
            or ctx.get("domain")
            or "unspecified"
        )
        sev_inputs = severity_inputs_from_context(conclusion, ctx)
        fi = FeatureInputs(
            conclusion_id=conclusion.id,
            config_id="pre-review",
            conclusion_text=conclusion.text or "",
            reasoning=getattr(conclusion, "reasoning", "") or "",
            domain=str(domain),
            confidence=float(getattr(conclusion, "confidence", 0.5) or 0.5),
            severity_inputs=sev_inputs,
            provider_mix=tuple(policy.base_mix),
            temperature=float(temperature),
            prompt_variant=str(prompt_variant),
        )
        predicted = float(agreement_model.predict_inputs(fi))
        decision = route(
            predicted,
            policy,
            founder_override_full_swarm=founder_override_full_swarm,
        )
        try:
            drivers = agreement_model.top_drivers(feature_dict(fi), k=4)
        except Exception:  # pragma: no cover - explainability is best-effort
            drivers = []
        return predicted, decision, drivers

    def _persist_agreement_prediction(
        self,
        conclusion_id: str,
        *,
        agreement_model: Any,
        decision: Any,
        top_drivers: list[dict[str, Any]],
    ) -> None:
        """Write the per-conclusion prediction artifact the review page reads.

        Best-effort: a failed artifact write must never fail the swarm
        run. The review page degrades gracefully when the file is
        absent (no pill rather than an error).
        """

        try:
            from noosphere.config import get_settings
            from noosphere.peer_review.swarm_router import prediction_record

            record = prediction_record(
                conclusion_id=conclusion_id,
                decision=decision,
                model_trained_at=getattr(agreement_model, "trained_at", ""),
                top_drivers=top_drivers,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )
            base = (
                get_settings().data_dir / "agreement_model" / "predictions"
            )
            base.mkdir(parents=True, exist_ok=True)
            out = base / f"{conclusion_id}.json"
            with out.open("w", encoding="utf-8") as fh:
                json.dump(record, fh, indent=2, sort_keys=True)
        except Exception:  # pragma: no cover - artifact write is best-effort
            logger.exception(
                "failed to persist agreement prediction for %s", conclusion_id
            )

    def _run_reviews(
        self,
        reviewers: list[Reviewer],
        conclusion: Conclusion,
        context: dict[str, Any],
    ) -> list[ReviewReport]:
        reports: list[ReviewReport] = []
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(r.review, conclusion, context): r
                for r in reviewers
            }
            for future in as_completed(futures):
                reviewer = futures[future]
                try:
                    reports.append(future.result())
                except Exception:
                    logger.exception("Reviewer %s failed", reviewer.name)
        return reports

    @staticmethod
    def _objections_as_reports(
        conclusion: Conclusion, run: MultiProviderRun
    ) -> list[ReviewReport]:
        """Convert provider objections to legacy :class:`ReviewReport`.

        We persist them in the same table the existing reviewers write
        to so the operator UI can keep using one query path. The
        ``evidence`` field carries provider/model/cost so the page can
        group by provider and show the diverge badge without a schema
        change.
        """
        reports: list[ReviewReport] = []
        # Quick lookup: for each provider, the set of providers it
        # disagrees with according to NLI. Surfaced in evidence so the
        # operator UI can render a diverge badge.
        disagrees_with: dict[str, set[str]] = {}
        for d in run.disagreements:
            disagrees_with.setdefault(d.provider_a, set()).add(d.provider_b)
            disagrees_with.setdefault(d.provider_b, set()).add(d.provider_a)

        for o in run.objections:
            evidence = [
                f"provider={o.provider}",
                f"model={o.model}",
                f"cost_usd={o.cost_usd:.6f}",
                f"latency_ms={o.latency_ms:.1f}",
                f"tokens_in={o.tokens_in}",
                f"tokens_out={o.tokens_out}",
            ]
            if run.partial:
                evidence.append(
                    f"swarm_partial={run.partial_reason or 'true'}"
                )
            if run.monoculture:
                evidence.append("swarm_monoculture=true")
            divergent = sorted(disagrees_with.get(o.provider, set()))
            if divergent:
                evidence.append("disagrees_with=" + ",".join(divergent))

            if o.ok:
                sev_blob = o.extra.get("severity") if o.extra else None
                if sev_blob:
                    label = str(sev_blob.get("label", "medium"))
                    finding_severity = _LABEL_TO_FINDING_SEVERITY.get(
                        label, "major"
                    )
                    evidence.append(
                        f"severity={label}:{sev_blob.get('value', 0.0):.4f}"
                    )
                    if sev_blob.get("judge_capped"):
                        evidence.append("severity_judge_capped=true")
                    if sev_blob.get("stale"):
                        evidence.append("severity_stale=true")
                else:
                    finding_severity = "major"
                finding = Finding(
                    severity=finding_severity,
                    category="adversarial_objection",
                    detail=o.text,
                    evidence=evidence,
                    suggested_action=(
                        "Address the objection in a rebuttal or revise "
                        "the methodology."
                    ),
                )
                verdict = "revise" if finding_severity != "blocker" else "reject"
                confidence = 0.7
            else:
                finding = Finding(
                    severity="info",
                    category="provider_error",
                    detail=(
                        f"Provider {o.provider} produced no objection: "
                        f"{o.error or 'empty response'}"
                    ),
                    evidence=evidence,
                    suggested_action=(
                        "Re-run when the provider is reachable; treat "
                        "this swarm as partial."
                    ),
                )
                verdict = "accept"
                confidence = 0.5

            reports.append(
                ReviewReport(
                    report_id=f"provider:{o.provider}-{conclusion.id}",
                    reviewer=f"provider:{o.provider}",
                    conclusion_id=conclusion.id,
                    findings=[finding],
                    overall_verdict=verdict,
                    confidence=confidence,
                    completed_at=datetime.now(timezone.utc),
                    method_invocation_ids=[],
                )
            )
        return reports

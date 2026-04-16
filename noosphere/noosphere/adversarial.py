"""
Adversarial coherence — generate strongest objections, formalize as claims,
run six-layer coherence vs evidence / conclusion anchor, persist verdicts,
and gate firm-tier promotion via Severity when enforcement is enabled.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from noosphere.coherence.aggregator import CoherenceAggregator
from noosphere.config import NoosphereSettings, get_settings
from noosphere.models import (
    AdversarialChallenge,
    AdversarialChallengeStatus,
    AdversarialGeneratorBundle,
    AdversarialObjectionDraft,
    Claim,
    ClaimOrigin,
    ClaimType,
    CoherenceEvaluationPayload,
    CoherenceVerdict,
    Conclusion,
    ConfidenceTier,
    EngagementPointer,
    HumanAdversarialOverride,
    Speaker,
)
from noosphere.observability import get_logger
from noosphere.store import Store

logger = get_logger(__name__)

FALLEN_CONFIDENCE_THRESHOLD = 0.65


def cluster_fingerprint(principle_id: str, evidence_claim_ids: list[str]) -> str:
    """Stable id for a principle + evidence chain (pre-conclusion)."""
    joined = "|".join([principle_id] + sorted(evidence_claim_ids))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def generator_content_hash(
    conclusion_text: str, evidence_claim_ids: list[str], tradition: str
) -> str:
    blob = f"{conclusion_text}\n{sorted(evidence_claim_ids)}\n{tradition}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def retrieve_prior_engagement(
    store: Store,
    conclusion_text: str,
    evidence_claim_ids: list[str],
    *,
    scan_limit: int = 400,
) -> list[EngagementPointer]:
    """
    Lightweight retrieval: scan recent claim texts for lexical overlap with the conclusion.
    Distinguishes novelty vs possible prior engagement (RAG placeholder).
    """
    needles = {w for w in conclusion_text.lower().split() if len(w) > 5}
    if not needles:
        return []
    out: list[EngagementPointer] = []
    seen: set[str] = set()
    for cid in store.list_claim_ids()[:scan_limit]:
        if cid in evidence_claim_ids:
            continue
        c = store.get_claim(cid)
        if c is None or c.claim_origin in (
            ClaimOrigin.ADVERSARIAL,
            ClaimOrigin.VOICE,
            ClaimOrigin.LITERATURE,
        ):
            continue
        tl = c.text.lower()
        hits = [n for n in needles if n in tl]
        if len(hits) >= 2 and cid not in seen:
            seen.add(cid)
            out.append(
                EngagementPointer(
                    claim_id=c.id,
                    artifact_uri="",
                    excerpt=c.text[:240],
                    relevance_note=f"Overlapping terms: {', '.join(hits[:5])}",
                )
            )
        if len(out) >= 12:
            break
    return out


def _generator_schema_json() -> str:
    return AdversarialGeneratorBundle.model_json_schema()


def build_generator_prompt(
    conclusion: Conclusion,
    evidence_texts: list[str],
    prior: list[EngagementPointer],
    *,
    voice_context: str = "",
) -> tuple[str, str]:
    system = (
        "You are an ideologically neutral epistemic adversary. "
        "Return JSON only matching the provided JSON Schema. "
        "Produce exactly three objections from three distinct intellectual traditions. "
        "Each objection must include atomic_claims (non-empty). "
        "Flag citation_style per objection as cited|synthesized|mixed. "
        "Set is_novel_vs_archive to false only if the firm likely already engaged this line "
        "(see prior_engagement summaries)."
    )
    user_obj: dict[str, Any] = {
        "json_schema": _generator_schema_json(),
        "conclusion": conclusion.text,
        "evidence_samples": evidence_texts[:24],
        "prior_engagement": [p.model_dump() for p in prior],
        "tradition_hints_empirical": [
            "methodological critique",
            "theory-laden / underdetermination critique",
            "base-rate / reference-class critique",
        ],
        "tradition_hints_normative": [
            "deontological tension",
            "consequentialist tradeoff",
            "institutional-design feasibility critique",
        ],
    }
    if voice_context:
        user_obj["tracked_voice_positions"] = voice_context
        user_obj["instruction_voice_bias"] = (
            "When tracked_voice_positions is present, prefer paraphrasing or quoting those "
            "ingested positions for at least 40% of objection substance before inventing synthetic critiques; "
            "still label citation_style accurately (cited vs synthesized)."
        )
    user = json.dumps(user_obj, indent=2)
    return system, user


def parse_generator_bundle(raw: str, *, max_retries: int = 3) -> AdversarialGeneratorBundle:
    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        m = re.search(r"\{[\s\S]*\}", raw, re.DOTALL)
        if not m:
            last_err = ValueError("no_json_object")
            continue
        try:
            return AdversarialGeneratorBundle.model_validate_json(m.group(0))
        except Exception as e:
            last_err = e
            logger.warning("adversarial_bundle_parse_retry", attempt=attempt, error=str(e))
    raise ValueError(f"Adversarial generator JSON invalid after retries: {last_err}")


def generate_objections_with_llm(
    llm: Any,
    conclusion: Conclusion,
    evidence_texts: list[str],
    prior: list[EngagementPointer],
    *,
    voice_context: str = "",
) -> AdversarialGeneratorBundle:
    system, user = build_generator_prompt(
        conclusion, evidence_texts, prior, voice_context=voice_context
    )
    raw = llm.complete(system=system, user=user, max_tokens=6000, temperature=0.35)
    return parse_generator_bundle(raw)


def _critic_speaker() -> Speaker:
    return Speaker(name="adversarial_critic", role="system")


def formalize_objection_to_claims(
    store: Store,
    draft: AdversarialObjectionDraft,
    challenge_id: str,
) -> list[str]:
    """Turn objection atomic strings into persisted claims tagged adversarial."""
    spk = _critic_speaker()
    when = date.today()
    epi = f"adversarial:{challenge_id}"
    ids: list[str] = []
    for i, line in enumerate(draft.atomic_claims):
        t = line.strip()
        if not t:
            continue
        cid = f"adv_{challenge_id}_{i}_{uuid.uuid4().hex[:8]}"
        cl = Claim(
            id=cid,
            text=t,
            speaker=spk,
            episode_id=epi,
            episode_date=when,
            claim_type=ClaimType.METHODOLOGICAL,
            claim_origin=ClaimOrigin.ADVERSARIAL,
            segment_context=draft.objection_text[:500],
        )
        store.put_claim(cl)
        ids.append(cid)
    return ids


def _conclusion_anchor_claim(conclusion: Conclusion) -> Claim:
    return Claim(
        id=f"_adv_anchor_{conclusion.id}",
        text=conclusion.text,
        speaker=Speaker(name="firm_conclusion_anchor", role="system"),
        episode_id="adversarial_anchor",
        episode_date=date.today(),
        claim_type=ClaimType.METHODOLOGICAL,
        claim_origin=ClaimOrigin.SYSTEM,
    )


def evaluate_challenge_coherence(
    store: Store,
    aggregator: CoherenceAggregator,
    conclusion: Conclusion,
    challenge: AdversarialChallenge,
    adversarial_claim_ids: list[str],
) -> AdversarialChallenge:
    anchor = _conclusion_anchor_claim(conclusion)
    rank = {
        CoherenceVerdict.COHERE: 0,
        CoherenceVerdict.UNRESOLVED: 1,
        CoherenceVerdict.CONTRADICT: 2,
    }
    worst_rank = -1
    worst_payload: Optional[CoherenceEvaluationPayload] = None

    for cid in adversarial_claim_ids:
        ac = store.get_claim(cid)
        if ac is None:
            continue
        res = aggregator.evaluate_pair(ac, anchor, store=store)
        p = res.payload
        fv = p.final_verdict
        rnk = rank.get(fv, 1)
        if rnk > worst_rank:
            worst_rank = rnk
            worst_payload = p

    if worst_payload is None:
        ch = challenge.model_copy(
            update={
                "status": AdversarialChallengeStatus.EVALUATED,
                "six_layer_json": "{}",
                "final_verdict": CoherenceVerdict.UNRESOLVED.value,
                "confidence": 0.0,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        return ch

    judge_overturn = bool(
        worst_payload.judge_override and bool(worst_payload.judge_override_rationale)
    )
    ch = challenge.model_copy(
        update={
            "status": AdversarialChallengeStatus.EVALUATED,
            "six_layer_json": worst_payload.model_dump_json(),
            "final_verdict": (
                worst_payload.final_verdict.value
                if isinstance(worst_payload.final_verdict, CoherenceVerdict)
                else str(worst_payload.final_verdict)
            ),
            "confidence": float(worst_payload.confidence),
            "judge_overturned_contradict": judge_overturn,
            "updated_at": datetime.now(timezone.utc),
        }
    )
    return finalize_survival_status(ch)


def finalize_survival_status(ch: AdversarialChallenge) -> AdversarialChallenge:
    if ch.human_override and ch.human_override.kind == "addressed":
        return ch.model_copy(
            update={"status": AdversarialChallengeStatus.ADDRESSED, "updated_at": datetime.now(timezone.utc)}
        )
    if ch.human_override and ch.human_override.kind == "fatal":
        return ch.model_copy(
            update={"status": AdversarialChallengeStatus.FATAL, "updated_at": datetime.now(timezone.utc)}
        )

    fv = ch.final_verdict
    conf = ch.confidence
    if not fv or fv == CoherenceVerdict.UNRESOLVED.value:
        return ch.model_copy(
            update={"status": AdversarialChallengeStatus.SURVIVED, "updated_at": datetime.now(timezone.utc)}
        )
    if fv == CoherenceVerdict.CONTRADICT.value and conf >= FALLEN_CONFIDENCE_THRESHOLD and not ch.judge_overturned_contradict:
        return ch.model_copy(
            update={"status": AdversarialChallengeStatus.FALLEN, "updated_at": datetime.now(timezone.utc)}
        )
    return ch.model_copy(
        update={"status": AdversarialChallengeStatus.SURVIVED, "updated_at": datetime.now(timezone.utc)}
    )


def demote_conclusion_tier(con: Conclusion) -> Conclusion:
    if con.confidence_tier == ConfidenceTier.FIRM:
        return con.model_copy(
            update={
                "confidence_tier": ConfidenceTier.FOUNDER,
                "rationale": (con.rationale + " | adversarial_demotion:firm_to_founder").strip("| "),
            }
        )
    if con.confidence_tier == ConfidenceTier.FOUNDER:
        return con.model_copy(
            update={
                "confidence_tier": ConfidenceTier.OPEN,
                "rationale": (con.rationale + " | adversarial_demotion:founder_to_open").strip("| "),
            }
        )
    return con


def apply_challenge_to_conclusion_demotion(
    store: Store,
    conclusion_id: str,
    settings: Optional[NoosphereSettings] = None,
) -> bool:
    """If any evaluated challenge is fallen, demote conclusion (unless shadow mode)."""
    s = settings or get_settings()
    if s.adversarial_shadow:
        return False
    chs = store.list_adversarial_challenges_for_conclusion(conclusion_id)
    if not any(c.status == AdversarialChallengeStatus.FALLEN for c in chs):
        return False
    con = store.get_conclusion(conclusion_id)
    if con is None:
        return False
    store.put_conclusion(demote_conclusion_tier(con))
    logger.info("adversarial_demoted_conclusion", conclusion_id=conclusion_id)
    return True


def adversarial_severity_criterion(store: Store, fingerprint: str, k: int) -> tuple[float, str]:
    """
    Returns (score 0..1, reasoning) for meta-analysis Severity slot.
    1.0 only when top-K engaged challenges all survived or were human-addressed.
    """
    ok, reason = fingerprint_engaged_and_survived(store, fingerprint, k)
    if ok:
        return 0.78, reason
    return 0.35, reason


def fingerprint_engaged_and_survived(store: Store, fingerprint: str, k: int) -> tuple[bool, str]:
    rows = store.list_adversarial_challenges_for_fingerprint(fingerprint)
    evaluated = [r for r in rows if r.status != AdversarialChallengeStatus.PENDING]
    if len(evaluated) < k:
        return False, f"Adversarial: only {len(evaluated)}/{k} challenges engaged for fingerprint."
    evaluated.sort(key=lambda x: x.created_at)
    top = evaluated[:k]
    for c in top:
        if c.status in (AdversarialChallengeStatus.FALLEN, AdversarialChallengeStatus.FATAL):
            return False, f"Adversarial: challenge {c.id} status={c.status.value}."
    return True, f"Adversarial: top-{k} challenges survived or addressed ({fingerprint[:10]}…)."


def persist_challenge_bundle(
    store: Store,
    conclusion: Conclusion,
    fingerprint: str,
    bundle: AdversarialGeneratorBundle,
    *,
    traditions_depth: int = 3,
) -> list[AdversarialChallenge]:
    prior = retrieve_prior_engagement(store, conclusion.text, conclusion.evidence_chain_claim_ids)
    stale_after = datetime.now(timezone.utc) + timedelta(days=get_settings().adversarial_stale_days)
    saved: list[AdversarialChallenge] = []
    for draft in bundle.objections[:traditions_depth]:
        ch_id = str(uuid.uuid4())
        h = generator_content_hash(conclusion.text, conclusion.evidence_chain_claim_ids, draft.tradition)
        cached = store.find_adversarial_challenge_by_content_hash(h)
        if cached is not None and cached.conclusion_id == conclusion.id:
            saved.append(cached)
            continue

        atomic_ids = formalize_objection_to_claims(store, draft, ch_id)
        ch = AdversarialChallenge(
            id=ch_id,
            conclusion_id=conclusion.id,
            cluster_fingerprint=fingerprint,
            content_hash=h,
            tradition=draft.tradition,
            primary_attack_vector=draft.primary_attack_vector,
            objection_text=draft.objection_text,
            cited_thinkers=list(draft.cited_thinkers),
            citation_style=draft.citation_style,
            atomic_claim_ids=atomic_ids,
            prior_engagement=prior,
            status=AdversarialChallengeStatus.PENDING,
            stale_after=stale_after,
        )
        store.put_adversarial_challenge(ch)
        saved.append(ch)
    return saved


def run_evaluation_for_challenges(
    store: Store,
    conclusion: Conclusion,
    challenges: list[AdversarialChallenge],
    aggregator: CoherenceAggregator,
) -> list[AdversarialChallenge]:
    out: list[AdversarialChallenge] = []
    for ch in challenges:
        updated = evaluate_challenge_coherence(
            store, aggregator, conclusion, ch, ch.atomic_claim_ids
        )
        store.put_adversarial_challenge(updated)
        out.append(updated)
    apply_challenge_to_conclusion_demotion(store, conclusion.id)
    return out


def apply_human_override(
    store: Store,
    challenge_id: str,
    override: HumanAdversarialOverride,
) -> AdversarialChallenge:
    ch = store.get_adversarial_challenge(challenge_id)
    if ch is None:
        raise ValueError(f"Unknown adversarial challenge {challenge_id}")
    ch = ch.model_copy(
        update={
            "human_override": override,
            "updated_at": datetime.now(timezone.utc),
        }
    )
    ch = finalize_survival_status(ch)
    store.put_adversarial_challenge(ch)
    if override.kind == "fatal" and ch.conclusion_id:
        con = store.get_conclusion(ch.conclusion_id)
        if con is not None:
            store.put_conclusion(
                con.model_copy(
                    update={
                        "confidence_tier": ConfidenceTier.OPEN,
                        "rationale": (con.rationale + " | adversarial_human_fatal").strip(),
                    }
                )
            )
    return ch


def run_adversarial_cycle_for_conclusion(
    store: Store,
    conclusion_id: str,
    *,
    llm: Any,
    aggregator: Optional[CoherenceAggregator] = None,
    settings: Optional[NoosphereSettings] = None,
    depth: int = 3,
) -> list[AdversarialChallenge]:
    s = settings or get_settings()
    con = store.get_conclusion(conclusion_id)
    if con is None:
        raise ValueError(f"Unknown conclusion {conclusion_id}")
    texts: list[str] = []
    for cid in con.evidence_chain_claim_ids:
        c = store.get_claim(cid)
        if c:
            texts.append(c.text)
    fp = cluster_fingerprint(
        con.supporting_principle_ids[0] if con.supporting_principle_ids else "none",
        list(con.evidence_chain_claim_ids),
    )
    from noosphere.voices import build_voice_context_for_adversarial

    vctx = build_voice_context_for_adversarial(store, con.text)
    bundle = generate_objections_with_llm(
        llm,
        con,
        texts,
        retrieve_prior_engagement(store, con.text, con.evidence_chain_claim_ids),
        voice_context=vctx,
    )
    challenges = persist_challenge_bundle(store, con, fp, bundle, traditions_depth=depth)
    has_llm = bool(s.effective_llm_api_key())
    agg = aggregator or CoherenceAggregator(
        skip_llm_judge=not has_llm,
        skip_probabilistic_llm=not has_llm,
    )
    return run_evaluation_for_challenges(store, con, challenges, agg)


def link_fingerprint_to_conclusion(store: Store, fingerprint: str, conclusion_id: str) -> None:
    store.link_adversarial_fingerprint_to_conclusion(fingerprint, conclusion_id)

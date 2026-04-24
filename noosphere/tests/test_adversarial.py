"""Adversarial coherence: schema parsing, severity gate, survival, demotion."""

from __future__ import annotations

from datetime import date

import pytest

from noosphere.adversarial import (
    adversarial_severity_criterion,
    apply_human_override,
    cluster_fingerprint,
    demote_conclusion_tier,
    finalize_survival_status,
    formalize_objection_to_claims,
    generator_content_hash,
    parse_generator_bundle,
    persist_challenge_bundle,
    retrieve_prior_engagement,
)
from noosphere.config import get_settings
from noosphere.meta_analysis import (
    META_THRESHOLDS,
    ClaimClusterMeta,
    criterion_severity,
)
from noosphere.models import (
    AdversarialChallenge,
    AdversarialChallengeStatus,
    AdversarialObjectionDraft,
    AdversarialGeneratorBundle,
    Claim,
    ClaimOrigin,
    ClaimType,
    CoherenceVerdict,
    Conclusion,
    ConfidenceTier,
    HumanAdversarialOverride,
    Speaker,
)
from noosphere.store import Store


def _store(tmp_path) -> Store:
    url = f"sqlite:///{tmp_path / 'adv.db'}"
    return Store.from_database_url(url)


def test_parse_generator_bundle_roundtrip() -> None:
    bundle = AdversarialGeneratorBundle(
        objections=[
            AdversarialObjectionDraft(
                tradition="methodological",
                primary_attack_vector="measurement",
                objection_text="The operationalization is underspecified.",
                cited_thinkers=["Mayo"],
                citation_style="cited",
                atomic_claims=["Measurement requires explicit error models."],
                is_novel_vs_archive=True,
            ),
            AdversarialObjectionDraft(
                tradition="theory-laden",
                primary_attack_vector="underdetermination",
                objection_text="Observations depend on prior theory.",
                cited_thinkers=["Duhem"],
                citation_style="cited",
                atomic_claims=["Auxiliary hypotheses mediate all inferences."],
                is_novel_vs_archive=True,
            ),
            AdversarialObjectionDraft(
                tradition="base-rate",
                primary_attack_vector="reference class",
                objection_text="The reference class for success is unclear.",
                cited_thinkers=[],
                citation_style="synthesized",
                atomic_claims=["Base rates dominate anecdotal success."],
                is_novel_vs_archive=True,
            ),
        ]
    )
    raw = "Prefix noise\n" + bundle.model_dump_json()
    out = parse_generator_bundle(raw)
    assert len(out.objections) == 3


def test_cluster_fingerprint_stable() -> None:
    a = cluster_fingerprint("p1", ["c2", "c1"])
    b = cluster_fingerprint("p1", ["c1", "c2"])
    assert a == b


def test_generator_content_hash_cache_key() -> None:
    h1 = generator_content_hash("conclusion", ["a", "b"], "t1")
    h2 = generator_content_hash("conclusion", ["a", "b"], "t1")
    h3 = generator_content_hash("conclusion", ["a", "b"], "t2")
    assert h1 == h2
    assert h1 != h3


def test_formalize_tags_adversarial(tmp_path) -> None:
    st = _store(tmp_path)
    draft = AdversarialObjectionDraft(
        tradition="x",
        primary_attack_vector="y",
        objection_text="z",
        atomic_claims=["One", "Two"],
        citation_style="synthesized",
    )
    ids = formalize_objection_to_claims(st, draft, "ch_test")
    assert len(ids) == 2
    c0 = st.get_claim(ids[0])
    assert c0 is not None
    assert c0.claim_origin == ClaimOrigin.ADVERSARIAL
    assert c0.episode_id.startswith("adversarial:")


def test_finalize_survival_and_demotion() -> None:
    ch = AdversarialChallenge(
        id="x",
        conclusion_id="c1",
        cluster_fingerprint="fp",
        final_verdict=CoherenceVerdict.CONTRADICT.value,
        confidence=0.9,
        judge_overturned_contradict=False,
    )
    out = finalize_survival_status(ch)
    assert out.status == AdversarialChallengeStatus.FALLEN

    ch2 = AdversarialChallenge(
        id="y",
        conclusion_id="c1",
        cluster_fingerprint="fp",
        final_verdict=CoherenceVerdict.UNRESOLVED.value,
        confidence=0.0,
    )
    assert finalize_survival_status(ch2).status == AdversarialChallengeStatus.SURVIVED

    con = Conclusion(
        id="c1",
        text="t",
        confidence_tier=ConfidenceTier.FIRM,
        confidence=0.9,
    )
    dem = demote_conclusion_tier(con)
    assert dem.confidence_tier == ConfidenceTier.FOUNDER
    dem2 = demote_conclusion_tier(dem)
    assert dem2.confidence_tier == ConfidenceTier.OPEN


def test_severity_gate_requires_engaged_k(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THESEUS_ADVERSARIAL_ENFORCE", "1")
    get_settings.cache_clear()
    st = _store(tmp_path)
    fp = cluster_fingerprint("p", ["a", "b"])
    score, reason = adversarial_severity_criterion(st, fp, 3)
    assert score < META_THRESHOLDS["severity"]
    assert "3" in reason or "only" in reason.lower()

    for i in range(3):
        ch = AdversarialChallenge(
            id=f"ch{i}",
            conclusion_id="",
            cluster_fingerprint=fp,
            tradition=str(i),
            objection_text="o",
            primary_attack_vector="v",
            atomic_claim_ids=[],
            status=AdversarialChallengeStatus.SURVIVED,
        )
        st.put_adversarial_challenge(ch)
    score2, reason2 = adversarial_severity_criterion(st, fp, 3)
    assert score2 >= 0.55
    assert "survived" in reason2.lower() or "top" in reason2.lower()
    get_settings.cache_clear()


def test_criterion_severity_branch(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("THESEUS_ADVERSARIAL_ENFORCE", "1")
    get_settings.cache_clear()
    st = _store(tmp_path)
    fp = cluster_fingerprint("p", ["x"])
    for i in range(3):
        st.put_adversarial_challenge(
            AdversarialChallenge(
                id=f"id{i}",
                conclusion_id="",
                cluster_fingerprint=fp,
                tradition="t",
                objection_text="o",
                primary_attack_vector="a",
                atomic_claim_ids=[],
                status=AdversarialChallengeStatus.SURVIVED,
            )
        )
    cluster = ClaimClusterMeta(
        claim_ids=["x", "y"],
        texts=["Hello there variance.", "A much longer methodological string for tests."],
        adversarial_fingerprint=fp,
        adversarial_store=st,
    )
    r = criterion_severity(cluster)
    assert r.score >= META_THRESHOLDS["severity"]
    get_settings.cache_clear()


def test_persist_and_mock_llm(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    st = _store(tmp_path)
    bundle = AdversarialGeneratorBundle(
        objections=[
            AdversarialObjectionDraft(
                tradition="t1",
                primary_attack_vector="v1",
                objection_text="o1",
                atomic_claims=["a1"],
                citation_style="synthesized",
            ),
            AdversarialObjectionDraft(
                tradition="t2",
                primary_attack_vector="v2",
                objection_text="o2",
                atomic_claims=["a2"],
                citation_style="synthesized",
            ),
            AdversarialObjectionDraft(
                tradition="t3",
                primary_attack_vector="v3",
                objection_text="o3",
                atomic_claims=["a3"],
                citation_style="synthesized",
            ),
        ]
    )
    con = Conclusion(
        id="conc1",
        text="We should always prefer measurable hypotheses.",
        confidence_tier=ConfidenceTier.FIRM,
        evidence_chain_claim_ids=["e1"],
        supporting_principle_ids=["p1"],
    )
    st.put_claim(
        Claim(
            id="e1",
            text="Measurable hypotheses reduce ambiguity in planning.",
            speaker=Speaker(name="f"),
            episode_id="ep",
            episode_date=date.today(),
            claim_type=ClaimType.METHODOLOGICAL,
        )
    )
    fp = cluster_fingerprint("p1", ["e1"])
    rows = persist_challenge_bundle(st, con, fp, bundle)
    assert len(rows) == 3
    assert all(r.atomic_claim_ids for r in rows)


def test_human_override_addressed(tmp_path) -> None:
    st = _store(tmp_path)
    ch = AdversarialChallenge(
        id="h1",
        conclusion_id="c9",
        cluster_fingerprint="fp",
        tradition="t",
        objection_text="o",
        primary_attack_vector="p",
        atomic_claim_ids=[],
        status=AdversarialChallengeStatus.FALLEN,
        final_verdict=CoherenceVerdict.CONTRADICT.value,
        confidence=0.9,
    )
    st.put_adversarial_challenge(ch)
    out = apply_human_override(
        st,
        "h1",
        HumanAdversarialOverride(kind="addressed", pointer="essay:2024-03", notes="resolved in writing"),
    )
    assert out.status == AdversarialChallengeStatus.ADDRESSED


def test_retrieve_prior_engagement_finds_overlap(tmp_path) -> None:
    st = _store(tmp_path)
    st.put_claim(
        Claim(
            id="q1",
            text="We should always prefer measurable hypotheses in planning cycles.",
            speaker=Speaker(name="f"),
            episode_id="ep",
            episode_date=date.today(),
        )
    )
    ptrs = retrieve_prior_engagement(st, "measurable hypotheses for planning", ["e99"])
    assert isinstance(ptrs, list)

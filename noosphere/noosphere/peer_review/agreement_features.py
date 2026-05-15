"""Feature extraction for the reviewer-agreement model.

The red-team tournament (:mod:`noosphere.peer_review.tournament`) rotates
several reviewer configurations over a frozen conclusion bench. Every
configuration returns a set of severity-scored objections — one per
provider in the configuration's provider mix. When the providers in a
configuration land on similar severities for a conclusion, the swarm
*converged*; when they scatter, the swarm was *contentious*.

This module turns a
:class:`~noosphere.peer_review.tournament.TournamentResult` into a
training corpus for a model that predicts that convergence *before the
swarm runs*, so the founder knows at review time whether to expect
contention.

Two granularities:

* :class:`ObjectionFeatureRow` — one row per
  ``(conclusion, swarm-config, objection)``. This is the raw corpus the
  prompt asks for: topic embedding, claim type, source mix, methodology,
  originating swarm config, severity, and reviewer-id (provider).
* :class:`AgreementExample` — one row per ``(conclusion, swarm-config)``,
  the unit the model trains on. It carries a flat **pre-review** feature
  vector (every feature is knowable before any provider is called) and
  the **agreement label** computed from the spread of per-objection
  severities.

The discipline that keeps the model honest: the label is computed from
severities, but no severity feeds the feature vector. A model that
needs the objections to predict whether the objections will agree is
not a *pre-review* model. The structural severity inputs (cascade
weight, claim centrality, failure-mode severity, source credibility)
*are* features — those are known from the conclusion's argument graph
before review.
"""

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

from noosphere.peer_review.severity import SeverityInputs

# ── Vocabularies (frozen — order defines the feature layout) ─────────

TOPIC_EMBED_DIM = 12

CLAIM_TYPES: tuple[str, ...] = (
    "empirical",
    "theoretical",
    "definitional",
    "normative",
    "methodological",
)
METHODOLOGIES: tuple[str, ...] = (
    "cross_section",
    "benchmark",
    "ablation",
    "formal_analysis",
    "rule_based",
    "unspecified",
)
SOURCE_MIXES: tuple[str, ...] = (
    "monoculture",
    "frontier_pair",
    "frontier_multi",
    "diverse_with_oss",
    "other",
)

# Providers that count as closed-weights frontier vendors. ``mistral_oss``
# is deliberately excluded — it is the open-weights voice the swarm keeps
# so the roster is not all one vendor lineage.
_FRONTIER = frozenset({"anthropic", "openai", "gemini"})

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


# ── Topic embedding ──────────────────────────────────────────────────


def topic_embedding(text: str, *, dim: int = TOPIC_EMBED_DIM) -> tuple[float, ...]:
    """Deterministic hashing bag-of-words embedding of a conclusion.

    No model, no external dependency, no network: each token is hashed
    (MD5 — stable across processes, unlike the salted builtin ``hash``)
    into one of ``dim`` buckets with a ±1 sign, the buckets are summed,
    and the vector is L2-normalised. Two conclusions about the same
    topic land near each other; the model can lean on that without the
    feature extractor ever calling an embedding service.
    """

    acc = [0.0] * dim
    for tok in _tokens(text):
        digest = hashlib.md5(tok.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] & 1 else -1.0
        acc[bucket] += sign
    norm = sum(v * v for v in acc) ** 0.5
    if norm <= 0.0:
        return tuple(acc)
    return tuple(v / norm for v in acc)


# ── Claim-type / methodology classifiers ─────────────────────────────
#
# Deliberately keyword heuristics, not an LLM call: the feature
# extractor must be deterministic and free. The exact mapping is not
# load-bearing for correctness — it only has to be a stable, repeatable
# signal the model can fit a weight to. Tests plant their own structure
# rather than relying on these.

_NORMATIVE_HINTS = (
    "ought",
    "should",
    "moral",
    "impermissible",
    "permissible",
    "immoral",
    "ethical",
    "duty",
    "wrong",
)
_METHODOLOGICAL_HINTS = (
    "guard",
    "policy hook",
    "returns false",
    "fires on",
    "rule fires",
    "harness",
    "attestation",
    "hook is in place",
    "cannot be set",
)
_EMPIRICAL_HINTS = (
    "cross-section",
    "cross section",
    "p<",
    "p <",
    "auroc",
    "benchmark",
    "outperform",
    "filings",
    "measurements",
    "measured",
    "dataset",
    "rates well above chance",
)
_DEFINITIONAL_HINTS = (
    "is defined",
    "by definition",
    "is sufficient to",
    "constant of proportionality",
    "modelled as",
    "treats ",
)


def classify_claim_type(text: str, reasoning: str, domain: str) -> str:
    """Map a conclusion onto one of :data:`CLAIM_TYPES`."""

    blob = f"{text} {reasoning}".lower()
    domain = (domain or "").lower()
    if domain == "ethics" or any(h in blob for h in _NORMATIVE_HINTS):
        return "normative"
    if any(h in blob for h in _METHODOLOGICAL_HINTS):
        return "methodological"
    if any(h in blob for h in _EMPIRICAL_HINTS):
        return "empirical"
    if any(h in blob for h in _DEFINITIONAL_HINTS):
        return "definitional"
    if domain in ("physics", "ai", "epistemology"):
        return "theoretical"
    return "theoretical"


def classify_methodology(reasoning: str) -> str:
    """Map a conclusion's reasoning onto one of :data:`METHODOLOGIES`."""

    r = (reasoning or "").lower()
    if not r.strip():
        return "unspecified"
    if "cross-section" in r or "cross section" in r:
        return "cross_section"
    if "ablation" in r:
        return "ablation"
    if "benchmark" in r or "auroc" in r or "probe" in r:
        return "benchmark"
    if (
        "returns false" in r
        or "rule fires" in r
        or "fires on" in r
        or "hook" in r
        or "guard" in r
    ):
        return "rule_based"
    if (
        "equilibrium" in r
        or "analysis" in r
        or "imperative" in r
        or "groundwork" in r
        or "e = h" in r
        or "quantum" in r
    ):
        return "formal_analysis"
    return "unspecified"


def classify_source_mix(provider_mix: Sequence[str]) -> str:
    """Map a configuration's provider mix onto one of :data:`SOURCE_MIXES`."""

    mix = tuple(provider_mix)
    if len(mix) <= 1:
        return "monoculture"
    if any(p not in _FRONTIER for p in mix):
        return "diverse_with_oss"
    if len(mix) == 2:
        return "frontier_pair"
    return "frontier_multi"


# ── Feature inputs + flat vector ─────────────────────────────────────


@dataclass(frozen=True)
class FeatureInputs:
    """The pre-review-knowable inputs to one feature row.

    Everything here is available *before* a single provider is called:
    the conclusion text/reasoning/domain, its structural severity
    inputs (read off the argument graph), and the swarm configuration
    the founder is about to run.
    """

    conclusion_id: str
    config_id: str
    conclusion_text: str
    reasoning: str
    domain: str
    confidence: float
    severity_inputs: SeverityInputs
    provider_mix: tuple[str, ...]
    temperature: float
    prompt_variant: str

    @classmethod
    def from_bench_and_config(
        cls, item: Any, config: Any
    ) -> "FeatureInputs":
        """Build from a tournament ``BenchItem`` + ``ReviewerConfig``."""

        return cls(
            conclusion_id=item.id,
            config_id=config.config_id,
            conclusion_text=item.text,
            reasoning=getattr(item, "reasoning", ""),
            domain=getattr(item, "domain", "unspecified"),
            confidence=float(getattr(item, "confidence", 0.5) or 0.5),
            severity_inputs=getattr(item, "severity_inputs", SeverityInputs()),
            provider_mix=tuple(config.provider_mix),
            temperature=float(config.temperature),
            prompt_variant=str(config.prompt_variant),
        )


def _onehot(prefix: str, value: str, vocab: Sequence[str]) -> "OrderedDict[str, float]":
    out: "OrderedDict[str, float]" = OrderedDict()
    for v in vocab:
        out[f"{prefix}__{v}"] = 1.0 if v == value else 0.0
    # An out-of-vocab value silently lands as all-zero; that is a real
    # state the model can fit a (zero) weight to, not an error.
    return out


def feature_dict(fi: FeatureInputs) -> "OrderedDict[str, float]":
    """Flatten :class:`FeatureInputs` into the canonical numeric vector.

    The key order here *is* :data:`FEATURE_NAMES`. Every value is in a
    bounded, roughly comparable range so an un-scaled ridge fit is
    well-behaved.
    """

    si = fi.severity_inputs
    feats: "OrderedDict[str, float]" = OrderedDict()

    emb = topic_embedding(fi.conclusion_text)
    for i, v in enumerate(emb):
        feats[f"topic_emb_{i:02d}"] = v

    claim_type = classify_claim_type(fi.conclusion_text, fi.reasoning, fi.domain)
    methodology = classify_methodology(fi.reasoning)
    source_mix = classify_source_mix(fi.provider_mix)
    feats.update(_onehot("claimtype", claim_type, CLAIM_TYPES))
    feats.update(_onehot("methodology", methodology, METHODOLOGIES))
    feats.update(_onehot("sourcemix", source_mix, SOURCE_MIXES))

    # Swarm configuration. ``n_providers`` is normalised against a
    # four-vendor roster so it sits in roughly [0, 1] like the rest.
    feats["n_providers_norm"] = min(1.0, len(fi.provider_mix) / 4.0)
    feats["temperature"] = float(fi.temperature)
    feats["prompt_default"] = 1.0 if fi.prompt_variant == "default" else 0.0

    # Conclusion-structural inputs (known pre-review off the graph).
    feats["confidence"] = _clamp01(fi.confidence)
    feats["cascade_weight"] = _clamp01(si.cascade_weight)
    feats["claim_centrality"] = _clamp01(si.claim_centrality)
    feats["failure_mode_severity"] = _clamp01(si.failure_mode_severity)
    feats["source_credibility"] = (
        _clamp01(si.source_credibility)
        if si.source_credibility is not None
        else 0.0
    )
    feats["has_source"] = 0.0 if si.source_credibility is None else 1.0
    return feats


def _build_feature_names() -> list[str]:
    names = [f"topic_emb_{i:02d}" for i in range(TOPIC_EMBED_DIM)]
    names += [f"claimtype__{v}" for v in CLAIM_TYPES]
    names += [f"methodology__{v}" for v in METHODOLOGIES]
    names += [f"sourcemix__{v}" for v in SOURCE_MIXES]
    names += [
        "n_providers_norm",
        "temperature",
        "prompt_default",
        "confidence",
        "cascade_weight",
        "claim_centrality",
        "failure_mode_severity",
        "source_credibility",
        "has_source",
    ]
    return names


FEATURE_NAMES: list[str] = _build_feature_names()


def feature_vector(fi: FeatureInputs) -> list[float]:
    """Return the feature row as a list aligned with :data:`FEATURE_NAMES`."""

    fd = feature_dict(fi)
    return [fd[name] for name in FEATURE_NAMES]


# ── Per-objection corpus row ─────────────────────────────────────────


@dataclass(frozen=True)
class ObjectionFeatureRow:
    """One ``(conclusion, swarm-config, objection)`` corpus row.

    This is the granularity part A of the prompt asks for. It is not
    what the model trains on (that is :class:`AgreementExample`) — it is
    the auditable corpus the example is built from, and what
    ``train_agreement_model.sh`` archives so a reviewer can see exactly
    which objections produced which agreement label.
    """

    conclusion_id: str
    config_id: str
    reviewer_id: str  # provider name — the "reviewer-id" the prompt asks for
    topic_embedding: tuple[float, ...]
    claim_type: str
    source_mix: str
    methodology: str
    swarm_config: str  # human-readable config descriptor
    severity_value: float
    severity_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "conclusion_id": self.conclusion_id,
            "config_id": self.config_id,
            "reviewer_id": self.reviewer_id,
            "topic_embedding": [round(v, 6) for v in self.topic_embedding],
            "claim_type": self.claim_type,
            "source_mix": self.source_mix,
            "methodology": self.methodology,
            "swarm_config": self.swarm_config,
            "severity_value": round(self.severity_value, 6),
            "severity_label": self.severity_label,
        }


# ── Per-(conclusion, config) training example ────────────────────────


@dataclass(frozen=True)
class AgreementExample:
    """One ``(conclusion, swarm-config)`` row — the unit the model fits.

    ``agreement`` is the label: how tightly the reviewers in the
    configuration landed on the same objection severity for this
    conclusion, in ``[0, 1]`` (1.0 = perfect agreement). It is computed
    by :func:`inter_reviewer_agreement` from the per-objection
    severities and never appears in :attr:`features`.
    """

    conclusion_id: str
    config_id: str
    features: "OrderedDict[str, float]"
    agreement: float
    n_reviewers: int
    domain: str
    objection_rows: tuple[ObjectionFeatureRow, ...] = field(default_factory=tuple)

    @property
    def trainable(self) -> bool:
        """Inter-reviewer agreement is undefined for a single reviewer.

        A monoculture configuration (one provider) produces one
        objection; there is no second reviewer to agree or disagree
        with. Those rows are kept in the corpus for completeness but
        excluded from the fit — see :func:`trainable_examples`.
        """

        return self.n_reviewers >= 2

    def vector(self) -> list[float]:
        return [self.features[name] for name in FEATURE_NAMES]

    def to_dict(self) -> dict[str, Any]:
        return {
            "conclusion_id": self.conclusion_id,
            "config_id": self.config_id,
            "domain": self.domain,
            "agreement": round(self.agreement, 6),
            "n_reviewers": self.n_reviewers,
            "trainable": self.trainable,
            "features": {k: round(v, 6) for k, v in self.features.items()},
            "objection_rows": [r.to_dict() for r in self.objection_rows],
        }


def _clamp01(x: float) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0.0
    if x != x:  # NaN
        return 0.0
    return max(0.0, min(1.0, x))


def inter_reviewer_agreement(severity_values: Sequence[float]) -> float:
    """Continuous inter-reviewer agreement score in ``[0, 1]``.

    Defined as ``1 - mean pairwise absolute difference`` of the
    per-objection severity values. Severity values are already in
    ``[0, 1]``, so the mean pairwise gap is too, and the score is
    bounded without a squashing function. A single reviewer (or none)
    trivially "agrees" — the caller is responsible for excluding those
    from the fit via :attr:`AgreementExample.trainable`.
    """

    vals = [_clamp01(v) for v in severity_values]
    if len(vals) < 2:
        return 1.0
    gaps: list[float] = []
    for i in range(len(vals)):
        for j in range(i + 1, len(vals)):
            gaps.append(abs(vals[i] - vals[j]))
    return _clamp01(1.0 - (sum(gaps) / len(gaps)))


# ── Corpus extraction from a TournamentResult ────────────────────────


def _config_descriptor(config: Any) -> str:
    mix = "+".join(sorted(config.provider_mix))
    return f"{mix}/{config.prompt_variant}/T{config.temperature:g}/s{config.seed}"


def _severity_values_and_providers(ccr: Any) -> tuple[list[float], list[str]]:
    """Pull aligned ``(severity_value, provider)`` pairs off one result.

    The tournament harness builds ``ccr.severities`` from the *ok*
    objections in order, so zipping ok-objections against severities
    re-aligns provider id with severity value. If the driver attached a
    per-objection ``severity`` blob to ``objection.extra`` we prefer
    that (it survives re-ordering); otherwise we fall back to the
    positional zip.
    """

    ok_objections = [o for o in ccr.objections if getattr(o, "ok", True)]
    severities = list(ccr.severities or [])

    values: list[float] = []
    providers: list[str] = []
    for idx, obj in enumerate(ok_objections):
        provider = getattr(obj, "provider", f"reviewer_{idx}")
        sev_blob = (getattr(obj, "extra", None) or {}).get("severity")
        if isinstance(sev_blob, Mapping) and "value" in sev_blob:
            values.append(_clamp01(sev_blob.get("value", 0.0)))
            providers.append(provider)
        elif idx < len(severities):
            values.append(_clamp01(severities[idx].value))
            providers.append(provider)
    # If we matched nothing positionally (e.g. objections list empty in
    # a stubbed driver) fall back to the bare severities list.
    if not values and severities:
        values = [_clamp01(s.value) for s in severities]
        providers = [f"reviewer_{i}" for i in range(len(values))]
    return values, providers


def _severity_label(value: float) -> str:
    # Local copy of severity.label_for thresholds so the corpus row does
    # not need to import the rubric internals.
    if value < 0.34:
        return "low"
    if value < 0.67:
        return "medium"
    return "high"


def extract_examples(
    result: Any,
    bench: Sequence[Any],
    roster: Sequence[Any],
) -> list[AgreementExample]:
    """Turn a :class:`TournamentResult` into a list of training examples.

    Parameters
    ----------
    result
        A ``TournamentResult`` (its ``per_config_results`` carries the
        per-conclusion objection sets).
    bench
        The ``BenchItem`` list the tournament ran on — supplies the
        conclusion-side features.
    roster
        The ``ReviewerConfig`` list — supplies the config-side features.
        Every ``config_id`` in ``result.per_config_results`` must be
        present here.
    """

    bench_by_id = {item.id: item for item in bench}
    roster_by_id = {cfg.config_id: cfg for cfg in roster}

    examples: list[AgreementExample] = []
    for config_id, results in result.per_config_results.items():
        config = roster_by_id.get(config_id)
        if config is None:
            raise ValueError(
                f"config_id {config_id} present in tournament result but "
                "missing from the roster passed to extract_examples"
            )
        descriptor = _config_descriptor(config)
        for ccr in results:
            item = bench_by_id.get(ccr.bench_item_id)
            if item is None:
                # A bench item the roster reviewed but that is not in the
                # bench we were handed: skip rather than guess.
                continue

            fi = FeatureInputs.from_bench_and_config(item, config)
            feats = feature_dict(fi)
            values, providers = _severity_values_and_providers(ccr)

            claim_type = classify_claim_type(item.text, fi.reasoning, fi.domain)
            methodology = classify_methodology(fi.reasoning)
            source_mix = classify_source_mix(fi.provider_mix)
            emb = topic_embedding(item.text)

            rows = tuple(
                ObjectionFeatureRow(
                    conclusion_id=item.id,
                    config_id=config_id,
                    reviewer_id=provider,
                    topic_embedding=emb,
                    claim_type=claim_type,
                    source_mix=source_mix,
                    methodology=methodology,
                    swarm_config=descriptor,
                    severity_value=value,
                    severity_label=_severity_label(value),
                )
                for value, provider in zip(values, providers)
            )

            examples.append(
                AgreementExample(
                    conclusion_id=item.id,
                    config_id=config_id,
                    features=feats,
                    agreement=inter_reviewer_agreement(values),
                    n_reviewers=len(values),
                    domain=fi.domain,
                    objection_rows=rows,
                )
            )
    return examples


def trainable_examples(
    examples: Iterable[AgreementExample],
) -> list[AgreementExample]:
    """Filter to examples with ≥2 reviewers (inter-reviewer agreement defined)."""

    return [e for e in examples if e.trainable]


# ── Held-out shard split ─────────────────────────────────────────────


def shard_of(conclusion_id: str, *, n_shards: int) -> int:
    """Deterministic shard index for a conclusion id.

    The tournament bench is frozen and content-addressed; sharding on a
    stable hash of the conclusion id means the held-out evaluation shard
    is the same set of conclusions on every training run, so a skill
    number is comparable run-to-run rather than re-rolled each time.
    """

    if n_shards < 1:
        raise ValueError("n_shards must be >= 1")
    digest = hashlib.sha256(conclusion_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % n_shards


def split_shards(
    examples: Sequence[AgreementExample],
    *,
    n_shards: int = 5,
    holdout_shard: int = 0,
) -> tuple[list[AgreementExample], list[AgreementExample]]:
    """Split examples into ``(train, holdout)`` by conclusion-id shard.

    Sharding is on the conclusion id, not the row, so a conclusion's
    rows never straddle the train/holdout boundary — otherwise the
    model could see one configuration's review of a conclusion in
    training and be "evaluated" on another configuration's review of the
    same conclusion, which is leakage.
    """

    train: list[AgreementExample] = []
    holdout: list[AgreementExample] = []
    for ex in examples:
        if shard_of(ex.conclusion_id, n_shards=n_shards) == holdout_shard:
            holdout.append(ex)
        else:
            train.append(ex)
    return train, holdout


__all__ = [
    "AgreementExample",
    "CLAIM_TYPES",
    "FEATURE_NAMES",
    "FeatureInputs",
    "METHODOLOGIES",
    "ObjectionFeatureRow",
    "SOURCE_MIXES",
    "TOPIC_EMBED_DIM",
    "classify_claim_type",
    "classify_methodology",
    "classify_source_mix",
    "extract_examples",
    "feature_dict",
    "feature_vector",
    "inter_reviewer_agreement",
    "shard_of",
    "split_shards",
    "topic_embedding",
    "trainable_examples",
]

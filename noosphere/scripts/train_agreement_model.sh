#!/usr/bin/env bash
# train_agreement_model.sh — fit the reviewer-agreement model.
#
# Builds a training corpus from the red-team tournament (prompt 16),
# trains a simple ridge model that predicts inter-reviewer agreement
# from a conclusion's *pre-review* features, evaluates it on a held-out
# tournament shard, and archives:
#
#   noosphere_data/agreement_model/model.json
#       the trained model + its held-out evaluation + full calibration
#       history + the routing policy + the routing ablation. This is the
#       single artifact the founder dashboard's "reviewer agreement
#       trends" widget reads.
#
#   noosphere_data/agreement_model/calibration_history.jsonl
#       one time-stamped calibration snapshot appended per run, so the
#       dashboard can plot whether the model's skill is holding or
#       drifting.
#
#   noosphere_data/agreement_model/corpus.jsonl
#       the per-(conclusion, swarm-config, objection) feature rows the
#       model was built from — the auditable corpus.
#
#   noosphere_data/agreement_model/predictions/<conclusion_id>.json
#       a pre-review prediction + routing decision per bench conclusion,
#       the artifact the peer-review page's "expected contention" pill
#       renders. At real review time the swarm writes the same shape.
#
# Driver: this script always uses the offline *deterministic* driver — a
# seeded simulation that routes severity through the real rubric and
# cost through the real price table. Training must be byte-reproducible
# (re-running gives an identical model.json modulo timestamps), so it
# never depends on live provider keys.
#
# Usage:
#
#   ./noosphere/scripts/train_agreement_model.sh
#
# Environment:
#
#   AGREEMENT_BENCH        override the frozen bench path
#   AGREEMENT_MODEL_DIR    override the output directory
#   AGREEMENT_L2           ridge penalty (default 1.0)
#   AGREEMENT_HOLDOUT_SHARD  held-out shard index (default 0, of 5)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BENCH_PATH="${AGREEMENT_BENCH:-${REPO_ROOT}/benchmarks/redteam/v1/conclusion_bench.jsonl}"
MODEL_DIR="${AGREEMENT_MODEL_DIR:-${REPO_ROOT}/noosphere_data/agreement_model}"
L2="${AGREEMENT_L2:-1.0}"
HOLDOUT_SHARD="${AGREEMENT_HOLDOUT_SHARD:-0}"

mkdir -p "${MODEL_DIR}/predictions"

cd "${REPO_ROOT}"
export PYTHONPATH="${REPO_ROOT}/noosphere:${PYTHONPATH:-}"
export AGREEMENT_BENCH="${BENCH_PATH}"
export AGREEMENT_MODEL_DIR="${MODEL_DIR}"
export AGREEMENT_L2="${L2}"
export AGREEMENT_HOLDOUT_SHARD="${HOLDOUT_SHARD}"

python3 - <<'PY'
"""Reviewer-agreement model training driver.

Deterministic by construction: the offline driver's only simulated
input (the per-provider judge severity) is a SHA-256 draw over the
run's structural inputs, fed through the real severity rubric. Same
bench + same roster -> identical corpus, identical model weights.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
from datetime import datetime, timezone
from pathlib import Path

from noosphere.peer_review.agreement_features import (
    extract_examples,
    split_shards,
    trainable_examples,
)
from noosphere.peer_review.agreement_model import (
    agreement_drift_rows,
    append_calibration_snapshot,
    calibration_snapshot,
    evaluate,
    load_calibration_history,
    model_artifact,
    train_agreement_model,
)
from noosphere.peer_review.providers import PROVIDER_DEFAULTS, ObjectionResult, estimate_cost
from noosphere.peer_review.severity import SeverityInputs, score_objection
from noosphere.peer_review.swarm_router import (
    default_policy,
    prediction_record,
    route,
    routing_ablation,
)
from noosphere.peer_review.tournament import (
    ReviewerConfig,
    bench_sha256,
    load_bench,
    run_tournament,
)

bench_path = Path(os.environ["AGREEMENT_BENCH"])
model_dir = Path(os.environ["AGREEMENT_MODEL_DIR"])
l2 = float(os.environ["AGREEMENT_L2"])
holdout_shard = int(os.environ["AGREEMENT_HOLDOUT_SHARD"])

bench = load_bench(bench_path)
bench_hash = bench_sha256(bench_path)
print(f"loaded {len(bench)} bench items from {bench_path}")
print(f"bench sha256 {bench_hash}")


# ── Reviewer configuration roster ────────────────────────────────────
#
# A spread of provider mixes and temperatures so the corpus has both
# converging and contentious examples to learn from. The single-provider
# probe is kept in the corpus for completeness but is excluded from the
# fit automatically — inter-reviewer agreement is undefined for one
# reviewer (see AgreementExample.trainable).

ROSTER: list[ReviewerConfig] = [
    ReviewerConfig(
        provider_mix=("anthropic", "openai"),
        prompt_variant="default", temperature=0.2, seed=42,
        label="frontier-pair",
    ),
    ReviewerConfig(
        provider_mix=("anthropic", "openai", "gemini", "mistral_oss"),
        prompt_variant="default", temperature=0.2, seed=42,
        label="full-swarm",
    ),
    ReviewerConfig(
        provider_mix=("anthropic", "openai", "gemini", "mistral_oss"),
        prompt_variant="seeded-v2", temperature=0.6, seed=1337,
        label="full-swarm-hot",
    ),
    ReviewerConfig(
        provider_mix=("gemini", "mistral_oss"),
        prompt_variant="default", temperature=0.3, seed=42,
        label="diverse-pair",
    ),
    ReviewerConfig(
        provider_mix=("anthropic", "openai"),
        prompt_variant="default", temperature=0.5, seed=7,
        label="frontier-pair-warm",
    ),
    ReviewerConfig(
        provider_mix=("anthropic",),
        prompt_variant="default", temperature=0.2, seed=42,
        label="anthropic-only",
    ),
]
print(f"roster: {len(ROSTER)} configurations")


# ── Offline deterministic driver ─────────────────────────────────────
#
# Mirrors run_redteam_tournament_v1.sh's driver: a seeded simulation
# whose severity goes through the REAL rubric (the bench item's
# structural inputs cap the ceiling) and whose cost goes through the
# REAL price table. The per-provider personality shifts plus the
# temperature-widened spread are what give the corpus learnable
# agreement structure: low-ceiling items compress every provider's
# severity into a tight cluster (high agreement), high-ceiling + hot
# configs scatter it (contention).

# The per-provider severity bias. The spread here is wider than the
# v1 tournament's cosmetic profile on purpose: a four-vendor swarm
# really does disagree more than a single-vendor pair, and the corpus
# needs that genuine spread for the agreement model to have signal to
# learn (and for the routing policy to see both contested and consensus
# conclusions). The structural ceiling still caps every draw — a
# provider cannot disagree its way past the rubric.
PROVIDER_PROFILE = {
    "anthropic": {"shift": 0.22, "latency": 2300.0, "tok_out": 250},
    "openai": {"shift": 0.06, "latency": 1750.0, "tok_out": 215},
    "gemini": {"shift": -0.10, "latency": 1400.0, "tok_out": 195},
    "mistral_oss": {"shift": -0.26, "latency": 950.0, "tok_out": 165},
}


def _unit(*parts: object) -> float:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return struct.unpack(">Q", hashlib.sha256(raw).digest()[:8])[0] / 2 ** 64


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def offline_driver(config, item):
    objections, severities = [], []
    for provider in config.provider_mix:
        prof = PROVIDER_PROFILE[provider]
        defaults = PROVIDER_DEFAULTS[provider]
        r = _unit(provider, item.id, config.prompt_variant, config.seed,
                  config.temperature)
        spread = 0.18 + 0.30 * config.temperature
        judge = _clamp01(0.5 + prof["shift"] + (r - 0.5) * 2.0 * spread)
        sev_inputs = SeverityInputs(
            cascade_weight=item.severity_inputs.cascade_weight,
            claim_centrality=item.severity_inputs.claim_centrality,
            failure_mode_severity=item.severity_inputs.failure_mode_severity,
            source_credibility=item.severity_inputs.source_credibility,
            judge_severity=judge,
        )
        sev = score_objection(sev_inputs, rationale=f"{provider}")
        tokens_in = 110 + int(_unit("tin", provider, item.id) * 70)
        tokens_out = prof["tok_out"] + int(
            _unit("tout", provider, item.id, config.prompt_variant) * 90
        )
        cost = estimate_cost(
            defaults=defaults, tokens_in=tokens_in, tokens_out=tokens_out
        )
        latency = prof["latency"] * (
            0.8 + 0.4 * _unit("lat", provider, item.id, config.seed)
        )
        obj = ObjectionResult(
            provider=provider, model=defaults.default_model,
            text=f"{provider} objection to {item.id}.",
            cost_usd=cost, latency_ms=latency,
            tokens_in=tokens_in, tokens_out=tokens_out, seed=config.seed,
            extra={"severity": sev.to_dict()},
        )
        objections.append(obj)
        severities.append(sev)
    return objections, severities, False, None


# ── Run the tournament + build the corpus ────────────────────────────

result = run_tournament(
    bench, ROSTER, driver=offline_driver,
    bench_path=bench_path, bench_hash=bench_hash,
)
examples = extract_examples(result, bench, ROSTER)
corpus_rows = [r for e in examples for r in e.objection_rows]
print(f"corpus: {len(examples)} (conclusion, config) examples, "
      f"{len(corpus_rows)} objection rows")

train_all, holdout_all = split_shards(
    examples, n_shards=5, holdout_shard=holdout_shard,
)
train = trainable_examples(train_all)
holdout = trainable_examples(holdout_all)
print(f"split: {len(train)} trainable train rows, "
      f"{len(holdout)} trainable holdout rows (shard {holdout_shard})")

if not train or not holdout:
    raise SystemExit(
        "empty train or holdout split — widen the roster or lower the "
        "shard count"
    )


# ── Train + evaluate ─────────────────────────────────────────────────

model = train_agreement_model(
    train, l2=l2,
    notes=(
        f"redteam-v1 corpus, offline-deterministic driver, "
        f"{len(ROSTER)} configs, holdout shard {holdout_shard}/5"
    ),
)
report = evaluate(model, holdout)
print(f"trained on {model.n_train} rows")
print(f"holdout: mae={report.mae:.4f} baseline_mae={report.baseline_mae:.4f} "
      f"skill={report.skill:+.4f} pearson_r={report.pearson_r:+.4f}")
print(f"  {'beats the predict-the-mean baseline' if report.beats_baseline else 'DOES NOT beat the baseline — treat as noise'}")


# ── Calibration history (append-only) ────────────────────────────────

now_iso = datetime.now(timezone.utc).isoformat()
history_path = model_dir / "calibration_history.jsonl"
snapshot = calibration_snapshot(model, report, observed_at=now_iso)
append_calibration_snapshot(str(history_path), snapshot)
history = load_calibration_history(str(history_path))
print(f"calibration history: {len(history)} snapshot(s)")


# ── Routing policy + ablation ────────────────────────────────────────
#
# Predict every bench conclusion's agreement (under the policy's base
# mix), then ablate the routing policy against the always-base and
# always-expanded baselines. The ablation reports cost saving and
# coverage delta side by side — the firm never sees one without the
# other.

policy = default_policy()
bench_predictions: dict[str, float] = {}
for item in bench:
    from noosphere.peer_review.agreement_features import FeatureInputs
    fi = FeatureInputs.from_bench_and_config(
        item,
        type("Cfg", (), {
            "config_id": "policy-base",
            "provider_mix": policy.base_mix,
            "temperature": 0.2,
            "prompt_variant": "default",
        })(),
    )
    bench_predictions[item.id] = model.predict_inputs(fi)

ablation = routing_ablation(list(bench_predictions.values()), policy)
print(f"routing ablation over {ablation.n_conclusions} conclusions: "
      f"expand={ablation.expand_count} keep={ablation.keep_count} "
      f"shrink={ablation.shrink_count}")
print(f"  cost saving vs always-expanded: "
      f"${ablation.cost_saving_vs_expanded_usd:.5f}  "
      f"coverage delta: {ablation.coverage_delta_vs_expanded} reviewers")
print(f"  cost delta vs always-base:      "
      f"${-ablation.cost_saving_vs_base_usd:+.5f}  "
      f"coverage delta: {ablation.coverage_delta_vs_base:+d} reviewers")


# ── Drift rows for the existing detector ─────────────────────────────
#
# Adapt the held-out predictions into method_drift.DriftResolution rows.
# A scheduler accumulates these across runs and feeds them straight into
# method_drift.evaluate_method under method_name="reviewer_agreement_model"
# — the agreement model is watched by the *existing* drift detector, not
# a bespoke one.

drift_rows = agreement_drift_rows(
    model, holdout, observed_at=datetime.now(timezone.utc),
)
drift_path = model_dir / "drift_resolutions.jsonl"
with drift_path.open("a", encoding="utf-8") as fh:
    for row in drift_rows:
        fh.write(json.dumps({
            "prediction_id": row.prediction_id,
            "probability": round(row.probability, 6),
            "outcome": row.outcome,
            "observed_at": row.observed_at.isoformat(),
            "domain": row.domain,
        }, sort_keys=True) + "\n")
print(f"appended {len(drift_rows)} drift resolution rows -> {drift_path}")


# ── Write artifacts ──────────────────────────────────────────────────

artifact = model_artifact(
    model, report, history,
    routing_policy=policy.to_dict(),
    extra={
        "routing_ablation": ablation.to_dict(),
        "bench_sha256": bench_hash,
        "n_configs": len(ROSTER),
        "n_corpus_examples": len(examples),
    },
)
model_path = model_dir / "model.json"
with model_path.open("w", encoding="utf-8") as fh:
    json.dump(artifact, fh, indent=2, sort_keys=True)
print(f"wrote {model_path}")

corpus_path = model_dir / "corpus.jsonl"
with corpus_path.open("w", encoding="utf-8") as fh:
    for ex in examples:
        fh.write(json.dumps(ex.to_dict(), sort_keys=True) + "\n")
print(f"wrote {corpus_path}")

# Per-conclusion prediction artifacts — the "expected contention" pill
# on the peer-review page reads these. At real review time the swarm
# writes the same shape via SwarmOrchestrator._persist_agreement_prediction.
pred_dir = model_dir / "predictions"
pred_dir.mkdir(parents=True, exist_ok=True)
for item in bench:
    predicted = bench_predictions[item.id]
    decision = route(predicted, policy)
    from noosphere.peer_review.agreement_features import FeatureInputs, feature_dict
    fi = FeatureInputs.from_bench_and_config(
        item,
        type("Cfg", (), {
            "config_id": "policy-base",
            "provider_mix": policy.base_mix,
            "temperature": 0.2,
            "prompt_variant": "default",
        })(),
    )
    record = prediction_record(
        conclusion_id=item.id,
        decision=decision,
        model_trained_at=model.trained_at,
        calibration_skill=report.skill,
        top_drivers=model.top_drivers(feature_dict(fi), k=4),
        generated_at=now_iso,
    )
    with (pred_dir / f"{item.id}.json").open("w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
print(f"wrote {len(bench)} prediction artifacts -> {pred_dir}")

print()
print("reviewer-agreement model trained.")
print(f"  skill        {report.skill:+.4f}  "
      f"({'beats baseline' if report.beats_baseline else 'no skill'})")
print(f"  pearson r    {report.pearson_r:+.4f}")
print(f"  holdout n    {report.n_eval}")
print(f"  model        {model_path}")
PY

echo ""
echo "model_dir=${MODEL_DIR}"

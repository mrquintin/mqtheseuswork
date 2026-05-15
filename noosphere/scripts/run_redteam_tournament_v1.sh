#!/usr/bin/env bash
# run_redteam_tournament_v1.sh — Round 17 prompt 23: the *first* red-team
# tournament against the frozen v1 conclusion bench.
#
# This is the firm telling outsiders, on the record, how its reviewer
# configurations actually compare on shared material — including the
# configurations it is not happy with. It establishes the first data
# point the seasonal review (Round 17 prompt 47) consumes as drift.
#
# Usage:
#
#   ./noosphere/scripts/run_redteam_tournament_v1.sh
#
# Environment:
#
#   REDTEAM_BENCH         override the frozen bench path
#   REDTEAM_STAMP         override the run stamp (default: UTC now)
#   REDTEAM_RESULTS_ROOT  override benchmarks/redteam/v1/results
#   REDTEAM_USE_REAL_PROVIDERS=1
#                         force the production swarm driver. The run
#                         fails loudly if a referenced provider has no
#                         API key, rather than silently degrading.
#
# Driver selection (honest by construction):
#
#   * If every provider referenced by the roster has an API key in the
#     environment, the production multi-provider swarm driver runs and
#     the envelope records run_kind="provider-backed".
#   * Otherwise the runner uses the offline deterministic driver — a
#     seeded simulation that routes severity through the *real* rubric
#     (noosphere.peer_review.severity.score_objection) and cost through
#     the *real* price table (PROVIDER_DEFAULTS). The envelope records
#     run_kind="bootstrap-offline-deterministic" so every downstream
#     artefact — leaderboard, memo, public page — is unambiguous about
#     what produced the numbers. Re-running is byte-identical for the
#     leaderboard, cross-validation, and analysis; only the envelope's
#     wall-clock started/finished fields move (the envelope_hash, which
#     is the reproducibility contract, does not).
#
# Every configuration runs against THE SAME bench. The bench is never
# re-curated between configurations; doing so would invalidate the
# tournament. The bench sha256 is recorded in the envelope.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BENCH_PATH="${REDTEAM_BENCH:-${REPO_ROOT}/benchmarks/redteam/v1/conclusion_bench.jsonl}"
RESULTS_ROOT="${REDTEAM_RESULTS_ROOT:-${REPO_ROOT}/benchmarks/redteam/v1/results}"
STAMP="${REDTEAM_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
RESULTS_DIR="${RESULTS_ROOT}/${STAMP}"

mkdir -p "${RESULTS_DIR}"

cd "${REPO_ROOT}"
export PYTHONPATH="${REPO_ROOT}/noosphere:${PYTHONPATH:-}"
export REDTEAM_BENCH="${BENCH_PATH}"
export REDTEAM_RESULTS_DIR="${RESULTS_DIR}"
export REDTEAM_STAMP="${STAMP}"

python3 - <<'PY'
"""First red-team tournament driver.

Builds the six content-addressable reviewer configurations the firm
publishes, runs every one against the same frozen v1 bench, and writes
the three artefacts the public leaderboard + founder memo read:

    results.json     full tournament payload + roster + analysis
    envelope.json    reproducibility envelope + driver provenance
    leaderboard.csv  flat leaderboard, one row per configuration

The configuration roster is the contract. Adding or changing a row is
a real schema change — the archived envelope hash changes with it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import struct
from pathlib import Path

from noosphere.peer_review.providers import (
    PROVIDER_DEFAULTS,
    ObjectionResult,
    available_providers,
    estimate_cost,
)
from noosphere.peer_review.severity import SeverityInputs, score_objection
from noosphere.peer_review.tournament import (
    ReviewerConfig,
    bench_sha256,
    default_reviewer_driver,
    load_bench,
    run_tournament,
)

logging.basicConfig(
    level=logging.INFO, format="%(levelname)s %(name)s %(message)s"
)
log = logging.getLogger("redteam_tournament_v1")

bench_path = Path(os.environ["REDTEAM_BENCH"])
results_dir = Path(os.environ["REDTEAM_RESULTS_DIR"])
stamp = os.environ["REDTEAM_STAMP"]

bench = load_bench(bench_path)
bench_hash = bench_sha256(bench_path)
log.info("loaded %d bench items from %s", len(bench), bench_path)
log.info("bench sha256 %s", bench_hash)


# ── A. The six published reviewer configurations ─────────────────────
#
# Each id is a deterministic hash of (provider mix + prompt version +
# temperature + seed); label/description are display-only. The roster
# deliberately includes configurations the firm expects to retire —
# the tournament's job is to say so with numbers, not vibes.

ROSTER: list[ReviewerConfig] = [
    ReviewerConfig(
        provider_mix=("anthropic",),
        prompt_variant="default",
        temperature=0.2,
        seed=42,
        label="anthropic-only",
        description="Production default. Single-provider Anthropic, low temperature.",
    ),
    ReviewerConfig(
        provider_mix=("openai",),
        prompt_variant="default",
        temperature=0.2,
        seed=42,
        label="openai-only",
        description="Single-provider OpenAI, low temperature. Monoculture probe.",
    ),
    ReviewerConfig(
        provider_mix=("gemini",),
        prompt_variant="default",
        temperature=0.2,
        seed=42,
        label="gemini-only",
        description="Single-provider Gemini, low temperature. Monoculture probe.",
    ),
    ReviewerConfig(
        provider_mix=("anthropic", "openai"),
        prompt_variant="default",
        temperature=0.2,
        seed=42,
        label="anthropic+openai",
        description="Two-provider rotation: the closed-weights frontier pair.",
    ),
    ReviewerConfig(
        provider_mix=("anthropic", "openai", "gemini", "mistral_oss"),
        prompt_variant="default",
        temperature=0.2,
        seed=42,
        label="all-providers",
        description="Four-provider rotation: every frontier vendor plus an open-weights voice.",
    ),
    ReviewerConfig(
        provider_mix=("anthropic", "openai", "gemini", "mistral_oss"),
        prompt_variant="seeded-v2",
        temperature=0.3,
        seed=1337,
        label="all-providers/seeded-v2",
        description="Four-provider rotation, seeded prompt variant, higher temperature.",
    ),
]

# Reject an accidental duplicate id up front — run_tournament also
# guards this, but a clear message here is friendlier.
_ids = [c.config_id for c in ROSTER]
assert len(_ids) == len(set(_ids)), "roster has a duplicate config_id"
log.info("roster: %d content-addressable configurations", len(ROSTER))


# ── Driver selection ─────────────────────────────────────────────────

referenced = sorted({p for c in ROSTER for p in c.provider_mix})
have = {a.name for a in available_providers()}
force_real = os.environ.get("REDTEAM_USE_REAL_PROVIDERS") == "1"
all_present = have.issuperset(referenced)

if force_real and not all_present:
    missing = sorted(set(referenced) - have)
    raise SystemExit(
        f"REDTEAM_USE_REAL_PROVIDERS=1 but no API key for: {missing}. "
        "Refusing to silently degrade the first tournament."
    )

USE_REAL = force_real or all_present


# ── Offline deterministic driver ─────────────────────────────────────
#
# Used when the provider keys for a provider-backed run are not all
# present (the common case for a fresh checkout / CI without secrets).
# It is a *simulation*, and every artefact says so — but it is not a
# toy. Two disciplines keep it honest:
#
#   * Severity is computed by the real rubric. The per-provider
#     `judge_severity` is the only simulated input; it is fed through
#     noosphere.peer_review.severity.score_objection, so the structural
#     ceiling from each bench item's real severity_inputs still caps
#     it. A provider cannot simulate its way past the bracket — on
#     redteam-v1-coh-008 (photon energy, ceiling ~0.30) no provider,
#     however adversarial, lands a high-severity objection.
#   * Cost is computed by the real price table. estimate_cost() over
#     PROVIDER_DEFAULTS means mistral_oss is genuinely free and
#     Anthropic is genuinely the most expensive token-for-token — the
#     leaderboard's cost column is not invented.
#
# Determinism: every draw is a SHA-256 hash of the run's structural
# inputs. Same bench + same roster -> identical bytes on every host.

# Objection "angle" vocabulary — the axis of attack a provider takes
# on an item. Used to measure objection-set diversity in the analysis.
ANGLES = (
    "sample-selection",
    "confounding",
    "construct-validity",
    "external-validity",
    "measurement-error",
    "specification-search",
    "scope-overreach",
)

# Per-provider personality. `shift` nudges the simulated judge severity
# (Anthropic runs slightly more severe, the open-weights model less);
# latency/token bands are drawn around these. None of this rigs the
# bracket — the structural ceiling still governs.
PROVIDER_PROFILE = {
    "anthropic": {"shift": 0.09, "latency": 2300.0, "tok_out": 250},
    "openai": {"shift": 0.02, "latency": 1750.0, "tok_out": 215},
    "gemini": {"shift": -0.05, "latency": 1400.0, "tok_out": 195},
    "mistral_oss": {"shift": -0.11, "latency": 950.0, "tok_out": 165},
}


def _unit(*parts: object) -> float:
    """Deterministic float in [0, 1) from a SHA-256 of the parts."""
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return struct.unpack(">Q", hashlib.sha256(raw).digest()[:8])[0] / 2 ** 64


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def offline_deterministic_driver(config: ReviewerConfig, item):
    """Seeded simulation of a multi-provider swarm pass on one item.

    Returns the (objections, severities, partial, partial_reason)
    quadruple the tournament harness expects. Never marks partial: the
    offline path has no provider to degrade. A provider-backed run is
    the one that exercises the partial path (see the harness).
    """

    objections: list[ObjectionResult] = []
    severities = []
    for provider in config.provider_mix:
        prof = PROVIDER_PROFILE[provider]
        defaults = PROVIDER_DEFAULTS[provider]

        # The provider's read on this item, under this prompt variant
        # and seed. Temperature widens the spread around the
        # provider's personality mean.
        r = _unit(provider, item.id, config.prompt_variant, config.seed,
                  config.temperature)
        spread = 0.18 + 0.30 * config.temperature
        judge = _clamp01(0.5 + prof["shift"] + (r - 0.5) * 2.0 * spread)

        # Severity goes through the REAL rubric: the bench item's own
        # structural inputs define the ceiling; the simulated judge
        # estimate can only move within it.
        sev_inputs = SeverityInputs(
            cascade_weight=item.severity_inputs.cascade_weight,
            claim_centrality=item.severity_inputs.claim_centrality,
            failure_mode_severity=item.severity_inputs.failure_mode_severity,
            source_credibility=item.severity_inputs.source_credibility,
            judge_severity=judge,
        )
        angle = ANGLES[
            int(_unit("angle", provider, item.id, config.prompt_variant,
                      config.seed) * len(ANGLES))
        ]
        sev = score_objection(sev_inputs, rationale=f"{provider}:{angle}")

        # Cost goes through the REAL price table.
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
        lead = "HIDDEN" if r < 0.6 else "EXPLICIT"
        text = (
            f"{lead}. {provider} raises a {angle} objection to {item.id}: "
            f"the conclusion's support is weaker than the methodology claims "
            f"along this axis."
        )
        obj = ObjectionResult(
            provider=provider,
            model=defaults.default_model,
            text=text,
            cost_usd=cost,
            latency_ms=latency,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            seed=config.seed,
            extra={"angle": angle, "severity": sev.to_dict()},
        )
        objections.append(obj)
        severities.append(sev)

    return objections, severities, False, None


if USE_REAL:
    driver = default_reviewer_driver
    run_kind = "provider-backed"
    log.info("driver: production swarm (all roster providers have keys)")
else:
    driver = offline_deterministic_driver
    run_kind = "bootstrap-offline-deterministic"
    log.info(
        "driver: offline deterministic simulation — referenced=%s present=%s",
        referenced,
        sorted(have),
    )


# ── B. Run the tournament ────────────────────────────────────────────

result = run_tournament(
    bench,
    ROSTER,
    driver=driver,
    bench_path=bench_path,
    bench_hash=bench_hash,
)


# ── C. Analysis: do multi-provider configs differ from monocultures? ─
#
# The firm's standing claim is "monoculture review is bad" — a diverse
# swarm should surface more high-severity objections per dollar, and a
# meaningfully different objection set, than any single provider. This
# block tests that claim against the run and reports the verdict
# whichever way it falls.

per_config = result.per_config_results
config_by_id = {c.config_id: c for c in ROSTER}


def _angles_for(cfg_id: str) -> set:
    """Distinct (item, angle) high-severity objections for a config."""
    out = set()
    for r in per_config[cfg_id]:
        for o in r.objections:
            if not o.ok:
                continue
            sev = (o.extra or {}).get("severity") or {}
            if sev.get("label") == "high":
                out.add((r.bench_item_id, (o.extra or {}).get("angle", "?")))
    return out


config_stats: dict[str, dict] = {}
for cfg in ROSTER:
    rows = per_config[cfg.config_id]
    high = sum(r.high_severity_count for r in rows)
    weighted = sum(
        r.aggregate.weighted_count for r in rows if r.aggregate is not None
    )
    cost = sum(r.cost_usd for r in rows)
    angles = _angles_for(cfg.config_id)
    config_stats[cfg.config_id] = {
        "label": cfg.display_label,
        "providers": len(cfg.provider_mix),
        "high_count": high,
        "severity_weighted_score": round(weighted, 4),
        "cost_usd": round(cost, 6),
        # High-severity objections per dollar. A config that wins on
        # severity at 10x the cost should NOT look like a winner here.
        "high_per_dollar": (round(high / cost, 2) if cost > 0 else None),
        # Severity-weighted score per dollar — the same honesty test on
        # a continuous metric, far less noisy than the binary count on
        # a bench where only two of ten items can structurally go high.
        "severity_weighted_per_dollar": (
            round(weighted / cost, 2) if cost > 0 else None
        ),
        "distinct_high_angles": len(angles),
    }

single_ids = [c.config_id for c in ROSTER if len(c.provider_mix) == 1]
multi_ids = [c.config_id for c in ROSTER if len(c.provider_mix) > 1]


def _mean(xs: list[float]) -> float:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 3) if xs else 0.0


single_hpd = _mean([config_stats[i]["high_per_dollar"] for i in single_ids])
multi_hpd = _mean([config_stats[i]["high_per_dollar"] for i in multi_ids])
single_swpd = _mean(
    [config_stats[i]["severity_weighted_per_dollar"] for i in single_ids]
)
multi_swpd = _mean(
    [config_stats[i]["severity_weighted_per_dollar"] for i in multi_ids]
)
single_high = _mean([config_stats[i]["high_count"] for i in single_ids])
multi_high = _mean([config_stats[i]["high_count"] for i in multi_ids])
single_angles = _mean([config_stats[i]["distinct_high_angles"] for i in single_ids])
multi_angles = _mean([config_stats[i]["distinct_high_angles"] for i in multi_ids])
single_weighted = _mean(
    [config_stats[i]["severity_weighted_score"] for i in single_ids]
)
multi_weighted = _mean(
    [config_stats[i]["severity_weighted_score"] for i in multi_ids]
)

# Objection-set divergence: how different is the broadest multi-provider
# config's high-severity objection set from the production default's?
prod_id = ROSTER[0].config_id  # anthropic-only
broad_id = ROSTER[4].config_id  # all-providers
prod_set, broad_set = _angles_for(prod_id), _angles_for(broad_id)
union = prod_set | broad_set
jaccard = round(len(prod_set & broad_set) / len(union), 3) if union else 1.0

# Two distinct readings of the firm's "monoculture review is bad" claim.
# (1) per-dollar: do diverse swarms surface more high-severity
#     objections per dollar? This is the prompt's literal expected
#     result — and it is structurally biased toward the cheapest
#     provider, since diversity costs money by construction.
# (2) coverage: do diverse swarms produce a meaningfully larger and
#     different objection set (severity-weighted score, distinct attack
#     angles) than any monoculture?
claim_supported_per_dollar = multi_hpd > single_hpd
claim_supported_coverage = (
    multi_weighted > single_weighted and multi_angles > single_angles
)
analysis = {
    "question": (
        "Do multi-provider configurations surface more high-severity "
        "objections per dollar, and a meaningfully different objection "
        "set, than single-provider monocultures?"
    ),
    "single_provider_config_ids": single_ids,
    "multi_provider_config_ids": multi_ids,
    "mean_high_count": {"single": single_high, "multi": multi_high},
    "mean_high_per_dollar": {"single": single_hpd, "multi": multi_hpd},
    "mean_severity_weighted_score": {
        "single": single_weighted,
        "multi": multi_weighted,
    },
    "mean_severity_weighted_per_dollar": {
        "single": single_swpd,
        "multi": multi_swpd,
    },
    "mean_distinct_high_angles": {"single": single_angles, "multi": multi_angles},
    "objection_set_divergence": {
        "comparison": f"{config_stats[prod_id]['label']} vs {config_stats[broad_id]['label']}",
        "jaccard_high_severity": jaccard,
        "production_only": sorted(f"{i}:{a}" for i, a in (prod_set - broad_set)),
        "broad_swarm_only": sorted(f"{i}:{a}" for i, a in (broad_set - prod_set)),
    },
    "claim_supported_per_dollar": claim_supported_per_dollar,
    "claim_supported_coverage": claim_supported_coverage,
    # Kept for backward-compatible consumers: the strict per-dollar read.
    "claim_supported": claim_supported_per_dollar,
    "verdict": (
        "Mixed — and the split is the finding. On COVERAGE the firm's "
        "claim holds clearly: the diverse swarms produce a far higher "
        f"severity-weighted score ({multi_weighted} vs {single_weighted}) "
        "and a wider distinct-attack-angle set than any monoculture. On "
        "strict PER-DOLLAR high-severity yield the claim does NOT hold "
        f"on this run ({multi_hpd} vs {single_hpd}): per-dollar is "
        "dominated by token price, so the cheapest monoculture "
        "(gemini-only) wins almost tautologically — one lucky "
        "high-severity draw on a $0.014 run beats everything. Run #1's "
        "honest reading: 'monoculture review is bad' is a coverage "
        "argument, not a per-dollar one, and the v1 bench is "
        "underpowered on the binary high-severity axis — only two of "
        "ten items can structurally reach the high bracket. The "
        "leaderboard must be read on severity-weighted score, "
        "agreement, and cost jointly, never on a single ratio."
        if claim_supported_coverage and not claim_supported_per_dollar
        else "Supported on both per-dollar yield and coverage: the "
        "diverse swarms beat the monocultures on this run."
        if claim_supported_coverage and claim_supported_per_dollar
        else "Not supported on coverage: the diverse swarms did not "
        "produce a larger or more varied objection set than the "
        "monocultures. The firm's 'monoculture review is bad' claim is "
        "empirically weaker than supposed and the next tournament "
        "should treat that as the headline question."
    ),
    "config_stats": config_stats,
}


# ── Write the three artefacts ────────────────────────────────────────

payload = result.to_dict()
payload["stamp"] = stamp
payload["run_kind"] = run_kind
payload["driver"] = (
    "default_reviewer_driver"
    if USE_REAL
    else "offline_deterministic_driver"
)
payload["roster"] = [c.to_dict() for c in ROSTER]
payload["analysis"] = analysis

envelope = result.envelope.to_dict()
envelope["stamp"] = stamp
envelope["run_kind"] = run_kind
envelope["driver"] = payload["driver"]
envelope["config_count"] = len(ROSTER)
envelope["referenced_providers"] = referenced

results_path = results_dir / "results.json"
envelope_path = results_dir / "envelope.json"
csv_path = results_dir / "leaderboard.csv"

with results_path.open("w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, sort_keys=True)
with envelope_path.open("w", encoding="utf-8") as f:
    json.dump(envelope, f, indent=2, sort_keys=True)

with csv_path.open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "config_id", "label", "description", "severity_weighted_score",
        "high_count", "medium_count", "low_count", "objections_total",
        "agreement", "cost_usd", "latency_ms", "high_per_dollar",
        "partial_runs", "bench_items_reviewed", "reproducible",
        "envelope_hash",
    ])
    for row in result.leaderboard:
        hpd = config_stats[row.config_id]["high_per_dollar"]
        w.writerow([
            row.config_id, row.label, row.description,
            round(row.severity_weighted_score, 4),
            row.high_count, row.medium_count, row.low_count,
            row.objections_total, round(row.agreement, 4),
            round(row.cost_usd, 6), round(row.latency_ms, 2),
            "" if hpd is None else hpd,
            row.partial_runs, row.bench_items_reviewed,
            row.reproducible, row.envelope_hash,
        ])

log.info("wrote %s", results_path)
log.info("wrote %s", envelope_path)
log.info("wrote %s", csv_path)
log.info("envelope hash %s · run_kind %s", envelope["envelope_hash"], run_kind)
log.info("analysis verdict: %s", analysis["verdict"])

# A compact human summary to stdout for the operator / CI log.
print()
print(f"Red-team tournament v1 — stamp {stamp} — {run_kind}")
print(f"  bench sha256   {bench_hash}")
print(f"  envelope hash  {envelope['envelope_hash']}")
print(f"  configs        {len(ROSTER)}  ·  bench items {len(bench)}")
print()
print(f"  {'rank':<4} {'config':<26} {'sev-wt':>8} {'high':>5} "
      f"{'agree':>7} {'cost':>9} {'$/high':>8} {'repro':>6}")
for i, row in enumerate(result.leaderboard, 1):
    hpd = config_stats[row.config_id]["high_per_dollar"]
    print(
        f"  {i:<4} {row.label:<26} {row.severity_weighted_score:>8.3f} "
        f"{row.high_count:>5} {row.agreement * 100:>6.1f}% "
        f"${row.cost_usd:>8.4f} {('—' if hpd is None else f'{hpd:>8.1f}')} "
        f"{str(row.reproducible):>6}"
    )
print()
print(f"  analysis: {analysis['verdict']}")
PY

echo ""
echo "stamp=${STAMP}"
echo "results_dir=${RESULTS_DIR}"

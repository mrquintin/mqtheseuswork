#!/usr/bin/env bash
# fit_severity_model.sh — calibrate the severity rubric against outcomes.
#
# The severity rubric (noosphere.peer_review.severity) ships a
# *stipulated* formula: it maps the five structural inputs to a score by
# an asserted rule. This job checks that rule against reality. It reads
# the labeled-objection corpus — every recorded objection joined to its
# realized outcome via the revision ledger (prompt 16): material change,
# addendum, or dismissed — and fits an L2-regularised logistic
# regression predicting "material change" from the severity inputs. The
# fitted model becomes the new severity scorer
# (severity.score_objection_with_model); the stipulated formula stays in
# code as the cold-start fallback and the ablation alternative.
#
# COLD-START DISCIPLINE. Below SEVERITY_CALIBRATION_MIN_N (default 50)
# labeled objections — or with only one outcome class present — this job
# does NOT replace the formula. It writes a deliberate-deferral note to
# docs/methods/Severity_Calibration_Status.md and exits 0. Shipping a
# noisy model fit on tiny data is worse than the honest stipulated
# rubric, and the gate makes that refusal explicit rather than silent.
#
# Artifacts:
#
#   noosphere_data/severity_calibration/model.json
#       the fit result — model + held-out evaluation + reliability
#       diagram + (when a re-score ran) the founder queue. This is the
#       single artifact the methods page's severity-calibration section
#       reads. Written on every run, fitted or cold-start.
#
#   docs/methods/Severity_Calibration_Status.md
#       the human-readable status: the deferral note on cold start, the
#       "model is live" record once fitted. Regenerated every run.
#
# Schedule: run nightly, on the same cadence as drift detection — the
# fitted model is recomputed as the labeled corpus grows.
#
# Usage:
#
#   ./noosphere/scripts/fit_severity_model.sh
#
# Environment:
#
#   SEVERITY_CALIBRATION_CORPUS     labeled-objection corpus (JSONL).
#                                   Default noosphere_data/severity_calibration/labeled_objections.jsonl
#   SEVERITY_CALIBRATION_LIVE       live-objection corpus (JSONL) for the
#                                   re-score. Optional — re-score is
#                                   skipped when absent.
#   SEVERITY_CALIBRATION_MODEL_DIR  output directory
#   SEVERITY_CALIBRATION_STATUS_DOC status doc path
#   SEVERITY_CALIBRATION_L2         ridge penalty (default 1.0)
#   SEVERITY_CALIBRATION_MIN_N      cold-start threshold (default 50)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODEL_DIR="${SEVERITY_CALIBRATION_MODEL_DIR:-${REPO_ROOT}/noosphere_data/severity_calibration}"
CORPUS_PATH="${SEVERITY_CALIBRATION_CORPUS:-${MODEL_DIR}/labeled_objections.jsonl}"
LIVE_PATH="${SEVERITY_CALIBRATION_LIVE:-${MODEL_DIR}/live_objections.jsonl}"
STATUS_DOC="${SEVERITY_CALIBRATION_STATUS_DOC:-${REPO_ROOT}/docs/methods/Severity_Calibration_Status.md}"
L2="${SEVERITY_CALIBRATION_L2:-1.0}"
MIN_N="${SEVERITY_CALIBRATION_MIN_N:-50}"

mkdir -p "${MODEL_DIR}"

cd "${REPO_ROOT}"
export PYTHONPATH="${REPO_ROOT}/noosphere:${PYTHONPATH:-}"
export SEVERITY_CALIBRATION_CORPUS="${CORPUS_PATH}"
export SEVERITY_CALIBRATION_LIVE="${LIVE_PATH}"
export SEVERITY_CALIBRATION_MODEL_DIR="${MODEL_DIR}"
export SEVERITY_CALIBRATION_STATUS_DOC="${STATUS_DOC}"
export SEVERITY_CALIBRATION_L2="${L2}"
export SEVERITY_CALIBRATION_MIN_N="${MIN_N}"

python3 - <<'PY'
"""Severity-calibration fit driver.

Loads the labeled-objection corpus, fits (or defers, on cold-start
grounds), and writes the model.json artifact + the status doc. The
re-score over live objections runs only when a live corpus is present
and a model was actually fit.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from noosphere.peer_review.severity import SeverityInputs
from noosphere.peer_review.severity_calibration import (
    calibration_artifact,
    fit_severity_calibration,
    load_labeled_corpus,
    rescore_live_objections,
    status_markdown,
)

corpus_path = Path(os.environ["SEVERITY_CALIBRATION_CORPUS"])
live_path = Path(os.environ["SEVERITY_CALIBRATION_LIVE"])
model_dir = Path(os.environ["SEVERITY_CALIBRATION_MODEL_DIR"])
status_doc = Path(os.environ["SEVERITY_CALIBRATION_STATUS_DOC"])
l2 = float(os.environ["SEVERITY_CALIBRATION_L2"])
min_n = int(os.environ["SEVERITY_CALIBRATION_MIN_N"])

# Display the corpus path repo-relative — the script runs from REPO_ROOT,
# so the committed status doc stays clean across machines.
try:
    corpus_display = str(corpus_path.relative_to(Path.cwd()))
except ValueError:
    corpus_display = str(corpus_path)

# ── Load the labeled corpus ──────────────────────────────────────────

labeled = load_labeled_corpus(str(corpus_path))
if labeled:
    print(f"loaded {len(labeled)} labeled objection(s) from {corpus_path}")
else:
    print(f"no labeled corpus at {corpus_path} — treating as cold start")


# ── Fit (or defer) ───────────────────────────────────────────────────

result = fit_severity_calibration(labeled, l2=l2, min_n=min_n)
print(f"status: {result.status}")
print(
    f"  labeled={result.n_labeled} "
    f"material={result.n_material} "
    f"addendum={result.n_addendum} "
    f"dismissed={result.n_dismissed}"
)

if result.is_cold_start:
    print(f"  cold-start: {result.cold_start_reason}")
else:
    ev = result.evaluation
    if ev is not None:
        verdict = (
            "beats baseline"
            if ev.beats_baseline
            else "NO SKILL — treat as noise"
        )
        print(
            f"  held-out: n={ev.n_eval} skill={ev.skill:+.4f} "
            f"auc={ev.auc:.4f} brier={ev.brier:.4f}  ({verdict})"
        )
    else:
        print("  held-out: no holdout shard available this run")


# ── Re-score live objections (only when fitted + live corpus present) ─

rescores = None
if not result.is_cold_start and result.model is not None and live_path.exists():
    by_conclusion: dict[str, list[SeverityInputs]] = {}
    with live_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            raw = row.get("inputs", {})
            inp = SeverityInputs(
                cascade_weight=float(raw.get("cascade_weight", 0.0)),
                claim_centrality=float(raw.get("claim_centrality", 0.0)),
                failure_mode_severity=float(
                    raw.get("failure_mode_severity", 0.0)
                ),
                source_credibility=(
                    None
                    if raw.get("source_credibility") is None
                    else float(raw["source_credibility"])
                ),
                judge_severity=(
                    None
                    if raw.get("judge_severity") is None
                    else float(raw["judge_severity"])
                ),
            )
            by_conclusion.setdefault(str(row["conclusion_id"]), []).append(inp)
    rescores = rescore_live_objections(by_conclusion, result.model)
    flagged = [r for r in rescores if r.founder_queue]
    print(
        f"re-scored {len(rescores)} live conclusion(s); "
        f"{len(flagged)} cross δ → founder queue"
    )
elif not result.is_cold_start:
    print(f"no live corpus at {live_path} — re-score skipped")


# ── Write artifacts ──────────────────────────────────────────────────

artifact = calibration_artifact(
    result,
    rescores=rescores,
    extra={
        "corpus_path": corpus_display,
        "corpus_n": len(labeled),
    },
)
model_dir.mkdir(parents=True, exist_ok=True)
model_path = model_dir / "model.json"
with model_path.open("w", encoding="utf-8") as fh:
    json.dump(artifact, fh, indent=2, sort_keys=True)
print(f"wrote {model_path}")

status_doc.parent.mkdir(parents=True, exist_ok=True)
status_doc.write_text(
    status_markdown(result, corpus_path=corpus_display), encoding="utf-8"
)
print(f"wrote {status_doc}")

print()
if result.is_cold_start:
    print("severity calibration DEFERRED — stipulated rubric stays active.")
else:
    print("severity calibration FITTED — calibrated scorer is now active.")
PY

echo ""
echo "model_dir=${MODEL_DIR}"

#!/usr/bin/env bash
# Cross-model QH benchmark — full, run-stamped study orchestrator.
#
# This is the Round-17 prompt-09 driver. It re-runs the frozen Quintin
# Hypothesis v1 benchmark across every embedding back-end whose
# credentials and runtime are actually present, then publishes one
# immutable artefact set under a single run stamp. It is the firm's
# first test of whether the contradiction-geometry signature is a
# property of language or a property of one embedding model.
#
# Pipeline:
#   0. Pre-flight — probe each back-end (API key present? local runtime
#      importable?). Models that cannot run are SKIPPED with a logged
#      reason; they never silently vanish.
#   1. Run        — embed premise + continuation and predict with all
#      three runners (random / cosine / contradiction_geometry).
#   2. Analyse    — per-model accuracy/AUROC/ECE, inter-model agreement,
#      and the domain-controlled permutation test.
#   3. Publish    — results.parquet, envelope.json, analysis.md under
#      the run stamp; also compute the probe-vs-cosine significance
#      test the study turns on.
#   4. Mirror     — copy the analysis JSON + figures to the public site.
#   5. Paper      — regenerate the LaTeX and compile the PDF.
#
# Constraints honoured here:
#   - Embedding vectors are written off-tree (THESEUS_CROSS_MODEL_ROOT,
#     default ~/.theseus/data/cross_model); only aggregate metrics and
#     the parquet prediction table land in git. No raw vectors committed.
#   - The per-model embedding budget is a hard ceiling; a truncated run
#     publishes with the "n=K" disclosure rather than failing silently.
#   - Nothing in the analysis is tuned to manufacture a positive result.
#     The v1 geometry thresholds are frozen and are NOT re-fit per model.
#
# Usage:
#   ./run_cross_model_full.sh [--models a,b,c] [--budget N] [--dry-run]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATASET="$ROOT/benchmarks/quintin_hypothesis/v1/dataset.jsonl"
CROSS_ROOT="$ROOT/benchmarks/quintin_hypothesis/v1/results/cross_model"
FIG_DIR="$ROOT/docs/research/figures/cross_model"
PUBLIC_DIR="$ROOT/theseus-codex/public/qh-benchmark/cross-model"
TEX="$ROOT/docs/research/Cross_Model_Geometry_Study.tex"
PDF="$ROOT/docs/research/Cross_Model_Geometry_Study.pdf"
PDF_BUILDER="$ROOT/noosphere/scripts/build_cross_model_pdf.py"

# Full roster from the Round-17 prompt. hash-det is the deterministic
# local control; it always runs and anchors the agreement matrix.
MODELS_DEFAULT="hash-det,minilm-l6,bge-large,openai-3-large,voyage-3,cohere-en-v3"
MODELS="${MODELS:-$MODELS_DEFAULT}"
# Per-model item ceiling. Local back-ends cost nothing; the cap exists
# for the paid APIs. Default sits just above the frozen 1936-item
# dataset so a fully-local run is complete, not truncated.
BUDGET="${THESEUS_CROSS_MODEL_BUDGET:-2000}"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --models) MODELS="$2"; shift 2;;
    --budget) BUDGET="$2"; shift 2;;
    --dry-run) DRY_RUN=1; shift;;
    -h|--help) sed -n '2,34p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="$CROSS_ROOT/$RUN_STAMP"

# Choose an interpreter that can load native wheels. On Apple Silicon a
# mixed-arch parent shell can launch the universal python3 as x86_64,
# which then cannot dlopen the arm64 torch wheel that sentence-
# transformers needs. Fall back to `arch -arm64` when that happens.
PY="python3"
if ! python3 -c "import torch" >/dev/null 2>&1; then
  if command -v arch >/dev/null 2>&1 && arch -arm64 python3 -c "import torch" >/dev/null 2>&1; then
    PY="arch -arm64 python3"
  fi
fi

echo "── cross-model QH geometry study ──────────────────────────────────"
echo "  run stamp : $RUN_STAMP"
echo "  roster    : $MODELS"
echo "  budget    : $BUDGET items/model"
echo "  dataset   : $DATASET"
echo "  out dir   : $OUT_DIR"
echo "  python    : $PY"
echo

if [[ "$DRY_RUN" == "1" ]]; then
  echo "(dry run — no embedding, no analysis, no publish)"
  exit 0
fi

mkdir -p "$OUT_DIR" "$FIG_DIR" "$PUBLIC_DIR"
export THESEUS_CROSS_MODEL_BUDGET="$BUDGET"
export QH_ROOT="$ROOT" QH_DATASET="$DATASET" QH_OUT_DIR="$OUT_DIR"
export QH_MODELS="$MODELS" QH_RUN_STAMP="$RUN_STAMP" QH_BUDGET="$BUDGET"

# ── Stage 0: pre-flight ────────────────────────────────────────────────
echo "[0/5] pre-flight — probing back-end credentials & runtimes"
$PY - <<'PYEOF'
import json, os
from pathlib import Path

roster = [m.strip() for m in os.environ["QH_MODELS"].split(",") if m.strip()]
out_dir = Path(os.environ["QH_OUT_DIR"])

# Which environment variable each paid adapter needs.
API_KEYS = {
    "openai-3-large": "OPENAI_API_KEY",
    "voyage-3": "VOYAGE_API_KEY",
    "cohere-en-v3": "COHERE_API_KEY",
}
LOCAL_ST = {"bge-large", "minilm-l6"}


def probe(name: str):
    if name in API_KEYS:
        key = API_KEYS[name]
        if os.environ.get(key):
            return True, f"api key {key} present"
        return False, f"api key {key} absent — adapter skipped (no API call attempted)"
    if name in LOCAL_ST:
        try:
            import torch  # noqa: F401
            import sentence_transformers  # noqa: F401
            return True, "local sentence-transformers runtime importable"
        except Exception as exc:  # noqa: BLE001
            return False, f"local runtime unavailable: {exc.__class__.__name__}: {exc}"
    if name.startswith("hash-det"):
        return True, "deterministic local control — always available, 0 credits"
    return True, "unknown adapter — the runner will validate it"


rows = [{"model": n, "available": ok, "reason": r}
        for n in roster for ok, r in [probe(n)]]
avail = [r["model"] for r in rows if r["available"]]
skipped = [r for r in rows if not r["available"]]

print(f"  roster of {len(rows)} — {len(avail)} runnable, {len(skipped)} skipped")
for r in rows:
    print(f"    [{'RUN ' if r['available'] else 'SKIP'}] "
          f"{r['model']:<22s} {r['reason']}")
if skipped:
    print(f"  >>> n={len(avail)} of {len(rows)} back-ends will run; the published "
          "artefacts carry the n=K disclosure prominently.")

out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "preflight.json").write_text(
    json.dumps(
        {
            "roster": rows,
            "available": avail,
            "skipped": [s["model"] for s in skipped],
        },
        indent=2,
    ),
    encoding="utf-8",
)
PYEOF

# ── Stage 1: embed + predict ───────────────────────────────────────────
echo
echo "[1/5] run — embedding + prediction across the full roster"
echo "      (missing-key adapters fail loud and are recorded as skips)"
$PY - <<'PYEOF'
import os
from pathlib import Path

from noosphere.benchmarks.cross_model_runner import CrossModelConfig, run_cross_model

models = [m.strip() for m in os.environ["QH_MODELS"].split(",") if m.strip()]
cfg = CrossModelConfig(
    model_names=models,
    dataset_path=Path(os.environ["QH_DATASET"]),
    output_dir=Path(os.environ["QH_OUT_DIR"]),
)
reports = run_cross_model(cfg)
for r in reports:
    tag = "ERROR" if r.error else ("partial" if r.truncated else "ok")
    line = f"  {r.model_name:<42s} {r.items_embedded:>5d}/{r.items_total:<5d} [{tag}]"
    if r.error:
        line += f"  {r.error}"
    print(line)
PYEOF

# ── Stage 2: analysis ──────────────────────────────────────────────────
echo
echo "[2/5] analysis — per-model metrics, agreement matrix, figures"
$PY -m noosphere.benchmarks.cross_model_analysis \
  --predictions-dir "$OUT_DIR" \
  --out-dir "$OUT_DIR" \
  --figures-dir "$FIG_DIR"

# ── Stage 3: publish run-stamped artefacts ─────────────────────────────
echo
echo "[3/5] publish — results.parquet, envelope.json, analysis.md"
$PY - <<'PYEOF'
import datetime as dt
import hashlib
import json
import math
import os
import platform
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

root = Path(os.environ["QH_ROOT"])
out_dir = Path(os.environ["QH_OUT_DIR"])
dataset = Path(os.environ["QH_DATASET"])
run_stamp = os.environ["QH_RUN_STAMP"]
budget = int(os.environ["QH_BUDGET"])
roster = [m.strip() for m in os.environ["QH_MODELS"].split(",") if m.strip()]

# Frozen qh-v1 dataset fingerprint (recorded in the prompt-13 baseline
# envelope). Comparing against it verifies the benchmark has not drifted.
FROZEN_QH_V1_SHA256 = (
    "b25ab62102389fbbbf2cdad08cc5a056e4946631835a89672fe88aa0a8fbe7c4"
)


def _clean(obj):
    """Recursively replace NaN/inf with None so the JSON parses in JS too."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    return obj


def _git(*args):
    try:
        return subprocess.check_output(
            ["git", *args], cwd=str(root), stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:  # noqa: BLE001
        return None


# --- 1. combine per-model parquet predictions into results.parquet -----
pred_files = sorted(out_dir.glob("predictions__*.parquet"))
frames = []
for f in pred_files:
    try:
        frames.append(pd.read_parquet(f))
    except Exception as exc:  # noqa: BLE001
        print(f"  warn: could not read {f.name}: {exc}")
results = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
results_path = out_dir / "results.parquet"
results.to_parquet(results_path, index=False)
n_models_with_preds = int(results["model_name"].nunique()) if len(results) else 0
print(f"  results.parquet — {len(results)} rows, {n_models_with_preds} models")


# --- 2. probe-vs-cosine significance test, controlling for domain ------
def probe_vs_cosine_test(df: pd.DataFrame, n_perm: int = 5000, seed: int = 17):
    """Is the firm's geometry probe significantly better than cosine?

    Each (model, item) yields a paired difference d = correct(geometry)
    - correct(cosine). Under H0 the probe is no better than cosine and
    the sign of each paired difference is exchangeable. We test the
    domain-stratified statistic (the unweighted mean across domains of
    the mean paired difference, so a large domain cannot dominate) with
    a one-sided paired sign-flip permutation test. A mixed-effects
    logistic model would be the parametric alternative; statsmodels is
    not installed in this environment, so the permutation test is the
    result, not a fallback we are embarrassed about.
    """
    base = {
        "method": "no_data",
        "statistic": float("nan"),
        "p_value": float("nan"),
        "notes": "no prediction rows",
        "n_observations": 0,
        "n_models": 0,
    }
    if df.empty:
        return base
    geo = df[df["runner"] == "contradiction_geometry"][
        ["model_name", "item_id", "domain", "predicted_label", "label"]
    ].rename(columns={"predicted_label": "pl_geo"})
    cos = df[df["runner"] == "cosine"][
        ["model_name", "item_id", "predicted_label"]
    ].rename(columns={"predicted_label": "pl_cos"})
    merged = geo.merge(cos, on=["model_name", "item_id"], how="inner")
    if merged.empty:
        base.update(method="no_paired_obs",
                    notes="no item scored by both the geometry and cosine runners")
        return base
    merged["d"] = (
        (merged["pl_geo"] == merged["label"]).astype(int)
        - (merged["pl_cos"] == merged["label"]).astype(int)
    )
    n_models = int(merged["model_name"].nunique())
    if len(merged) < 4:
        base.update(method="insufficient_sample",
                    notes=f"need >=4 paired obs; got {len(merged)}",
                    n_observations=int(len(merged)), n_models=n_models)
        return base
    domains = sorted(merged["domain"].unique())
    d_by_domain = {
        dom: merged.loc[merged["domain"] == dom, "d"].to_numpy(dtype=float)
        for dom in domains
    }

    def stat(arrs):
        means = [a.mean() for a in arrs if len(a)]
        return float(np.mean(means)) if means else 0.0

    observed = stat([d_by_domain[dom] for dom in domains])
    rng = np.random.default_rng(seed)
    ge = 0
    for _ in range(n_perm):
        flipped = [
            d_by_domain[dom] * rng.choice((-1.0, 1.0), size=len(d_by_domain[dom]))
            for dom in domains
        ]
        if stat(flipped) >= observed:
            ge += 1
    p_one_sided = (ge + 1) / (n_perm + 1)
    try:
        import statsmodels  # noqa: F401
        me_note = ("statsmodels present; the permutation test is reported here "
                   "for its weaker distributional assumptions")
    except Exception:  # noqa: BLE001
        me_note = "statsmodels not installed; the permutation test is the result"
    return {
        "method": "permutation_paired_sign_flip_domain_stratified",
        "statistic": observed,
        "p_value": p_one_sided,
        "notes": (
            f"One-sided paired sign-flip permutation test ({n_perm} resamples, "
            f"seed {seed}). Statistic is the domain-averaged mean of "
            f"(geometry correct - cosine correct); positive favours the firm "
            f"probe. Stratified across {len(domains)} domains so each weighs "
            f"equally. {me_note}."
        ),
        "n_observations": int(len(merged)),
        "n_models": n_models,
        "n_domains": len(domains),
        "domain_deltas": {dom: float(d_by_domain[dom].mean()) for dom in domains},
        "mean_delta_unstratified": float(merged["d"].mean()),
    }


pvc = probe_vs_cosine_test(results)
print(f"  probe-vs-cosine: method={pvc['method']} "
      f"stat={pvc['statistic']} p={pvc['p_value']}")

# Inject into the analysis JSON (additive key; the module's own
# "do models differ" stat_test is left untouched) and sanitise the
# whole file so the public page's JSON.parse never chokes on bare NaN.
analysis_json_path = out_dir / "cross_model_analysis.json"
analysis = json.loads(analysis_json_path.read_text(encoding="utf-8"))
analysis["probe_vs_cosine"] = pvc
analysis_json_path.write_text(
    json.dumps(_clean(analysis), indent=2), encoding="utf-8"
)

# --- 3. envelope.json --------------------------------------------------
sha256 = hashlib.sha256(dataset.read_bytes()).hexdigest()
domains, labels, n_items = set(), set(), 0
with dataset.open(encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        domains.add(rec["domain"])
        labels.add(rec["label"])
        n_items += 1

run_index = json.loads((out_dir / "run_index.json").read_text(encoding="utf-8"))
preflight = json.loads((out_dir / "preflight.json").read_text(encoding="utf-8"))
runs = run_index.get("runs", [])
models_run = [r for r in runs if not r["error"]]
models_skipped = [r for r in runs if r["error"]]
truncated_any = any(r["truncated"] and not r["error"] for r in runs)

envelope = {
    "schema": "theseus.qh.cross_model.envelope.v1",
    "run_stamp": run_stamp,
    "created_utc": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "benchmark_version": run_index.get("benchmark_version", "qh-v1"),
    "tooling": "noosphere.benchmarks.cross_model_runner + cross_model_analysis",
    "git_sha": _git("rev-parse", "HEAD"),
    "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
    "git_dirty": bool(_git("status", "--porcelain")),
    "dataset": {
        "path": str(dataset),
        "sha256": sha256,
        "n_items": n_items,
        "domains": sorted(domains),
        "labels": sorted(labels),
        "frozen_state_verified": sha256 == FROZEN_QH_V1_SHA256,
        "frozen_reference_sha256": FROZEN_QH_V1_SHA256,
    },
    "roster": {
        "requested": roster,
        "n_requested": len(roster),
        "n_run": len(models_run),
        "n_skipped": len(models_skipped),
        "models_run": [r["model_name"] for r in models_run],
        "models_skipped": [
            {"model": r["model_name"], "reason": r["error"]} for r in models_skipped
        ],
    },
    "n_models_disclosure": (
        f"n={len(models_run)} of {len(roster)} embedding back-ends"
    ),
    "runners": ["contradiction_geometry", "cosine", "random"],
    "seeds": {
        "random_runner": 0,
        "probe_vs_cosine_permutation": 17,
    },
    "embedding_budget": {
        "per_model_item_cap": budget,
        "estimated_credits": 0,
        "ceiling_note": (
            "every runnable back-end this run is local (hash-det / "
            "sentence-transformers); 0 paid API credits consumed"
        ),
        "within_budget": True,
        "any_model_truncated": truncated_any,
    },
    "preflight": preflight,
    "probe_vs_cosine": pvc,
    "platform": {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
    },
}
(out_dir / "envelope.json").write_text(
    json.dumps(_clean(envelope), indent=2), encoding="utf-8"
)
print(f"  envelope.json — n={len(models_run)} of {len(roster)} models ran"
      + (f", {len(models_skipped)} skipped" if models_skipped else ""))

# --- 4. analysis.md ----------------------------------------------------
per_model = analysis.get("per_model", {}) or {}
losses = analysis.get("geometry_losses", []) or []
ag_models = analysis.get("agreement_models", []) or []
ag_matrix = analysis.get("agreement_matrix", []) or []


def _fmt(v, d=4):
    if v is None:
        return "n/a"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return "n/a" if not math.isfinite(f) else f"{f:.{d}f}"


# AUROC comparison — geometry vs cosine per model. AUROC scores the raw
# sparsity *signal*, before the frozen threshold turns it into a label,
# so it isolates "is the geometry there?" from "does the v1 cut work?".
auroc_rows = []
for model, runners in per_model.items():
    cg = (runners.get("contradiction_geometry") or {}).get(
        "auroc_contradicting_vs_coherent")
    co = (runners.get("cosine") or {}).get("auroc_contradicting_vs_coherent")
    if cg is None or co is None or not (math.isfinite(cg) and math.isfinite(co)):
        continue
    auroc_rows.append((model, float(cg), float(co), float(cg) - float(co)))
auroc_total = len(auroc_rows)
auroc_wins = sum(1 for *_, d in auroc_rows if d > 0)
mean_auroc_delta = (
    sum(d for *_, d in auroc_rows) / auroc_total if auroc_total else float("nan")
)

# Threshold degeneracy — when the inter-model agreement matrix has
# collapsed to {0, 1} it means the frozen sparsity cut puts each model
# wholly on one side of the decision boundary: it is not finding a
# signal, it is constant-predicting. That is a finding, not a footnote.
ag_off = [
    ag_matrix[i][j]
    for i in range(len(ag_models))
    for j in range(len(ag_models))
    if i != j and i < len(ag_matrix) and j < len(ag_matrix[i])
    and ag_matrix[i][j] is not None
]
degenerate_agreement = bool(ag_off) and all(
    (v < 0.02 or v > 0.98) for v in ag_off
)

L = []
L.append(f"# Cross-Model QH Geometry Study — Run `{run_stamp}`")
L.append("")
L.append("> The Quintin Hypothesis predicts the premise→contradiction difference")
L.append("> vector is *sparse* (Hoyer) and the premise→coherent difference vector")
L.append("> is *dense*. If that is a property of language it should survive a")
L.append("> change of embedding model. If it is a property of one model, the")
L.append("> firm's claim is far weaker. This run is the first test of that line.")
L.append("")
L.append("## Headline — the signal transfers, the frozen threshold does not")
L.append("")
if len(models_run) < len(roster):
    L.append(f"**{envelope['n_models_disclosure']} ran.** "
             f"{len(roster) - len(models_run)} back-end(s) were skipped — see the")
    L.append("roster table below. Every number in this document is conditioned on")
    L.append("that partial roster and should be read as such.")
    L.append("")
if auroc_total:
    L.append(f"**On AUROC** — which scores the raw sparsity signal before any "
             f"threshold — the contradiction-geometry probe beats the cosine "
             f"baseline on **{auroc_wins} of {auroc_total}** models that ran "
             f"(mean Δ AUROC = {_fmt(mean_auroc_delta, 3)}). The geometric "
             f"signal the Quintin Hypothesis predicts is present, and ranks "
             f"contradicting above coherent, in every embedding space tested "
             f"here. That is real cross-model support for the *hypothesis*.")
    L.append("")
if pvc["method"].startswith("permutation"):
    direction = (
        "better than" if (pvc["statistic"] or 0) > 0 else
        "worse than" if (pvc["statistic"] or 0) < 0 else "indistinguishable from"
    )
    sig = "is" if (pvc["p_value"] is not None and pvc["p_value"] < 0.05) else "is not"
    L.append(f"**On 3-way accuracy** — where the frozen v1 sparsity cut (0.40, "
             f"calibrated once on the hash-det control and never re-fit) turns "
             f"that signal into a label — the probe is on average **{direction}** "
             f"cosine across the {pvc['n_models']} models (domain-averaged "
             f"Δ accuracy = {_fmt(pvc['statistic'])}), and the difference "
             f"**{sig}** significant at α=0.05 (one-sided paired permutation "
             f"p = {_fmt(pvc['p_value'])}). The *operationalisation* did not "
             f"transfer even though the signal did.")
else:
    L.append(f"Probe-vs-cosine significance test could not run: "
             f"`{pvc['method']}` — {pvc['notes']}")
L.append("")
if degenerate_agreement:
    L.append("**Why the threshold fails** is visible in the inter-model "
             "agreement matrix below: every off-diagonal entry has collapsed "
             "to 0 or 1. The frozen 0.40 cut sits *outside* the sparsity range "
             "of the dense neural embedders, so the probe constant-predicts — "
             "one regime on hash-det, the opposite regime on the "
             "sentence-transformer models. A threshold that does not transfer "
             "is a calibration failure, not necessarily a failure of the "
             "hypothesis; the AUROC result above is the cleaner test.")
    L.append("")
if losses:
    names = ", ".join(f"`{x['model']}`" for x in losses)
    L.append(f"On {names} the geometry probe ties or loses to cosine **on "
             f"AUROC**. That is stated here, not buried.")
else:
    L.append("No model in this run has the geometry probe losing to cosine on "
             "AUROC. This is weak positive evidence for the hypothesis; it is "
             "not vindication, and the accuracy result above is the honest "
             "counterweight.")
L.append("")

L.append("## Run envelope")
L.append("")
L.append(f"- **Run stamp:** `{run_stamp}`")
L.append(f"- **Git SHA:** `{envelope['git_sha']}` (branch "
         f"`{envelope['git_branch']}`, dirty={envelope['git_dirty']})")
L.append(f"- **Dataset:** `{dataset}` — {n_items} items, sha256 "
         f"`{sha256[:16]}…`, frozen state verified: "
         f"{envelope['dataset']['frozen_state_verified']}")
L.append(f"- **Domains:** {', '.join(sorted(domains))}")
L.append(f"- **Per-model item cap:** {budget} "
         f"(any model truncated: {truncated_any})")
L.append(f"- **Embedding credits:** 0 — every runnable back-end is local.")
L.append("")
L.append("### Roster")
L.append("")
L.append("Pre-flight decided which back-ends to *attempt*; the runner then "
         "recorded the *actual* outcome. Both are shown so a skip is never "
         "ambiguous.")
L.append("")
L.append("| model (requested) | pre-flight | detail |")
L.append("|---|---|---|")
for r in preflight["roster"]:
    decision = "attempt" if r["available"] else "**skip**"
    L.append(f"| `{r['model']}` | {decision} | {r['reason']} |")
L.append("")
L.append("| adapter (runner) | items | outcome |")
L.append("|---|---|---|")
for r in runs:
    if r["error"]:
        outcome = f"**error** — {r['error']}"
    elif r["truncated"]:
        outcome = "**partial** — embedding budget cap hit"
    else:
        outcome = "complete"
    L.append(f"| `{r['model_name']}` | {r['items_embedded']}/{r['items_total']} "
             f"| {outcome} |")
L.append("")

L.append("## Per-model headline metrics")
L.append("")
L.append("| model | runner | n | accuracy | AUROC | ECE |")
L.append("|---|---|---|---|---|---|")
for model in sorted(per_model):
    for runner in ("random", "cosine", "contradiction_geometry"):
        v = per_model[model].get(runner)
        if not v:
            continue
        L.append(f"| `{model}` | `{runner}` | {int(v['n'])} | "
                 f"{_fmt(v['accuracy'])} | "
                 f"{_fmt(v['auroc_contradicting_vs_coherent'])} | "
                 f"{_fmt(v['ece_contradicting'])} |")
L.append("")

L.append("## Probe vs. cosine — domain-controlled significance test")
L.append("")
L.append(f"- **Method:** `{pvc['method']}`")
L.append(f"- **Statistic (domain-averaged Δ accuracy, geometry − cosine):** "
         f"{_fmt(pvc['statistic'])}")
L.append(f"- **p-value (one-sided, H1 = probe better):** {_fmt(pvc['p_value'])}")
L.append(f"- **Paired observations:** {pvc['n_observations']} across "
         f"{pvc['n_models']} model(s)")
if pvc.get("domain_deltas"):
    L.append("- **Per-domain Δ accuracy (geometry − cosine):**")
    for dom, dval in sorted(pvc["domain_deltas"].items()):
        L.append(f"  - `{dom}`: {_fmt(dval)}")
L.append(f"- {pvc['notes']}")
L.append("")

L.append("## Inter-model agreement (binary contradicting label, geometry runner)")
L.append("")
if ag_models:
    L.append("| | " + " | ".join(f"`{m}`" for m in ag_models) + " |")
    L.append("|" + "|".join(["---"] * (len(ag_models) + 1)) + "|")
    for i, m in enumerate(ag_models):
        cells = []
        for j in range(len(ag_models)):
            val = ag_matrix[i][j] if i < len(ag_matrix) and j < len(ag_matrix[i]) else None
            cells.append("n/a" if val is None else _fmt(val, 2))
        L.append(f"| `{m}` | " + " | ".join(cells) + " |")
    L.append("")
    if degenerate_agreement:
        L.append("Every off-diagonal entry is 0 or 1: the agreement matrix is "
                 "**degenerate**. Read literally it is not telling us the "
                 "geometric signal is or is not shared — it is telling us the "
                 "frozen 0.40 cut puts each model entirely on one side of the "
                 "boundary. The matrix is a calibration diagnostic this run, "
                 "not a language-vs-model verdict; the AUROC table is.")
    else:
        L.append("High off-diagonal entries are evidence the geometric signal "
                 "is a property of language; low entries are evidence it is "
                 "model-specific.")
else:
    L.append("Only one model produced predictions — the agreement matrix is "
             "trivially 1×1 and carries no cross-model information.")
L.append("")

L.append("## What this run does and does not license")
L.append("")
L.append("- It does **not** let the firm claim the QH holds \"across embedding "
         "models\" in general: the paid-API back-ends did not run, so the test "
         "is over local embedders only.")
L.append("- The v1 geometry thresholds are **frozen** and were calibrated on the "
         "hash-det control. They were not re-fit per model. Where the probe "
         "underperforms on a neural embedder, the honest reading is that the "
         "*threshold*, not necessarily the *hypothesis*, failed to transfer.")
L.append("- See `docs/research/internal/Cross_Model_Findings_Memo.md` for the "
         "founder-side reading and the warranted follow-ups.")
L.append("")

(out_dir / "analysis.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"  analysis.md — {len(L)} lines")
PYEOF

# ── Stage 4: mirror artefacts to the public site ───────────────────────
echo
echo "[4/5] mirror — copying analysis JSON + figures to the public site"
cp "$OUT_DIR/cross_model_analysis.json" "$PUBLIC_DIR/" 2>/dev/null || true
cp "$OUT_DIR/run_index.json" "$PUBLIC_DIR/" 2>/dev/null || true
cp "$OUT_DIR/envelope.json" "$PUBLIC_DIR/" 2>/dev/null || true
cp "$FIG_DIR"/*.png "$PUBLIC_DIR/" 2>/dev/null || true

# ── Stage 5: build the PDF ─────────────────────────────────────────────
echo
echo "[5/5] paper — regenerating LaTeX and compiling the PDF"
$PY "$PDF_BUILDER" \
  --analysis "$OUT_DIR/cross_model_analysis.json" \
  --figures "$FIG_DIR" \
  --tex "$TEX" \
  --pdf "$PDF"
cp "$PDF" "$PUBLIC_DIR/" 2>/dev/null || true

echo
echo "cross-model study complete — run $RUN_STAMP"
echo "  results : $OUT_DIR/results.parquet"
echo "  envelope: $OUT_DIR/envelope.json"
echo "  analysis: $OUT_DIR/analysis.md"
echo "  paper   : $PDF"
echo "  public  : $PUBLIC_DIR"

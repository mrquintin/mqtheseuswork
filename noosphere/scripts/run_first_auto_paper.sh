#!/usr/bin/env bash
# Produce the firm's first auto-generated research papers (Round 17
# prompt 29 generator, "actually run it" step).
#
# The cluster selector, the paper generator, the founder triage tab,
# and the signed-publication path already exist. This script is the
# step that turns that code into real artifacts on disk: it ranks the
# firm's conclusion clusters by maturity, drafts the top three as
# .tex + .pdf, runs an internal review on each, writes the founder a
# candidate memo, and verifies the signed-publication path end to end
# on a synthetic paper.
#
# Stages:
#   1. Rank       — paper_clustering.rank_clusters over the full
#      conclusion set. Clusters are scored by maturity: resolved
#      forecast count, principle backing, then size. The top three
#      are the publish candidates; the founder picks which (if any)
#      ships.
#   2. Generate   — for each top-3 cluster, paper_generator.generate_
#      paper writes docs/research/auto/<slug>/paper.tex and, when
#      pdflatex is on PATH, paper.pdf. Every numeric claim carries a
#      \rowref{...} marker that resolves to a database row; a number
#      the generator could not back to a source prints a \todomark,
#      never an estimate.
#   3. Review     — the peer-review swarm runs over each draft's
#      conclusions, objections are severity-weighted, and the MQS
#      composite is recomputed with the objection penalty folded in.
#      A draft below the MQS publish bar is flagged "not ready" with
#      an explicit weakness list. The result is written into the
#      draft's paper.json so the triage tab can show it.
#   4. Memo       — docs/research/internal/Auto_Paper_Candidates_<stamp>.md
#      summarizes the three drafts: cluster shape, length, top three
#      strengths, top three weaknesses, recommended action.
#   5. Signing    — a synthetic paper is run through the signed-
#      publication path (sign -> verify ok -> mutate -> verify fails)
#      to prove the path works before any real paper is approved.
#
# What this script does NOT do — every one of these is a founder
# action, never the agent's:
#   * It does not publish. Drafts land in docs/research/auto/ for
#     triage; promotion to docs/research/published/ is a founder step.
#   * It does not flip review_state. The internal review is advisory.
#   * It does not announce anything externally. The first auto-paper
#     does not auto-post to social; the founder authorizes any
#     external announcement explicitly.
#
# The byline is honest and non-removable: every draft carries the
# "machine-drafted, founder-reviewed" disclosure label in its .tex
# body, its paper.json sidecar, and the public page template.
#
# Run modes:
#   --demo-corpus  (default) seed an embedded, frozen verification
#                  corpus into a scratch SQLite store and draft from
#                  it. This is the committed-artifact path: the four
#                  seeded clusters are deterministic, so re-running
#                  refreshes docs/research/auto/ cleanly.
#   --store        draft from the live noosphere store instead. If the
#                  store has no mature cluster the run logs it and
#                  exits 0 (nothing to draft is not a failure).
#
# Usage:
#   ./run_first_auto_paper.sh [--demo-corpus | --store]
#       [--out-root DIR] [--memo-dir DIR] [--top-n N] [--no-pdf]
#
#   --out-root DIR   Where draft slug dirs land. Default docs/research/auto.
#   --memo-dir DIR   Where the candidate memo lands. Default
#                    docs/research/internal.
#   --top-n N        How many top clusters to draft. Default 3.
#   --no-pdf         Skip pdflatex; emit only .tex (the .tex is the
#                    authoritative artifact, the PDF is a build product).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/noosphere:${PYTHONPATH:-}"

PY="${PYTHON:-python3}"
CORPUS_MODE="demo"
OUT_ROOT="$ROOT/docs/research/auto"
MEMO_DIR="$ROOT/docs/research/internal"
TOP_N="3"
BUILD_PDF="1"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --demo-corpus) CORPUS_MODE="demo"; shift;;
    --store) CORPUS_MODE="store"; shift;;
    --out-root) OUT_ROOT="$2"; shift 2;;
    --memo-dir) MEMO_DIR="$2"; shift 2;;
    --top-n) TOP_N="$2"; shift 2;;
    --no-pdf) BUILD_PDF="0"; shift;;
    -h|--help) sed -n '2,84p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

# AUTO_PAPER_STAMP pins the run stamp (and therefore the memo
# filename) so a re-run overwrites cleanly instead of leaving a trail
# of near-identical memos.
STAMP="${AUTO_PAPER_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT_ROOT" "$MEMO_DIR"

echo "=== First auto-paper run ==="
echo "  root       : $ROOT"
echo "  run stamp  : $STAMP"
echo "  corpus     : $CORPUS_MODE"
echo "  out root   : $OUT_ROOT"
echo "  memo dir   : $MEMO_DIR"
echo "  top-n      : $TOP_N"
echo "  build pdf  : $BUILD_PDF"
echo

AUTO_PAPER_MODE="$CORPUS_MODE" \
AUTO_PAPER_STAMP="$STAMP" \
AUTO_PAPER_OUT_ROOT="$OUT_ROOT" \
AUTO_PAPER_MEMO_DIR="$MEMO_DIR" \
AUTO_PAPER_TOP_N="$TOP_N" \
AUTO_PAPER_BUILD_PDF="$BUILD_PDF" \
"$PY" - <<'PYEOF'
"""Driver: rank clusters, draft the top N, review them, write the
founder memo, verify the signing path. Stages are tightly coupled
(the cluster ranked in stage 1 is what stages 2-3 draft and review),
so they run in one process."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

# The peer-review swarm and the MQS scorer log a steady stream of
# benign warnings on a scratch store (no ledger store wired, no real
# embeddings for the geometric reviewer). None of it changes the
# result; quiet it so the stage log stays readable.
logging.disable(logging.WARNING)

# LaTeX build by-products pdflatex drops next to paper.pdf. The .tex
# and .pdf are the artifacts; these are not.
_LATEX_BYPRODUCTS = (
    ".aux",
    ".log",
    ".out",
    ".fls",
    ".fdb_latexmk",
    ".synctex.gz",
    ".toc",
)


def _clean_latex_byproducts(tex_path: Path) -> None:
    for suffix in _LATEX_BYPRODUCTS:
        candidate = tex_path.with_suffix(suffix)
        if candidate.exists():
            candidate.unlink()

from noosphere.docgen.paper_clustering import rank_clusters
from noosphere.docgen.paper_generator import (
    DISCLOSURE_LABEL,
    MQS_PUBLISH_THRESHOLD,
    attach_review_to_sidecar,
    generate_paper,
    paper_canonical_input,
    review_paper_cluster,
)

MODE = os.environ["AUTO_PAPER_MODE"]
STAMP = os.environ["AUTO_PAPER_STAMP"]
OUT_ROOT = Path(os.environ["AUTO_PAPER_OUT_ROOT"])
MEMO_DIR = Path(os.environ["AUTO_PAPER_MEMO_DIR"])
TOP_N = int(os.environ["AUTO_PAPER_TOP_N"])
BUILD_PDF = os.environ["AUTO_PAPER_BUILD_PDF"] == "1"
NOW = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
ORG_ID = "org_first_auto_paper"


def log(msg: str) -> None:
    print(msg, flush=True)


# ── Demo corpus ──────────────────────────────────────────────────────
#
# An embedded, frozen verification corpus: four conclusion clusters the
# firm keeps re-deriving, each with a shared methodology root, resolved
# forecasts that touch it, an extracted-from source for the references
# section, and a seeded peer-review report for the discussion section.
# The clusters are deliberately uneven in maturity so stage 1's ranking
# has something real to sort, and one cluster (representational-
# geometry) deliberately ships with no registered failure modes so the
# stage-3 review has a genuine "not ready" draft to flag.
#
# A real run (--store) reads the live noosphere store instead; this
# corpus only backs the committed --demo-corpus artifacts.

# (cluster_key, methodology, [conclusion specs], n_forecasts)
_DEMO_CLUSTERS = [
    {
        "key": "calibration-over-coverage",
        "methodology": {
            "pattern_type": "bayesian-update",
            "title": "Calibrated narrowing under uncertainty",
            "summary": (
                "Resolve a broad question into the narrowest claim the "
                "evidence actually licenses, then widen only as resolved "
                "forecasts justify it."
            ),
            "reasoning_moves": [
                "anchor on the base rate before reading the signal",
                "prefer the narrow calibrated claim to the broad confident one",
                "widen the claim only when a resolved forecast licenses it",
            ],
            "transfer_targets": [
                "adjacent forecast markets",
                "confidence-tier assignment",
            ],
            "assumptions": [
                "signals are conditionally independent given the regime",
                "the base rate is stationary over the forecast horizon",
            ],
            "failure_modes": [
                "regime change invalidates the stationarity assumption",
                "common-mode bias across correlated signals",
                "narrowing past the point the evidence supports",
            ],
        },
        "conclusions": [
            {
                "text": (
                    "A calibrated narrow claim beats a confident broad claim "
                    "when the firm must commit; we will revisit if a resolved "
                    "forecast contradicts the narrowing."
                ),
                "principles": ["principle-calibration", "principle-narrowing"],
            },
            {
                "text": (
                    "Reliability priors should decay toward the base rate "
                    "when the regime shifts, by 2026 Q4 at the latest."
                ),
                "principles": ["principle-calibration", "principle-regime-decay"],
            },
            {
                "text": (
                    "When forced to choose, the firm publishes the calibrated "
                    "claim and files the broad one as an open question."
                ),
                "principles": ["principle-narrowing"],
            },
        ],
        "n_forecasts": 2,
    },
    {
        "key": "adversarial-audit",
        "methodology": {
            "pattern_type": "adversarial-audit",
            "title": "Adversarial probing of hidden assumptions",
            "summary": (
                "Surface the assumption a friendly read leaves buried by "
                "running an adversarial reviewer against every load-bearing "
                "claim before it is published."
            ),
            "reasoning_moves": [
                "ask what would have to be true for the claim to fail",
                "run the adversarial reviewer before the friendly one",
                "treat an unaddressed objection as a publication blocker",
            ],
            "transfer_targets": ["peer-review swarm configuration"],
            "assumptions": [
                "the adversarial reviewer is not subject to the same blind spot",
                "objections are cheaper to surface than to discover post-hoc",
                "a buried assumption is load-bearing until shown otherwise",
            ],
            "failure_modes": [
                "adversarial monoculture shares the friendly reviewer's blind spot",
                "objection fatigue downgrades a structural objection to a nitpick",
            ],
        },
        "conclusions": [
            {
                "text": (
                    "Adversarial review surfaces the hidden assumption a "
                    "friendly read leaves buried; we will block publication "
                    "if an objection is unaddressed."
                ),
                "principles": ["principle-adversarial-first"],
            },
            {
                "text": (
                    "A buried assumption stays buried under a friendly read, "
                    "so the firm runs the adversarial reviewer first."
                ),
                "principles": ["principle-adversarial-first", "principle-blocker-gate"],
            },
        ],
        "n_forecasts": 1,
    },
    {
        "key": "representational-geometry",
        "methodology": {
            "pattern_type": "representational-geometry",
            "title": "Geometric contradiction detection",
            "summary": (
                "Read the geometry of a claim's embedding to catch a "
                "contradiction before a semantic reading would."
            ),
            "reasoning_moves": [
                "embed the claim and its negation",
                "measure the angle before reading the sentences",
            ],
            "transfer_targets": ["contradiction triage"],
            "assumptions": [
                "the embedding geometry tracks semantic contradiction",
            ],
            # Deliberately empty: this cluster ships with no registered
            # failure modes, so the generator prints a \todomark in the
            # limits section and the internal review flags it not ready.
            "failure_modes": [],
        },
        "conclusions": [
            {
                "text": (
                    "The geometry of a claim reveals a contradiction before "
                    "the semantics of the claim does."
                ),
                "principles": ["principle-geometry-first"],
            },
            {
                "text": (
                    "A contradiction shows up in the angle between a claim "
                    "and its negation before it shows up in a close read."
                ),
                "principles": ["principle-geometry-first"],
            },
        ],
        "n_forecasts": 1,
    },
    {
        "key": "retraction-cascade",
        "methodology": {
            "pattern_type": "retraction-cascade",
            "title": "Cascading source retraction",
            "summary": (
                "When a source is retracted, cascade the retraction through "
                "every conclusion it touched rather than letting it persist."
            ),
            "reasoning_moves": [
                "walk the cascade graph from the retracted source outward",
            ],
            "transfer_targets": ["provenance maintenance"],
            "assumptions": [
                "the cascade graph records every conclusion a source touched",
            ],
            "failure_modes": [
                "a source touched a conclusion off-graph and the cascade misses it",
            ],
        },
        "conclusions": [
            {
                "text": (
                    "A retracted source must cascade through every conclusion "
                    "it touched, not quietly persist."
                ),
                "principles": [],
            },
        ],
        "n_forecasts": 1,
    },
]


def _seed_method_invocation(store):
    from noosphere.models import (
        Method,
        MethodImplRef,
        MethodInvocation,
        MethodType,
    )

    method = Method(
        method_id="auto_paper_seed_method_v1",
        name="auto_paper_seed_method",
        version="1.0.0",
        method_type=MethodType.JUDGMENT,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        description="Seed method for the first auto-paper run.",
        rationale="Wired only to satisfy the cascade-edge FK.",
        preconditions=[],
        postconditions=[],
        dependencies=[],
        implementation=MethodImplRef(
            module="noosphere.methods.auto_paper_seed_method",
            fn_name="auto_paper_seed_method",
            git_sha="0" * 40,
        ),
        owner="founder",
        status="active",
        nondeterministic=False,
        created_at=NOW,
    )
    store.insert_method(method)
    inv = MethodInvocation(
        id=str(uuid4()),
        method_id=method.method_id,
        input_hash="a" * 64,
        output_hash="b" * 64,
        started_at=NOW,
        ended_at=NOW,
        succeeded=True,
        correlation_id=str(uuid4()),
        tenant_id=ORG_ID,
    )
    store.insert_method_invocation(inv)
    return inv


def _seed_cluster(store, inv, spec):
    from noosphere.models import (
        CascadeEdge,
        CascadeEdgeRelation,
        CascadeNode,
        CascadeNodeKind,
        Conclusion,
        ConclusionKind,
        ConfidenceTier,
        Finding,
        ForecastMarket,
        ForecastMarketStatus,
        ForecastOutcome,
        ForecastPrediction,
        ForecastPredictionStatus,
        ForecastResolution,
        ForecastSource,
        ForecastTrace,
        MethodologyProfile,
        ReviewReport,
    )

    key = spec["key"]
    conclusion_ids = []
    node_ids = {}

    # Conclusions + their CONCLUSION cascade nodes.
    for idx, cspec in enumerate(spec["conclusions"]):
        cid = f"conclusion-{key}-{idx + 1}"
        conclusion_ids.append(cid)
        store.put_conclusion(
            Conclusion(
                id=cid,
                text=cspec["text"],
                rationale=(
                    f"Derived under the {spec['methodology']['title']!r} "
                    "methodology root and re-tested against resolved forecasts."
                ),
                kind=ConclusionKind.FIRM,
                confidence_tier=ConfidenceTier.FIRM,
                confidence=0.74,
                supporting_principle_ids=list(cspec["principles"]),
                created_at=NOW,
                updated_at=NOW,
            )
        )
        nid = str(uuid4())
        node_ids[cid] = nid
        store.insert_cascade_node(
            CascadeNode(
                node_id=nid,
                kind=CascadeNodeKind.CONCLUSION,
                ref=cid,
                attrs={},
            )
        )

    # One ARTIFACT node every conclusion was EXTRACTED_FROM (references).
    artifact_node_id = str(uuid4())
    store.insert_cascade_node(
        CascadeNode(
            node_id=artifact_node_id,
            kind=CascadeNodeKind.ARTIFACT,
            ref=f"artifact-{key}-source-memo",
            attrs={
                "title": (
                    f"Firm source memo: {spec['methodology']['title']}, "
                    "May 2026"
                )
            },
        )
    )
    for cid in conclusion_ids:
        store.insert_cascade_edge(
            CascadeEdge(
                edge_id=str(uuid4()),
                src=node_ids[cid],
                dst=artifact_node_id,
                relation=CascadeEdgeRelation.EXTRACTED_FROM,
                method_invocation_id=inv.id,
                confidence=0.9,
                unresolved=False,
                established_at=NOW,
            )
        )

    # SUPPORTS edges chaining the conclusions into one connected cluster.
    for a, b in zip(conclusion_ids, conclusion_ids[1:]):
        store.insert_cascade_edge(
            CascadeEdge(
                edge_id=str(uuid4()),
                src=node_ids[a],
                dst=node_ids[b],
                relation=CascadeEdgeRelation.SUPPORTS,
                method_invocation_id=inv.id,
                confidence=0.82,
                unresolved=False,
                established_at=NOW,
            )
        )

    # Shared methodology root: one MethodologyProfile per conclusion,
    # all sharing a dedupe_key so the selector treats them as one root.
    # Each profile carries its own organization_id — the store enforces
    # a unique (organization_id, dedupe_key), and a shared root is
    # exactly "the same methodology pattern seen across uploads."
    m = spec["methodology"]
    for idx, cid in enumerate(conclusion_ids):
        profile = MethodologyProfile(
            id=f"profile-{key}-{idx + 1}",
            organization_id=f"{ORG_ID}-{key}-{idx + 1}",
            upload_id=None,
            conclusion_id=cid,
            source_kind="UPLOAD",
            pattern_type=m["pattern_type"],
            title=m["title"],
            summary=m["summary"],
            reasoning_moves=list(m["reasoning_moves"]),
            transfer_targets=list(m["transfer_targets"]),
            assumptions=list(m["assumptions"]),
            failure_modes=list(m["failure_modes"]),
            evidence_anchors=["calibration ledger"],
            confidence=0.85,
            dedupe_key=f"methodology-root-{key}",
            created_at=NOW,
            updated_at=NOW,
        )
        with store.session() as s:
            s.add(profile)
            s.commit()

    # Resolved forecasts touching the cluster: each trace lists a
    # cluster conclusion in principles_used, which is how the selector
    # ties a resolved forecast to a cluster.
    for fidx in range(spec["n_forecasts"]):
        touched = conclusion_ids[fidx % len(conclusion_ids)]
        market = ForecastMarket(
            id=f"market-{key}-{fidx + 1}",
            organization_id=ORG_ID,
            source=ForecastSource.POLYMARKET,
            external_id=f"{key}-mkt-{fidx + 1}",
            title=f"Will the {key} cluster's claim {fidx + 1} resolve YES?",
            description="Resolved forecast backing the auto-paper cluster.",
            resolution_criteria="Venue oracle settlement.",
            current_yes_price=Decimal("0.620000"),
            current_no_price=Decimal("0.380000"),
            open_time=NOW - timedelta(days=30),
            close_time=NOW - timedelta(days=1),
            status=ForecastMarketStatus.RESOLVED,
            resolved_outcome=ForecastOutcome.YES,
            resolved_at=NOW,
            raw_payload={"fixture": True},
        )
        store.put_forecast_market(market)
        pred = ForecastPrediction(
            id=f"prediction-{key}-{fidx + 1}",
            market_id=market.id,
            organization_id=ORG_ID,
            probability_yes=Decimal("0.700000"),
            confidence_low=Decimal("0.600000"),
            confidence_high=Decimal("0.800000"),
            headline=f"{spec['methodology']['title']}: claim {fidx + 1} holds",
            reasoning="Firm prediction anchored to the cluster's methodology root.",
            status=ForecastPredictionStatus.PUBLISHED,
            topic_hint=key,
            model_name="firm-forecaster-v1",
            created_at=NOW - timedelta(days=20),
        )
        store.put_forecast_prediction(pred)
        store.put_forecast_trace(
            ForecastTrace(
                id=str(uuid4()),
                prediction_id=pred.id,
                market_id=market.id,
                organization_id=ORG_ID,
                market_title=market.title,
                principles_used=[{"conclusionId": touched, "weight": 1.0}],
                model_output={"probability_yes": 0.7},
                gate_results=[],
                created_at=NOW - timedelta(days=20),
            )
        )
        store.put_forecast_resolution(
            ForecastResolution(
                id=str(uuid4()),
                prediction_id=pred.id,
                market_outcome=ForecastOutcome.YES,
                brier_score=0.09,
                log_loss=0.357,
                calibration_bucket=Decimal("0.7"),
                resolved_at=NOW,
                justification="Market resolved YES via the venue oracle.",
            )
        )

    # One seeded peer-review report on the lead conclusion so the
    # generated paper has a real discussion section to render.
    store.insert_review_report(
        ReviewReport(
            report_id=f"review-{key}-seed",
            reviewer="firm-peer-review",
            conclusion_id=conclusion_ids[0],
            findings=[
                Finding(
                    severity="minor",
                    category="evidence",
                    detail=(
                        "One supporting signal rests on a single source; "
                        "triangulate before widening the claim."
                    ),
                    evidence=[],
                    suggested_action="Add an independent confirming source.",
                )
            ],
            overall_verdict="revise",
            confidence=0.78,
            completed_at=NOW,
            method_invocation_ids=[],
        )
    )

    return conclusion_ids


def seed_demo_store():
    from noosphere.store import Store

    store = Store.from_database_url("sqlite:///:memory:")
    inv = _seed_method_invocation(store)
    for spec in _DEMO_CLUSTERS:
        _seed_cluster(store, inv, spec)
    return store


def load_store():
    if MODE == "demo":
        log("  corpus source : embedded verification corpus (frozen)")
        return seed_demo_store()
    log("  corpus source : live noosphere store")
    from noosphere.cli import get_orchestrator

    return get_orchestrator(None).store


# ── Stage 1: rank ────────────────────────────────────────────────────
log("--- Stage 1: rank clusters by maturity ---")
store = load_store()
rankings = rank_clusters(store, top_n=TOP_N)
log(f"  candidate clusters (top {TOP_N}): {len(rankings)}")
for i, r in enumerate(rankings, start=1):
    m = r.maturity
    log(
        f"    {i}. {r.cluster.cluster_id}  "
        f"maturity={m.score:.1f} "
        f"(size={m.size}, resolved_forecasts={m.resolved_forecast_count}, "
        f"principle_backing={m.principle_backing})"
    )

if not rankings:
    log("  no mature cluster found — nothing to draft.")
    log("  (populate the store, or run with --demo-corpus.)")
    memo_path = MEMO_DIR / f"Auto_Paper_Candidates_{STAMP}.md"
    memo_path.write_text(
        f"# Auto-Paper Candidates — {STAMP}\n\n"
        f"Run mode: `{MODE}`. No mature cluster was found; no drafts were "
        "generated. Populate the store or run with `--demo-corpus`.\n",
        encoding="utf-8",
    )
    log(f"  wrote memo: {memo_path}")
    raise SystemExit(0)

# ── Stage 2 + 3: generate and review each candidate ──────────────────
log("--- Stage 2: generate drafts ---")
candidates = []
for r in rankings:
    cluster = r.cluster
    artifact = generate_paper(
        store,
        cluster=cluster,
        out_root=OUT_ROOT,
        build_pdf=BUILD_PDF,
    )
    _clean_latex_byproducts(artifact.tex_path)
    log(
        f"  drafted {artifact.slug}: "
        f"tex={artifact.tex_path} "
        f"pdf={'yes' if artifact.pdf_path else 'no'} "
        f"rowrefs={len(artifact.row_refs)} todo={artifact.todo_count}"
    )
    if BUILD_PDF and artifact.pdf_path is None:
        log(
            f"    NOTE: pdflatex did not produce a PDF for {artifact.slug}; "
            "the .tex remains the authoritative artifact."
        )
    candidates.append((r, artifact))

log("--- Stage 3: internal review (severity-weighted peer-review swarm) ---")
reviewed = []
for r, artifact in candidates:
    review = review_paper_cluster(store, r.cluster, artifact)
    attach_review_to_sidecar(
        out_root=OUT_ROOT, slug=artifact.slug, review=review
    )
    state = "READY" if review.publish_ready else "NOT READY"
    log(
        f"  {artifact.slug}: MQS={review.mqs_composite:.3f} "
        f"(bar {review.mqs_threshold:.2f}) -> {state}; "
        f"action={review.recommended_action}; "
        f"objections(b/m/n)={review.blocker_count}/{review.major_count}/"
        f"{review.minor_count}"
    )
    reviewed.append((r, artifact, review))

# ── Stage 4: founder candidate memo ──────────────────────────────────
log("--- Stage 4: founder candidate memo ---")


def _fmt_list(items, empty):
    items = list(items)[:3]
    if not items:
        return f"  - _{empty}_\n"
    return "".join(f"  {i}. {x}\n" for i, x in enumerate(items, start=1))


memo_lines = []
memo_lines.append(f"# Auto-Paper Candidates — {STAMP}")
memo_lines.append("")
memo_lines.append(
    "The firm's first auto-generated research papers. The cluster "
    "selector ranked every mature conclusion cluster by maturity "
    "(resolved forecast count, principle backing, then size); the top "
    f"{len(reviewed)} are drafted below. Each draft is "
    "**machine-drafted, founder-reviewed** — the disclosure byline is "
    "non-removable and every numeric claim in the .tex resolves to a "
    "database row (a number the generator could not back to a source "
    "prints a `\\todomark`, never an estimate)."
)
memo_lines.append("")
memo_lines.append(
    f"Run mode: `{MODE}`. MQS publish bar: `{MQS_PUBLISH_THRESHOLD:.2f}`. "
    "Nothing here is published, and `review_state` is left at `pending` — "
    "triage is a founder action at `/papers`. The first auto-paper does "
    "not auto-announce; any external announcement is an explicit founder "
    "authorization."
)
memo_lines.append("")

action_counts = {"publish": 0, "revise": 0, "abandon": 0}
for idx, (r, artifact, review) in enumerate(reviewed, start=1):
    action_counts[review.recommended_action] = (
        action_counts.get(review.recommended_action, 0) + 1
    )
    cluster = r.cluster
    m = r.maturity
    tex_text = artifact.tex_path.read_text(encoding="utf-8")
    tex_lines = tex_text.count("\n") + 1
    tex_bytes = len(tex_text.encode("utf-8"))
    pdf_note = (
        f"{artifact.pdf_path.stat().st_size} bytes"
        if artifact.pdf_path
        else "not built"
    )
    memo_lines.append(f"## Candidate {idx}: `{cluster.cluster_id}`")
    memo_lines.append("")
    memo_lines.append(f"- **Slug**: `{artifact.slug}`")
    memo_lines.append(
        f"- **Cluster**: {m.size} conclusion(s), "
        f"{m.resolved_forecast_count} resolved forecast(s), "
        f"{m.principle_backing} supporting principle(s); "
        f"maturity score {m.score:.1f}"
    )
    memo_lines.append(
        f"- **Methodology root**: {cluster.methodology_root.title} "
        f"(`{cluster.methodology_root.profile_id}`, pattern "
        f"`{cluster.methodology_root.pattern_type}`)"
    )
    memo_lines.append(f"- **Lead conclusion**: `{cluster.lead_conclusion_id}`")
    memo_lines.append(
        f"- **Length**: {tex_lines} lines of LaTeX ({tex_bytes} bytes); "
        f"PDF {pdf_note}; {review.reference_count} reference row(s); "
        f"{artifact.todo_count} TODO marker(s); "
        f"{len(artifact.row_refs)} `\\rowref` marker(s)"
    )
    memo_lines.append(
        f"- **Internal review**: MQS composite **{review.mqs_composite:.3f}** "
        f"vs publish bar {review.mqs_threshold:.2f} -> "
        f"{'**READY**' if review.publish_ready else '**NOT READY**'}; "
        f"severity-weighted objections {review.severity_weighted:.2f} "
        f"(blocker {review.blocker_count}, major {review.major_count}, "
        f"minor {review.minor_count})"
    )
    memo_lines.append("- **Top strengths**:")
    memo_lines.append(_fmt_list(review.strengths, "no strength cleared the bar").rstrip("\n"))
    memo_lines.append("- **Top weaknesses**:")
    memo_lines.append(_fmt_list(review.weaknesses, "no weakness above the reporting bar").rstrip("\n"))
    memo_lines.append(
        f"- **Recommended action**: **{review.recommended_action.upper()}**"
    )
    memo_lines.append("")

memo_lines.append("## Founder decision")
memo_lines.append("")
memo_lines.append(
    f"Recommended actions across the {len(reviewed)} candidate(s): "
    f"{action_counts.get('publish', 0)} publish, "
    f"{action_counts.get('revise', 0)} revise, "
    f"{action_counts.get('abandon', 0)} abandon."
)
memo_lines.append("")
memo_lines.append(
    "Triage each draft at `/papers`. The `.tex` file is the authoritative "
    "artifact; the PDF is a build product. Edits land in the `.tex` "
    "directly; `review_state` tracks whether a draft is kept, published, "
    "or rejected. A draft approved for publication passes through the "
    "signed-publication path (sign over the canonical input, verify the "
    "live row still hashes to the signed bytes) before it reaches the "
    "public `/research/<slug>` surface — that path is verified on a "
    "synthetic paper at the end of this run. The byline stays "
    f'"{DISCLOSURE_LABEL}" even after founder review.'
)
memo_lines.append("")

memo_path = MEMO_DIR / f"Auto_Paper_Candidates_{STAMP}.md"
memo_path.write_text("\n".join(memo_lines) + "\n", encoding="utf-8")
log(f"  wrote memo: {memo_path}")

# ── Stage 5: verify the signed-publication path on a synthetic paper ─
log("--- Stage 5: verify the signed-publication path (synthetic paper) ---")
import tempfile

from noosphere.ledger.publication_signing import (
    PublicationKeyring,
    sign_publication,
    verify_signature,
)

# Use the top candidate's cluster as the synthetic paper's basis — a
# real, fully-backed cluster — but sign it under a throwaway keyring so
# nothing about this verification touches the firm's publication keys.
synthetic_cluster = reviewed[0][0].cluster
synthetic_review = reviewed[0][2]
signing_ok = False
with tempfile.TemporaryDirectory() as tmp:
    keyring = PublicationKeyring(Path(tmp) / "publication-keys")
    keyring.ensure()

    canonical = paper_canonical_input(
        store,
        synthetic_cluster,
        slug=f"synthetic-{synthetic_cluster.cluster_id}",
        mqs_composite=synthetic_review.mqs_composite,
        version=1,
        published_at="2026-05-14T12:00:00Z",
    )
    sig = sign_publication(canonical, keyring)
    result_ok = verify_signature(sig, keyring, live_input=canonical)
    log(
        f"  sign + verify (unmodified): ok={result_ok.ok} "
        f"hash={sig.canonical_hash[:16]}..."
    )

    # Mutate the live input the way a post-signing DB edit would, and
    # confirm verification now rejects it.
    mutated = paper_canonical_input(
        store,
        synthetic_cluster,
        slug=f"synthetic-{synthetic_cluster.cluster_id}",
        mqs_composite=synthetic_review.mqs_composite,
        version=1,
        published_at="2026-05-14T12:00:00Z",
        stated_confidence=(canonical.stated_confidence + 0.05),
    )
    result_tampered = verify_signature(sig, keyring, live_input=mutated)
    log(
        f"  verify after mutation: ok={result_tampered.ok} "
        f"(expected ok=False)"
    )
    signing_ok = result_ok.ok and not result_tampered.ok

if signing_ok:
    log("  signed-publication path: VERIFIED")
else:
    log("  signed-publication path: FAILED")
    raise SystemExit(1)

log("")
log("=== First auto-paper run complete ===")
log(f"  drafts under : {OUT_ROOT}")
log(f"  memo         : {memo_path}")
log(
    "  next: the founder triages at /papers — keep, edit-and-publish, or "
    "reject. A draft approved for publication goes through the signed-"
    "publication path (verified above) before it is public. The agent "
    "does not publish, does not flip review_state, and does not announce "
    "anything externally on the founder's behalf."
)
PYEOF

echo
echo "=== run_first_auto_paper.sh done ==="

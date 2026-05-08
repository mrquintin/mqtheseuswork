"""Replication harness driver.

One entry point with three subcommands. Each subcommand:

1. Resolves the dataset and configures the deterministic env if asked.
2. Builds a reproducibility envelope and writes it before running.
3. Invokes the firm's existing benchmark code under
   ``noosphere.benchmarks``.
4. Normalises results into ``<run_dir>/metrics_summary.json`` so
   ``replication.lib.verify`` can compare runs across targets.
5. On failure: prints the stack trace AND a one-paragraph human
   explanation of likely causes (the prompt requires both).

The script is intentionally thin. It is not a re-implementation of
the benchmark; it is a wrapper that records *what* was run alongside
the numbers. Production code stays the source of truth.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# Allow ``python replication/run.py ...`` from the repo root without
# requiring an editable install. The harness is meant to be runnable
# by an external researcher who has cloned the tree but not (yet)
# installed it.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
NOOSPHERE_ROOT = REPO_ROOT / "noosphere"
if NOOSPHERE_ROOT.is_dir() and str(NOOSPHERE_ROOT) not in sys.path:
    sys.path.insert(0, str(NOOSPHERE_ROOT))

from replication.lib.envelope import (  # noqa: E402
    Envelope,
    apply_deterministic_env,
    build_envelope,
    discover_available_models,
    write_envelope,
)

DEFAULT_DATASET = REPO_ROOT / "benchmarks" / "quintin_hypothesis" / "v1" / "dataset.jsonl"
DEFAULT_RUN_ROOT = REPO_ROOT / "replication" / "runs"


# ---------------------------------------------------------------------------
# Friendly error helper


_ERROR_HINTS = {
    "OPENAI_API_KEY": (
        "Cross-model targets need an embedding API key. Either set "
        "OPENAI_API_KEY / VOYAGE_API_KEY / COHERE_API_KEY before running, "
        "or accept that those models will be skipped (the harness logs "
        "every skip explicitly)."
    ),
    "ImportError": (
        "A dependency is missing. The harness expects "
        "`pip install -e .[dev] && pip install -r noosphere/requirements.txt` "
        "from the repo root. If you are on Python <3.11 the import is "
        "expected to fail; the firm pins 3.11."
    ),
    "ModuleNotFoundError": (
        "A Python module is not installed. From `replication/`, run "
        "`make install` (which installs the editable package and "
        "noosphere/requirements.txt). The ablation target in particular "
        "needs scikit-learn for the production direction estimator."
    ),
    "FileNotFoundError": (
        "The dataset file or run directory was not found. Verify "
        "`benchmarks/quintin_hypothesis/v1/dataset.jsonl` exists "
        "(the public QH v1 dataset ships with the repository)."
    ),
    "RateLimitError": (
        "An embedding API rate-limited the run. Re-run with "
        "`THESEUS_CROSS_MODEL_BUDGET=200` to take a smaller shard, or "
        "wait and retry. Partial runs still produce a valid envelope; "
        "the manifest records `items_embedded < items_total`."
    ),
}


def _print_human_explanation(exc: BaseException) -> None:
    """One paragraph explaining likely causes; printed alongside the trace."""
    name = type(exc).__name__
    msg = str(exc)
    hints: list[str] = []
    for pattern, hint in _ERROR_HINTS.items():
        if pattern.lower() in name.lower() or pattern.lower() in msg.lower():
            hints.append(hint)
    if not hints:
        hints.append(
            "Likely causes: a missing environment variable (see "
            "`replication/README.md`), an off-by-one Python version "
            "(the firm pins 3.11), or a model-API rate limit. Re-run "
            "with `--deterministic` to take seeds and threading out of "
            "the picture before suspecting a deeper problem."
        )
    print("\n--- replication failure: likely causes ---", file=sys.stderr)
    for h in hints:
        print(h, file=sys.stderr)
    print("--- end of human explanation ---\n", file=sys.stderr)


# ---------------------------------------------------------------------------
# Helpers shared across subcommands


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_run_dir(label: str, run_root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = run_root / f"{stamp}_{label}"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _write_summary(run_dir: Path, summary: dict[str, Any]) -> Path:
    p = run_dir / "metrics_summary.json"
    p.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return p


def _finalize_envelope(envelope: Envelope, run_dir: Path) -> None:
    """Write a finished envelope (with finished_at_utc) over the start one."""
    finished = build_envelope(
        benchmark_version=envelope.benchmark_version,
        runner=envelope.runner,
        dataset_path=envelope.dataset_path,
        models=envelope.models,
        deterministic=envelope.deterministic,
        seed=envelope.seed,
        repo_root=REPO_ROOT,
        started_at_utc=envelope.started_at_utc,
        finished_at_utc=_now(),
        extra=envelope.extra,
    )
    write_envelope(finished, run_dir)


# ---------------------------------------------------------------------------
# qh-benchmark


def cmd_qh(args: argparse.Namespace) -> int:
    from noosphere.benchmarks import (  # noqa: E402
        BENCHMARK_VERSION,
        HashEmbedder,
        compute_metrics,
        run_benchmark,
    )
    from noosphere.benchmarks.qh_metrics import write_metrics_report  # noqa: E402

    dataset_path = Path(args.dataset)
    if not dataset_path.is_file():
        raise FileNotFoundError(f"dataset not found: {dataset_path}")

    extra: dict[str, Any] = {}
    if args.deterministic:
        extra["deterministic_env"] = apply_deterministic_env()
    extra["python_executable"] = sys.executable

    run_dir = _make_run_dir("qh-benchmark", Path(args.run_root))
    runners = list(args.runners) or ["random", "cosine", "contradiction_geometry"]

    envelope = build_envelope(
        benchmark_version=BENCHMARK_VERSION,
        runner="+".join(runners),
        dataset_path=dataset_path,
        models=("hash-det:qh-v1",),
        deterministic=bool(args.deterministic),
        seed=int(args.seed),
        repo_root=REPO_ROOT,
        extra=extra,
    )
    write_envelope(envelope, run_dir)

    embedder = HashEmbedder(dim=int(args.embedder_dim))
    summary: dict[str, Any] = {
        "benchmark_version": BENCHMARK_VERSION,
        "deterministic": bool(args.deterministic),
        "seed": int(args.seed),
        "runners": runners,
        "per_runner": {},
    }
    for runner in runners:
        result_path = run_dir / f"results_{runner}.json"
        result = run_benchmark(
            dataset_path,
            runner,
            embedder=embedder,
            seed=int(args.seed),
            output_path=result_path,
            repo_root=REPO_ROOT,
        )
        metrics = compute_metrics(result["predictions"])
        write_metrics_report(result, metrics, run_dir, runner=runner)
        summary["per_runner"][runner] = {
            "n": int(metrics.get("n", 0)),
            "accuracy": float(metrics.get("accuracy", float("nan"))),
            "auroc_contradicting_vs_coherent": float(
                metrics.get("auroc_contradicting_vs_coherent", float("nan"))
            ),
            "ece_contradicting": float(metrics.get("ece_contradicting", float("nan"))),
        }
        print(
            f"[qh-benchmark] runner={runner} "
            f"n={summary['per_runner'][runner]['n']} "
            f"acc={summary['per_runner'][runner]['accuracy']:.4f} "
            f"auroc={summary['per_runner'][runner]['auroc_contradicting_vs_coherent']:.4f}"
        )

    _write_summary(run_dir, summary)
    _finalize_envelope(envelope, run_dir)
    print(f"[qh-benchmark] run dir: {run_dir}")
    return 0


# ---------------------------------------------------------------------------
# cross-model


def cmd_cross_model(args: argparse.Namespace) -> int:
    from noosphere.benchmarks import BENCHMARK_VERSION  # noqa: E402
    from noosphere.benchmarks.cross_model_runner import (  # noqa: E402
        CrossModelConfig,
        run_cross_model,
    )

    dataset_path = Path(args.dataset)
    if not dataset_path.is_file():
        raise FileNotFoundError(f"dataset not found: {dataset_path}")

    extra: dict[str, Any] = {}
    if args.deterministic:
        extra["deterministic_env"] = apply_deterministic_env()

    available = discover_available_models()
    requested = list(args.models) if args.models else available
    skipped: list[str] = []
    to_run: list[str] = []
    for name in requested:
        if name in available:
            to_run.append(name)
        else:
            skipped.append(name)
            print(
                f"[cross-model] SKIP {name}: API key not found in environment "
                "(see replication/README.md for the variable names)",
                file=sys.stderr,
            )

    if args.deterministic:
        # Adapters that talk to a remote API are not bit-stable; the
        # harness drops them rather than pretend.
        nondet = [m for m in to_run if not m.startswith("hash-det")]
        for m in nondet:
            print(
                f"[cross-model] SKIP {m}: backend is not deterministic; "
                "deterministic mode keeps only the hash-det adapter",
                file=sys.stderr,
            )
        skipped.extend(nondet)
        to_run = [m for m in to_run if m.startswith("hash-det")]

    if not to_run:
        print(
            "[cross-model] no runnable adapters; the harness expected at "
            "least the hash-det fallback. Aborting.",
            file=sys.stderr,
        )
        return 1

    run_dir = _make_run_dir("cross-model", Path(args.run_root))
    extra["skipped_models"] = skipped
    extra["available_models"] = available
    envelope = build_envelope(
        benchmark_version=BENCHMARK_VERSION,
        runner="cross_model",
        dataset_path=dataset_path,
        models=tuple(to_run),
        deterministic=bool(args.deterministic),
        seed=int(args.seed),
        repo_root=REPO_ROOT,
        extra=extra,
    )
    write_envelope(envelope, run_dir)

    config = CrossModelConfig(
        model_names=to_run,
        dataset_path=dataset_path,
        output_dir=run_dir,
        seed=int(args.seed),
        item_budget=args.budget,
    )
    reports = run_cross_model(config)

    summary: dict[str, Any] = {
        "benchmark_version": BENCHMARK_VERSION,
        "deterministic": bool(args.deterministic),
        "seed": int(args.seed),
        "runs": [
            {
                "model_name": r.model_name,
                "items_embedded": r.items_embedded,
                "items_total": r.items_total,
                "truncated": r.truncated,
                "error": r.error,
            }
            for r in reports
        ],
        "skipped_models": skipped,
    }
    _write_summary(run_dir, summary)
    _finalize_envelope(envelope, run_dir)
    print(f"[cross-model] run dir: {run_dir}")
    print(f"[cross-model] models run: {to_run}; skipped: {skipped}")
    return 0


# ---------------------------------------------------------------------------
# ablation


def cmd_ablation(args: argparse.Namespace) -> int:
    from noosphere.benchmarks import BENCHMARK_VERSION  # noqa: E402
    from noosphere.benchmarks.qh_ablations import run_ablation  # noqa: E402

    dataset_path = Path(args.dataset)
    if not dataset_path.is_file():
        raise FileNotFoundError(f"dataset not found: {dataset_path}")

    extra: dict[str, Any] = {}
    if args.deterministic:
        extra["deterministic_env"] = apply_deterministic_env()

    run_dir = _make_run_dir("ablation", Path(args.run_root))
    envelope = build_envelope(
        benchmark_version=BENCHMARK_VERSION,
        runner="householder_ablation",
        dataset_path=dataset_path,
        models=("hash-det:qh-v1",),
        deterministic=bool(args.deterministic),
        seed=int(args.seed),
        repo_root=REPO_ROOT,
        extra=extra,
    )
    write_envelope(envelope, run_dir)

    payload = run_ablation(
        dataset_path,
        output_dir=run_dir,
        random_seed=int(args.seed),
        repo_root=REPO_ROOT,
    )
    summary = {
        "benchmark_version": BENCHMARK_VERSION,
        "deterministic": bool(args.deterministic),
        "seed": int(args.seed),
        "accuracies": payload.get("accuracies", {}),
        "n_items_evaluation": payload.get("n_items_evaluation"),
        "n_seed_pairs": payload.get("n_seed_pairs"),
        "direction_method": payload.get("direction_method"),
        "mcnemar_summary": {
            name: {
                "p_value": r.get("p_value"),
                "control_only_correct": r.get("control_only_correct"),
                "variant_only_correct": r.get("variant_only_correct"),
            }
            for name, r in (payload.get("mcnemar_vs_full") or {}).items()
        },
    }
    _write_summary(run_dir, summary)
    _finalize_envelope(envelope, run_dir)
    print(f"[ablation] run dir: {run_dir}")
    return 0


# ---------------------------------------------------------------------------
# CLI


def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET),
        help=f"Path to the QH dataset JSONL (default: {DEFAULT_DATASET})",
    )
    p.add_argument(
        "--seed", type=int, default=0, help="Seed (default: 0)"
    )
    p.add_argument(
        "--deterministic",
        action="store_true",
        help=(
            "Pin seeds, single-thread BLAS, and skip nondeterministic "
            "backends. Bit-stable across runs on the same machine."
        ),
    )
    p.add_argument(
        "--run-root",
        default=str(DEFAULT_RUN_ROOT),
        help=f"Where to write per-run output dirs (default: {DEFAULT_RUN_ROOT})",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="replication.run",
        description="One-command replication harness for the firm's headline empirical claims.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    qh = sub.add_parser("qh-benchmark", help="QH benchmark with random/cosine/contradiction_geometry")
    _add_common_args(qh)
    qh.add_argument("--embedder-dim", type=int, default=192)
    qh.add_argument(
        "--runners",
        nargs="+",
        default=["random", "cosine", "contradiction_geometry"],
        help="Subset of runners to score (default: all three)",
    )
    qh.set_defaults(func=cmd_qh)

    cm = sub.add_parser("cross-model", help="Cross-model QH study (skips models without keys)")
    _add_common_args(cm)
    cm.add_argument(
        "--models",
        nargs="+",
        default=None,
        help=(
            "Adapter names to include (default: every adapter whose API key "
            "is present in env). Unknown / unkeyed adapters are skipped, not "
            "errored on."
        ),
    )
    cm.add_argument(
        "--budget",
        type=int,
        default=None,
        help="Per-model item budget (None = full dataset)",
    )
    cm.set_defaults(func=cmd_cross_model)

    ab = sub.add_parser("ablation", help="Householder reflection ablation")
    _add_common_args(ab)
    ab.set_defaults(func=cmd_ablation)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 — print, then re-surface
        traceback.print_exc()
        _print_human_explanation(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

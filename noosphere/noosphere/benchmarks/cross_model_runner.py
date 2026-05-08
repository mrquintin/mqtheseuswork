"""Cross-model QH benchmark runner.

Re-runs the Quintin Hypothesis benchmark with a swappable embedding
back-end. The runner is the bridge between
:mod:`noosphere.embeddings.multi` and :mod:`noosphere.benchmarks.qh_runner`:
it embeds each item with the configured adapter, executes all three
runners (random / cosine / contradiction_geometry), and writes
predictions to parquet keyed by ``(model, item_id, runner)``.

Budget cap: each adapter has a per-dataset item budget (env override
``THESEUS_CROSS_MODEL_BUDGET``). When the budget is exhausted the runner
writes *partial* results with ``items_embedded < items_total`` so the
downstream report can show the "n=K of N" caveat. Silent truncation is
the failure mode this guards against.

Vector blobs are persisted off-tree (``default_vector_root()``) with a
manifest. The git tree only ever sees aggregated metrics and parquet
prediction tables, never raw vectors.
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

from noosphere.benchmarks.qh_runner import (
    BENCHMARK_VERSION,
    BenchmarkItem,
    RUNNERS,
    _git_sha,
    load_dataset,
)
from noosphere.embeddings.multi import (
    EmbeddingAdapter,
    EmbeddingResult,
    default_vector_root,
    get_adapter,
    write_manifest,
)


@dataclass
class CrossModelConfig:
    model_names: list[str]
    dataset_path: Path
    output_dir: Path
    vector_root: Path = field(default_factory=default_vector_root)
    seed: int = 0
    item_budget: int | None = None  # None == no cap
    runners: tuple[str, ...] = ("random", "cosine", "contradiction_geometry")


@dataclass
class CrossModelRunReport:
    model_name: str
    items_embedded: int
    items_total: int
    truncated: bool
    parquet_path: Path | None
    manifest_path: Path
    error: str | None = None


def _embed_batch(
    adapter: EmbeddingAdapter,
    items: Sequence[BenchmarkItem],
    *,
    budget: int | None,
    vector_root: Path,
) -> tuple[dict[str, EmbeddingResult], dict[str, EmbeddingResult], int]:
    """Embed premise + continuation for each item until budget exhausts.

    Returns ``(premise_results, continuation_results, items_embedded)``.
    Each result map is keyed by item id. Vectors are persisted to
    ``vector_root`` as ``.npy`` files keyed by (model, content_hash).
    """
    safe_model = adapter.model_name.replace("/", "_").replace(":", "__")
    blob_dir = vector_root / safe_model
    blob_dir.mkdir(parents=True, exist_ok=True)

    p_results: dict[str, EmbeddingResult] = {}
    c_results: dict[str, EmbeddingResult] = {}
    items_embedded = 0

    for item in items:
        if budget is not None and items_embedded >= budget:
            break
        try:
            ep = adapter.embed(item.premise)
            ec = adapter.embed(item.candidate_continuation)
        except Exception as exc:  # noqa: BLE001 — fail loud and surface
            raise RuntimeError(
                f"adapter {adapter.model_name!r} failed on item {item.id!r}: {exc}"
            ) from exc
        p_results[item.id] = ep
        c_results[item.id] = ec
        # Persist vectors off-tree for replay/debug. Hash-based file
        # names dedupe: identical text across items only stored once.
        np.save(blob_dir / f"{ep.content_hash}.npy", ep.vector)
        np.save(blob_dir / f"{ec.content_hash}.npy", ec.vector)
        items_embedded += 1

    return p_results, c_results, items_embedded


def _predict(
    items: Sequence[BenchmarkItem],
    p_emb: dict[str, EmbeddingResult],
    c_emb: dict[str, EmbeddingResult],
    *,
    runner_names: Iterable[str],
    seed: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for runner_name in runner_names:
        if runner_name not in RUNNERS:
            raise ValueError(f"unknown runner {runner_name!r}")
        runner = RUNNERS[runner_name]
        rng = random.Random(seed)
        for item in items:
            ep = p_emb.get(item.id)
            ec = c_emb.get(item.id)
            if ep is None or ec is None:
                continue  # budget truncation
            t0 = time.perf_counter()
            pred_label, score, extras = runner(ep.vector, ec.vector, rng)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            rows.append(
                {
                    "model_name": ep.model_name,
                    "runner": runner_name,
                    "item_id": item.id,
                    "domain": item.domain,
                    "label": item.label,
                    "predicted_label": pred_label,
                    "predicted_score": float(score),
                    "predict_latency_ms": float(latency_ms),
                    "embed_latency_premise_ms": float(ep.latency_ms),
                    "embed_latency_continuation_ms": float(ec.latency_ms),
                    "premise_hash": ep.content_hash,
                    "continuation_hash": ec.content_hash,
                    "extras_cosine": float(extras.get("cosine", float("nan"))),
                    "extras_sparsity": float(extras.get("sparsity", float("nan"))),
                }
            )
    return rows


def _write_predictions(
    rows: Sequence[dict[str, Any]],
    out_path: Path,
) -> Path | None:
    """Persist predictions as parquet (preferred) or JSON fallback."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd  # type: ignore
        df = pd.DataFrame(list(rows))
        try:
            df.to_parquet(out_path, index=False)
            return out_path
        except Exception:
            # pyarrow/fastparquet missing — fall through to JSON.
            pass
    except ImportError:
        pass
    json_path = out_path.with_suffix(".json")
    json_path.write_text(json.dumps(list(rows), indent=2), encoding="utf-8")
    return json_path


def _resolve_budget(cli_budget: int | None) -> int | None:
    """Env var ``THESEUS_CROSS_MODEL_BUDGET`` overrides the default cap."""
    env = os.environ.get("THESEUS_CROSS_MODEL_BUDGET")
    if env:
        try:
            n = int(env)
            return n if n > 0 else None
        except ValueError:
            pass
    return cli_budget


def run_cross_model(
    config: CrossModelConfig,
    *,
    adapters: dict[str, EmbeddingAdapter] | None = None,
) -> list[CrossModelRunReport]:
    """Run the QH benchmark for each configured model.

    Parameters
    ----------
    config:
        Run configuration.
    adapters:
        Optional preinstantiated adapter map (used by tests). Falls back
        to :func:`noosphere.embeddings.multi.get_adapter` for unknowns.
    """
    items = load_dataset(config.dataset_path)
    budget = _resolve_budget(config.item_budget)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    git_sha = _git_sha()
    reports: list[CrossModelRunReport] = []

    for model_name in config.model_names:
        adapter: EmbeddingAdapter | None
        if adapters and model_name in adapters:
            adapter = adapters[model_name]
        else:
            try:
                adapter = get_adapter(model_name)
            except Exception as exc:  # noqa: BLE001
                manifest_path = write_manifest(
                    config.vector_root,
                    model_name=model_name,
                    dataset_path=str(config.dataset_path),
                    items_embedded=0,
                    items_total=len(items),
                    git_sha=git_sha,
                    extra={"error": str(exc)},
                )
                reports.append(
                    CrossModelRunReport(
                        model_name=model_name,
                        items_embedded=0,
                        items_total=len(items),
                        truncated=True,
                        parquet_path=None,
                        manifest_path=manifest_path,
                        error=str(exc),
                    )
                )
                continue

        try:
            p_emb, c_emb, items_embedded = _embed_batch(
                adapter, items, budget=budget, vector_root=config.vector_root
            )
            rows = _predict(
                items,
                p_emb,
                c_emb,
                runner_names=config.runners,
                seed=config.seed,
            )
        except Exception as exc:  # noqa: BLE001
            manifest_path = write_manifest(
                config.vector_root,
                model_name=adapter.model_name,
                dataset_path=str(config.dataset_path),
                items_embedded=0,
                items_total=len(items),
                git_sha=git_sha,
                extra={"error": str(exc)},
            )
            reports.append(
                CrossModelRunReport(
                    model_name=adapter.model_name,
                    items_embedded=0,
                    items_total=len(items),
                    truncated=True,
                    parquet_path=None,
                    manifest_path=manifest_path,
                    error=str(exc),
                )
            )
            continue

        safe = adapter.model_name.replace("/", "_").replace(":", "__")
        out_path = config.output_dir / f"predictions__{safe}.parquet"
        parquet_path = _write_predictions(rows, out_path)
        manifest_path = write_manifest(
            config.vector_root,
            model_name=adapter.model_name,
            dataset_path=str(config.dataset_path),
            items_embedded=items_embedded,
            items_total=len(items),
            git_sha=git_sha,
            extra={
                "dim": adapter.dim,
                "max_tokens": adapter.max_tokens,
                "predictions_path": str(parquet_path) if parquet_path else None,
                "n_predictions": len(rows),
                "budget": budget,
            },
        )
        reports.append(
            CrossModelRunReport(
                model_name=adapter.model_name,
                items_embedded=items_embedded,
                items_total=len(items),
                truncated=items_embedded < len(items),
                parquet_path=parquet_path,
                manifest_path=manifest_path,
                error=None,
            )
        )

    _write_run_index(config.output_dir, reports, git_sha=git_sha)
    return reports


def _write_run_index(
    output_dir: Path,
    reports: Sequence[CrossModelRunReport],
    *,
    git_sha: str,
) -> Path:
    """Write a single index file summarising all per-model runs."""
    payload = {
        "benchmark_version": BENCHMARK_VERSION,
        "git_sha": git_sha,
        "runs": [
            {
                "model_name": r.model_name,
                "items_embedded": r.items_embedded,
                "items_total": r.items_total,
                "truncated": r.truncated,
                "predictions_path": (
                    str(r.parquet_path) if r.parquet_path else None
                ),
                "manifest_path": str(r.manifest_path),
                "error": r.error,
            }
            for r in reports
        ],
    }
    p = output_dir / "run_index.json"
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


__all__ = [
    "CrossModelConfig",
    "CrossModelRunReport",
    "run_cross_model",
]

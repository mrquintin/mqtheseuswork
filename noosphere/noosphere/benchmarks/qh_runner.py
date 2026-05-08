"""Quintin Hypothesis benchmark harness.

Loads a frozen JSONL dataset of (premise, candidate_continuation,
label) items and runs one of three baseline runners on each item:

- ``random`` — picks a label uniformly at random (lower bound).
- ``cosine`` — uses cosine similarity of the embeddings only,
  thresholded against fixed cuts. The "no geometry, just direction"
  baseline.
- ``contradiction_geometry`` — the firm's full probe: Hoyer sparsity
  of the difference vector combined with cosine. The Quintin
  Hypothesis prediction.

The harness is deterministic given a seed and a dataset, and records
provenance (git SHA, embedder, runner, model identifier, timestamp,
benchmark version) so any result can be re-run.

The default embedder is ``hash-det-v1``: a deterministic
sign-hashing token embedder. It is *not* a strong embedder — it lets
the harness run in CI without API keys, and it gives every runner the
same input. To swap in a real embedding model, pass an ``Embedder``
instance to :func:`run_benchmark`.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import random
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

import numpy as np

BENCHMARK_VERSION = "qh-v1"
DEFAULT_EMBEDDER_ID = "hash-det-v1"
DEFAULT_DIM = 192
LABELS = ("coherent", "contradicting", "orthogonal")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


# ---------------------------------------------------------------------------
# Dataset I/O


@dataclasses.dataclass(frozen=True)
class BenchmarkItem:
    id: str
    premise: str
    candidate_continuation: str
    label: str
    domain: str
    source: str
    license: str
    notes: str | None = None
    seed: int | None = None

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "BenchmarkItem":
        missing = [
            k
            for k in ("id", "premise", "candidate_continuation", "label", "domain", "source", "license")
            if k not in record
        ]
        if missing:
            raise ValueError(f"benchmark item missing required fields: {missing}")
        if record["label"] not in LABELS:
            raise ValueError(
                f"invalid label {record['label']!r}; expected one of {LABELS}"
            )
        return cls(
            id=str(record["id"]),
            premise=str(record["premise"]),
            candidate_continuation=str(record["candidate_continuation"]),
            label=str(record["label"]),
            domain=str(record["domain"]),
            source=str(record["source"]),
            license=str(record["license"]),
            notes=record.get("notes"),
            seed=record.get("seed"),
        )


def load_dataset(path: Path | str) -> list[BenchmarkItem]:
    p = Path(path)
    items: list[BenchmarkItem] = []
    seen_ids: set[str] = set()
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{p}:{lineno}: invalid JSON: {exc}") from exc
        item = BenchmarkItem.from_dict(record)
        if item.id in seen_ids:
            raise ValueError(f"{p}:{lineno}: duplicate id {item.id!r}")
        seen_ids.add(item.id)
        items.append(item)
    return items


# ---------------------------------------------------------------------------
# Embedder


class Embedder:
    """Embedder protocol: ``embed(text) -> np.ndarray`` of fixed dim."""

    identifier: str = "abstract"
    dim: int = 0

    def embed(self, text: str) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError


class HashEmbedder(Embedder):
    """Deterministic sign-hashing token embedder.

    For each token in the input text we compute a 64-bit BLAKE2b hash,
    use the low bits to pick a coordinate, and use one bit for the
    sign. Embeddings are L2-normalized. This is the deterministic
    baseline embedder; a real embedding API can be substituted via the
    ``Embedder`` protocol.
    """

    identifier: str = DEFAULT_EMBEDDER_ID

    def __init__(self, dim: int = DEFAULT_DIM, salt: str = "qh-v1") -> None:
        if dim <= 1:
            raise ValueError("dim must be >= 2")
        self.dim = int(dim)
        self.salt = str(salt)

    def _hash(self, token: str) -> int:
        digest = hashlib.blake2b(
            f"{self.salt}:{token}".encode("utf-8"), digest_size=8
        ).digest()
        return int.from_bytes(digest, "big")

    def embed(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=float)
        tokens = _TOKEN_RE.findall(text.lower())
        for tok in tokens:
            h = self._hash(tok)
            idx = h % self.dim
            sign = 1.0 if (h >> 32) & 1 else -1.0
            v[idx] += sign
        norm = float(np.linalg.norm(v))
        if norm > 0.0:
            v = v / norm
        return v


# ---------------------------------------------------------------------------
# Runners
#
# Each runner is a callable (premise_emb, continuation_emb, rng) ->
# (predicted_label, predicted_score, extras). ``predicted_score`` is
# the score for the binary task ``contradicting vs coherent`` —
# higher means "more likely contradicting". This keeps AUROC and ECE
# well-defined across all runners.


def _hoyer_sparsity(x: np.ndarray) -> float:
    n = x.size
    if n < 2:
        return 0.0
    l1 = float(np.sum(np.abs(x)))
    l2 = float(np.linalg.norm(x))
    if l2 < 1e-12:
        return 0.0
    sqrt_n = float(np.sqrt(n))
    return float(np.clip((sqrt_n - l1 / l2) / (sqrt_n - 1.0), 0.0, 1.0))


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _runner_random(
    premise: np.ndarray, cont: np.ndarray, rng: random.Random
) -> tuple[str, float, dict[str, float]]:
    label = rng.choice(list(LABELS))
    score = rng.random()
    return label, score, {"cosine": _cosine(premise, cont)}


# Cosine-only thresholds — fixed and frozen. These were chosen
# from the v1 calibration split (first 10 items per domain) and are
# *not* re-tuned per run. Documented so reviewers can reproduce.
_COSINE_COHERENT_CUT = 0.30
_COSINE_CONTRADICTING_CUT = 0.05


def _runner_cosine(
    premise: np.ndarray, cont: np.ndarray, rng: random.Random
) -> tuple[str, float, dict[str, float]]:
    cos = _cosine(premise, cont)
    if cos >= _COSINE_COHERENT_CUT:
        label = "coherent"
    elif cos <= _COSINE_CONTRADICTING_CUT:
        label = "contradicting"
    else:
        label = "orthogonal"
    # contradicting score is higher when cosine is lower
    score = float(np.clip((_COSINE_COHERENT_CUT - cos) / max(_COSINE_COHERENT_CUT, 1e-9), 0.0, 1.0))
    return label, score, {"cosine": cos}


# Geometry runner thresholds — frozen for v1.
_QH_SPARSITY_CONTRA = 0.40
_QH_SPARSITY_COHERENT = 0.20


def _runner_contradiction_geometry(
    premise: np.ndarray, cont: np.ndarray, rng: random.Random
) -> tuple[str, float, dict[str, float]]:
    diff = cont - premise
    sparsity = _hoyer_sparsity(diff)
    cos = _cosine(premise, cont)
    if sparsity >= _QH_SPARSITY_CONTRA:
        label = "contradicting"
    elif sparsity <= _QH_SPARSITY_COHERENT and cos >= 0.0:
        label = "coherent"
    else:
        label = "orthogonal"
    return label, float(sparsity), {"cosine": cos, "sparsity": sparsity}


RunnerFn = Callable[[np.ndarray, np.ndarray, random.Random], tuple[str, float, dict[str, float]]]

RUNNERS: dict[str, RunnerFn] = {
    "random": _runner_random,
    "cosine": _runner_cosine,
    "contradiction_geometry": _runner_contradiction_geometry,
}


# ---------------------------------------------------------------------------
# Provenance


def _git_sha(repo_root: Path | None = None) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root) if repo_root else None,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# Public API


def iter_predictions(
    items: Sequence[BenchmarkItem],
    runner_name: str,
    embedder: Embedder | None = None,
    *,
    seed: int = 0,
) -> Iterator[dict[str, Any]]:
    if runner_name not in RUNNERS:
        raise ValueError(
            f"unknown runner {runner_name!r}; expected one of {sorted(RUNNERS)}"
        )
    runner = RUNNERS[runner_name]
    emb = embedder or HashEmbedder()
    rng = random.Random(seed)
    for item in items:
        ep = emb.embed(item.premise)
        ec = emb.embed(item.candidate_continuation)
        t0 = time.perf_counter()
        pred_label, score, extras = runner(ep, ec, rng)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        yield {
            "id": item.id,
            "domain": item.domain,
            "label": item.label,
            "predicted_label": pred_label,
            "predicted_score": float(score),
            "latency_ms": float(latency_ms),
            "extras": extras,
        }


def run_benchmark(
    dataset_path: Path | str,
    runner_name: str,
    *,
    embedder: Embedder | None = None,
    seed: int = 0,
    output_path: Path | str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Run a benchmark end-to-end and (optionally) write a results JSON.

    Returns the in-memory results dict.
    """
    items = load_dataset(dataset_path)
    emb = embedder or HashEmbedder()
    predictions = list(
        iter_predictions(items, runner_name, embedder=emb, seed=seed)
    )
    payload: dict[str, Any] = {
        "benchmark_version": BENCHMARK_VERSION,
        "runner": runner_name,
        "embedder": getattr(emb, "identifier", "unknown"),
        "embedder_dim": getattr(emb, "dim", 0),
        "seed": int(seed),
        "git_sha": _git_sha(repo_root),
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataset_path": str(dataset_path),
        "n_items": len(items),
        "predictions": predictions,
    }
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


# ---------------------------------------------------------------------------
# Data-leakage guard
#
# ``--validate`` checks that no benchmark item appears (verbatim or as
# an n-gram match) in any file under the firm's training/conditioning
# data directory. The default scan paths cover the contradiction
# direction exemplars and the coherence calibration corpus, which are
# the only places a leak could plausibly come from in this repo.


def _ngram_set(text: str, n: int = 5) -> set[tuple[str, ...]]:
    tokens = _TOKEN_RE.findall(text.lower())
    if len(tokens) < n:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def validate_no_leakage(
    items: Sequence[BenchmarkItem],
    scan_paths: Iterable[Path | str],
    *,
    jaccard_threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """Return a list of suspected leaks (empty list = clean).

    Each leak entry is ``{"item_id", "scan_path", "jaccard"}``.
    """
    leaks: list[dict[str, Any]] = []
    item_ngrams = [
        (item.id, _ngram_set(f"{item.premise} || {item.candidate_continuation}"))
        for item in items
    ]
    for raw in scan_paths:
        path = Path(raw)
        if not path.exists():
            continue
        if path.is_file():
            files = [path]
        else:
            files = [p for p in path.rglob("*") if p.is_file()]
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            scan_ngrams = _ngram_set(text)
            if not scan_ngrams:
                continue
            for item_id, ngrams in item_ngrams:
                if not ngrams:
                    continue
                inter = len(ngrams & scan_ngrams)
                if inter == 0:
                    continue
                union = len(ngrams | scan_ngrams)
                j = inter / union if union else 0.0
                if j >= jaccard_threshold or inter >= max(3, int(0.5 * len(ngrams))):
                    leaks.append(
                        {
                            "item_id": item_id,
                            "scan_path": str(f),
                            "jaccard": float(j),
                            "intersection": int(inter),
                        }
                    )
    return leaks


def default_scan_paths(repo_root: Path) -> list[Path]:
    """Return the standard places to scan for leakage."""
    candidates = [
        repo_root / "noosphere" / "noosphere" / "coherence" / "data",
        repo_root / "noosphere_data",
        repo_root / "noosphere" / "noosphere_data",
    ]
    return [p for p in candidates if p.exists()]

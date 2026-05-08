"""Benchmark harnesses owned by the firm.

Currently exposes the Quintin Hypothesis (QH) benchmark — a frozen,
public, replicable test of the claim that logical coherence is a
geometric property of embedding space. See
``docs/benchmarks/QH_Benchmark_Schema.md``.
"""

from __future__ import annotations

from noosphere.benchmarks.qh_runner import (
    BENCHMARK_VERSION,
    HashEmbedder,
    RUNNERS,
    load_dataset,
    run_benchmark,
)
from noosphere.benchmarks.qh_metrics import compute_metrics, render_markdown_summary

__all__ = [
    "BENCHMARK_VERSION",
    "HashEmbedder",
    "RUNNERS",
    "compute_metrics",
    "load_dataset",
    "render_markdown_summary",
    "run_benchmark",
]

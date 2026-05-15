"""Plot helpers for the quantitative runner.

The runner materialises one plot per test so the founder can scan an
artifact directory and judge whether a regression looks plausible
without re-running the fit. Each helper is a pure function over numpy
arrays — the runner passes already-fitted values in.

matplotlib is loaded lazily and the helpers degrade to a no-op when
the headless ``Agg`` backend is unavailable. The runner records the
output path either way so callers can detect missing plots without
inspecting the filesystem.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence


def _setup_matplotlib():
    """Return matplotlib.pyplot configured for headless rendering.

    Returns ``None`` if matplotlib is not installed; the runner treats
    that as "skip the plot" rather than failing the whole pass.
    """

    try:
        import matplotlib

        matplotlib.use("Agg", force=False)
        import matplotlib.pyplot as plt  # noqa: WPS433 — lazy import.

        return plt
    except Exception:
        return None


def residual_plot(
    fitted: Sequence[float],
    residuals: Sequence[float],
    *,
    out_path: Path,
    title: str = "Residuals vs fitted",
) -> Path | None:
    plt = _setup_matplotlib()
    if plt is None:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(5, 3.5))
    ax.scatter(list(fitted), list(residuals), s=10, alpha=0.7)
    ax.axhline(0.0, color="black", linewidth=0.6, alpha=0.4)
    ax.set_xlabel("fitted")
    ax.set_ylabel("residual")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def distribution_overlay(
    sample_a: Sequence[float],
    sample_b: Sequence[float],
    *,
    out_path: Path,
    label_a: str = "A",
    label_b: str = "B",
    title: str = "Distribution overlay",
) -> Path | None:
    plt = _setup_matplotlib()
    if plt is None:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(5, 3.5))
    ax.hist(list(sample_a), bins=20, alpha=0.5, label=label_a, density=True)
    ax.hist(list(sample_b), bins=20, alpha=0.5, label=label_b, density=True)
    ax.legend()
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def calibration_plot(
    predicted: Sequence[float],
    actual: Sequence[float],
    *,
    out_path: Path,
    bins: int = 10,
    title: str = "Calibration",
) -> Path | None:
    plt = _setup_matplotlib()
    if plt is None:
        return None
    try:
        import numpy as np
    except ImportError:
        return None
    pred = np.asarray(list(predicted), dtype=float)
    act = np.asarray(list(actual), dtype=float)
    if pred.size == 0:
        return None
    edges = np.linspace(0.0, 1.0, bins + 1)
    centres: list[float] = []
    fracs: list[float] = []
    for i in range(bins):
        mask = (pred >= edges[i]) & (pred < edges[i + 1])
        if i == bins - 1:
            mask = (pred >= edges[i]) & (pred <= edges[i + 1])
        if mask.sum() == 0:
            continue
        centres.append(float((edges[i] + edges[i + 1]) / 2.0))
        fracs.append(float(act[mask].mean()))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0.0, 1.0], [0.0, 1.0], color="grey", linewidth=0.8, linestyle="--")
    ax.plot(centres, fracs, marker="o")
    ax.set_xlabel("predicted")
    ax.set_ylabel("empirical")
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path

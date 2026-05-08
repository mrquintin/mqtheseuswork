"""Replication verification.

Compares two run directories (each containing a replication envelope
plus one or more metrics JSON files) and produces a verdict:

- ``incompatible`` — envelopes disagree on a structural field
  (different runner, different dataset hash, different deterministic
  flag, different model set). The numbers are not comparable; that is
  the verdict, full stop.
- ``mismatch`` — envelopes are compatible but metric values diverge
  outside the firm's declared tolerance.
- ``match`` — envelopes compatible, metrics agree within tolerance.

The firm's tolerance is published here, not in the comparison call,
so reviewers see exactly what bar a replication is being held to.
"""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from replication.lib.envelope import (
    ENVELOPE_FILENAME,
    Envelope,
    STRUCTURAL_FIELDS,
    read_envelope,
)

# ---------------------------------------------------------------------------
# Tolerance — the firm's declared bar for "the numbers agree".
#
# Bit-stable mode (deterministic + same machine) should hit zero. Mode
# tolerances above zero are for runs across machines or after a model
# upgrade. The page at /methodology/replicate documents these bounds;
# any change here is a public revision of what counts as a successful
# replication.

DETERMINISTIC_ABS_TOL = 1e-12
DEFAULT_ABS_TOL = 5e-3  # 0.5 percentage points on a [0, 1] metric
DEFAULT_REL_TOL = 1e-2

# Metric names compared by default. Other keys (latency, counts) are
# informative; the verdict is driven by the metrics that the firm's
# headline claims rest on.
DEFAULT_METRIC_KEYS: tuple[str, ...] = (
    "accuracy",
    "auroc_contradicting_vs_coherent",
    "ece_contradicting",
)

# Files compared by default, in priority order. The harness writes
# ``metrics_<runner>.json`` for QH; cross-model and ablation use
# ``metrics_summary.json``.
DEFAULT_METRIC_FILES: tuple[str, ...] = (
    "metrics_summary.json",
)


@dataclasses.dataclass
class VerificationReport:
    verdict: str  # "match" | "mismatch" | "incompatible"
    structural_diff: dict[str, tuple[Any, Any]]
    metric_diff: list[dict[str, Any]]
    informational: list[str]
    abs_tol: float
    rel_tol: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "structural_diff": {
                k: list(v) for k, v in self.structural_diff.items()
            },
            "metric_diff": list(self.metric_diff),
            "informational": list(self.informational),
            "abs_tol": float(self.abs_tol),
            "rel_tol": float(self.rel_tol),
        }


# ---------------------------------------------------------------------------
# Envelope comparison


def compare_envelopes(a: Envelope, b: Envelope) -> dict[str, tuple[Any, Any]]:
    """Return the structural fields that differ.

    Empty dict means the envelopes are compatible. Caller decides what
    to do with non-structural drift (git SHA, OS) — that is reported
    in :func:`verify_runs` as informational, not as failure.
    """
    a_struct = a.structural()
    b_struct = b.structural()
    diff: dict[str, tuple[Any, Any]] = {}
    for field in STRUCTURAL_FIELDS:
        if a_struct.get(field) != b_struct.get(field):
            diff[field] = (a_struct.get(field), b_struct.get(field))
    return diff


def informational_drift(a: Envelope, b: Envelope) -> list[str]:
    """Return a list of human-readable lines about non-structural drift."""
    notes: list[str] = []
    if a.git_sha != b.git_sha:
        notes.append(
            f"git SHA differs: {a.git_sha[:12]} vs {b.git_sha[:12]} "
            "(informational; numbers may still agree)"
        )
    if a.git_dirty or b.git_dirty:
        notes.append(
            "at least one envelope was recorded against a dirty worktree; "
            "the SHA is not actually a fixed point"
        )
    if a.python_version != b.python_version:
        notes.append(
            f"Python version differs: {a.python_version} vs {b.python_version}"
        )
    if a.platform != b.platform:
        notes.append(f"platform differs: {a.platform} vs {b.platform}")
    if a.deterministic != b.deterministic:
        notes.append(
            "deterministic flag differs — this is a structural mismatch, "
            "not just informational"
        )
    return notes


# ---------------------------------------------------------------------------
# Metric comparison


def _flatten(prefix: str, obj: Any, out: dict[str, float]) -> None:
    """Walk a metrics dict and collect numeric leaves keyed by dotted path."""
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            _flatten(f"{prefix}.{k}" if prefix else str(k), v, out)
    elif isinstance(obj, (list, tuple)):
        # Lists in metrics blobs are usually CIs; index them so order
        # is preserved.
        for i, v in enumerate(obj):
            _flatten(f"{prefix}[{i}]", v, out)
    else:
        if isinstance(obj, bool):
            return
        if isinstance(obj, (int, float)):
            v = float(obj)
            if not math.isnan(v):
                out[prefix] = v


def _close(a: float, b: float, *, abs_tol: float, rel_tol: float) -> bool:
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)


def compare_metrics(
    prior: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    keys: Sequence[str] | None = None,
    abs_tol: float = DEFAULT_ABS_TOL,
    rel_tol: float = DEFAULT_REL_TOL,
) -> list[dict[str, Any]]:
    """Compare two flat-or-nested metrics dicts.

    Returns the list of metric-level disagreements, each
    ``{key, prior, current, abs_diff}``. Empty list means the metrics
    agree within tolerance.
    """
    flat_a: dict[str, float] = {}
    flat_b: dict[str, float] = {}
    _flatten("", prior, flat_a)
    _flatten("", current, flat_b)
    if keys is None:
        candidate_keys = sorted(set(flat_a) | set(flat_b))
        # Restrict to interesting keys when no override is provided.
        candidate_keys = [
            k
            for k in candidate_keys
            if any(k == name or k.endswith("." + name) for name in DEFAULT_METRIC_KEYS)
        ]
    else:
        candidate_keys = list(keys)
    diffs: list[dict[str, Any]] = []
    for k in candidate_keys:
        if k not in flat_a or k not in flat_b:
            diffs.append(
                {
                    "key": k,
                    "prior": flat_a.get(k),
                    "current": flat_b.get(k),
                    "note": "missing in one of the runs",
                }
            )
            continue
        a = flat_a[k]
        b = flat_b[k]
        if not _close(a, b, abs_tol=abs_tol, rel_tol=rel_tol):
            diffs.append(
                {
                    "key": k,
                    "prior": a,
                    "current": b,
                    "abs_diff": abs(a - b),
                }
            )
    return diffs


# ---------------------------------------------------------------------------
# Run-directory verification


def _gather_metric_files(
    run_dir: Path, *, filenames: Iterable[str] | None
) -> list[Path]:
    """Return metric JSON files inside ``run_dir`` worth comparing.

    Strategy: prefer the explicit filenames; fall back to anything that
    looks like a metrics file (``metrics_*.json``). The fallback keeps
    the verifier useful even when a runner shape changes.
    """
    if filenames:
        explicit = [run_dir / f for f in filenames if (run_dir / f).is_file()]
        if explicit:
            return explicit
    return sorted(run_dir.glob("metrics_*.json"))


def verify_runs(
    prior_dir: Path | str,
    current_dir: Path | str,
    *,
    abs_tol: float | None = None,
    rel_tol: float = DEFAULT_REL_TOL,
    metric_files: Iterable[str] | None = DEFAULT_METRIC_FILES,
    metric_keys: Sequence[str] | None = None,
) -> VerificationReport:
    """Compare two replication run directories end-to-end.

    Tolerance defaulting: when both envelopes are deterministic and on
    the same platform, the harness uses ``DETERMINISTIC_ABS_TOL`` (i.e.
    insists on bit-stability). Otherwise it uses ``DEFAULT_ABS_TOL``.
    Override with the ``abs_tol`` argument if you need a different bar.
    """
    prior = read_envelope(prior_dir)
    current = read_envelope(current_dir)
    structural_diff = compare_envelopes(prior, current)
    info = informational_drift(prior, current)

    if abs_tol is None:
        same_platform = prior.platform == current.platform
        if prior.deterministic and current.deterministic and same_platform:
            abs_tol_resolved = DETERMINISTIC_ABS_TOL
        else:
            abs_tol_resolved = DEFAULT_ABS_TOL
    else:
        abs_tol_resolved = float(abs_tol)

    if structural_diff:
        return VerificationReport(
            verdict="incompatible",
            structural_diff=structural_diff,
            metric_diff=[],
            informational=info
            + [
                "structural mismatch: numbers from these two runs are not "
                "comparable. Re-run with the same dataset, runner, model "
                "set, and deterministic flag."
            ],
            abs_tol=abs_tol_resolved,
            rel_tol=rel_tol,
        )

    prior_files = _gather_metric_files(Path(prior_dir), filenames=metric_files)
    current_files = _gather_metric_files(Path(current_dir), filenames=metric_files)
    if not prior_files or not current_files:
        return VerificationReport(
            verdict="incompatible",
            structural_diff={},
            metric_diff=[],
            informational=info
            + [
                f"no metrics files found in one of the run dirs "
                f"(prior={len(prior_files)}, current={len(current_files)}); "
                "verify there is a metrics_*.json present"
            ],
            abs_tol=abs_tol_resolved,
            rel_tol=rel_tol,
        )

    # Pair files by name when possible, otherwise compare the first of
    # each. We err on the side of being explicit about which files we
    # paired so the output is auditable.
    paired: list[tuple[Path, Path]] = []
    by_name = {p.name: p for p in current_files}
    for f in prior_files:
        match = by_name.get(f.name)
        if match is not None:
            paired.append((f, match))
    if not paired:
        # Different filenames on each side; pair positionally and note it.
        paired = list(zip(sorted(prior_files), sorted(current_files)))
        info.append(
            "metric filenames differ between runs; paired positionally "
            "(check the metric_diff entries to confirm what was compared)"
        )

    all_diffs: list[dict[str, Any]] = []
    for prior_path, current_path in paired:
        a_blob = json.loads(prior_path.read_text(encoding="utf-8"))
        b_blob = json.loads(current_path.read_text(encoding="utf-8"))
        diffs = compare_metrics(
            a_blob,
            b_blob,
            keys=metric_keys,
            abs_tol=abs_tol_resolved,
            rel_tol=rel_tol,
        )
        for d in diffs:
            d["file"] = prior_path.name
        all_diffs.extend(diffs)

    verdict = "match" if not all_diffs else "mismatch"
    return VerificationReport(
        verdict=verdict,
        structural_diff={},
        metric_diff=all_diffs,
        informational=info,
        abs_tol=abs_tol_resolved,
        rel_tol=rel_tol,
    )


# ---------------------------------------------------------------------------
# CLI entry point used by ``make verify``


def _format_report(report: VerificationReport) -> str:
    lines: list[str] = [f"verdict: {report.verdict}"]
    lines.append(
        f"tolerance: abs={report.abs_tol:.2e} rel={report.rel_tol:.2e}"
    )
    if report.structural_diff:
        lines.append("structural diffs:")
        for k, (pv, cv) in report.structural_diff.items():
            lines.append(f"  - {k}: prior={pv!r} current={cv!r}")
    if report.metric_diff:
        lines.append("metric diffs:")
        for d in report.metric_diff:
            f = d.get("file", "?")
            k = d.get("key", "?")
            note = d.get("note")
            if note:
                lines.append(f"  - [{f}] {k}: {note}")
            else:
                lines.append(
                    f"  - [{f}] {k}: prior={d.get('prior')} "
                    f"current={d.get('current')} "
                    f"(|Δ| = {d.get('abs_diff', float('nan')):.4g})"
                )
    if report.informational:
        lines.append("informational:")
        for n in report.informational:
            lines.append(f"  - {n}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Compare two replication run directories. Exits 0 on match, "
            "2 on mismatch, 3 on incompatible envelopes."
        )
    )
    parser.add_argument("prior", help="Path to a prior run directory")
    parser.add_argument("current", help="Path to the current run directory")
    parser.add_argument(
        "--abs-tol",
        type=float,
        default=None,
        help="Absolute tolerance override (default: deterministic-aware)",
    )
    parser.add_argument(
        "--rel-tol",
        type=float,
        default=DEFAULT_REL_TOL,
        help="Relative tolerance (default: 1e-2)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON instead of human-readable text",
    )
    args = parser.parse_args(argv)

    report = verify_runs(
        args.prior, args.current, abs_tol=args.abs_tol, rel_tol=args.rel_tol
    )
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(_format_report(report))
    if report.verdict == "match":
        return 0
    if report.verdict == "incompatible":
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

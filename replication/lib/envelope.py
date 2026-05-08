"""Reproducibility envelope.

Every replication target writes a small JSON record describing *what*
it ran, separately from the numbers it produced. Two replications are
"compatible" iff their envelopes match on the structural fields:

- ``benchmark_version``    e.g. ``qh-v1``. Frozen by the dataset.
- ``runner``               e.g. ``contradiction_geometry``.
- ``dataset_sha256``       Hash of the dataset shard actually consumed.
- ``models``               Sorted tuple of model identifiers.
- ``deterministic``        Whether the runner ran in deterministic mode.

Comparing envelopes that disagree on these fields produces a clear
"incompatible" verdict; the firm does not pretend numbers from
different inputs can be compared. Non-structural fields (git SHA,
timestamp, OS, Python version) are recorded for context but do not
gate compatibility — a different SHA is informative, not disqualifying.

The envelope is read and written by the harness only; production code
never depends on it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ENVELOPE_FILENAME = "replication_envelope.json"
ENVELOPE_VERSION = "envelope-v1"

# Fields that must match for two runs to be "compatible". Numbers can
# only be compared meaningfully across runs whose envelopes agree here.
STRUCTURAL_FIELDS: tuple[str, ...] = (
    "benchmark_version",
    "runner",
    "dataset_sha256",
    "models",
    "deterministic",
)


@dataclasses.dataclass(frozen=True)
class Envelope:
    """The reproducibility envelope written alongside every run."""

    envelope_version: str
    benchmark_version: str
    runner: str
    dataset_path: str
    dataset_sha256: str
    models: tuple[str, ...]
    deterministic: bool
    seed: int | None
    git_sha: str
    git_dirty: bool
    python_version: str
    platform: str
    os_release: str
    started_at_utc: str
    finished_at_utc: str | None
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["models"] = list(self.models)
        return d

    def structural(self) -> dict[str, Any]:
        """Just the fields that gate cross-run comparability."""
        return {
            "benchmark_version": self.benchmark_version,
            "runner": self.runner,
            "dataset_sha256": self.dataset_sha256,
            "models": list(self.models),
            "deterministic": self.deterministic,
        }


# ---------------------------------------------------------------------------
# Construction


def hash_dataset(path: Path | str) -> str:
    """Return ``sha256:<hex>`` of the dataset file's bytes.

    Works for any file (JSONL, CSV, tarball). For directories, walks
    children in sorted order and hashes ``(relpath, content)`` pairs so
    the digest is deterministic regardless of filesystem order.
    """
    p = Path(path)
    if not p.exists():
        return "sha256:missing"
    h = hashlib.sha256()
    if p.is_file():
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    else:
        for child in sorted(p.rglob("*")):
            if not child.is_file():
                continue
            rel = child.relative_to(p).as_posix()
            h.update(rel.encode("utf-8"))
            h.update(b"\0")
            with child.open("rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            h.update(b"\0\0")
    return f"sha256:{h.hexdigest()}"


def _git_sha(repo_root: Path | None = None) -> tuple[str, bool]:
    """Return (sha, dirty). ``dirty`` is True when the worktree has
    uncommitted changes; this matters for replication because a dirty
    SHA is not actually a fixed point."""
    cwd = str(repo_root) if repo_root else None
    try:
        sha_proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if sha_proc.returncode != 0:
            return ("unknown", False)
        sha = sha_proc.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        dirty = bool(status.stdout.strip()) if status.returncode == 0 else False
        return (sha, dirty)
    except (FileNotFoundError, subprocess.SubprocessError):
        return ("unknown", False)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_envelope(
    *,
    benchmark_version: str,
    runner: str,
    dataset_path: Path | str,
    models: Iterable[str] = (),
    deterministic: bool = False,
    seed: int | None = None,
    repo_root: Path | None = None,
    started_at_utc: str | None = None,
    finished_at_utc: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Envelope:
    """Build an envelope from runtime context. Pure: does not write."""
    sha, dirty = _git_sha(repo_root)
    return Envelope(
        envelope_version=ENVELOPE_VERSION,
        benchmark_version=str(benchmark_version),
        runner=str(runner),
        dataset_path=str(dataset_path),
        dataset_sha256=hash_dataset(dataset_path),
        models=tuple(sorted(models)),
        deterministic=bool(deterministic),
        seed=int(seed) if seed is not None else None,
        git_sha=sha,
        git_dirty=dirty,
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        os_release=platform.release(),
        started_at_utc=started_at_utc or _now_utc(),
        finished_at_utc=finished_at_utc,
        extra=dict(extra) if extra else {},
    )


# ---------------------------------------------------------------------------
# I/O


def write_envelope(envelope: Envelope, run_dir: Path | str) -> Path:
    """Write the envelope JSON into ``run_dir``. Idempotent."""
    out_dir = Path(run_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / ENVELOPE_FILENAME
    out_path.write_text(
        json.dumps(envelope.as_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return out_path


def read_envelope(run_dir: Path | str) -> Envelope:
    """Load the envelope JSON from ``run_dir``.

    Accepts either the directory containing the file or the file path
    itself. Raises ``FileNotFoundError`` with a friendly message when
    the envelope is absent, since that is a frequent user error.
    """
    p = Path(run_dir)
    if p.is_dir():
        p = p / ENVELOPE_FILENAME
    if not p.exists():
        raise FileNotFoundError(
            f"no replication envelope at {p}. Did the run finish, or "
            "are you pointing at a non-replication directory?"
        )
    raw = json.loads(p.read_text(encoding="utf-8"))
    return Envelope(
        envelope_version=str(raw.get("envelope_version", "envelope-v0")),
        benchmark_version=str(raw["benchmark_version"]),
        runner=str(raw["runner"]),
        dataset_path=str(raw.get("dataset_path", "")),
        dataset_sha256=str(raw["dataset_sha256"]),
        models=tuple(raw.get("models", []) or []),
        deterministic=bool(raw.get("deterministic", False)),
        seed=raw.get("seed"),
        git_sha=str(raw.get("git_sha", "unknown")),
        git_dirty=bool(raw.get("git_dirty", False)),
        python_version=str(raw.get("python_version", "unknown")),
        platform=str(raw.get("platform", "unknown")),
        os_release=str(raw.get("os_release", "unknown")),
        started_at_utc=str(raw.get("started_at_utc", "")),
        finished_at_utc=raw.get("finished_at_utc"),
        extra=dict(raw.get("extra", {}) or {}),
    )


# ---------------------------------------------------------------------------
# Helpers used by the runner scripts


def apply_deterministic_env() -> dict[str, str]:
    """Set process env vars that disable common nondeterminism sources.

    Returns the dict of vars set so the caller can record them in the
    envelope's ``extra`` field. Safe to call repeatedly.
    """
    vars_to_set = {
        "PYTHONHASHSEED": "0",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
        "TF_DETERMINISTIC_OPS": "1",
    }
    for k, v in vars_to_set.items():
        os.environ.setdefault(k, v)
    return dict(vars_to_set)


def discover_available_models() -> list[str]:
    """Return the cross-model adapter names whose API keys are present.

    A "skip" log line is the harness's way of saying: this model could
    not be exercised on this machine; that is data, not failure.
    """
    available = ["hash-det"]  # always works, no key needed
    if os.environ.get("OPENAI_API_KEY"):
        available.append("openai-3-large")
    if os.environ.get("VOYAGE_API_KEY"):
        available.append("voyage-3")
    if os.environ.get("COHERE_API_KEY"):
        available.append("cohere-en-v3")
    return available

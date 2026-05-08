"""Red-team tournament harness.

A tournament is a structured, repeatable comparison: a frozen
conclusion bench is reviewed by several reviewer configurations
(provider mix, prompt variant, temperature, seed). Each configuration
returns a set of severity-scored objections. The tournament aggregates
the objections into a per-configuration leaderboard row, then performs
inter-config cross-validation — given configuration ``A``'s
high-severity objections on a conclusion, can configuration ``B``
reproduce a high-severity objection on the same conclusion?

The honest comparison is what makes the leaderboard load-bearing. The
swarm itself is a noisy adversary; the tournament's discipline is

* **Frozen bench.** The conclusion set is versioned and immutable —
  every configuration is judged on the same material. Adding items
  ships as ``v2/`` rather than mutating ``v1/``.
* **Content-addressable configs.** A configuration's id is a
  deterministic hash of its provider mix, prompt variant, temperature,
  and seed. Same inputs → same id; the leaderboard cannot quietly mutate
  what a row means.
* **Reproducibility envelope.** The tournament writes an envelope
  alongside every run (bench hash, configuration ids, environment
  metadata). The leaderboard surfaces the envelope's hash so a row
  whose envelope cannot be reproduced is flagged rather than promoted.

The harness is deliberately swarm-pluggable: the default driver calls
:meth:`SwarmOrchestrator.run_multi_provider`, but tests inject a stub
that returns canned :class:`ObjectionResult` lists. This lets the test
suite exercise the cross-validation and leaderboard logic without
touching a real provider.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

from noosphere.models import Conclusion, ConfidenceTier
from noosphere.peer_review.providers import ObjectionResult
from noosphere.peer_review.severity import (
    ObjectionSeverity,
    SeverityAggregate,
    SeverityInputs,
    aggregate as aggregate_severity,
    score_objection as score_objection_severity,
)

logger = logging.getLogger(__name__)


TOURNAMENT_VERSION = "redteam-tournament-v1"
DEFAULT_BENCH_PATH = (
    Path(__file__).resolve().parents[3]
    / "benchmarks"
    / "redteam"
    / "v1"
    / "conclusion_bench.jsonl"
)


# ── Bench loader ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class BenchItem:
    """One frozen conclusion in the tournament bench."""

    id: str
    text: str
    reasoning: str
    domain: str
    license: str
    frozen_at: str
    confidence: float = 0.5
    severity_inputs: SeverityInputs = field(default_factory=SeverityInputs)

    def as_conclusion(self) -> Conclusion:
        return Conclusion(
            id=self.id,
            text=self.text,
            reasoning=self.reasoning,
            confidence=self.confidence,
            confidence_tier=ConfidenceTier.MODERATE,
        )


def _coerce_severity_inputs(blob: Optional[dict[str, Any]]) -> SeverityInputs:
    blob = blob or {}
    return SeverityInputs(
        cascade_weight=float(blob.get("cascade_weight", 0.0)),
        claim_centrality=float(blob.get("claim_centrality", 0.0)),
        failure_mode_severity=float(blob.get("failure_mode_severity", 0.0)),
        source_credibility=(
            float(blob["source_credibility"])
            if blob.get("source_credibility") is not None
            else None
        ),
        judge_severity=(
            float(blob["judge_severity"])
            if blob.get("judge_severity") is not None
            else None
        ),
    )


def load_bench(path: Path | str = DEFAULT_BENCH_PATH) -> list[BenchItem]:
    """Read the frozen JSONL bench. Raises ``FileNotFoundError`` if missing."""

    p = Path(path)
    items: list[BenchItem] = []
    with p.open("r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            items.append(
                BenchItem(
                    id=obj["id"],
                    text=obj["text"],
                    reasoning=obj.get("reasoning", ""),
                    domain=obj.get("domain", "unspecified"),
                    license=obj.get("license", "firm-internal-public"),
                    frozen_at=obj.get("frozen_at", ""),
                    confidence=float(obj.get("confidence", 0.5)),
                    severity_inputs=_coerce_severity_inputs(
                        obj.get("severity_inputs")
                    ),
                )
            )
    return items


def bench_sha256(path: Path | str = DEFAULT_BENCH_PATH) -> str:
    """Stable hash of the bench file bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ── Reviewer configurations (content-addressable) ────────────────────


@dataclass(frozen=True)
class ReviewerConfig:
    """A reviewer configuration the tournament can evaluate.

    The configuration's :attr:`config_id` is a deterministic content
    hash of every input that meaningfully changes the configuration's
    output — provider mix, prompt variant, temperature, seed. Same
    inputs → same id. This is what makes the leaderboard honest: if
    two rows share an id, they came from the same configuration.

    ``label`` and ``description`` are display-only; they do **not** feed
    the id. A row whose label changes still has the same id and is the
    same row.
    """

    provider_mix: tuple[str, ...]
    prompt_variant: str
    temperature: float
    seed: int
    label: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        # Pydantic-free dataclass; cheap normalisation.
        if not self.provider_mix:
            raise ValueError("provider_mix must contain at least one provider")

    @property
    def config_id(self) -> str:
        payload = {
            "provider_mix": sorted(self.provider_mix),
            "prompt_variant": self.prompt_variant,
            "temperature": round(float(self.temperature), 6),
            "seed": int(self.seed),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "cfg-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @property
    def display_label(self) -> str:
        return self.label or "+".join(sorted(self.provider_mix))

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_id": self.config_id,
            "label": self.display_label,
            "description": self.description,
            "provider_mix": list(self.provider_mix),
            "prompt_variant": self.prompt_variant,
            "temperature": float(self.temperature),
            "seed": int(self.seed),
        }


# ── Per-conclusion + per-config result ───────────────────────────────


@dataclass
class ConfigConclusionResult:
    """One configuration's review of one bench item."""

    config_id: str
    bench_item_id: str
    objections: list[ObjectionResult] = field(default_factory=list)
    severities: list[ObjectionSeverity] = field(default_factory=list)
    aggregate: Optional[SeverityAggregate] = None
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    partial: bool = False
    partial_reason: Optional[str] = None

    @property
    def high_severity_count(self) -> int:
        return self.aggregate.high_count if self.aggregate else 0

    @property
    def has_high(self) -> bool:
        return self.high_severity_count > 0


# ── Reviewer driver protocol ─────────────────────────────────────────


# A reviewer driver runs a configuration against a single bench item and
# returns the (objections, severities, partial) triple. The default
# wraps SwarmOrchestrator; tests inject a stub.
ReviewerDriver = Callable[
    [ReviewerConfig, BenchItem],
    tuple[list[ObjectionResult], list[ObjectionSeverity], bool, Optional[str]],
]


def default_reviewer_driver(
    config: ReviewerConfig, item: BenchItem
) -> tuple[list[ObjectionResult], list[ObjectionSeverity], bool, Optional[str]]:
    """Default driver: route through the multi-provider swarm.

    Lazily imports :class:`SwarmOrchestrator` so unit tests that stub
    the driver don't need a configured store. The default driver is
    the production path — operators run it from the recurring workflow.
    """

    from noosphere.peer_review.providers import all_adapters
    from noosphere.peer_review.swarm import SwarmOrchestrator
    from noosphere.store import Store

    store = Store.from_database_url("sqlite:///:memory:")
    store.put_conclusion(item.as_conclusion())

    adapters = [a for a in all_adapters() if a.name in config.provider_mix]
    if not adapters:
        return ([], [], True, "no_adapters_for_config")

    orch = SwarmOrchestrator(store)
    run = orch.run_multi_provider(
        item.id,
        context={"severity": _severity_inputs_as_context(item.severity_inputs)},
        adapters=adapters,
        temperature=config.temperature,
        seed=config.seed,
        persist_findings=False,
    )
    return (
        run.objections,
        run.severities,
        bool(run.partial),
        run.partial_reason,
    )


def _severity_inputs_as_context(inp: SeverityInputs) -> dict[str, Any]:
    return {
        "cascade_weight": inp.cascade_weight,
        "claim_centrality": inp.claim_centrality,
        "failure_mode_severity": inp.failure_mode_severity,
        "source_credibility": inp.source_credibility,
        "judge_severity": inp.judge_severity,
    }


# ── Cross-validation ─────────────────────────────────────────────────


@dataclass(frozen=True)
class CrossValidationCell:
    """How well config B reproduces config A's high-severity items."""

    config_a: str
    config_b: str
    targets: int  # bench items where A produced ≥1 high-severity objection
    reproduced: int  # of those, items where B also produced ≥1 high
    score: float  # reproduced / targets, or 1.0 when targets == 0


def cross_validate(
    per_config: dict[str, list[ConfigConclusionResult]],
) -> list[CrossValidationCell]:
    """Compute pairwise reproduction scores.

    For each ordered pair (A, B), the cell records the fraction of
    bench items on which A produced a high-severity objection and B
    also produced a high-severity objection on the same item. This is
    the bare reproduction signal — not a similarity metric on the
    objection text, which would fold model-specific phrasing into the
    score. The text-level signal is the swarm's NLI disagreement
    detector (a different question).

    A cell with ``targets == 0`` scores 1.0 by convention: A flagged
    nothing, so there is nothing for B to fail to reproduce.
    """

    config_ids = list(per_config.keys())
    cells: list[CrossValidationCell] = []
    for a in config_ids:
        a_high: set[str] = {
            r.bench_item_id for r in per_config[a] if r.has_high
        }
        for b in config_ids:
            if a == b:
                continue
            b_high: set[str] = {
                r.bench_item_id for r in per_config[b] if r.has_high
            }
            targets = len(a_high)
            reproduced = len(a_high & b_high)
            score = (reproduced / targets) if targets else 1.0
            cells.append(
                CrossValidationCell(
                    config_a=a,
                    config_b=b,
                    targets=targets,
                    reproduced=reproduced,
                    score=score,
                )
            )
    return cells


def agreement_score(
    config_id: str, cells: Sequence[CrossValidationCell]
) -> float:
    """Mean of every cell where ``config_id`` is the *target* (config A).

    Read as: "when this config raises a high-severity objection, how
    often does the rest of the field agree?" A configuration whose
    high-severity calls nobody else can reproduce trends low — exactly
    what the leaderboard should surface.
    """
    relevant = [c.score for c in cells if c.config_a == config_id]
    if not relevant:
        return 0.0
    return sum(relevant) / len(relevant)


# ── Leaderboard rows ─────────────────────────────────────────────────


@dataclass(frozen=True)
class LeaderboardRow:
    """One row in the public tournament leaderboard."""

    config_id: str
    label: str
    description: str
    severity_weighted_score: float
    high_count: int
    medium_count: int
    low_count: int
    objections_total: int
    agreement: float
    cost_usd: float
    latency_ms: float
    partial_runs: int
    bench_items_reviewed: int
    envelope_hash: str
    reproducible: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_id": self.config_id,
            "label": self.label,
            "description": self.description,
            "severity_weighted_score": round(self.severity_weighted_score, 4),
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "objections_total": self.objections_total,
            "agreement": round(self.agreement, 4),
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms": round(self.latency_ms, 2),
            "partial_runs": self.partial_runs,
            "bench_items_reviewed": self.bench_items_reviewed,
            "envelope_hash": self.envelope_hash,
            "reproducible": self.reproducible,
        }


# ── Tournament result ────────────────────────────────────────────────


@dataclass(frozen=True)
class ReproducibilityEnvelope:
    """Minimal envelope so a leaderboard row can prove what it ran on.

    Mirrors the structural fields the replication harness writes (see
    ``replication/lib/envelope.py``) so an outside reviewer can tie a
    leaderboard hash back to a concrete run on disk.
    """

    tournament_version: str
    bench_path: str
    bench_sha256: str
    config_ids: tuple[str, ...]
    started_at_utc: str
    finished_at_utc: str
    python_version: str
    platform: str

    @property
    def envelope_hash(self) -> str:
        canonical = json.dumps(
            {
                "tournament_version": self.tournament_version,
                "bench_sha256": self.bench_sha256,
                "config_ids": sorted(self.config_ids),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return "env-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tournament_version": self.tournament_version,
            "bench_path": self.bench_path,
            "bench_sha256": self.bench_sha256,
            "config_ids": list(self.config_ids),
            "started_at_utc": self.started_at_utc,
            "finished_at_utc": self.finished_at_utc,
            "python_version": self.python_version,
            "platform": self.platform,
            "envelope_hash": self.envelope_hash,
        }


@dataclass
class TournamentResult:
    """The full tournament output: leaderboard + envelope + raw cells."""

    envelope: ReproducibilityEnvelope
    leaderboard: list[LeaderboardRow]
    cross_validation: list[CrossValidationCell]
    per_config_results: dict[str, list[ConfigConclusionResult]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_dict(),
            "leaderboard": [row.to_dict() for row in self.leaderboard],
            "cross_validation": [
                {
                    "config_a": c.config_a,
                    "config_b": c.config_b,
                    "targets": c.targets,
                    "reproduced": c.reproduced,
                    "score": round(c.score, 4),
                }
                for c in self.cross_validation
            ],
        }


# ── Driver ───────────────────────────────────────────────────────────


def run_tournament(
    bench: Sequence[BenchItem],
    configs: Sequence[ReviewerConfig],
    *,
    driver: ReviewerDriver = default_reviewer_driver,
    bench_path: str | Path = DEFAULT_BENCH_PATH,
    bench_hash: Optional[str] = None,
    minimum_agreement_for_reproducible: float = 0.5,
) -> TournamentResult:
    """Run every configuration against every bench item and tabulate.

    Parameters
    ----------
    bench
        Frozen conclusion items. Loaded with :func:`load_bench` in
        production; tests pass a hand-built list.
    configs
        Reviewer configurations. Duplicate ``config_id`` values are
        rejected because the leaderboard would silently merge them.
    driver
        Function that runs one configuration on one bench item. The
        default routes through :class:`SwarmOrchestrator`; tests
        inject a deterministic stub.
    bench_path / bench_hash
        Filled into the reproducibility envelope. ``bench_hash`` is
        computed from ``bench_path`` if not provided and the path
        exists; otherwise it falls back to a hash of the in-memory
        bench item ids (good enough for the test path).
    minimum_agreement_for_reproducible
        A row whose agreement falls below this threshold is marked
        ``reproducible=False`` so the leaderboard can refuse to
        promote it.
    """

    seen_ids: set[str] = set()
    for c in configs:
        if c.config_id in seen_ids:
            raise ValueError(
                f"duplicate config_id {c.config_id} — content-addressable "
                "configurations must be distinct"
            )
        seen_ids.add(c.config_id)

    started = datetime.now(timezone.utc)

    per_config: dict[str, list[ConfigConclusionResult]] = {
        c.config_id: [] for c in configs
    }

    for config in configs:
        for item in bench:
            objections, severities, partial, partial_reason = driver(config, item)
            sev_agg = aggregate_severity(severities)
            cost = sum(o.cost_usd for o in objections if o.ok)
            latency = sum(o.latency_ms for o in objections)
            per_config[config.config_id].append(
                ConfigConclusionResult(
                    config_id=config.config_id,
                    bench_item_id=item.id,
                    objections=list(objections),
                    severities=list(severities),
                    aggregate=sev_agg,
                    cost_usd=cost,
                    latency_ms=latency,
                    partial=partial,
                    partial_reason=partial_reason,
                )
            )

    cells = cross_validate(per_config)

    finished = datetime.now(timezone.utc)
    bench_path_str = str(bench_path)
    if bench_hash is None:
        try:
            bench_hash = bench_sha256(bench_path)
        except (FileNotFoundError, OSError):
            bench_hash = hashlib.sha256(
                "|".join(item.id for item in bench).encode("utf-8")
            ).hexdigest()

    envelope = ReproducibilityEnvelope(
        tournament_version=TOURNAMENT_VERSION,
        bench_path=bench_path_str,
        bench_sha256=bench_hash,
        config_ids=tuple(c.config_id for c in configs),
        started_at_utc=started.isoformat(),
        finished_at_utc=finished.isoformat(),
        python_version=sys.version.split()[0],
        platform=platform.platform(),
    )

    leaderboard: list[LeaderboardRow] = []
    config_lookup = {c.config_id: c for c in configs}
    for cfg_id, results in per_config.items():
        cfg = config_lookup[cfg_id]
        weighted = 0.0
        high = medium = low = total = 0
        cost = 0.0
        latency = 0.0
        partial_runs = 0
        for r in results:
            if r.partial:
                partial_runs += 1
            if r.aggregate is not None:
                weighted += r.aggregate.weighted_count
                high += r.aggregate.high_count
                medium += r.aggregate.medium_count
                low += r.aggregate.low_count
                total += r.aggregate.objections_total
            cost += r.cost_usd
            latency += r.latency_ms

        agreement = agreement_score(cfg_id, cells)
        bench_n = len(results)
        avg_latency = latency / bench_n if bench_n else 0.0
        reproducible = (
            agreement >= minimum_agreement_for_reproducible
            and partial_runs == 0
        )
        leaderboard.append(
            LeaderboardRow(
                config_id=cfg_id,
                label=cfg.display_label,
                description=cfg.description,
                severity_weighted_score=weighted,
                high_count=high,
                medium_count=medium,
                low_count=low,
                objections_total=total,
                agreement=agreement,
                cost_usd=cost,
                latency_ms=avg_latency,
                partial_runs=partial_runs,
                bench_items_reviewed=bench_n,
                envelope_hash=envelope.envelope_hash,
                reproducible=reproducible,
            )
        )

    # Sort: reproducible-first, then severity-weighted score desc, then
    # agreement desc. The leaderboard's top entry is the configuration
    # the firm most trusts to draw blood and survive replication.
    leaderboard.sort(
        key=lambda r: (
            0 if r.reproducible else 1,
            -r.severity_weighted_score,
            -r.agreement,
        )
    )

    return TournamentResult(
        envelope=envelope,
        leaderboard=leaderboard,
        cross_validation=cells,
        per_config_results=per_config,
    )


# ── Result archival ──────────────────────────────────────────────────


def write_tournament_result(
    result: TournamentResult, archive_dir: Path | str
) -> Path:
    """Write the leaderboard + envelope to a timestamped JSON file.

    Recurring runs (see ``.github/workflows/redteam_tournament.yml``)
    archive every result so drift across runs feeds prompt 04's drift
    detector.
    """

    archive = Path(archive_dir)
    archive.mkdir(parents=True, exist_ok=True)
    stamp = result.envelope.finished_at_utc.replace(":", "-")
    out = archive / f"tournament-{stamp}.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2, sort_keys=True)
    return out


__all__ = [
    "BenchItem",
    "ConfigConclusionResult",
    "CrossValidationCell",
    "DEFAULT_BENCH_PATH",
    "LeaderboardRow",
    "ReproducibilityEnvelope",
    "ReviewerConfig",
    "ReviewerDriver",
    "TOURNAMENT_VERSION",
    "TournamentResult",
    "agreement_score",
    "bench_sha256",
    "cross_validate",
    "default_reviewer_driver",
    "load_bench",
    "run_tournament",
    "write_tournament_result",
]

"""
Counterfactual replay engine.

Given a past Conclusion and an alternative method, reconstruct the firm's
state as it stood at the conclusion's creation time and run the alternative
method against the same time-bounded inputs. The output is an alternative
confidence plus a reasoning trace, which can be compared to the actual
outcome (if the conclusion has a resolved Brier score) to ask:
"would the alternative method have done better?"

Three properties matter:

1. **No anachronism.** The replay is bounded by claims and conclusions
   visible at ``conclusion.created_at`` per ``temporal_replay``. A method
   that quietly reads from the live ledger would falsify the replay; we
   do not silently downgrade — the engine errors loud on incompatibility.

2. **Method compatibility.** Not every method can be re-run on every
   conclusion. ``extract_methodology`` cannot be replayed against a
   conclusion that has no transcript artifact in evidence. Compatibility
   is gated by an adapter registry: if no adapter knows how to project
   the conclusion into the method's input schema, replay raises
   ``MethodIncompatibleError``.

3. **Caching.** A counterfactual run is expensive. Results are cached
   by (method_version, conclusion_id, ledger_snapshot_id). The snapshot
   id is computed by ``temporal_replay.ledger_snapshot_id`` so the cache
   key changes when the underlying visibility set changes — replays do
   not become silently stale.

This module deliberately produces **private** numbers. Counterfactual
results are never published as-is; they will be misread (people will
assume the firm should have used the best-cell method, ignoring that
domain bounds and inputs differed). The public calibration scorecard
gets a single restrained line that says the analysis exists privately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

from noosphere.methods._registry import (
    REGISTRY,
    MethodNotFoundError,
    MethodRegistry,
)
from noosphere.models import Conclusion, Method
from noosphere.temporal_replay import (
    claim_visible_as_of,
    cutoff_datetime_inclusive_utc,
    embedding_model_disclaimer,
    ledger_snapshot_id,
)


class MethodIncompatibleError(Exception):
    """Raised when an alternative method has no adapter for a conclusion."""


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class LedgerSnapshot:
    """Frozen view of what the firm could see as of a past cutoff."""

    snapshot_id: str
    as_of: datetime
    visible_claim_ids: tuple[str, ...]
    visible_conclusion_ids: tuple[str, ...]
    encoder_warnings: tuple[str, ...]


@dataclass
class ReplayResult:
    """Output of one counterfactual replay invocation."""

    conclusion_id: str
    method_name: str
    method_version: str
    snapshot_id: str
    alternative_confidence: Optional[float]
    reasoning_trace: str
    raw_output: Any
    cached: bool = False


@dataclass
class WouldHaveBeenBetterCell:
    """One cell of the would-have-been-better matrix.

    ``mean_brier_delta`` is signed: ``alt - actual``. Negative means the
    alternative would have been better on average. ``mean_abs_brier_delta``
    is the prompt's "absolute Brier difference" aggregate — it measures
    how *different* the alternative would have been, regardless of which
    way the difference cuts.
    """

    actual_method: str
    alternative_method: str
    n: int
    mean_brier_actual: float
    mean_brier_alternative: float
    mean_brier_delta: float
    mean_abs_brier_delta: float
    alt_better_count: int


# An adapter projects (Conclusion, LedgerSnapshot, store) → method input.
MethodAdapter = Callable[[Conclusion, LedgerSnapshot, Any], Any]
# An extractor pulls a confidence float in [0, 1] out of a method's raw output.
ConfidenceExtractor = Callable[[Any], Optional[float]]


def _default_confidence_extractor(out: Any) -> Optional[float]:
    """Best-effort: pull ``confidence`` / ``probability`` from common shapes."""
    if isinstance(out, (int, float)):
        v = float(out)
        return v if 0.0 <= v <= 1.0 else None
    if hasattr(out, "confidence"):
        try:
            v = float(getattr(out, "confidence"))
            if 0.0 <= v <= 1.0:
                return v
        except (TypeError, ValueError):
            pass
    if isinstance(out, dict):
        for key in ("confidence", "probability", "probability_yes", "prediction"):
            if key in out:
                try:
                    v = float(out[key])
                    if 0.0 <= v <= 1.0:
                        return v
                except (TypeError, ValueError):
                    continue
    return None


class CounterfactualReplayEngine:
    """Replay alternative methods against past conclusions, bounded by ``as_of``."""

    def __init__(
        self,
        store: Any,
        registry: MethodRegistry = REGISTRY,
        adapters: Optional[dict[str, MethodAdapter]] = None,
        confidence_extractors: Optional[dict[str, ConfidenceExtractor]] = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._adapters: dict[str, MethodAdapter] = dict(adapters or {})
        self._extractors: dict[str, ConfidenceExtractor] = dict(
            confidence_extractors or {}
        )
        self._cache: dict[tuple[str, str, str], ReplayResult] = {}

    # ── public API ──────────────────────────────────────────────────

    def register_adapter(
        self,
        method_name: str,
        adapter: MethodAdapter,
        extractor: Optional[ConfidenceExtractor] = None,
    ) -> None:
        self._adapters[method_name] = adapter
        if extractor is not None:
            self._extractors[method_name] = extractor

    def is_compatible(self, conclusion: Conclusion, method_name: str) -> bool:
        if method_name not in self._adapters:
            return False
        try:
            self._registry.get(method_name)
        except MethodNotFoundError:
            return False
        try:
            snap = self.snapshot_for(conclusion)
            self._adapters[method_name](conclusion, snap, self._store)
        except MethodIncompatibleError:
            return False
        except Exception:
            return False
        return True

    def snapshot_for(self, conclusion: Conclusion) -> LedgerSnapshot:
        cutoff = _ensure_utc(conclusion.created_at)
        cutoff_date = cutoff.date()
        end_of_day = cutoff_datetime_inclusive_utc(cutoff_date)

        visible_claims: list[str] = []
        list_ids = getattr(self._store, "list_claim_ids", None)
        if callable(list_ids):
            for cid in list_ids():
                cl = self._store.get_claim(cid)
                if cl is not None and claim_visible_as_of(self._store, cl, end_of_day):
                    visible_claims.append(cid)

        visible_concls: list[str] = []
        list_concs = getattr(self._store, "list_conclusions", None)
        if callable(list_concs):
            for con in list_concs():
                if con.superseded_at is not None and _ensure_utc(con.superseded_at) <= cutoff:
                    continue
                if _ensure_utc(con.created_at) <= cutoff:
                    visible_concls.append(con.id)

        try:
            warns = tuple(embedding_model_disclaimer(self._store, cutoff_date))
        except Exception:
            warns = ()

        snap_id = ledger_snapshot_id(self._store, cutoff_date)
        return LedgerSnapshot(
            snapshot_id=snap_id,
            as_of=cutoff,
            visible_claim_ids=tuple(sorted(visible_claims)),
            visible_conclusion_ids=tuple(sorted(visible_concls)),
            encoder_warnings=warns,
        )

    def replay(
        self,
        conclusion: Conclusion,
        method_name: str,
        *,
        version: str = "latest",
    ) -> ReplayResult:
        spec, fn = self._resolve_method(method_name, version)
        adapter = self._adapters.get(spec.name)
        if adapter is None:
            raise MethodIncompatibleError(
                f"No adapter registered for method {spec.name}; "
                "cannot project conclusion into its input schema."
            )

        snap = self.snapshot_for(conclusion)
        cache_key = (f"{spec.name}@{spec.version}", conclusion.id, snap.snapshot_id)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return ReplayResult(
                conclusion_id=cached.conclusion_id,
                method_name=cached.method_name,
                method_version=cached.method_version,
                snapshot_id=cached.snapshot_id,
                alternative_confidence=cached.alternative_confidence,
                reasoning_trace=cached.reasoning_trace,
                raw_output=cached.raw_output,
                cached=True,
            )

        try:
            method_input = adapter(conclusion, snap, self._store)
        except MethodIncompatibleError:
            raise
        except Exception as e:
            raise MethodIncompatibleError(
                f"Adapter for {spec.name} could not project conclusion "
                f"{conclusion.id}: {e}"
            ) from e

        raw = fn(method_input)
        extractor = self._extractors.get(spec.name, _default_confidence_extractor)
        confidence = extractor(raw)
        trace = _trace_from_output(raw, snap)

        result = ReplayResult(
            conclusion_id=conclusion.id,
            method_name=spec.name,
            method_version=spec.version,
            snapshot_id=snap.snapshot_id,
            alternative_confidence=confidence,
            reasoning_trace=trace,
            raw_output=raw,
            cached=False,
        )
        self._cache[cache_key] = result
        return result

    def replay_all_compatible(
        self, conclusion: Conclusion
    ) -> list[ReplayResult]:
        out: list[ReplayResult] = []
        for name in sorted(self._adapters):
            try:
                self._registry.get(name)
            except MethodNotFoundError:
                continue
            try:
                out.append(self.replay(conclusion, name))
            except MethodIncompatibleError:
                continue
        return out

    # ── internals ───────────────────────────────────────────────────

    def _resolve_method(
        self, method_name: str, version: str
    ) -> tuple[Method, Callable]:
        return self._registry.get(method_name, version=version)


def _trace_from_output(raw: Any, snap: LedgerSnapshot) -> str:
    """Compose a short, structured reasoning trace from the raw output."""
    head = (
        f"snapshot={snap.snapshot_id} "
        f"as_of={snap.as_of.isoformat()} "
        f"n_claims={len(snap.visible_claim_ids)} "
        f"n_conclusions={len(snap.visible_conclusion_ids)}"
    )
    if hasattr(raw, "model_dump"):
        body = str(raw.model_dump())
    elif isinstance(raw, dict):
        body = str(raw)
    else:
        body = str(raw)
    if len(body) > 800:
        body = body[:797] + "..."
    return head + " | " + body


# ── comparison metric ──────────────────────────────────────────────


def _brier_binary(prob: float, actual: bool) -> float:
    return (float(prob) - (1.0 if actual else 0.0)) ** 2


@dataclass
class ResolvedRow:
    """A resolved binary forecast linked to a conclusion + actual method."""

    conclusion: Conclusion
    actual_method: str
    actual_confidence_yes: float
    outcome: bool


def would_have_been_better_matrix(
    engine: CounterfactualReplayEngine,
    rows: list[ResolvedRow],
    alternative_methods: list[str],
) -> list[WouldHaveBeenBetterCell]:
    """Aggregate per (actual_method, alternative_method) pair.

    For every (resolved row, alternative method) where the alternative
    is compatible with the row's conclusion, we score by Brier on the
    same realized outcome and aggregate. Cells with ``n == 0`` are
    omitted; the UI surfaces sample-size pills so small ``n`` is not
    silently presented as a verdict.
    """
    buckets: dict[tuple[str, str], dict[str, list[float]]] = {}
    for row in rows:
        actual_brier = _brier_binary(row.actual_confidence_yes, row.outcome)
        for alt in alternative_methods:
            if alt == row.actual_method:
                continue
            try:
                result = engine.replay(row.conclusion, alt)
            except MethodIncompatibleError:
                continue
            except MethodNotFoundError:
                continue
            if result.alternative_confidence is None:
                continue
            alt_brier = _brier_binary(result.alternative_confidence, row.outcome)
            key = (row.actual_method, alt)
            bucket = buckets.setdefault(
                key, {"actual": [], "alt": [], "abs_delta": [], "alt_better": []}
            )
            bucket["actual"].append(actual_brier)
            bucket["alt"].append(alt_brier)
            bucket["abs_delta"].append(abs(alt_brier - actual_brier))
            bucket["alt_better"].append(1.0 if alt_brier < actual_brier else 0.0)

    cells: list[WouldHaveBeenBetterCell] = []
    for (actual, alt), b in buckets.items():
        n = len(b["actual"])
        if n == 0:
            continue
        cells.append(
            WouldHaveBeenBetterCell(
                actual_method=actual,
                alternative_method=alt,
                n=n,
                mean_brier_actual=sum(b["actual"]) / n,
                mean_brier_alternative=sum(b["alt"]) / n,
                mean_brier_delta=(sum(b["alt"]) - sum(b["actual"])) / n,
                mean_abs_brier_delta=sum(b["abs_delta"]) / n,
                alt_better_count=int(sum(b["alt_better"])),
            )
        )
    cells.sort(key=lambda c: (c.actual_method, c.alternative_method))
    return cells


__all__ = [
    "ConfidenceExtractor",
    "CounterfactualReplayEngine",
    "LedgerSnapshot",
    "MethodAdapter",
    "MethodIncompatibleError",
    "ReplayResult",
    "ResolvedRow",
    "WouldHaveBeenBetterCell",
    "would_have_been_better_matrix",
]

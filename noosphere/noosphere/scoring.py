"""
Calibration scoreboard: Brier, log-loss, reliability bins, synthesis discount.

Honest-uncertainty predictions (midpoint ~0.5) are excluded from scoring aggregates
per firm policy (they neither help nor hurt calibration curves).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from noosphere.models import PredictiveClaim, PredictiveClaimStatus
from noosphere.store import Store

_BIN_EDGES = [i / 10 for i in range(11)]


def prob_mid(pc: PredictiveClaim) -> float:
    return 0.5 * (float(pc.prob_low) + float(pc.prob_high))


def brier_score(p: float, y: int) -> float:
    return (float(p) - float(y)) ** 2


def log_loss_binary(p: float, y: int, eps: float = 1e-6) -> float:
    p = min(1.0 - eps, max(eps, float(p)))
    if y == 1:
        return -math.log(p)
    return -math.log(1.0 - p)


def _resolved_rows(store: Store) -> list[tuple[PredictiveClaim, int, float]]:
    """(claim, outcome, prob_mid) for resolved + scoring-eligible rows."""
    out: list[tuple[PredictiveClaim, int, float]] = []
    for pc in store.list_predictive_claims():
        if pc.status != PredictiveClaimStatus.RESOLVED:
            continue
        if not pc.scoring_eligible or pc.honest_uncertainty:
            continue
        res = store.get_prediction_resolution_for_claim(pc.id)
        if res is None:
            continue
        y = int(res.outcome)
        out.append((pc, y, prob_mid(pc)))
    return out


def _primary_domain(pc: PredictiveClaim) -> str:
    if pc.domains:
        return pc.domains[0]
    return "unspecified"


def aggregate_author_domain(store: Store) -> dict[str, dict[str, dict[str, float]]]:
    """
    Nested dict author_key -> domain -> metrics:
    n, mean_brier, mean_log_loss

    Each resolved prediction contributes once, keyed by its **primary** ontology
    domain (first in ``domains``) to avoid double-counting multi-tagged rows.
    """
    buckets: dict[tuple[str, str], list[tuple[float, int]]] = defaultdict(list)
    for pc, y, p in _resolved_rows(store):
        dom = _primary_domain(pc)
        buckets[(pc.author_key or "unknown", dom)].append((p, y))
    out: dict[str, dict[str, dict[str, float]]] = {}
    for (author, dom), pairs in buckets.items():
        if author not in out:
            out[author] = {}
        bs = [brier_score(p, y) for p, y in pairs]
        ls = [log_loss_binary(p, y) for p, y in pairs]
        out[author][dom] = {
            "n": float(len(pairs)),
            "mean_brier": sum(bs) / len(bs) if bs else 0.0,
            "mean_log_loss": sum(ls) / len(ls) if ls else 0.0,
        }
    return out


def calibration_bins(
    store: Store,
    *,
    author_key: str | None = None,
    domain: str | None = None,
) -> list[dict[str, float]]:
    """
    Decile bins on stated probability mid; empirical hit rate with Beta(0.5,0.5) smoothing.
    """
    hits = [0] * 10
    totals = [0] * 10
    for pc, y, p in _resolved_rows(store):
        if author_key and (pc.author_key or "unknown") != author_key:
            continue
        if domain and domain not in (pc.domains or []):
            continue
        idx = min(9, max(0, int(p * 10)))
        totals[idx] += 1
        hits[idx] += y
    rows: list[dict[str, float]] = []
    for i in range(10):
        lo, hi = _BIN_EDGES[i], _BIN_EDGES[i + 1]
        n = totals[i]
        rate = (hits[i] + 0.5) / (n + 1.0) if n else float("nan")
        rows.append(
            {
                "bin_low": lo,
                "bin_high": hi,
                "bin_mid": 0.5 * (lo + hi),
                "n": float(n),
                "empirical_rate": rate,
            }
        )
    return rows


def _pool_hits_for_stated_probability(
    store: Store,
    author_key: str,
    domain: str,
    stated: float,
) -> tuple[float, float, str]:
    """
    Return (hits, trials, pool_note) for the reliability bin for ``stated``,
    preferring ``domain`` then pooling all domains for the same author.
    """
    idx = min(9, max(0, int(float(stated) * 10)))

    def collect(filter_domain: bool) -> tuple[float, float]:
        h = t = 0.0
        for pc, y, p in _resolved_rows(store):
            if (pc.author_key or "unknown") != author_key:
                continue
            if filter_domain and domain not in (pc.domains or []):
                continue
            if min(9, max(0, int(p * 10))) == idx:
                h += float(y)
                t += 1.0
        return h, t

    h, t = collect(True)
    note = f"bin={idx} domain={domain!r}"
    if t < 5.0:
        h2, t2 = collect(False)
        if t2 >= t:
            h, t = h2, t2
            note = f"bin={idx} pooled_across_domains"
    return h, t, note


def beta_smoothed_rate(hits: float, trials: float, a: float = 0.5, b: float = 0.5) -> float:
    return (hits + a) / (trials + a + b) if trials + a + b > 0 else 0.5


def discount_conclusion_confidence(
    store: Store,
    *,
    author_key: str,
    domain: str,
    stated_confidence: float,
) -> tuple[float, str]:
    """
    Map stated confidence to an **empirically expected resolution rate** in the
    matching probability decile, using a Beta(0.5, 0.5) prior per bin.

    This is the firm's principled stand-in for a full hierarchical calibration model:
    the posterior mean in the stated-probability bin is the best single-number
    summary of how often similar past predictions resolved true, under a weak prior.
    """
    c = float(max(0.01, min(0.99, stated_confidence)))
    h, t, note = _pool_hits_for_stated_probability(store, author_key, domain, c)
    if t <= 0.0:
        return c, "calibration_discount:insufficient_history " + note
    adj = beta_smoothed_rate(h, t)
    adj = float(max(0.01, min(0.99, adj)))
    return adj, f"calibration_discount:{note} trials={int(t)} posterior_mean={adj:.4f}"


def weak_calibration_domains(
    store: Store,
    *,
    max_items: int = 6,
    min_n: int = 4,
) -> list[tuple[str, str, float, int]]:
    """
    (author, domain, mean_brier, n) for pockets worth deeper empirical work.
    Sorted by mean_brier descending.
    """
    agg = aggregate_author_domain(store)
    rows: list[tuple[str, str, float, int]] = []
    for author, doms in agg.items():
        for dom, m in doms.items():
            n = int(m["n"])
            if n < min_n:
                continue
            rows.append((author, dom, float(m["mean_brier"]), n))
    rows.sort(key=lambda x: -x[2])
    return rows[:max_items]


def scoreboard_payload(store: Store) -> dict[str, Any]:
    """JSON-serializable bundle for CLI / portal."""
    agg = aggregate_author_domain(store)
    authors = sorted(agg.keys())
    bins_global = calibration_bins(store)
    per_author: dict[str, Any] = {}
    for a in authors:
        per_author[a] = {
            "domains": agg[a],
            "bins": calibration_bins(store, author_key=a),
        }
    return {
        "authors": authors,
        "aggregates": agg,
        "calibration_bins_global": bins_global,
        "per_author": per_author,
        "weak_domains": [
            {"author": au, "domain": d, "mean_brier": b, "n": n}
            for au, d, b, n in weak_calibration_domains(store)
        ],
    }

"""
Belief-state replay: reconstruct what the store would expose as of a past cutoff.

Honesty constraints:
- Embedding vectors and cluster IDs reflect the *current* encoder and graph; replay
  filters *which* claims/conclusions participate by effective time, not historical weights.
- Use ``embedding_model_version`` rows to surface which encoder was pinned when; if the
  table only has the auto-seed row, callers should warn that encoder drift is unmodeled.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any, Iterable, Optional

from noosphere.models import Artifact, Claim, Conclusion
from noosphere.observability import get_logger
from noosphere.store import Store, StoredEmbeddingModelVersion

logger = get_logger(__name__)


def parse_cutoff_date(s: str) -> date:
    return date.fromisoformat(s.strip())


def cutoff_datetime_inclusive_utc(d: date) -> datetime:
    """Inclusive end-of-calendar-day UTC for ``effective_at <= cutoff`` checks."""
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def effective_datetime_for_artifact(art: Artifact) -> tuple[datetime, bool]:
    if art.effective_at is not None:
        return _ensure_utc(art.effective_at), art.effective_at_inferred
    if art.source_date:
        d = art.source_date
        return (
            datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc),
            False,
        )
    return _ensure_utc(art.created_at), True


def effective_datetime_for_claim(store: Store, c: Claim) -> tuple[datetime, bool]:
    if c.effective_at is not None:
        return _ensure_utc(c.effective_at), c.effective_at_inferred
    if c.source_id:
        art = store.get_artifact(c.source_id)
        if art is not None:
            return effective_datetime_for_artifact(art)
    return datetime.combine(c.episode_date, time.max, tzinfo=timezone.utc), True


def is_active_superseded(superseded_at: Optional[datetime], cutoff: datetime) -> bool:
    if superseded_at is None:
        return True
    return _ensure_utc(superseded_at) > cutoff


def claim_visible_as_of(store: Store, c: Claim, cutoff: datetime) -> bool:
    if not is_active_superseded(c.superseded_at, cutoff):
        return False
    eff, _ = effective_datetime_for_claim(store, c)
    return eff <= cutoff


def artifact_visible_as_of(store: Store, artifact_id: str, cutoff: datetime) -> bool:
    if not artifact_id:
        return True
    art = store.get_artifact(artifact_id)
    if art is None:
        return True
    if not is_active_superseded(art.superseded_at, cutoff):
        return False
    eff, _ = effective_datetime_for_artifact(art)
    return eff <= cutoff


def filter_claims_as_of(
    store: Store,
    claims: dict[str, Claim],
    as_of: date,
    *,
    exclude_artifact_ids: Optional[set[str]] = None,
) -> dict[str, Claim]:
    cutoff = cutoff_datetime_inclusive_utc(as_of)
    ex = exclude_artifact_ids or set()
    out: dict[str, Claim] = {}
    for cid, c in claims.items():
        if c.source_id and c.source_id in ex:
            continue
        if not claim_visible_as_of(store, c, cutoff):
            continue
        if c.source_id and not artifact_visible_as_of(store, c.source_id, cutoff):
            continue
        out[cid] = c
    return out


def list_conclusions_replay_consistent(store: Store, as_of: date) -> list[Conclusion]:
    """
    Conclusions that could have been asserted by ``as_of``: synthesized no later than the
    cutoff and whose stored evidence claims are all visible on that cutoff.
    """
    cutoff = cutoff_datetime_inclusive_utc(as_of)
    out: list[Conclusion] = []
    for con in store.list_conclusions():
        if con.superseded_at is not None and _ensure_utc(con.superseded_at) <= cutoff:
            continue
        if _ensure_utc(con.created_at) > cutoff:
            continue
        ok = True
        for eid in con.evidence_chain_claim_ids:
            cl = store.get_claim(eid)
            if cl is None or not claim_visible_as_of(store, cl, cutoff):
                ok = False
                break
        if ok:
            out.append(con)
    return out


def embedding_model_disclaimer(store: Store, as_of: date) -> list[str]:
    cutoff = cutoff_datetime_inclusive_utc(as_of)
    rows: list[tuple[datetime, str]] = []
    with store.session() as s:
        from sqlmodel import select

        for r in s.exec(select(StoredEmbeddingModelVersion).order_by(StoredEmbeddingModelVersion.effective_from)).all():
            eff_r = r.effective_from
            if eff_r.tzinfo is None:
                eff_r = eff_r.replace(tzinfo=timezone.utc)
            rows.append((eff_r, r.model_name))
    warns: list[str] = []
    if not rows:
        warns.append("No embedding_model_version rows; encoder history is unmodeled.")
        return warns
    best: Optional[tuple[datetime, str]] = None
    for eff, name in rows:
        if eff <= cutoff:
            best = (eff, name)
    if best is None:
        warns.append(
            f"No embedding_model_version effective on or before {as_of.isoformat()}; "
            f"using earliest recorded ({rows[0][1]} from {rows[0][0].date().isoformat()})."
        )
    elif len(rows) == 1:
        warns.append(
            "Only one embedding_model_version row (auto-seed). Encoder drift vs historical "
            "replay is not fully tracked; vectors in the store reflect the current encoder run."
        )
    return warns


@dataclass
class BeliefDiff:
    """Structured diff between two replay cutoffs (conclusion ids)."""

    date_a: date
    date_b: date
    conclusions_only_in_b: list[str] = field(default_factory=list)
    conclusions_only_in_a: list[str] = field(default_factory=list)
    claims_gained_visibility_in_b: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def diff_belief_cutoffs(store: Store, date_a: date, date_b: date) -> BeliefDiff:
    if date_a > date_b:
        date_a, date_b = date_b, date_a
    sa = {c.id for c in list_conclusions_replay_consistent(store, date_a)}
    sb = {c.id for c in list_conclusions_replay_consistent(store, date_b)}
    diff = BeliefDiff(date_a=date_a, date_b=date_b)
    diff.conclusions_only_in_b = sorted(sb - sa)
    diff.conclusions_only_in_a = sorted(sa - sb)
    ca = cutoff_datetime_inclusive_utc(date_a)
    cb = cutoff_datetime_inclusive_utc(date_b)
    for cid in store.list_claim_ids():
        cl = store.get_claim(cid)
        if cl is None:
            continue
        va = claim_visible_as_of(store, cl, ca)
        vb = claim_visible_as_of(store, cl, cb)
        if not va and vb:
            diff.claims_gained_visibility_in_b.append(cid)
    diff.warnings.extend(embedding_model_disclaimer(store, date_b))
    return diff


def diff_structured_json(store: Store, date_a: date, date_b: date) -> dict[str, Any]:
    d = diff_belief_cutoffs(store, date_a, date_b)
    return {
        "date_a": d.date_a.isoformat(),
        "date_b": d.date_b.isoformat(),
        "conclusions_new_or_visible_by_b": d.conclusions_only_in_b,
        "conclusions_visible_by_a_not_b": d.conclusions_only_in_a,
        "claims_first_visible_by_b": d.claims_gained_visibility_in_b[:200],
        "warnings": d.warnings,
    }


def narrative_from_diff(
    store: Store,
    date_a: date,
    date_b: date,
    *,
    llm: Any | None = None,
) -> str:
    """
    Short narrative grounded in ``diff_structured_json``. Uses LLM when provided;
    otherwise a deterministic template.
    """
    payload = diff_structured_json(store, date_a, date_b)
    added = payload["conclusions_new_or_visible_by_b"]
    lost = payload["conclusions_visible_by_a_not_b"]
    claims = payload["claims_first_visible_by_b"]
    arts: set[str] = set()
    for cid in claims[:40]:
        cl = store.get_claim(cid)
        if cl and cl.source_id:
            arts.add(cl.source_id)
    art_meta = []
    for aid in sorted(arts)[:12]:
        a = store.get_artifact(aid)
        if a:
            art_meta.append({"id": aid, "title": a.title, "uri": a.uri})
    if llm is not None:
        try:
            prompt = (
                "Write 2–4 sentences summarizing intellectual change between two dates for a firm. "
                "You MUST only use the JSON facts below; cite artifact titles when present.\n"
                + json.dumps({**payload, "pivotal_artifacts": art_meta}, indent=2)
            )
            out = llm.complete(
                system="You write precise, grounded summaries. Never invent artifacts or claims.",
                user=prompt,
                max_tokens=400,
            )
            if isinstance(out, str) and out.strip():
                return out.strip()
        except Exception as e:  # pragma: no cover
            logger.warning("replay_narrative_llm_failed", error=str(e))
    lines = [
        f"Between {date_a.isoformat()} and {date_b.isoformat()}, the replay-consistent conclusion set "
        f"gained {len(added)} id(s) and lost {len(lost)} relative to the earlier cutoff.",
    ]
    if art_meta:
        titles = ", ".join(m["title"] or m["id"] for m in art_meta[:5])
        lines.append(f"Pivotal newly-visible evidence appears tied to artifacts: {titles}.")
    if payload["warnings"]:
        lines.append("Imperfections: " + " ".join(payload["warnings"]))
    return " ".join(lines)


def run_counterfactual_preview(
    orch: Any,
    *,
    exclude_artifact_ids: set[str],
    as_of: date,
) -> tuple[list[Conclusion], list[str]]:
    """Dry-run synthesis while excluding one or more artifact ids (claims sourced there dropped)."""
    claims = filter_claims_as_of(
        orch.store,
        dict(orch.graph.claims),
        as_of,
        exclude_artifact_ids=exclude_artifact_ids,
    )
    warns = embedding_model_disclaimer(orch.store, as_of)
    from noosphere.synthesis import run_synthesis_pipeline

    res = run_synthesis_pipeline(orch, store=orch.store, claims_by_id=claims, dry_run=True)
    return list(res.preview_conclusions), warns


def run_synthesis_as_of_preview(orch: Any, as_of: date) -> tuple[list[Conclusion], list[str]]:
    """
    Dry-run synthesis assembly using claims visible as of ``as_of`` (graph + SQL artifact filter).

    Returns (preview conclusions, warnings).
    """
    from noosphere.synthesis import run_synthesis_pipeline

    claims = filter_claims_as_of(orch.store, dict(orch.graph.claims), as_of)
    warns = embedding_model_disclaimer(orch.store, as_of)
    res = run_synthesis_pipeline(orch, store=orch.store, claims_by_id=claims, dry_run=True)
    return list(res.preview_conclusions), warns

"""Read-only store proxy pinned to a TemporalCut."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from noosphere.models import (
    Artifact,
    Chunk,
    Claim,
    Conclusion,
    CorpusSelector,
    TemporalCut,
)


class EmbargoViolation(Exception):
    """Raised when a read reaches past the temporal cut boundary."""


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _matches_selector(artifact: Artifact, sel: CorpusSelector) -> bool:
    if sel.tenant_id_filter is not None:
        if getattr(artifact, "tenant_id", None) not in sel.tenant_id_filter:
            return False
    if sel.artifact_kind_filter is not None:
        if artifact.mime_type not in sel.artifact_kind_filter:
            return False
    return True


class CorpusSlicer:
    """Frozen, read-only view of a Store pinned to a past date.

    Every read goes through the cut's ``as_of`` predicate.  Objects created
    after the cut raise ``EmbargoViolation``.  Write methods are not proxied
    — calling them raises ``AttributeError``.
    """

    PROXIED_READ_METHODS = frozenset({
        "get_artifact",
        "get_chunk",
        "get_claim",
        "get_conclusion",
        "get_embedding_vector",
        "get_drift_event",
        "list_claim_ids",
        "list_conclusions",
        "list_chunks_for_artifact",
        "list_drift_events",
        "get_temporal_cut",
        "list_outcomes_for_cut",
    })

    def __init__(self, store: Any, cut: TemporalCut) -> None:
        self._store = store
        self._cut = cut
        self._as_of = _ensure_tz(cut.as_of)

    @property
    def cut(self) -> TemporalCut:
        return self._cut

    def _check_artifact_embargo(self, obj: Artifact, label: str) -> None:
        created = _ensure_tz(obj.created_at)
        if created > self._as_of:
            raise EmbargoViolation(
                f"{label} is after {self._as_of.isoformat()}"
            )
        if not _matches_selector(obj, self._cut.corpus_slice):
            raise EmbargoViolation(
                f"{label} does not match corpus_slice selector"
            )

    def _check_created_at(self, obj: Any, label: str) -> None:
        created = getattr(obj, "created_at", None)
        if created is not None:
            if _ensure_tz(created) > self._as_of:
                raise EmbargoViolation(
                    f"{label} is after {self._as_of.isoformat()}"
                )

    # ── Proxied reads ──────────────────────────────────────────────────

    def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        obj = self._store.get_artifact(artifact_id)
        if obj is None:
            return None
        self._check_artifact_embargo(obj, artifact_id)
        return obj

    def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        obj = self._store.get_chunk(chunk_id)
        if obj is None:
            return None
        art = self._store.get_artifact(obj.artifact_id)
        if art is not None:
            self._check_artifact_embargo(art, f"chunk:{chunk_id}/artifact:{obj.artifact_id}")
        return obj

    def get_claim(self, claim_id: str) -> Optional[Claim]:
        obj = self._store.get_claim(claim_id)
        if obj is None:
            return None
        ep_date = getattr(obj, "episode_date", None)
        if ep_date is not None:
            from datetime import date as _date
            if isinstance(ep_date, _date):
                ep_dt = datetime(ep_date.year, ep_date.month, ep_date.day,
                                 23, 59, 59, tzinfo=timezone.utc)
                if ep_dt > self._as_of:
                    raise EmbargoViolation(
                        f"{claim_id} is after {self._as_of.isoformat()}"
                    )
        return obj

    def get_conclusion(self, conclusion_id: str) -> Optional[Conclusion]:
        obj = self._store.get_conclusion(conclusion_id)
        if obj is None:
            return None
        self._check_created_at(obj, conclusion_id)
        return obj

    def get_embedding_vector(self, embedding_id: str) -> Optional[list[float]]:
        return self._store.get_embedding_vector(embedding_id)

    def get_drift_event(self, drift_id: str):
        obj = self._store.get_drift_event(drift_id)
        if obj is None:
            return None
        return obj

    def list_claim_ids(self) -> list[str]:
        all_ids = self._store.list_claim_ids()
        filtered: list[str] = []
        for cid in all_ids:
            try:
                c = self.get_claim(cid)
                if c is not None:
                    filtered.append(cid)
            except EmbargoViolation:
                continue
        return filtered

    def list_conclusions(self) -> list[Conclusion]:
        all_conc = self._store.list_conclusions()
        filtered: list[Conclusion] = []
        for c in all_conc:
            created = getattr(c, "created_at", None)
            if created is not None and _ensure_tz(created) > self._as_of:
                continue
            filtered.append(c)
        return filtered

    def list_chunks_for_artifact(self, artifact_id: str) -> list[Chunk]:
        self.get_artifact(artifact_id)
        return self._store.list_chunks_for_artifact(artifact_id)

    def list_drift_events(self, *, limit: int = 500):
        return self._store.list_drift_events(limit=limit)

    def get_temporal_cut(self, cut_id: str):
        return self._store.get_temporal_cut(cut_id)

    def list_outcomes_for_cut(self, cut_id: str):
        return self._store.list_outcomes_for_cut(cut_id)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        raise AttributeError(
            f"CorpusSlicer does not proxy '{name}'. "
            f"Only read operations are available under embargo."
        )

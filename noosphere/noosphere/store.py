"""
SQLite persistence via SQLModel. Raw SQL is confined to this module.
"""

from __future__ import annotations

import json
import struct
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Generator, Iterator, Literal, Optional

try:
    import numpy as np
except ImportError as exc:  # pragma: no cover - exercised only on broken local wheels.
    np = None  # type: ignore[assignment]
    _NUMPY_IMPORT_ERROR = exc
else:
    _NUMPY_IMPORT_ERROR = None
from sqlalchemy import Column, LargeBinary, asc, desc, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, create_engine, select

from noosphere.models import (
    AbstentionReason,
    Actor,
    AdversarialChallenge,
    Artifact,
    BatteryRunResult,
    CalibrationMetrics,
    CascadeEdge,
    CascadeEdgeRelation,
    CascadeNode,
    CascadeNodeKind,
    Chunk,
    CitationRecord,
    Claim,
    CoherenceEvaluationPayload,
    CoherenceVerdict,
    ConfidenceTier,
    Conclusion,
    ContextMeta,
    CorpusBundle,
    CorpusSelector,
    CounterfactualEvalRun,
    CurrentEvent,
    CurrentEventStatus,
    DecayPolicy,
    DriftEvent,
    Entity,
    EventOpinion,
    FounderOverride,
    FollowUpMessage,
    FollowUpSession,
    Freshness,
    LedgerEntry,
    Method,
    MethodInvocation,
    MethodRef,
    MIPManifest,
    Outcome,
    OutcomeKind,
    OpinionCitation,
    PredictionResolution,
    PredictiveClaim,
    ReadingQueueEntry,
    Rebuttal,
    RelativePositionMap,
    ResearchSuggestion,
    RevalidationResult,
    ReviewItem,
    ReviewReport,
    RigorSubmission,
    RigorVerdict,
    SixLayerScore,
    TemporalCut,
    Topic,
    TransferStudy,
    VoicePhaseRecord,
    VoiceProfile,
    voice_canonical_key,
)


def _dt(v: datetime | date) -> datetime:
    if isinstance(v, datetime):
        return v
    return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _float_vector(value: Any) -> list[float]:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        if len(raw) % 4 != 0:
            return []
        return [float(x) for x in struct.unpack(f"<{len(raw) // 4}f", raw)]
    if hasattr(value, "ravel") and np is not None:
        value = value.ravel()
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [float(x) for x in value]


def _float32_bytes(value: Any) -> bytes:
    vec = _float_vector(value)
    if not vec:
        return b""
    return struct.pack(f"<{len(vec)}f", *vec)


def _cosine(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or not left:
        return None
    left_norm = sum(x * x for x in left) ** 0.5
    right_norm = sum(x * x for x in right) ** 0.5
    if left_norm == 0.0 or right_norm == 0.0:
        return None
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


class LedgerChainError(Exception):
    """prev_hash does not match the current ledger tail."""


class CascadeEdgeOrphanError(Exception):
    """Referenced method_invocation_id does not exist."""


class CascadeEdgeConflictError(Exception):
    """Supports/refutes conflict on the same (src, dst) pair."""


class StoredArtifact(SQLModel, table=True):
    __tablename__ = "artifact"
    id: str = Field(primary_key=True)
    uri: str = ""
    mime_type: str = ""
    byte_length: int = 0
    content_sha256: str = ""
    title: str = ""
    author: str = ""
    source_date_iso: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    effective_at: Optional[datetime] = Field(default=None)
    superseded_at: Optional[datetime] = Field(default=None)
    effective_at_inferred: bool = Field(default=True)
    license_status: str = Field(default="unknown")
    literature_connector: str = Field(default="")


class StoredChunk(SQLModel, table=True):
    __tablename__ = "chunk"
    id: str = Field(primary_key=True)
    artifact_id: str = Field(index=True)
    start_offset: int = 0
    end_offset: int = 0
    text: str = ""
    metadata_json: str = "{}"


class StoredClaim(SQLModel, table=True):
    __tablename__ = "claim"
    id: str = Field(primary_key=True)
    payload_json: str = ""
    freshness: str = Field(default="fresh")
    last_validated_at: Optional[datetime] = Field(default=None)


class StoredEmbedding(SQLModel, table=True):
    __tablename__ = "embedding"
    id: str = Field(primary_key=True)
    model_name: str = Field(index=True)
    text_sha256: str = Field(index=True)
    dimension: int = 0
    vector: bytes = Field(sa_column=Column(LargeBinary))
    ref_claim_id: str = Field(default="", index=True)


class StoredCoherencePair(SQLModel, table=True):
    __tablename__ = "coherence_pair"
    id: str = Field(primary_key=True)
    claim_a_id: str = Field(index=True)
    claim_b_id: str = Field(index=True)
    verdict: str = ""
    scores_json: str = "{}"
    confidence: float = 0.0
    created_at: datetime = Field(default_factory=_utcnow)


class StoredDriftEvent(SQLModel, table=True):
    __tablename__ = "drift_event"
    id: str = Field(primary_key=True)
    payload_json: str = ""


class StoredConclusion(SQLModel, table=True):
    __tablename__ = "conclusion"
    id: str = Field(primary_key=True)
    payload_json: str = ""
    freshness: str = Field(default="fresh")
    last_validated_at: Optional[datetime] = Field(default=None)


class StoredResearchSuggestion(SQLModel, table=True):
    __tablename__ = "research_suggestion"
    id: str = Field(primary_key=True)
    payload_json: str = ""


class StoredTopicCluster(SQLModel, table=True):
    __tablename__ = "topic_cluster"
    cluster_id: str = Field(primary_key=True)
    label: str = ""
    description: str = ""
    centroid_json: str = ""
    model_version: str = ""
    params_hash: str = ""
    updated_at: datetime = Field(default_factory=_utcnow)
    freshness: str = Field(default="fresh")
    last_validated_at: Optional[datetime] = Field(default=None)


class StoredTopicMembership(SQLModel, table=True):
    __tablename__ = "topic_membership"
    claim_id: str = Field(primary_key=True)
    cluster_id: str = Field(index=True)


class StoredEntity(SQLModel, table=True):
    __tablename__ = "entity"
    id: str = Field(primary_key=True)
    canonical_key: str = Field(index=True)
    label: str = ""
    entity_type: str = ""
    payload_json: str = "{}"


class StoredExtractionCache(SQLModel, table=True):
    __tablename__ = "claim_extraction_cache"
    chunk_id: str = Field(primary_key=True)
    payload_json: str = ""
    updated_at: datetime = Field(default_factory=_utcnow)


class StoredCoherenceResultCache(SQLModel, table=True):
    """Content- and version-keyed coherence evaluation cache."""

    __tablename__ = "coherence_result_cache"
    evaluation_key: str = Field(primary_key=True)
    claim_a_id: str = Field(index=True)
    claim_b_id: str = Field(index=True)
    content_hash: str = ""
    versions_json: str = "{}"
    payload_json: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow)


class StoredReviewItem(SQLModel, table=True):
    __tablename__ = "review_item"
    id: str = Field(primary_key=True)
    claim_a_id: str = Field(index=True)
    claim_b_id: str = Field(index=True)
    payload_json: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow)


class StoredAdversarialChallenge(SQLModel, table=True):
    __tablename__ = "adversarial_challenge"

    id: str = Field(primary_key=True)
    conclusion_id: str = Field(default="", index=True)
    cluster_fingerprint: str = Field(default="", index=True)
    payload_json: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class StoredVoice(SQLModel, table=True):
    __tablename__ = "voice"

    id: str = Field(primary_key=True)
    canonical_key: str = Field(index=True, unique=True)
    payload_json: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class StoredVoicePhase(SQLModel, table=True):
    __tablename__ = "voice_phase"

    id: str = Field(primary_key=True)
    voice_id: str = Field(index=True)
    payload_json: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow)


class StoredCitation(SQLModel, table=True):
    __tablename__ = "citation"

    id: str = Field(primary_key=True)
    firm_claim_id: str = Field(index=True)
    voice_id: str = Field(index=True)
    payload_json: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow)


class StoredRelativePositionMap(SQLModel, table=True):
    __tablename__ = "relative_position_map"

    conclusion_id: str = Field(primary_key=True)
    payload_json: str = "{}"
    updated_at: datetime = Field(default_factory=_utcnow)


class StoredEmbeddingModelVersion(SQLModel, table=True):
    """Pinned embedding encoder versions for honest replay disclaimers."""

    __tablename__ = "embedding_model_version"

    id: str = Field(primary_key=True)
    effective_from: datetime = Field(index=True)
    model_name: str = ""
    notes: str = ""


class StoredReadingQueue(SQLModel, table=True):
    __tablename__ = "reading_queue"

    id: str = Field(primary_key=True)
    payload_json: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class StoredPredictiveClaim(SQLModel, table=True):
    __tablename__ = "predictive_claim"

    id: str = Field(primary_key=True)
    author_key: str = Field(default="", index=True)
    artifact_id: str = Field(default="", index=True)
    status: str = Field(default="draft", index=True)
    payload_json: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class StoredPredictionResolution(SQLModel, table=True):
    __tablename__ = "prediction_resolution"

    id: str = Field(primary_key=True)
    predictive_claim_id: str = Field(index=True, unique=True)
    payload_json: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow)


# ── Round 3: Stored tables ──────────────────────────────────────────────────


class StoredMethod(SQLModel, table=True):
    __tablename__ = "method"
    method_id: str = Field(primary_key=True)
    status: str = Field(default="", index=True)
    payload_json: str = ""


class StoredMethodInvocation(SQLModel, table=True):
    __tablename__ = "method_invocation"
    id: str = Field(primary_key=True)
    method_id: str = Field(default="", index=True)
    correlation_id: str = Field(default="", index=True)
    payload_json: str = ""


class StoredLedgerEntry(SQLModel, table=True):
    __tablename__ = "ledger_entry"
    entry_id: str = Field(primary_key=True)
    prev_hash: str = Field(default="", index=True)
    method_id: Optional[str] = Field(default=None, index=True)
    timestamp: datetime = Field(default_factory=_utcnow, index=True)
    payload_json: str = ""


class StoredCascadeNode(SQLModel, table=True):
    __tablename__ = "cascade_node"
    node_id: str = Field(primary_key=True)
    kind: str = Field(default="", index=True)
    payload_json: str = ""


class StoredCascadeEdge(SQLModel, table=True):
    __tablename__ = "cascade_edge"
    edge_id: str = Field(primary_key=True)
    src: str = Field(default="", index=True)
    dst: str = Field(default="", index=True)
    relation: str = Field(default="", index=True)
    method_invocation_id: str = Field(default="")
    retracted_at: Optional[datetime] = Field(default=None, index=True)
    payload_json: str = ""


class StoredTemporalCut(SQLModel, table=True):
    __tablename__ = "temporal_cut"
    cut_id: str = Field(primary_key=True)
    payload_json: str = ""


class StoredOutcome(SQLModel, table=True):
    __tablename__ = "outcome"
    outcome_id: str = Field(primary_key=True)
    payload_json: str = ""


class StoredCutOutcome(SQLModel, table=True):
    __tablename__ = "cut_outcome"
    id: str = Field(primary_key=True)
    cut_id: str = Field(default="", index=True)
    outcome_id: str = Field(default="", index=True)


class StoredCounterfactualRun(SQLModel, table=True):
    __tablename__ = "counterfactual_eval_run"
    run_id: str = Field(primary_key=True)
    payload_json: str = ""


class StoredExternalBundle(SQLModel, table=True):
    __tablename__ = "external_bundle"
    content_hash: str = Field(primary_key=True)
    payload_json: str = ""


class StoredBatteryRun(SQLModel, table=True):
    __tablename__ = "battery_run"
    run_id: str = Field(primary_key=True)
    payload_json: str = ""


class StoredTransferStudy(SQLModel, table=True):
    __tablename__ = "transfer_study"
    study_id: str = Field(primary_key=True)
    method_ref_name: str = Field(default="", index=True)
    method_ref_version: str = Field(default="", index=True)
    payload_json: str = ""


class StoredReviewReport(SQLModel, table=True):
    __tablename__ = "review_report"
    report_id: str = Field(primary_key=True)
    conclusion_id: str = Field(default="", index=True)
    payload_json: str = ""


class StoredRebuttal(SQLModel, table=True):
    __tablename__ = "rebuttal"
    id: str = Field(primary_key=True)
    report_id: str = Field(default="", index=True)
    finding_id: str = Field(default="", index=True)
    payload_json: str = ""


class StoredDecayPolicy(SQLModel, table=True):
    __tablename__ = "decay_policy"
    id: str = Field(primary_key=True)
    payload_json: str = ""


class StoredObjectPolicyBinding(SQLModel, table=True):
    __tablename__ = "object_policy_binding"
    id: str = Field(primary_key=True)
    object_id: str = Field(default="", index=True)
    policy_id: str = Field(default="", index=True)


class StoredRevalidation(SQLModel, table=True):
    __tablename__ = "revalidation"
    id: str = Field(primary_key=True)
    object_id: str = Field(default="", index=True)
    payload_json: str = ""


class StoredRigorSubmission(SQLModel, table=True):
    __tablename__ = "rigor_submission"
    submission_id: str = Field(primary_key=True)
    author_id: str = Field(default="", index=True)
    intended_venue: str = Field(default="", index=True)
    payload_json: str = ""


class StoredRigorVerdict(SQLModel, table=True):
    __tablename__ = "rigor_verdict"
    ledger_entry_id: str = Field(primary_key=True)
    payload_json: str = ""


class StoredFounderOverride(SQLModel, table=True):
    __tablename__ = "founder_override"
    override_id: str = Field(primary_key=True)
    payload_json: str = ""


class StoredMIPManifest(SQLModel, table=True):
    __tablename__ = "mip_manifest"
    content_hash: str = Field(primary_key=True)
    payload_json: str = ""


def _sqlite_migrate_literature_columns(engine: Engine) -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    insp = inspect(engine)
    tables = insp.get_table_names()
    if "artifact" not in tables:
        return
    acols = {c["name"] for c in insp.get_columns("artifact")}
    with engine.begin() as conn:
        if "license_status" not in acols:
            conn.execute(text("ALTER TABLE artifact ADD COLUMN license_status VARCHAR DEFAULT 'unknown'"))
        if "literature_connector" not in acols:
            conn.execute(text("ALTER TABLE artifact ADD COLUMN literature_connector VARCHAR DEFAULT ''"))


def _sqlite_migrate_temporal_columns(engine: Engine) -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    insp = inspect(engine)
    tables = insp.get_table_names()
    if "artifact" not in tables:
        return
    acols = {c["name"] for c in insp.get_columns("artifact")}
    with engine.begin() as conn:
        if "effective_at" not in acols:
            conn.execute(text("ALTER TABLE artifact ADD COLUMN effective_at DATETIME"))
        if "superseded_at" not in acols:
            conn.execute(text("ALTER TABLE artifact ADD COLUMN superseded_at DATETIME"))
        if "effective_at_inferred" not in acols:
            conn.execute(text("ALTER TABLE artifact ADD COLUMN effective_at_inferred BOOLEAN DEFAULT 1"))


def _artifact_row_default_effective(row: StoredArtifact) -> tuple[datetime, bool]:
    """Return (effective_at, inferred) for a DB row missing effective_at."""
    if row.source_date_iso:
        try:
            d = date.fromisoformat(row.source_date_iso[:10])
            return (
                datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc),
                False,
            )
        except ValueError:
            pass
    return _dt(row.created_at), True


def _backfill_artifact_effective_times(engine: Engine) -> None:
    with Session(engine) as s:
        rows = s.exec(select(StoredArtifact)).all()
        changed = False
        for r in rows:
            if getattr(r, "effective_at", None) is not None:
                continue
            eff, inf = _artifact_row_default_effective(r)
            r.effective_at = eff
            r.effective_at_inferred = inf
            s.add(r)
            changed = True
        if changed:
            s.commit()


def _seed_embedding_model_versions(engine: Engine) -> None:
    from noosphere.config import get_settings

    with Session(engine) as s:
        n = len(s.exec(select(StoredEmbeddingModelVersion)).all())
        if n > 0:
            return
        sid = "seed-embedding-default"
        s.add(
            StoredEmbeddingModelVersion(
                id=sid,
                effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                model_name=get_settings().embedding_model_name,
                notes="Auto-seed: replace with dated rows when upgrading encoders.",
            )
        )
        s.commit()


class Store:
    """Typed CRUD facade over SQLAlchemy.

    Supports both SQLite (local dev; ``sqlite:///./noosphere.db``) and
    Postgres (``postgresql://…``, e.g. Supabase / Neon / local Docker).
    The SQLite-specific ALTER TABLE migrations below short-circuit on
    non-sqlite URLs — Postgres gets its schema from
    ``SQLModel.metadata.create_all`` and the Alembic revisions under
    ``noosphere/alembic/``. Prefer Alembic in production.
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def from_database_url(cls, url: str) -> Store:
        connect_args: dict[str, Any] = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        eng = create_engine(url, connect_args=connect_args)
        SQLModel.metadata.create_all(eng)
        _sqlite_migrate_temporal_columns(eng)
        _sqlite_migrate_literature_columns(eng)
        _backfill_artifact_effective_times(eng)
        _seed_embedding_model_versions(eng)
        return cls(eng)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        with Session(self.engine) as s:
            yield s

    # --- Artifact ---
    def put_artifact(self, a: Artifact) -> None:
        eff = a.effective_at
        eff_inferred = a.effective_at_inferred
        if eff is None:
            if a.source_date:
                d = a.source_date
                eff = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)
                eff_inferred = False
            else:
                eff = _dt(a.created_at)
                eff_inferred = True
        row = StoredArtifact(
            id=a.id,
            uri=a.uri,
            mime_type=a.mime_type,
            byte_length=a.byte_length,
            content_sha256=a.content_sha256,
            title=a.title,
            author=a.author,
            source_date_iso=a.source_date.isoformat() if a.source_date else "",
            created_at=_dt(a.created_at),
            effective_at=eff,
            superseded_at=_dt(a.superseded_at) if a.superseded_at else None,
            effective_at_inferred=eff_inferred,
            license_status=a.license_status or "unknown",
            literature_connector=a.literature_connector or "",
        )
        with self.session() as s:
            existing = s.get(StoredArtifact, a.id)
            if existing:
                for k, v in row.model_dump(exclude={"id"}).items():
                    setattr(existing, k, v)
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        with self.session() as s:
            r = s.get(StoredArtifact, artifact_id)
            if r is None:
                return None
            sd: Optional[date] = None
            if r.source_date_iso:
                try:
                    sd = date.fromisoformat(r.source_date_iso[:10])
                except ValueError:
                    sd = None
            eff = getattr(r, "effective_at", None)
            if eff is not None and eff.tzinfo is None:
                eff = eff.replace(tzinfo=timezone.utc)
            sup = getattr(r, "superseded_at", None)
            if sup is not None and sup.tzinfo is None:
                sup = sup.replace(tzinfo=timezone.utc)
            return Artifact(
                id=r.id,
                uri=r.uri,
                mime_type=r.mime_type,
                byte_length=r.byte_length,
                content_sha256=r.content_sha256,
                title=r.title,
                author=r.author,
                source_date=sd,
                created_at=r.created_at,
                effective_at=eff,
                superseded_at=sup,
                effective_at_inferred=bool(getattr(r, "effective_at_inferred", True)),
                license_status=str(getattr(r, "license_status", None) or "unknown"),
                literature_connector=str(getattr(r, "literature_connector", None) or ""),
            )

    # --- Chunk ---
    def put_chunk(self, c: Chunk) -> None:
        row = StoredChunk(
            id=c.id,
            artifact_id=c.artifact_id,
            start_offset=c.start_offset,
            end_offset=c.end_offset,
            text=c.text,
            metadata_json=json.dumps(c.metadata, ensure_ascii=False),
        )
        with self.session() as s:
            existing = s.get(StoredChunk, c.id)
            if existing:
                for k, v in row.model_dump(exclude={"id"}).items():
                    setattr(existing, k, v)
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        with self.session() as s:
            r = s.get(StoredChunk, chunk_id)
            if r is None:
                return None
            meta: dict[str, str] = {}
            if r.metadata_json:
                try:
                    raw = json.loads(r.metadata_json)
                    if isinstance(raw, dict):
                        meta = {str(k): str(v) for k, v in raw.items()}
                except json.JSONDecodeError:
                    meta = {}
            return Chunk(
                id=r.id,
                artifact_id=r.artifact_id,
                start_offset=r.start_offset,
                end_offset=r.end_offset,
                text=r.text,
                metadata=meta,
            )

    # --- Claim ---
    def put_claim(self, c: Claim) -> None:
        row = StoredClaim(id=c.id, payload_json=c.model_dump_json())
        with self.session() as s:
            existing = s.get(StoredClaim, c.id)
            if existing:
                existing.payload_json = row.payload_json
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_claim(self, claim_id: str) -> Optional[Claim]:
        with self.session() as s:
            r = s.get(StoredClaim, claim_id)
            if r is None:
                return None
            return Claim.model_validate_json(r.payload_json)

    # --- Embedding ---
    def put_embedding(
        self,
        *,
        embedding_id: str,
        model_name: str,
        text_sha256: str,
        vector: list[float],
        ref_claim_id: str = "",
    ) -> None:
        if np is None:
            raise ImportError("NumPy is required for embedding persistence") from _NUMPY_IMPORT_ERROR
        arr = np.asarray(vector, dtype=np.float32)
        blob = arr.tobytes()
        row = StoredEmbedding(
            id=embedding_id,
            model_name=model_name,
            text_sha256=text_sha256,
            dimension=len(vector),
            vector=blob,
            ref_claim_id=ref_claim_id,
        )
        with self.session() as s:
            existing = s.get(StoredEmbedding, embedding_id)
            if existing:
                existing.model_name = row.model_name
                existing.text_sha256 = row.text_sha256
                existing.dimension = row.dimension
                existing.vector = row.vector
                existing.ref_claim_id = row.ref_claim_id
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_embedding_vector(self, embedding_id: str) -> Optional[list[float]]:
        if np is None:
            raise ImportError("NumPy is required for embedding persistence") from _NUMPY_IMPORT_ERROR
        with self.session() as s:
            r = s.get(StoredEmbedding, embedding_id)
            if r is None:
                return None
            arr = np.frombuffer(r.vector, dtype=np.float32)
            return arr.astype(float).tolist()

    # --- Coherence pair ---
    def put_coherence_pair(
        self,
        *,
        pair_id: str,
        claim_a_id: str,
        claim_b_id: str,
        verdict: CoherenceVerdict,
        scores: SixLayerScore,
        confidence: float = 0.0,
    ) -> None:
        row = StoredCoherencePair(
            id=pair_id,
            claim_a_id=claim_a_id,
            claim_b_id=claim_b_id,
            verdict=verdict.value,
            scores_json=scores.model_dump_json(),
            confidence=confidence,
        )
        with self.session() as s:
            existing = s.get(StoredCoherencePair, pair_id)
            if existing:
                for k, v in row.model_dump(exclude={"id"}).items():
                    setattr(existing, k, v)
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_coherence_pair(
        self, pair_id: str
    ) -> Optional[tuple[str, str, CoherenceVerdict, SixLayerScore, float]]:
        with self.session() as s:
            r = s.get(StoredCoherencePair, pair_id)
            if r is None:
                return None
            scores = SixLayerScore.model_validate_json(r.scores_json)
            return (
                r.claim_a_id,
                r.claim_b_id,
                CoherenceVerdict(r.verdict),
                scores,
                r.confidence,
            )

    # --- Drift ---
    def put_drift_event(self, e: DriftEvent) -> None:
        row = StoredDriftEvent(id=e.id, payload_json=e.model_dump_json())
        with self.session() as s:
            existing = s.get(StoredDriftEvent, e.id)
            if existing:
                existing.payload_json = row.payload_json
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_drift_event(self, drift_id: str) -> Optional[DriftEvent]:
        with self.session() as s:
            r = s.get(StoredDriftEvent, drift_id)
            if r is None:
                return None
            return DriftEvent.model_validate_json(r.payload_json)

    def list_drift_events(self, *, limit: int = 500) -> list[DriftEvent]:
        with self.session() as s:
            rows = s.exec(select(StoredDriftEvent)).all()[:limit]
            out: list[DriftEvent] = []
            for r in rows:
                try:
                    out.append(DriftEvent.model_validate_json(r.payload_json))
                except Exception:
                    continue
            return out

    # --- Conclusion (tiered) ---
    def put_conclusion(self, c: Conclusion) -> None:
        row = StoredConclusion(id=c.id, payload_json=c.model_dump_json())
        with self.session() as s:
            existing = s.get(StoredConclusion, c.id)
            if existing:
                existing.payload_json = row.payload_json
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_conclusion(self, conclusion_id: str) -> Optional[Conclusion]:
        with self.session() as s:
            r = s.get(StoredConclusion, conclusion_id)
            if r is not None:
                return Conclusion.model_validate_json(r.payload_json)
        return self._get_prisma_conclusion(conclusion_id)

    def list_conclusions(self) -> list[Conclusion]:
        with self.session() as s:
            rows = s.exec(select(StoredConclusion)).all()
            stored = [Conclusion.model_validate_json(r.payload_json) for r in rows]
        seen = {conclusion.id for conclusion in stored}
        return [
            *stored,
            *[
                conclusion
                for conclusion in self._list_prisma_conclusions()
                if conclusion.id not in seen
            ],
        ]

    @staticmethod
    def _json_string_list(value: Any | None) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if isinstance(item, str)]
        if not isinstance(value, str):
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed if isinstance(item, str)]

    @staticmethod
    def _confidence_tier(value: str | None) -> ConfidenceTier:
        raw = (value or "").strip().lower()
        if raw in {tier.value for tier in ConfidenceTier}:
            return ConfidenceTier(raw)
        if raw == "firm":
            return ConfidenceTier.HIGH
        if raw == "open":
            return ConfidenceTier.LOW
        return ConfidenceTier.MODERATE

    def _has_prisma_conclusion_table(self) -> bool:
        inspector = inspect(self.engine)
        if not inspector.has_table("Conclusion"):
            return False
        columns = {column["name"] for column in inspector.get_columns("Conclusion")}
        return {
            "id",
            "text",
            "confidenceTier",
            "rationale",
            "supportingPrincipleIds",
            "evidenceChainClaimIds",
            "confidence",
            "createdAt",
        }.issubset(columns)

    def _prisma_conclusion_row_to_model(self, row: Any) -> Conclusion:
        data = row._mapping if hasattr(row, "_mapping") else row
        created_at = data.get("createdAt") or _utcnow()
        return Conclusion(
            id=str(data["id"]),
            text=str(data["text"]),
            reasoning=str(data.get("rationale") or ""),
            confidence_tier=self._confidence_tier(data.get("confidenceTier")),
            principles_used=self._json_string_list(data.get("supportingPrincipleIds")),
            claims_used=self._json_string_list(data.get("evidenceChainClaimIds")),
            confidence=float(data.get("confidence") or 0.0),
            created_at=created_at,
            updated_at=created_at,
        )

    def _list_prisma_conclusions(self) -> list[Conclusion]:
        if not self._has_prisma_conclusion_table():
            return []
        sql = text(
            'SELECT id, text, "confidenceTier", rationale, '
            '"supportingPrincipleIds", "evidenceChainClaimIds", confidence, "createdAt" '
            'FROM "Conclusion" ORDER BY "createdAt" DESC'
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [self._prisma_conclusion_row_to_model(row) for row in rows]

    def _get_prisma_conclusion(self, conclusion_id: str) -> Optional[Conclusion]:
        if not self._has_prisma_conclusion_table():
            return None
        sql = text(
            'SELECT id, text, "confidenceTier", rationale, '
            '"supportingPrincipleIds", "evidenceChainClaimIds", confidence, "createdAt" '
            'FROM "Conclusion" WHERE id = :id LIMIT 1'
        )
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"id": conclusion_id}).first()
        if row is None:
            return None
        return self._prisma_conclusion_row_to_model(row)

    # --- Research suggestion ---
    def put_research_suggestion(self, r: ResearchSuggestion) -> None:
        row = StoredResearchSuggestion(id=r.id, payload_json=r.model_dump_json())
        with self.session() as s:
            existing = s.get(StoredResearchSuggestion, r.id)
            if existing:
                existing.payload_json = row.payload_json
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_research_suggestion(self, rid: str) -> Optional[ResearchSuggestion]:
        with self.session() as s:
            row = s.get(StoredResearchSuggestion, rid)
            if row is None:
                return None
            return ResearchSuggestion.model_validate_json(row.payload_json)

    def list_research_suggestions(self, *, limit: int = 500) -> list[ResearchSuggestion]:
        with self.session() as s:
            rows = s.exec(select(StoredResearchSuggestion).limit(limit)).all()
            out: list[ResearchSuggestion] = []
            for r in rows:
                try:
                    out.append(ResearchSuggestion.model_validate_json(r.payload_json))
                except Exception:
                    continue
            return out

    # --- Currents ---
    def add_current_event(self, event: CurrentEvent) -> str:
        """Insert a CurrentEvent, returning the existing id on dedupe collision."""
        event_id = event.id
        with self.session() as s:
            existing = s.exec(
                select(CurrentEvent).where(CurrentEvent.dedupe_hash == event.dedupe_hash)
            ).first()
            if existing is not None:
                return existing.id
            event.updated_at = _utcnow()
            s.add(event)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                existing = s.exec(
                    select(CurrentEvent).where(CurrentEvent.dedupe_hash == event.dedupe_hash)
                ).first()
                if existing is None:
                    raise
                return existing.id
            return event_id

    def find_current_event_by_dedupe(self, hash: str) -> Optional[CurrentEvent]:
        with self.session() as s:
            return s.exec(select(CurrentEvent).where(CurrentEvent.dedupe_hash == hash)).first()

    def get_current_event(self, event_id: str) -> Optional[CurrentEvent]:
        with self.session() as s:
            return s.get(CurrentEvent, event_id)

    def list_current_event_ids_by_status(
        self,
        statuses: list[CurrentEventStatus | str],
        *,
        limit: int = 40,
    ) -> list[str]:
        """Return oldest CurrentEvent ids in any of the supplied statuses."""
        if limit <= 0:
            return []
        status_values = [
            status.value if isinstance(status, CurrentEventStatus) else str(status)
            for status in statuses
        ]
        with self.session() as s:
            rows = s.exec(
                select(CurrentEvent.id)
                .where(CurrentEvent.status.in_(status_values))
                .order_by(asc(CurrentEvent.observed_at))
                .limit(limit)
            ).all()
        return [str(row) for row in rows]

    def set_event_embedding(self, event_id: str, vector: Any) -> None:
        """Persist a CurrentEvent embedding as float32 little-endian bytes."""
        if np is not None:
            raw_embedding = np.asarray(vector, dtype=np.float32).ravel().tobytes()
        else:
            raw_embedding = _float32_bytes(vector)
        with self.session() as s:
            event = s.get(CurrentEvent, event_id)
            if event is None:
                raise KeyError(f"unknown current event: {event_id}")
            event.embedding = raw_embedding
            event.updated_at = _utcnow()
            s.add(event)
            s.commit()

    def find_near_duplicates(
        self,
        vector: Any,
        *,
        since_days: int,
        cosine_min: float,
        exclude_id: str | None = None,
    ) -> list[CurrentEvent]:
        """Return recent CurrentEvents whose stored embedding is cosine-close."""
        if np is not None:
            q = np.asarray(vector, dtype=float).ravel()
            q_norm = float(np.linalg.norm(q))
            if q_norm == 0.0:
                return []
        else:
            q_fallback = _float_vector(vector)
            if not q_fallback or sum(x * x for x in q_fallback) == 0.0:
                return []
        scored: list[tuple[float, CurrentEvent]] = []
        with self.session() as s:
            rows = s.exec(select(CurrentEvent)).all()
            reference_at = _utcnow()
            if exclude_id is not None:
                for event in rows:
                    if event.id != exclude_id:
                        continue
                    reference_at = event.observed_at
                    if reference_at.tzinfo is None:
                        reference_at = reference_at.replace(tzinfo=timezone.utc)
                    break
            cutoff = reference_at - timedelta(days=since_days)
            for event in rows:
                if event.id == exclude_id or not event.embedding:
                    continue
                observed_at = event.observed_at
                if observed_at.tzinfo is None:
                    observed_at = observed_at.replace(tzinfo=timezone.utc)
                if observed_at < cutoff or observed_at > reference_at:
                    continue
                if np is not None:
                    candidate = np.frombuffer(event.embedding, dtype=np.float32).astype(
                        float
                    )
                    if candidate.shape != q.shape:
                        continue
                    candidate_norm = float(np.linalg.norm(candidate))
                    if candidate_norm == 0.0:
                        continue
                    cosine = float(np.dot(q, candidate) / (q_norm * candidate_norm))
                else:
                    maybe_cosine = _cosine(q_fallback, _float_vector(event.embedding))
                    if maybe_cosine is None:
                        continue
                    cosine = maybe_cosine
                if cosine >= cosine_min:
                    scored.append((cosine, event))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [event for _, event in scored]

    def nearest_topic(self, vector: Any, *, cosine_min: float) -> Optional[str]:
        """Return the nearest stored topic-cluster id above the cosine threshold."""
        if np is not None:
            q = np.asarray(vector, dtype=float).ravel()
            q_norm = float(np.linalg.norm(q))
            if q_norm == 0.0:
                return None
        else:
            q_fallback = _float_vector(vector)
            if not q_fallback or sum(x * x for x in q_fallback) == 0.0:
                return None
        best: tuple[float, str] | None = None
        with self.session() as s:
            rows = s.exec(select(StoredTopicCluster)).all()
            for row in rows:
                try:
                    centroid_raw = json.loads(row.centroid_json)
                except json.JSONDecodeError:
                    continue
                if not isinstance(centroid_raw, list):
                    continue
                if np is not None:
                    centroid = np.asarray(
                        [float(x) for x in centroid_raw], dtype=float
                    ).ravel()
                    if centroid.shape != q.shape:
                        continue
                    centroid_norm = float(np.linalg.norm(centroid))
                    if centroid_norm == 0.0:
                        continue
                    cosine = float(np.dot(q, centroid) / (q_norm * centroid_norm))
                else:
                    maybe_cosine = _cosine(
                        q_fallback,
                        [float(x) for x in centroid_raw],
                    )
                    if maybe_cosine is None:
                        continue
                    cosine = maybe_cosine
                if cosine >= cosine_min and (best is None or cosine > best[0]):
                    best = (cosine, row.cluster_id)
        return best[1] if best is not None else None

    def set_event_topic(self, event_id: str, topic_id: str) -> None:
        """Attach the chosen topic id to CurrentEvent.topic_hint."""
        with self.session() as s:
            event = s.get(CurrentEvent, event_id)
            if event is None:
                raise KeyError(f"unknown current event: {event_id}")
            event.topic_hint = topic_id
            event.updated_at = _utcnow()
            s.add(event)
            s.commit()

    def set_event_status(
        self,
        event_id: str,
        status: CurrentEventStatus | str,
        *,
        note: str | None = None,
    ) -> None:
        """Update CurrentEvent.status; near-duplicate revocations set the flag too."""
        status_value = (
            status.value if isinstance(status, CurrentEventStatus) else str(status)
        )
        parsed_status = CurrentEventStatus(status_value)
        with self.session() as s:
            event = s.get(CurrentEvent, event_id)
            if event is None:
                raise KeyError(f"unknown current event: {event_id}")
            event.status = parsed_status
            if parsed_status == CurrentEventStatus.REVOKED and (
                note or ""
            ).startswith("near_duplicate_of:"):
                event.is_near_duplicate = True
            event.updated_at = _utcnow()
            s.add(event)
            s.commit()

    def _source_text_for_citation(self, s: Session, citation: OpinionCitation) -> str:
        source_kind = citation.source_kind.lower()
        if source_kind == "conclusion":
            if not citation.conclusion_id:
                raise ValueError("conclusion citation requires conclusion_id")
            row = s.get(StoredConclusion, citation.conclusion_id)
            if row is not None:
                return Conclusion.model_validate_json(row.payload_json).text
            prisma = self._get_prisma_conclusion(citation.conclusion_id)
            if prisma is not None:
                return prisma.text
            raise ValueError(f"unknown conclusion citation source: {citation.conclusion_id}")
        if source_kind == "claim":
            if not citation.claim_id:
                raise ValueError("claim citation requires claim_id")
            row = s.get(StoredClaim, citation.claim_id)
            if row is None:
                raise ValueError(f"unknown claim citation source: {citation.claim_id}")
            return Claim.model_validate_json(row.payload_json).text
        raise ValueError(f"unsupported citation source_kind: {citation.source_kind}")

    def add_event_opinion(self, opinion: EventOpinion, citations: list[OpinionCitation]) -> str:
        """Insert an opinion and citations atomically after verbatim-span checks."""
        opinion_id = opinion.id
        with self.session() as s:
            for citation in citations:
                citation.source_kind = citation.source_kind.lower()
                source_text = self._source_text_for_citation(s, citation)
                if citation.quoted_span not in source_text:
                    raise ValueError("quoted_span is not a verbatim substring of the cited source text")

            s.add(opinion)
            for citation in citations:
                citation.opinion_id = opinion_id
                s.add(citation)
            s.commit()
            return opinion_id

    def get_event_opinion(self, opinion_id: str) -> Optional[EventOpinion]:
        with self.session() as s:
            return s.get(EventOpinion, opinion_id)

    def list_opinion_citations(self, opinion_id: str) -> list[OpinionCitation]:
        with self.session() as s:
            return list(
                s.exec(
                    select(OpinionCitation).where(OpinionCitation.opinion_id == opinion_id)
                ).all()
            )

    def list_recent_opinions(
        self, org_id: str, since: datetime, limit: int
    ) -> list[EventOpinion]:
        with self.session() as s:
            return list(
                s.exec(
                    select(EventOpinion)
                    .where(EventOpinion.organization_id == org_id)
                    .where(EventOpinion.generated_at >= since)
                    .order_by(desc(EventOpinion.generated_at))
                    .limit(limit)
                ).all()
            )

    def revoke_opinion(self, opinion_id: str, reason: str) -> None:
        with self.session() as s:
            opinion = s.get(EventOpinion, opinion_id)
            if opinion is None:
                return
            opinion.revoked_at = _utcnow()
            opinion.revoked_reason = reason
            s.add(opinion)
            s.commit()

    def revoke_citations_for_source(self, source_kind: str, source_id: str, reason: str) -> int:
        source_kind_norm = source_kind.lower()
        with self.session() as s:
            stmt = select(OpinionCitation).where(OpinionCitation.source_kind == source_kind_norm)
            if source_kind_norm == "conclusion":
                stmt = stmt.where(OpinionCitation.conclusion_id == source_id)
            elif source_kind_norm == "claim":
                stmt = stmt.where(OpinionCitation.claim_id == source_id)
            else:
                raise ValueError(f"unsupported citation source_kind: {source_kind}")

            rows = list(s.exec(stmt).all())
            affected_opinion_ids = {row.opinion_id for row in rows}
            for row in rows:
                row.is_revoked = True
                row.revoked_reason = reason
                s.add(row)

            for opinion_id in affected_opinion_ids:
                citations = list(
                    s.exec(
                        select(OpinionCitation).where(OpinionCitation.opinion_id == opinion_id)
                    ).all()
                )
                if citations and all(c.is_revoked for c in citations):
                    opinion = s.get(EventOpinion, opinion_id)
                    if opinion is not None:
                        opinion.abstention_reason = AbstentionReason.REVOKED_SOURCES
                        s.add(opinion)

            s.commit()
            return len(rows)

    def add_followup_session(self, session: FollowUpSession) -> str:
        session_id = session.id
        with self.session() as s:
            s.add(session)
            s.commit()
            return session_id

    def get_followup_session(self, session_id: str) -> Optional[FollowUpSession]:
        with self.session() as s:
            return s.get(FollowUpSession, session_id)

    def add_followup_message(self, message: FollowUpMessage) -> str:
        message_id = message.id
        with self.session() as s:
            s.add(message)
            session = s.get(FollowUpSession, message.session_id)
            if session is not None:
                session.last_activity_at = message.created_at
                s.add(session)
            s.commit()
            return message_id

    def get_followup_message(self, message_id: str) -> Optional[FollowUpMessage]:
        with self.session() as s:
            return s.get(FollowUpMessage, message_id)

    def list_claim_ids(self) -> list[str]:
        with self.session() as s:
            rows = s.exec(select(StoredClaim)).all()
            return [r.id for r in rows]

    def get_state_as_of(self, as_of: date) -> dict[str, Any]:
        """
        Snapshot of claim / artifact ids whose ``effective_at`` is on or before ``as_of``
        and that are not superseded on that cutoff. Downstream replay should filter reads
        through this set (or ``temporal_replay.filter_claims_as_of`` on a claim dict).
        """
        from noosphere.temporal_replay import filter_claims_as_of

        claims: dict[str, Claim] = {}
        for cid in self.list_claim_ids():
            c = self.get_claim(cid)
            if c is not None:
                claims[cid] = c
        filtered = filter_claims_as_of(self, claims, as_of)
        artifact_ids = sorted({c.source_id for c in filtered.values() if c.source_id})
        return {
            "as_of": as_of.isoformat(),
            "claim_count": len(filtered),
            "claim_ids": sorted(filtered.keys()),
            "artifact_ids": artifact_ids,
        }

    # --- Topic clusters (stable IDs) ---
    def put_topic_cluster(self, t: Topic, *, centroid: list[float], params_hash: str) -> None:
        row = StoredTopicCluster(
            cluster_id=t.id,
            label=t.label,
            description=t.description,
            centroid_json=json.dumps(centroid),
            model_version=t.cluster_version,
            params_hash=params_hash,
        )
        with self.session() as s:
            existing = s.get(StoredTopicCluster, t.id)
            if existing:
                for k, v in row.model_dump(exclude={"cluster_id"}).items():
                    setattr(existing, k, v)
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_topic_cluster(self, cluster_id: str) -> Optional[tuple[Topic, list[float]]]:
        with self.session() as s:
            r = s.get(StoredTopicCluster, cluster_id)
            if r is None:
                return None
            cent = json.loads(r.centroid_json)
            vec = [float(x) for x in cent] if isinstance(cent, list) else []
            top = Topic(
                id=r.cluster_id,
                label=r.label,
                description=r.description,
                cluster_version=r.model_version,
            )
            return top, vec

    def list_topic_cluster_ids(self) -> list[str]:
        with self.session() as s:
            rows = s.exec(select(StoredTopicCluster)).all()
            return [r.cluster_id for r in rows]

    def put_claim_topic(self, claim_id: str, cluster_id: str) -> None:
        row = StoredTopicMembership(claim_id=claim_id, cluster_id=cluster_id)
        with self.session() as s:
            s.merge(row)
            s.commit()

    def get_topic_id_for_claim(self, claim_id: str) -> Optional[str]:
        with self.session() as s:
            r = s.get(StoredTopicMembership, claim_id)
            if r is None:
                return None
            return r.cluster_id

    # --- Entities ---
    def put_entity(self, e: Entity) -> None:
        row = StoredEntity(
            id=e.id,
            canonical_key=e.canonical_key or e.label.lower(),
            label=e.label,
            entity_type=e.entity_type,
            payload_json=e.model_dump_json(),
        )
        with self.session() as s:
            existing = s.get(StoredEntity, e.id)
            if existing:
                for k, v in row.model_dump(exclude={"id"}).items():
                    setattr(existing, k, v)
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_entity_by_canonical(self, canonical_key: str) -> Optional[Entity]:
        with self.session() as s:
            stmt = select(StoredEntity).where(StoredEntity.canonical_key == canonical_key)
            r = s.exec(stmt).first()
            if r is None:
                return None
            return Entity.model_validate_json(r.payload_json)

    # --- Extraction cache ---
    def get_extraction_cache(self, chunk_id: str) -> Optional[str]:
        with self.session() as s:
            r = s.get(StoredExtractionCache, chunk_id)
            if r is None:
                return None
            return r.payload_json

    def put_extraction_cache(self, chunk_id: str, payload_json: str) -> None:
        row = StoredExtractionCache(chunk_id=chunk_id, payload_json=payload_json)
        with self.session() as s:
            s.merge(row)
            s.commit()

    def delete_embeddings_for_model(self, model_name: str) -> int:
        """Remove all embedding rows for a model (rebuild). Returns deleted count."""
        with self.session() as s:
            rows = s.exec(
                select(StoredEmbedding).where(StoredEmbedding.model_name == model_name)
            ).all()
            n = 0
            for r in rows:
                s.delete(r)
                n += 1
            s.commit()
            return n

    # --- Coherence evaluation cache (pair + versions + content hash) ---
    def get_coherence_evaluation(self, evaluation_key: str) -> Optional[CoherenceEvaluationPayload]:
        with self.session() as s:
            r = s.get(StoredCoherenceResultCache, evaluation_key)
            if r is None:
                return None
            return CoherenceEvaluationPayload.model_validate_json(r.payload_json)

    def put_coherence_evaluation(
        self,
        *,
        evaluation_key: str,
        claim_a_id: str,
        claim_b_id: str,
        content_hash: str,
        versions_json: str,
        payload: CoherenceEvaluationPayload,
    ) -> None:
        row = StoredCoherenceResultCache(
            evaluation_key=evaluation_key,
            claim_a_id=claim_a_id,
            claim_b_id=claim_b_id,
            content_hash=content_hash,
            versions_json=versions_json,
            payload_json=payload.model_dump_json(),
        )
        with self.session() as s:
            existing = s.get(StoredCoherenceResultCache, evaluation_key)
            if existing:
                for k, v in row.model_dump(exclude={"evaluation_key"}).items():
                    setattr(existing, k, v)
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def delete_coherence_cache_for_versions_mismatch(self, versions_json: str) -> int:
        """Invalidate rows not matching current version bundle (optional maintenance)."""
        with self.session() as s:
            rows = s.exec(
                select(StoredCoherenceResultCache).where(
                    StoredCoherenceResultCache.versions_json != versions_json
                )
            ).all()
            n = 0
            for r in rows:
                s.delete(r)
                n += 1
            s.commit()
            return n

    # --- Review queue ---
    def put_review_item(self, item: ReviewItem) -> None:
        row = StoredReviewItem(
            id=item.id,
            claim_a_id=item.claim_a_id,
            claim_b_id=item.claim_b_id,
            payload_json=item.model_dump_json(),
            created_at=_dt(item.created_at),
        )
        with self.session() as s:
            existing = s.get(StoredReviewItem, item.id)
            if existing:
                for k, v in row.model_dump(exclude={"id"}).items():
                    setattr(existing, k, v)
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_review_item(self, item_id: str) -> Optional[ReviewItem]:
        with self.session() as s:
            r = s.get(StoredReviewItem, item_id)
            if r is None:
                return None
            return ReviewItem.model_validate_json(r.payload_json)

    def list_open_review_items(self) -> list[ReviewItem]:
        with self.session() as s:
            rows = s.exec(select(StoredReviewItem)).all()
            out: list[ReviewItem] = []
            for r in rows:
                item = ReviewItem.model_validate_json(r.payload_json)
                if item.status == "open":
                    out.append(item)
            return out

    # --- Adversarial challenges ---
    def put_adversarial_challenge(self, ch: AdversarialChallenge) -> None:
        row = StoredAdversarialChallenge(
            id=ch.id,
            conclusion_id=ch.conclusion_id,
            cluster_fingerprint=ch.cluster_fingerprint,
            payload_json=ch.model_dump_json(),
            created_at=_dt(ch.created_at),
            updated_at=_dt(ch.updated_at),
        )
        with self.session() as s:
            existing = s.get(StoredAdversarialChallenge, ch.id)
            if existing:
                for k, v in row.model_dump(exclude={"id"}).items():
                    setattr(existing, k, v)
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_adversarial_challenge(self, challenge_id: str) -> Optional[AdversarialChallenge]:
        with self.session() as s:
            r = s.get(StoredAdversarialChallenge, challenge_id)
            if r is None:
                return None
            return AdversarialChallenge.model_validate_json(r.payload_json)

    def list_adversarial_challenges_for_conclusion(self, conclusion_id: str) -> list[AdversarialChallenge]:
        with self.session() as s:
            rows = s.exec(
                select(StoredAdversarialChallenge).where(
                    StoredAdversarialChallenge.conclusion_id == conclusion_id
                )
            ).all()
            out: list[AdversarialChallenge] = []
            for r in rows:
                try:
                    out.append(AdversarialChallenge.model_validate_json(r.payload_json))
                except Exception:
                    continue
            return out

    def list_adversarial_challenges_for_fingerprint(self, fingerprint: str) -> list[AdversarialChallenge]:
        with self.session() as s:
            rows = s.exec(
                select(StoredAdversarialChallenge).where(
                    StoredAdversarialChallenge.cluster_fingerprint == fingerprint
                )
            ).all()
            out: list[AdversarialChallenge] = []
            for r in rows:
                try:
                    out.append(AdversarialChallenge.model_validate_json(r.payload_json))
                except Exception:
                    continue
            return out

    def find_adversarial_challenge_by_content_hash(self, content_hash: str) -> Optional[AdversarialChallenge]:
        with self.session() as s:
            rows = s.exec(select(StoredAdversarialChallenge)).all()
            for r in rows:
                try:
                    ch = AdversarialChallenge.model_validate_json(r.payload_json)
                except Exception:
                    continue
                if ch.content_hash == content_hash:
                    return ch
            return None

    def link_adversarial_fingerprint_to_conclusion(
        self, fingerprint: str, conclusion_id: str
    ) -> None:
        with self.session() as s:
            rows = s.exec(
                select(StoredAdversarialChallenge).where(
                    StoredAdversarialChallenge.cluster_fingerprint == fingerprint
                )
            ).all()
            for r in rows:
                ch = AdversarialChallenge.model_validate_json(r.payload_json)
                ch = ch.model_copy(
                    update={"conclusion_id": conclusion_id, "updated_at": datetime.now(timezone.utc)}
                )
                r.conclusion_id = conclusion_id
                r.payload_json = ch.model_dump_json()
                r.updated_at = datetime.now(timezone.utc)
                s.add(r)
            s.commit()

    # --- Chunks by artifact ---
    def list_chunks_for_artifact(self, artifact_id: str) -> list[Chunk]:
        with self.session() as s:
            rows = s.exec(select(StoredChunk).where(StoredChunk.artifact_id == artifact_id)).all()
            out: list[Chunk] = []
            for r in rows:
                meta: dict[str, str] = {}
                if r.metadata_json:
                    try:
                        raw = json.loads(r.metadata_json)
                        if isinstance(raw, dict):
                            meta = {str(k): str(v) for k, v in raw.items()}
                    except json.JSONDecodeError:
                        meta = {}
                out.append(
                    Chunk(
                        id=r.id,
                        artifact_id=r.artifact_id,
                        start_offset=r.start_offset,
                        end_offset=r.end_offset,
                        text=r.text,
                        metadata=meta,
                    )
                )
            return out

    # --- Voices (STRATEGIC 02) ---
    def put_voice_profile(self, v: VoiceProfile) -> None:
        key = voice_canonical_key(v.canonical_name)
        row = StoredVoice(
            id=v.id,
            canonical_key=key,
            payload_json=v.model_dump_json(),
            created_at=_dt(v.created_at),
            updated_at=_dt(v.updated_at),
        )
        with self.session() as s:
            existing = s.get(StoredVoice, v.id)
            if existing:
                for k, val in row.model_dump(exclude={"id"}).items():
                    setattr(existing, k, val)
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_voice_by_key(self, canonical_key: str) -> Optional[VoiceProfile]:
        with self.session() as s:
            rows = s.exec(select(StoredVoice).where(StoredVoice.canonical_key == canonical_key)).all()
            if not rows:
                return None
            return VoiceProfile.model_validate_json(rows[0].payload_json)

    def get_voice(self, voice_id: str) -> Optional[VoiceProfile]:
        with self.session() as s:
            r = s.get(StoredVoice, voice_id)
            if r is None:
                return None
            return VoiceProfile.model_validate_json(r.payload_json)

    def list_voice_profiles(self, *, limit: int = 200) -> list[VoiceProfile]:
        with self.session() as s:
            rows = s.exec(
                select(StoredVoice).order_by(asc(StoredVoice.canonical_key)).limit(limit)
            ).all()
            out: list[VoiceProfile] = []
            for r in rows:
                try:
                    out.append(VoiceProfile.model_validate_json(r.payload_json))
                except Exception:
                    continue
            return out

    def put_voice_phase(self, ph: VoicePhaseRecord) -> None:
        row = StoredVoicePhase(
            id=ph.id,
            voice_id=ph.voice_id,
            payload_json=ph.model_dump_json(),
            created_at=_utcnow(),
        )
        with self.session() as s:
            existing = s.get(StoredVoicePhase, ph.id)
            if existing:
                existing.voice_id = row.voice_id
                existing.payload_json = row.payload_json
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def list_voice_phases(self, voice_id: str) -> list[VoicePhaseRecord]:
        with self.session() as s:
            rows = s.exec(select(StoredVoicePhase).where(StoredVoicePhase.voice_id == voice_id)).all()
            out: list[VoicePhaseRecord] = []
            for r in rows:
                try:
                    out.append(VoicePhaseRecord.model_validate_json(r.payload_json))
                except Exception:
                    continue
            return out

    def put_citation(self, c: CitationRecord) -> None:
        row = StoredCitation(
            id=c.id,
            firm_claim_id=c.firm_claim_id,
            voice_id=c.voice_id,
            payload_json=c.model_dump_json(),
            created_at=_utcnow(),
        )
        with self.session() as s:
            existing = s.get(StoredCitation, c.id)
            if existing:
                for k, val in row.model_dump(exclude={"id"}).items():
                    setattr(existing, k, val)
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def list_citations_for_voice(self, voice_id: str) -> list[CitationRecord]:
        with self.session() as s:
            rows = s.exec(select(StoredCitation).where(StoredCitation.voice_id == voice_id)).all()
            out: list[CitationRecord] = []
            for r in rows:
                try:
                    out.append(CitationRecord.model_validate_json(r.payload_json))
                except Exception:
                    continue
            return out

    def put_relative_position_map(self, m: RelativePositionMap) -> None:
        row = StoredRelativePositionMap(
            conclusion_id=m.conclusion_id,
            payload_json=m.model_dump_json(),
            updated_at=_utcnow(),
        )
        with self.session() as s:
            existing = s.get(StoredRelativePositionMap, m.conclusion_id)
            if existing:
                existing.payload_json = row.payload_json
                existing.updated_at = row.updated_at
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_relative_position_map(self, conclusion_id: str) -> Optional[RelativePositionMap]:
        with self.session() as s:
            r = s.get(StoredRelativePositionMap, conclusion_id)
            if r is None:
                return None
            return RelativePositionMap.model_validate_json(r.payload_json)

    def list_relative_position_maps(self, *, limit: int = 300) -> list[RelativePositionMap]:
        with self.session() as s:
            rows = s.exec(
                select(StoredRelativePositionMap)
                .order_by(desc(StoredRelativePositionMap.updated_at))
                .limit(limit)
            ).all()
            out: list[RelativePositionMap] = []
            for r in rows:
                try:
                    out.append(RelativePositionMap.model_validate_json(r.payload_json))
                except Exception:
                    continue
            return out

    def list_claims_for_voice(self, voice_id: str, *, limit: int = 80) -> list[Claim]:
        out: list[Claim] = []
        for cid in self.list_claim_ids():
            cl = self.get_claim(cid)
            if cl is not None and cl.voice_id == voice_id:
                out.append(cl)
            if len(out) >= limit:
                break
        return out

    # --- Reading queue (literature / advisor) ---
    def put_reading_queue_entry(self, e: ReadingQueueEntry) -> None:
        row = StoredReadingQueue(
            id=e.id,
            payload_json=e.model_dump_json(),
            created_at=_dt(e.created_at),
            updated_at=_utcnow(),
        )
        with self.session() as s:
            existing = s.get(StoredReadingQueue, e.id)
            if existing:
                existing.payload_json = row.payload_json
                existing.updated_at = row.updated_at
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_reading_queue_entry(self, entry_id: str) -> Optional[ReadingQueueEntry]:
        with self.session() as s:
            r = s.get(StoredReadingQueue, entry_id)
            if r is None:
                return None
            return ReadingQueueEntry.model_validate_json(r.payload_json)

    def list_reading_queue_entries(self, *, limit: int = 200) -> list[ReadingQueueEntry]:
        with self.session() as s:
            rows = s.exec(select(StoredReadingQueue).order_by(desc(StoredReadingQueue.created_at)).limit(limit)).all()
            out: list[ReadingQueueEntry] = []
            for r in rows:
                try:
                    out.append(ReadingQueueEntry.model_validate_json(r.payload_json))
                except Exception:
                    continue
            return out

    def update_reading_queue_status(
        self,
        entry_id: str,
        status: Literal["queued", "reading", "engaged", "not_relevant", "skipped"],
        *,
        notes: str = "",
    ) -> bool:
        e = self.get_reading_queue_entry(entry_id)
        if e is None:
            return False
        from datetime import datetime, timezone

        d = e.model_dump()
        d["status"] = status
        d["rationale"] = (e.rationale + (" | " if e.rationale and notes else "") + notes).strip()
        d["updated_at"] = datetime.now(timezone.utc)
        e2 = ReadingQueueEntry.model_validate(d)
        self.put_reading_queue_entry(e2)
        return True

    def list_literature_artifacts(self, *, limit: int = 200) -> list[Artifact]:
        with self.session() as s:
            rows = s.exec(
                select(StoredArtifact)
                .where(StoredArtifact.literature_connector != "")
                .order_by(desc(StoredArtifact.created_at))
                .limit(limit)
            ).all()
            out: list[Artifact] = []
            for r in rows:
                a = self.get_artifact(r.id)
                if a is not None:
                    out.append(a)
            return out

    # --- Predictive claims (calibration scoreboard) ---
    def put_predictive_claim(self, pc: PredictiveClaim) -> None:
        row = StoredPredictiveClaim(
            id=pc.id,
            author_key=pc.author_key or "",
            artifact_id=pc.artifact_id or "",
            status=pc.status.value,
            payload_json=pc.model_dump_json(),
            created_at=_dt(pc.created_at),
            updated_at=_utcnow(),
        )
        with self.session() as s:
            existing = s.get(StoredPredictiveClaim, pc.id)
            if existing:
                for k, v in row.model_dump(exclude={"id"}).items():
                    setattr(existing, k, v)
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_predictive_claim(self, pred_id: str) -> Optional[PredictiveClaim]:
        with self.session() as s:
            r = s.get(StoredPredictiveClaim, pred_id)
            if r is None:
                return None
            return PredictiveClaim.model_validate_json(r.payload_json)

    def list_predictive_claims(self, *, limit: int = 5000) -> list[PredictiveClaim]:
        with self.session() as s:
            rows = s.exec(select(StoredPredictiveClaim).order_by(desc(StoredPredictiveClaim.created_at)).limit(limit)).all()
            out: list[PredictiveClaim] = []
            for r in rows:
                try:
                    out.append(PredictiveClaim.model_validate_json(r.payload_json))
                except Exception:
                    continue
            return out

    def list_predictive_claims_for_claim(self, source_claim_id: str) -> list[PredictiveClaim]:
        out: list[PredictiveClaim] = []
        for pc in self.list_predictive_claims():
            if pc.source_claim_id == source_claim_id:
                out.append(pc)
        return out

    def put_prediction_resolution(self, res: PredictionResolution) -> None:
        row = StoredPredictionResolution(
            id=res.id,
            predictive_claim_id=res.predictive_claim_id,
            payload_json=res.model_dump_json(),
            created_at=_dt(res.resolved_at),
        )
        with self.session() as s:
            existing = s.get(StoredPredictionResolution, res.id)
            if existing:
                for k, v in row.model_dump(exclude={"id"}).items():
                    setattr(existing, k, v)
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_prediction_resolution_for_claim(self, predictive_claim_id: str) -> Optional[PredictionResolution]:
        with self.session() as s:
            stmt = select(StoredPredictionResolution).where(
                StoredPredictionResolution.predictive_claim_id == predictive_claim_id
            )
            r = s.exec(stmt).first()
            if r is None:
                return None
            return PredictionResolution.model_validate_json(r.payload_json)

    # ── Round 3: Methods ──────────────────────────────────────────────────

    def insert_method(self, method: Method) -> None:
        with self.session() as s:
            existing = s.get(StoredMethod, method.method_id)
            if existing:
                return
            row = StoredMethod(
                method_id=method.method_id,
                status=method.status,
                payload_json=method.model_dump_json(),
            )
            s.add(row)
            s.commit()

    def get_method(self, method_id: str) -> Optional[Method]:
        with self.session() as s:
            r = s.get(StoredMethod, method_id)
            if r is None:
                return None
            return Method.model_validate_json(r.payload_json)

    def list_methods(self, status_filter: Optional[str] = None) -> list[Method]:
        with self.session() as s:
            stmt = select(StoredMethod)
            if status_filter is not None:
                stmt = stmt.where(StoredMethod.status == status_filter)
            rows = s.exec(stmt).all()
            return [Method.model_validate_json(r.payload_json) for r in rows]

    def insert_method_invocation(self, inv: MethodInvocation) -> None:
        row = StoredMethodInvocation(
            id=inv.id,
            method_id=inv.method_id,
            correlation_id=inv.correlation_id,
            payload_json=inv.model_dump_json(),
        )
        with self.session() as s:
            s.add(row)
            s.commit()

    def get_method_invocation(self, inv_id: str) -> Optional[MethodInvocation]:
        with self.session() as s:
            r = s.get(StoredMethodInvocation, inv_id)
            if r is None:
                return None
            return MethodInvocation.model_validate_json(r.payload_json)

    # ── Round 3: Ledger ───────────────────────────────────────────────────

    def append_ledger_entry(self, entry: LedgerEntry) -> None:
        with self.session() as s:
            tail_row = s.exec(
                select(StoredLedgerEntry)
                .order_by(desc(StoredLedgerEntry.timestamp))
                .limit(1)
            ).first()
            if tail_row is not None:
                if entry.prev_hash != tail_row.entry_id:
                    raise LedgerChainError(
                        f"prev_hash {entry.prev_hash!r} != tail {tail_row.entry_id!r}"
                    )
            row = StoredLedgerEntry(
                entry_id=entry.entry_id,
                prev_hash=entry.prev_hash,
                method_id=entry.method_id,
                timestamp=entry.timestamp,
                payload_json=entry.model_dump_json(),
            )
            s.add(row)
            s.commit()

    def get_ledger_entry(self, entry_id: str) -> Optional[LedgerEntry]:
        with self.session() as s:
            r = s.get(StoredLedgerEntry, entry_id)
            if r is None:
                return None
            return LedgerEntry.model_validate_json(r.payload_json)

    def iter_ledger(
        self, from_id: Optional[str] = None, to_id: Optional[str] = None
    ) -> Iterator[LedgerEntry]:
        with self.session() as s:
            rows = s.exec(
                select(StoredLedgerEntry).order_by(asc(StoredLedgerEntry.timestamp))
            ).all()
        started = from_id is None
        for r in rows:
            if not started:
                if r.entry_id == from_id:
                    started = True
                else:
                    continue
            yield LedgerEntry.model_validate_json(r.payload_json)
            if to_id is not None and r.entry_id == to_id:
                return

    def ledger_tail(self) -> Optional[LedgerEntry]:
        with self.session() as s:
            r = s.exec(
                select(StoredLedgerEntry)
                .order_by(desc(StoredLedgerEntry.timestamp))
                .limit(1)
            ).first()
            if r is None:
                return None
            return LedgerEntry.model_validate_json(r.payload_json)

    # ── Round 3: Cascade ──────────────────────────────────────────────────

    def insert_cascade_node(self, node: CascadeNode) -> None:
        row = StoredCascadeNode(
            node_id=node.node_id,
            kind=node.kind.value,
            payload_json=node.model_dump_json(),
        )
        with self.session() as s:
            s.add(row)
            s.commit()

    def get_cascade_node(self, node_id: str) -> Optional[CascadeNode]:
        with self.session() as s:
            r = s.get(StoredCascadeNode, node_id)
            if r is None:
                return None
            return CascadeNode.model_validate_json(r.payload_json)

    def insert_cascade_edge(self, edge: CascadeEdge) -> None:
        with self.session() as s:
            inv = s.get(StoredMethodInvocation, edge.method_invocation_id)
            if inv is None:
                raise CascadeEdgeOrphanError(
                    f"method_invocation_id {edge.method_invocation_id!r} not found"
                )
            if edge.relation in (
                CascadeEdgeRelation.SUPPORTS,
                CascadeEdgeRelation.REFUTES,
            ):
                opposite = (
                    CascadeEdgeRelation.REFUTES
                    if edge.relation == CascadeEdgeRelation.SUPPORTS
                    else CascadeEdgeRelation.SUPPORTS
                )
                conflict = s.exec(
                    select(StoredCascadeEdge).where(
                        StoredCascadeEdge.src == edge.src,
                        StoredCascadeEdge.dst == edge.dst,
                        StoredCascadeEdge.relation == opposite.value,
                        StoredCascadeEdge.retracted_at == None,  # noqa: E711
                    )
                ).first()
                if conflict is not None:
                    raise CascadeEdgeConflictError(
                        f"Non-retracted {opposite.value} edge exists "
                        f"between {edge.src} -> {edge.dst}"
                    )
            row = StoredCascadeEdge(
                edge_id=edge.edge_id,
                src=edge.src,
                dst=edge.dst,
                relation=edge.relation.value,
                method_invocation_id=edge.method_invocation_id,
                retracted_at=edge.retracted_at,
                payload_json=edge.model_dump_json(),
            )
            s.add(row)
            s.commit()

    def retract_cascade_edge(self, edge_id: str, retracted_at: datetime) -> None:
        with self.session() as s:
            r = s.get(StoredCascadeEdge, edge_id)
            if r is None:
                return
            r.retracted_at = retracted_at
            edge = CascadeEdge.model_validate_json(r.payload_json)
            edge.retracted_at = retracted_at
            r.payload_json = edge.model_dump_json()
            s.add(r)
            s.commit()

    def iter_cascade_edges(
        self,
        src: Optional[str] = None,
        dst: Optional[str] = None,
        relation: Optional[str] = None,
        include_retracted: bool = False,
    ) -> Iterator[CascadeEdge]:
        with self.session() as s:
            stmt = select(StoredCascadeEdge)
            if src is not None:
                stmt = stmt.where(StoredCascadeEdge.src == src)
            if dst is not None:
                stmt = stmt.where(StoredCascadeEdge.dst == dst)
            if relation is not None:
                stmt = stmt.where(StoredCascadeEdge.relation == relation)
            if not include_retracted:
                stmt = stmt.where(StoredCascadeEdge.retracted_at == None)  # noqa: E711
            rows = s.exec(stmt).all()
        for r in rows:
            yield CascadeEdge.model_validate_json(r.payload_json)

    # ── Round 3: Temporal cuts / Evaluation ───────────────────────────────

    def insert_temporal_cut(self, cut: TemporalCut) -> None:
        row = StoredTemporalCut(
            cut_id=cut.cut_id, payload_json=cut.model_dump_json()
        )
        with self.session() as s:
            s.add(row)
            for outcome in cut.outcomes:
                if not s.get(StoredOutcome, outcome.outcome_id):
                    s.add(StoredOutcome(
                        outcome_id=outcome.outcome_id,
                        payload_json=outcome.model_dump_json(),
                    ))
                assoc_id = f"{cut.cut_id}:{outcome.outcome_id}"
                if not s.get(StoredCutOutcome, assoc_id):
                    s.add(StoredCutOutcome(
                        id=assoc_id,
                        cut_id=cut.cut_id,
                        outcome_id=outcome.outcome_id,
                    ))
            s.commit()

    def get_temporal_cut(self, cut_id: str) -> Optional[TemporalCut]:
        with self.session() as s:
            r = s.get(StoredTemporalCut, cut_id)
            if r is None:
                return None
            return TemporalCut.model_validate_json(r.payload_json)

    def iter_temporal_cuts(self) -> Iterator[TemporalCut]:
        with self.session() as s:
            rows = s.exec(select(StoredTemporalCut)).all()
        for r in rows:
            yield TemporalCut.model_validate_json(r.payload_json)

    def insert_outcome(self, outcome: Outcome, *, cut_id: str) -> None:
        with self.session() as s:
            if not s.get(StoredOutcome, outcome.outcome_id):
                s.add(StoredOutcome(
                    outcome_id=outcome.outcome_id,
                    payload_json=outcome.model_dump_json(),
                ))
            assoc_id = f"{cut_id}:{outcome.outcome_id}"
            if not s.get(StoredCutOutcome, assoc_id):
                s.add(StoredCutOutcome(
                    id=assoc_id,
                    cut_id=cut_id,
                    outcome_id=outcome.outcome_id,
                ))
            s.commit()

    def list_outcomes_for_cut(self, cut_id: str) -> list[Outcome]:
        with self.session() as s:
            assocs = s.exec(
                select(StoredCutOutcome).where(StoredCutOutcome.cut_id == cut_id)
            ).all()
            out: list[Outcome] = []
            for a in assocs:
                r = s.get(StoredOutcome, a.outcome_id)
                if r is not None:
                    out.append(Outcome.model_validate_json(r.payload_json))
            return out

    def insert_counterfactual_run(self, run: CounterfactualEvalRun) -> None:
        row = StoredCounterfactualRun(
            run_id=run.run_id, payload_json=run.model_dump_json()
        )
        with self.session() as s:
            s.add(row)
            s.commit()

    def get_counterfactual_run(self, run_id: str) -> Optional[CounterfactualEvalRun]:
        with self.session() as s:
            r = s.get(StoredCounterfactualRun, run_id)
            if r is None:
                return None
            return CounterfactualEvalRun.model_validate_json(r.payload_json)

    # ── Round 3: External battery ─────────────────────────────────────────

    def insert_corpus_bundle(self, bundle: CorpusBundle) -> None:
        row = StoredExternalBundle(
            content_hash=bundle.content_hash,
            payload_json=bundle.model_dump_json(),
        )
        with self.session() as s:
            s.add(row)
            s.commit()

    def get_corpus_bundle(self, content_hash: str) -> Optional[CorpusBundle]:
        with self.session() as s:
            r = s.get(StoredExternalBundle, content_hash)
            if r is None:
                return None
            return CorpusBundle.model_validate_json(r.payload_json)

    def insert_battery_run(self, run: BatteryRunResult) -> None:
        row = StoredBatteryRun(
            run_id=run.run_id, payload_json=run.model_dump_json()
        )
        with self.session() as s:
            s.add(row)
            s.commit()

    def get_battery_run(self, run_id: str) -> Optional[BatteryRunResult]:
        with self.session() as s:
            r = s.get(StoredBatteryRun, run_id)
            if r is None:
                return None
            return BatteryRunResult.model_validate_json(r.payload_json)

    # ── Round 3: Transfer / Review / Rebuttal ─────────────────────────────

    def insert_transfer_study(self, study: TransferStudy) -> None:
        row = StoredTransferStudy(
            study_id=study.study_id,
            method_ref_name=study.method_ref.name,
            method_ref_version=study.method_ref.version,
            payload_json=study.model_dump_json(),
        )
        with self.session() as s:
            s.add(row)
            s.commit()

    def list_transfer_studies(self, method_ref: MethodRef) -> list[TransferStudy]:
        with self.session() as s:
            rows = s.exec(
                select(StoredTransferStudy).where(
                    StoredTransferStudy.method_ref_name == method_ref.name,
                    StoredTransferStudy.method_ref_version == method_ref.version,
                )
            ).all()
            return [TransferStudy.model_validate_json(r.payload_json) for r in rows]

    def insert_review_report(self, report: ReviewReport) -> None:
        row = StoredReviewReport(
            report_id=report.report_id,
            conclusion_id=report.conclusion_id,
            payload_json=report.model_dump_json(),
        )
        with self.session() as s:
            s.add(row)
            s.commit()

    def list_review_reports(self, conclusion_id: str) -> list[ReviewReport]:
        with self.session() as s:
            rows = s.exec(
                select(StoredReviewReport).where(
                    StoredReviewReport.conclusion_id == conclusion_id
                )
            ).all()
            return [ReviewReport.model_validate_json(r.payload_json) for r in rows]

    def insert_rebuttal(self, rebuttal: Rebuttal, *, report_id: str) -> None:
        row = StoredRebuttal(
            id=str(uuid.uuid4()),
            report_id=report_id,
            finding_id=rebuttal.finding_id,
            payload_json=rebuttal.model_dump_json(),
        )
        with self.session() as s:
            s.add(row)
            s.commit()

    def list_rebuttals(self, report_id: str) -> list[Rebuttal]:
        with self.session() as s:
            rows = s.exec(
                select(StoredRebuttal).where(
                    StoredRebuttal.report_id == report_id
                )
            ).all()
            return [Rebuttal.model_validate_json(r.payload_json) for r in rows]

    # ── Round 3: Decay / Revalidation ─────────────────────────────────────

    def insert_decay_policy(self, policy: DecayPolicy) -> str:
        pid = str(uuid.uuid4())
        row = StoredDecayPolicy(id=pid, payload_json=policy.model_dump_json())
        with self.session() as s:
            s.add(row)
            s.commit()
        return pid

    def bind_policy(self, object_id: str, policy_id: str) -> None:
        row = StoredObjectPolicyBinding(
            id=f"{object_id}:{policy_id}",
            object_id=object_id,
            policy_id=policy_id,
        )
        with self.session() as s:
            s.merge(row)
            s.commit()

    def unbind_policy(self, object_id: str, policy_id: str) -> None:
        bid = f"{object_id}:{policy_id}"
        with self.session() as s:
            r = s.get(StoredObjectPolicyBinding, bid)
            if r is not None:
                s.delete(r)
                s.commit()

    def insert_revalidation(self, result: RevalidationResult) -> None:
        row = StoredRevalidation(
            id=str(uuid.uuid4()),
            object_id=result.object_id,
            payload_json=result.model_dump_json(),
        )
        with self.session() as s:
            s.add(row)
            s.commit()

    def list_revalidations(self, object_id: str) -> list[RevalidationResult]:
        with self.session() as s:
            rows = s.exec(
                select(StoredRevalidation).where(
                    StoredRevalidation.object_id == object_id
                )
            ).all()
            return [RevalidationResult.model_validate_json(r.payload_json) for r in rows]

    # ── Round 3: Rigor gate ───────────────────────────────────────────────

    def insert_rigor_submission(self, sub: RigorSubmission) -> None:
        row = StoredRigorSubmission(
            submission_id=sub.submission_id,
            author_id=sub.author.id,
            intended_venue=sub.intended_venue,
            payload_json=sub.model_dump_json(),
        )
        with self.session() as s:
            s.add(row)
            s.commit()

    def insert_rigor_verdict(self, verdict: RigorVerdict) -> None:
        row = StoredRigorVerdict(
            ledger_entry_id=verdict.ledger_entry_id,
            payload_json=verdict.model_dump_json(),
        )
        with self.session() as s:
            s.add(row)
            s.commit()

    def insert_founder_override(self, override: FounderOverride) -> None:
        row = StoredFounderOverride(
            override_id=override.override_id,
            payload_json=override.model_dump_json(),
        )
        with self.session() as s:
            s.add(row)
            s.commit()

    # ── Round 3: MIP ──────────────────────────────────────────────────────

    def insert_mip_manifest(self, manifest: MIPManifest) -> None:
        row = StoredMIPManifest(
            content_hash=manifest.content_hash,
            payload_json=manifest.model_dump_json(),
        )
        with self.session() as s:
            s.add(row)
            s.commit()

    def list_mip_manifests(self) -> list[MIPManifest]:
        with self.session() as s:
            rows = s.exec(select(StoredMIPManifest)).all()
            return [MIPManifest.model_validate_json(r.payload_json) for r in rows]

"""
SQLite persistence via SQLModel. Raw SQL is confined to this module.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Any, Generator, Iterator, Literal, Optional

import numpy as np
import sqlalchemy as sa
from sqlalchemy import Column, LargeBinary, UniqueConstraint, asc, desc, inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, create_engine, select

from noosphere.models import (
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
    FollowUpMessage,
    FollowUpSession,
    FounderOverride,
    Freshness,
    LedgerEntry,
    Method,
    MethodInvocation,
    MethodRef,
    MIPManifest,
    OpinionCitation,
    Outcome,
    OutcomeKind,
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


# ── Currents (Wave 1): Stored tables ────────────────────────────────────────


class StoredCurrentEvent(SQLModel, table=True):
    __tablename__ = "current_event"
    __table_args__ = (
        sa.Index(
            "ix_current_event_status_source_captured_at",
            "status",
            "source_captured_at",
        ),
        sa.Index(
            "ix_current_event_dedupe_hash",
            "dedupe_hash",
            unique=True,
        ),
    )

    id: str = Field(primary_key=True)
    source: str = Field(default="")
    source_captured_at: datetime = Field(default_factory=_utcnow)
    ingested_at: datetime = Field(default_factory=_utcnow)
    dedupe_hash: str = Field(default="")
    status: str = Field(default="observed")
    topic_hint: Optional[str] = Field(default=None)
    payload_json: str = ""


class StoredEventOpinion(SQLModel, table=True):
    __tablename__ = "event_opinion"
    __table_args__ = (
        sa.Index("ix_event_opinion_event_id", "event_id"),
        sa.Index("ix_event_opinion_generated_at", "generated_at"),
    )

    id: str = Field(primary_key=True)
    event_id: str = Field(default="")
    generated_at: datetime = Field(default_factory=_utcnow)
    revoked: bool = Field(default=False)
    payload_json: str = ""


class StoredOpinionCitation(SQLModel, table=True):
    __tablename__ = "opinion_citation"
    __table_args__ = (
        sa.Index("ix_opinion_citation_opinion_id", "opinion_id"),
        sa.Index("ix_opinion_citation_conclusion_id", "conclusion_id"),
        sa.Index("ix_opinion_citation_claim_id", "claim_id"),
    )

    id: str = Field(primary_key=True)
    opinion_id: str = Field(default="")
    conclusion_id: Optional[str] = Field(default=None)
    claim_id: Optional[str] = Field(default=None)
    ordinal: int = Field(default=0)
    payload_json: str = ""


class StoredFollowUpSession(SQLModel, table=True):
    __tablename__ = "followup_session"
    __table_args__ = (
        sa.Index("ix_followup_session_expires_at", "expires_at"),
        sa.Index("ix_followup_session_client_fingerprint", "client_fingerprint"),
    )

    id: str = Field(primary_key=True)
    opinion_id: str = Field(default="")
    expires_at: datetime = Field(default_factory=_utcnow)
    client_fingerprint: str = Field(default="")
    payload_json: str = ""


class StoredFollowUpMessage(SQLModel, table=True):
    __tablename__ = "followup_message"
    __table_args__ = (
        sa.Index(
            "ix_followup_message_session_id_created_at",
            "session_id",
            "created_at",
        ),
    )

    id: str = Field(primary_key=True)
    session_id: str = Field(default="")
    created_at: datetime = Field(default_factory=_utcnow)
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
            if r is None:
                return None
            return Conclusion.model_validate_json(r.payload_json)

    def list_conclusions(self) -> list[Conclusion]:
        with self.session() as s:
            rows = s.exec(select(StoredConclusion)).all()
            return [Conclusion.model_validate_json(r.payload_json) for r in rows]

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

    # ── Currents (Wave 1) accessors ──────────────────────────────────────

    # --- CurrentEvent ---
    def add_current_event(self, ev: CurrentEvent) -> None:
        row = StoredCurrentEvent(
            id=ev.id,
            source=ev.source.value,
            source_captured_at=_dt(ev.source_captured_at),
            ingested_at=_dt(ev.ingested_at),
            dedupe_hash=ev.dedupe_hash,
            status=ev.status.value,
            topic_hint=ev.topic_hint,
            payload_json=ev.model_dump_json(),
        )
        with self.session() as s:
            existing = s.get(StoredCurrentEvent, ev.id)
            if existing:
                existing.source = row.source
                existing.source_captured_at = row.source_captured_at
                existing.ingested_at = row.ingested_at
                existing.dedupe_hash = row.dedupe_hash
                existing.status = row.status
                existing.topic_hint = row.topic_hint
                existing.payload_json = row.payload_json
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_current_event(self, event_id: str) -> Optional[CurrentEvent]:
        with self.session() as s:
            r = s.get(StoredCurrentEvent, event_id)
            if r is None:
                return None
            return CurrentEvent.model_validate_json(r.payload_json)

    def find_current_event_by_dedupe(self, dedupe_hash: str) -> Optional[CurrentEvent]:
        with self.session() as s:
            r = s.exec(
                select(StoredCurrentEvent).where(
                    StoredCurrentEvent.dedupe_hash == dedupe_hash
                )
            ).first()
            if r is None:
                return None
            return CurrentEvent.model_validate_json(r.payload_json)

    def list_current_event_ids(
        self,
        *,
        status: Optional[CurrentEventStatus] = None,
        since: Optional[datetime] = None,
        limit: int = 200,
    ) -> list[str]:
        with self.session() as s:
            stmt = select(StoredCurrentEvent)
            if status is not None:
                stmt = stmt.where(StoredCurrentEvent.status == status.value)
            if since is not None:
                stmt = stmt.where(StoredCurrentEvent.source_captured_at >= _dt(since))
            stmt = stmt.order_by(desc(StoredCurrentEvent.source_captured_at)).limit(limit)
            rows = s.exec(stmt).all()
            return [r.id for r in rows]

    def update_current_event_status(
        self,
        event_id: str,
        status: CurrentEventStatus,
        *,
        reason: Optional[str] = None,
    ) -> None:
        with self.session() as s:
            r = s.get(StoredCurrentEvent, event_id)
            if r is None:
                return
            ev = CurrentEvent.model_validate_json(r.payload_json)
            ev = ev.model_copy(update={"status": status, "status_reason": reason})
            r.status = status.value
            r.payload_json = ev.model_dump_json()
            s.add(r)
            s.commit()

    def set_current_event_topic_and_embedding(
        self,
        event_id: str,
        *,
        topic_hint: str,
        embedding: list[float],
    ) -> None:
        with self.session() as s:
            r = s.get(StoredCurrentEvent, event_id)
            if r is None:
                return
            ev = CurrentEvent.model_validate_json(r.payload_json)
            ev = ev.model_copy(update={"topic_hint": topic_hint, "embedding": list(embedding)})
            r.topic_hint = topic_hint
            r.payload_json = ev.model_dump_json()
            s.add(r)
            s.commit()

    # --- EventOpinion ---
    def add_event_opinion(
        self, op: EventOpinion, citations: list[OpinionCitation]
    ) -> None:
        """Transactional write: opinion + all its citations committed atomically."""
        for c in citations:
            if c.opinion_id != op.id:
                raise ValueError(
                    f"citation.opinion_id {c.opinion_id!r} does not match opinion {op.id!r}"
                )
        op_row = StoredEventOpinion(
            id=op.id,
            event_id=op.event_id,
            generated_at=_dt(op.generated_at),
            revoked=bool(op.revoked),
            payload_json=op.model_dump_json(),
        )
        cite_rows = [
            StoredOpinionCitation(
                id=c.id,
                opinion_id=c.opinion_id,
                conclusion_id=c.conclusion_id,
                claim_id=c.claim_id,
                ordinal=c.ordinal,
                payload_json=c.model_dump_json(),
            )
            for c in citations
        ]
        with self.session() as s:
            existing = s.get(StoredEventOpinion, op.id)
            if existing:
                existing.event_id = op_row.event_id
                existing.generated_at = op_row.generated_at
                existing.revoked = op_row.revoked
                existing.payload_json = op_row.payload_json
                s.add(existing)
            else:
                s.add(op_row)
            for cr in cite_rows:
                existing_cite = s.get(StoredOpinionCitation, cr.id)
                if existing_cite:
                    existing_cite.opinion_id = cr.opinion_id
                    existing_cite.conclusion_id = cr.conclusion_id
                    existing_cite.claim_id = cr.claim_id
                    existing_cite.ordinal = cr.ordinal
                    existing_cite.payload_json = cr.payload_json
                    s.add(existing_cite)
                else:
                    s.add(cr)
            s.commit()

    def get_event_opinion(self, opinion_id: str) -> Optional[EventOpinion]:
        with self.session() as s:
            r = s.get(StoredEventOpinion, opinion_id)
            if r is None:
                return None
            return EventOpinion.model_validate_json(r.payload_json)

    def list_opinions_for_event(self, event_id: str) -> list[str]:
        with self.session() as s:
            rows = s.exec(
                select(StoredEventOpinion)
                .where(StoredEventOpinion.event_id == event_id)
                .order_by(desc(StoredEventOpinion.generated_at))
            ).all()
            return [r.id for r in rows]

    def list_recent_opinion_ids(
        self, *, limit: int = 50, offset: int = 0
    ) -> list[str]:
        with self.session() as s:
            stmt = (
                select(StoredEventOpinion)
                .order_by(desc(StoredEventOpinion.generated_at))
                .offset(offset)
                .limit(limit)
            )
            rows = s.exec(stmt).all()
            return [r.id for r in rows]

    def list_event_opinions_since(
        self, since: Optional[datetime], *, limit: int = 64
    ) -> list[EventOpinion]:
        """Return opinions with generated_at strictly greater than ``since``.

        Ordered by ``generated_at ASC`` so the in-process tailer can advance
        its cursor monotonically. When ``since`` is ``None``, returns the
        first ``limit`` opinions ordered by generated_at ascending.
        """
        with self.session() as s:
            stmt = select(StoredEventOpinion)
            if since is not None:
                stmt = stmt.where(StoredEventOpinion.generated_at > _dt(since))
            stmt = stmt.order_by(asc(StoredEventOpinion.generated_at)).limit(limit)
            rows = s.exec(stmt).all()
            return [EventOpinion.model_validate_json(r.payload_json) for r in rows]

    def count_event_opinions(
        self,
        *,
        revoked: Optional[bool] = None,
    ) -> int:
        """Count stored event opinions. Filters on ``revoked`` when supplied.

        We do not store a separate abstention_reason column — abstained events
        never produce an EventOpinion row, so the count here maps cleanly to
        'published opinions' (minus revoked ones if the caller filters).
        """
        with self.session() as s:
            stmt = select(StoredEventOpinion)
            if revoked is not None:
                stmt = stmt.where(StoredEventOpinion.revoked == bool(revoked))
            rows = s.exec(stmt).all()
            return len(rows)

    def count_active_followup_sessions(self, *, window_minutes: int = 30) -> int:
        """Approximate count of followup sessions active within the last window.

        A session is 'active' if its expires_at is in the future. We use
        expires_at as a proxy for recent activity: sessions are re-upped on
        each message, so a still-valid expires_at implies recent engagement.
        """
        from datetime import datetime as _datetime, timezone as _timezone
        now = _datetime.now(_timezone.utc)
        with self.session() as s:
            stmt = select(StoredFollowUpSession).where(
                StoredFollowUpSession.expires_at >= _dt(now)
            )
            rows = s.exec(stmt).all()
            return len(rows)

    def list_citations_for_opinion(self, opinion_id: str) -> list[OpinionCitation]:
        with self.session() as s:
            rows = s.exec(
                select(StoredOpinionCitation)
                .where(StoredOpinionCitation.opinion_id == opinion_id)
                .order_by(asc(StoredOpinionCitation.ordinal))
            ).all()
            return [OpinionCitation.model_validate_json(r.payload_json) for r in rows]

    def revoke_opinion(self, opinion_id: str, reason: str) -> None:
        with self.session() as s:
            r = s.get(StoredEventOpinion, opinion_id)
            if r is None:
                return
            op = EventOpinion.model_validate_json(r.payload_json)
            op = op.model_copy(update={"revoked": True, "revoked_reason": reason})
            r.revoked = True
            r.payload_json = op.model_dump_json()
            s.add(r)
            s.commit()

    # --- FollowUp ---
    def add_followup_session(self, sess: FollowUpSession) -> None:
        row = StoredFollowUpSession(
            id=sess.id,
            opinion_id=sess.opinion_id,
            expires_at=_dt(sess.expires_at),
            client_fingerprint=sess.client_fingerprint,
            payload_json=sess.model_dump_json(),
        )
        with self.session() as s:
            existing = s.get(StoredFollowUpSession, sess.id)
            if existing:
                existing.opinion_id = row.opinion_id
                existing.expires_at = row.expires_at
                existing.client_fingerprint = row.client_fingerprint
                existing.payload_json = row.payload_json
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_followup_session(self, session_id: str) -> Optional[FollowUpSession]:
        with self.session() as s:
            r = s.get(StoredFollowUpSession, session_id)
            if r is None:
                return None
            return FollowUpSession.model_validate_json(r.payload_json)

    def touch_followup_session(self, session_id: str, *, now: datetime) -> None:
        with self.session() as s:
            r = s.get(StoredFollowUpSession, session_id)
            if r is None:
                return
            sess = FollowUpSession.model_validate_json(r.payload_json)
            sess = sess.model_copy(update={"last_activity_at": now})
            r.payload_json = sess.model_dump_json()
            s.add(r)
            s.commit()

    def add_followup_message(self, msg: FollowUpMessage) -> None:
        row = StoredFollowUpMessage(
            id=msg.id,
            session_id=msg.session_id,
            created_at=_dt(msg.created_at),
            payload_json=msg.model_dump_json(),
        )
        with self.session() as s:
            existing = s.get(StoredFollowUpMessage, msg.id)
            if existing:
                existing.session_id = row.session_id
                existing.created_at = row.created_at
                existing.payload_json = row.payload_json
                s.add(existing)
            else:
                s.add(row)
            # Update session message_count + last_activity_at
            sess_row = s.get(StoredFollowUpSession, msg.session_id)
            if sess_row is not None:
                sess = FollowUpSession.model_validate_json(sess_row.payload_json)
                sess = sess.model_copy(
                    update={
                        "message_count": sess.message_count + (0 if existing else 1),
                        "last_activity_at": _dt(msg.created_at),
                    }
                )
                sess_row.payload_json = sess.model_dump_json()
                s.add(sess_row)
            s.commit()

    def list_followup_messages(self, session_id: str) -> list[FollowUpMessage]:
        with self.session() as s:
            rows = s.exec(
                select(StoredFollowUpMessage)
                .where(StoredFollowUpMessage.session_id == session_id)
                .order_by(asc(StoredFollowUpMessage.created_at))
            ).all()
            return [FollowUpMessage.model_validate_json(r.payload_json) for r in rows]

    def count_followup_messages_in_window(
        self, client_fingerprint: str, *, since: datetime
    ) -> int:
        with self.session() as s:
            # Join through followup_session to filter by client_fingerprint
            sessions = s.exec(
                select(StoredFollowUpSession).where(
                    StoredFollowUpSession.client_fingerprint == client_fingerprint
                )
            ).all()
            session_ids = [sess.id for sess in sessions]
            if not session_ids:
                return 0
            since_dt = _dt(since)
            rows = s.exec(
                select(StoredFollowUpMessage).where(
                    StoredFollowUpMessage.session_id.in_(session_ids),  # type: ignore[attr-defined]
                    StoredFollowUpMessage.created_at >= since_dt,
                )
            ).all()
            return len(rows)

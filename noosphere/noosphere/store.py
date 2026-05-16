"""
SQLite persistence via SQLModel. Raw SQL is confined to this module.
"""

from __future__ import annotations

import json
import os
import struct
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Generator, Iterable, Iterator, Literal, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    import numpy as np
except ImportError as exc:  # pragma: no cover - exercised only on broken local wheels.
    np = None  # type: ignore[assignment]
    _NUMPY_IMPORT_ERROR = exc
else:
    _NUMPY_IMPORT_ERROR = None
from sqlalchemy import (
    Column,
    Index,
    LargeBinary,
    UniqueConstraint,
    asc,
    desc,
    inspect,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.pool import NullPool, StaticPool
from sqlmodel import Field, Session, SQLModel, create_engine, select

from noosphere.algorithms.validators import (
    AlgorithmValidationError,
    validate_inputs,
    validate_output_schema,
    validate_promotion_to_active,
    validate_reasoning_chain,
    validate_status_transition,
    validate_trigger_predicate,
)
from noosphere.models import (
    AbstentionReason,
    Actor,
    AdversarialChallenge,
    AlgorithmCalibrationSnapshot,
    AlgorithmCorrectness,
    AlgorithmInvocation,
    AlgorithmInputObservation,
    AlgorithmStatus,
    AlgorithmTriageRecommendation,
    TriageRecommendationAction,
    TriageRecommendationStatus,
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
    EquityInstrument,
    EquityPortfolioState,
    EquityPosition,
    EquityPositionMode,
    EquityPriceTick,
    EquitySignal,
    EquitySignalCitation,
    EquitySignalStatus,
    EventOpinion,
    ForecastBet,
    ForecastBetMode,
    ForecastCitation,
    ForecastFollowUpMessage,
    ForecastFollowUpSession,
    ForecastMarket,
    ForecastMarketStatus,
    ForecastPortfolioState,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastResolution,
    ForecastTrace,
    FormalisationStatus,
    FounderOverride,
    FollowUpMessage,
    FollowUpSession,
    Freshness,
    LedgerEntry,
    LogicalAlgorithm,
    Method,
    MethodInvocation,
    MethodRef,
    MIPManifest,
    Outcome,
    OutcomeKind,
    OpinionCitation,
    OperatorState,
    PredictionResolution,
    PredictiveClaim,
    Principle,
    QuantitativeFormalisation,
    QuantitativeTestResult,
    ReadingQueueEntry,
    Rebuttal,
    ResolutionMismatch,
    ResolutionOverride,
    ResolutionRevision,
    RelativePositionMap,
    ResearchSuggestion,
    RevalidationResult,
    ReviewItem,
    ReviewReport,
    RigorSubmission,
    RigorVerdict,
    SixLayerScore,
    SocialPost,
    InvestmentMemo,
    MemoDispatch,
    MemoDispatchBetKind,
    MemoDispatchOutcome,
    MemoStatus,
    PortfolioAgent,
    PortfolioAgentKind,
    PortfolioAgentStatus,
    SynthesizerMemo,
    SynthesizerTask,
    SynthesizerTaskStatus,
    SynthesizerTaskTrigger,
    TemporalCut,
    Topic,
    TransferStudy,
    VoicePhaseRecord,
    VoiceProfile,
    WatchedMarket,
    voice_canonical_key,
)

_PSYCOPG2_UNSUPPORTED_QUERY_PARAMS = {
    "pgbouncer",
    "connection_limit",
    "pool_timeout",
}


def _is_postgres_url(url: str) -> bool:
    return urlsplit(url).scheme.startswith("postgres")


def _psycopg2_compatible_url(url: str) -> str:
    """Remove client-only pooler hints that psycopg2 rejects."""

    if "?" not in url or not _is_postgres_url(url):
        return url
    parts = urlsplit(url)
    filtered = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _PSYCOPG2_UNSUPPORTED_QUERY_PARAMS
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(filtered), parts.fragment)
    )


def _env_int(name: str, default: int, *, minimum: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(minimum, value)


def _default_pool_size(url: str) -> int:
    host = urlsplit(url).hostname or ""
    if ".pooler.supabase.com" in host:
        return 1
    return 2


def _is_supabase_transaction_pooler(url: str) -> bool:
    parts = urlsplit(url)
    return (parts.hostname or "").endswith(
        ".pooler.supabase.com"
    ) and parts.port == 6543


def _engine_kwargs_for_url(url: str) -> dict[str, Any]:
    """Keep long-lived Noosphere processes inside managed Postgres limits."""

    if url in {"sqlite://", "sqlite:///:memory:"}:
        return {"poolclass": StaticPool}
    if not _is_postgres_url(url):
        return {}
    if _is_supabase_transaction_pooler(url):
        return {"poolclass": NullPool, "pool_pre_ping": True}
    return {
        "pool_size": _env_int(
            "NOOSPHERE_DB_POOL_SIZE",
            _default_pool_size(url),
            minimum=1,
        ),
        "max_overflow": _env_int("NOOSPHERE_DB_MAX_OVERFLOW", 0, minimum=0),
        "pool_timeout": _env_int("NOOSPHERE_DB_POOL_TIMEOUT", 10, minimum=1),
        "pool_recycle": _env_int("NOOSPHERE_DB_POOL_RECYCLE_SECONDS", 300, minimum=30),
        "pool_pre_ping": True,
        "pool_use_lifo": True,
    }


def _dt(v: datetime | date) -> datetime:
    if isinstance(v, datetime):
        return v
    return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)


def _as_utc_aware(v: datetime | None) -> datetime | None:
    if v is None or v.tzinfo is not None:
        return v
    return v.replace(tzinfo=timezone.utc)


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


def _copy_sqlmodel_fields(target: Any, source: Any, *, exclude: set[str]) -> None:
    for key in type(source).model_fields:
        if key not in exclude:
            setattr(target, key, getattr(source, key))


class LedgerChainError(Exception):
    """prev_hash does not match the current ledger tail."""


class CascadeEdgeOrphanError(Exception):
    """Referenced method_invocation_id does not exist."""


class CascadeEdgeConflictError(Exception):
    """Supports/refutes conflict on the same (src, dst) pair."""


class StoredArtifact(SQLModel, table=True):
    __tablename__ = "artifact"
    __table_args__ = (
        Index("ix_artifact_provenance_created_at", "provenance", "created_at"),
    )
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
    # Prompt 09 — upload-time provenance demarcation. Stored as the enum
    # string ("PROPRIETARY" | "ENDORSED_EXTERNAL" | ...). Founder-set or
    # CLI-set only; never inferred. Indexed so Oracle filters are fast.
    provenance: str = Field(default="PROPRIETARY", index=True)
    provenance_rationale: str = Field(default="")


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
    # Prompt 09 — inherited from source artifact. Indexed for Oracle filters.
    provenance: str = Field(default="PROPRIETARY", index=True)


class StoredEmbedding(SQLModel, table=True):
    __tablename__ = "embedding"
    id: str = Field(primary_key=True)
    model_name: str = Field(index=True)
    text_sha256: str = Field(index=True)
    dimension: int = 0
    vector: bytes = Field(sa_column=Column(LargeBinary))
    ref_claim_id: str = Field(default="", index=True)


class StoredEmbeddingRetry(SQLModel, table=True):
    __tablename__ = "embedding_retry"

    id: str = Field(primary_key=True)
    source_kind: str = Field(index=True)
    source_id: str = Field(index=True)
    model_name: str = Field(index=True)
    text_sha256: str = Field(index=True)
    attempts: int = 0
    last_error: str = ""
    updated_at: datetime = Field(default_factory=_utcnow)


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
    # Prompt 09 — inherited from source artifact. Indexed for Oracle filters.
    provenance: str = Field(default="PROPRIETARY", index=True)


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


class StoredQuantitativeFormalisation(SQLModel, table=True):
    """Persistent row for the quantitative-formalisation spec layer.

    One row per ``QuantitativeFormalisation``. The full payload is held
    as JSON (so the schema evolves without alembic churn); the
    duplicated ``principle_id`` and ``status`` columns exist for the
    indexed queries the founder triage UI relies on. Mirrors the
    Codex-side ``QuantitativeFormalisation`` Prisma model.
    """

    __tablename__ = "quantitative_formalisation"
    id: str = Field(primary_key=True)
    principle_id: str = Field(index=True)
    status: str = Field(default="DRAFT", index=True)
    payload_json: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class StoredQuantitativeTestResult(SQLModel, table=True):
    """One row per runner pass over an APPROVED quantitative formalisation.

    The full payload is held as JSON (``payload_json``); duplicated
    indexed columns power the most-recent-per-formalisation read the
    public surface and CLI ``status`` view depend on. Mirrors the
    Codex-side ``QuantitativeTestResult`` Prisma model.
    """

    __tablename__ = "quantitative_test_result"
    id: str = Field(primary_key=True)
    formalisation_id: str = Field(index=True)
    principle_id: str = Field(default="", index=True)
    run_stamp: str = Field(index=True)
    status: str = Field(default="RAN", index=True)
    artifacts_path: str = ""
    payload_json: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class StoredLogicalAlgorithm(SQLModel, table=True):
    """One row per LogicalAlgorithm — the Round-19 Layer-3 entity.

    The full Pydantic payload lives in ``payload_json``; duplicated
    indexed columns (``organization_id``, ``status``, ``name``) power
    the founder triage queue and per-tenant listing without parsing
    JSON. Mirrors the Codex-side ``LogicalAlgorithm`` Prisma model.
    """

    __tablename__ = "logical_algorithm"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "name",
            name="logical_algorithm_org_name_key",
        ),
    )
    id: str = Field(primary_key=True)
    organization_id: str = Field(index=True)
    name: str = Field(index=True)
    status: str = Field(default="DRAFT", index=True)
    payload_json: str = ""
    weighting_multiplier: float = Field(default=1.0)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    last_invoked_at: Optional[datetime] = Field(default=None)
    # Prompt 09 — provenance inherited from source principles.
    provenance: str = Field(default="PROPRIETARY", index=True)


class StoredAlgorithmInvocation(SQLModel, table=True):
    """One row per algorithm firing.

    Resolution columns (``resolved_at`` etc.) live inside
    ``payload_json``; the indexed columns are the access keys the
    runtime and calibrator hit hardest — algorithm-id (per-algorithm
    history) and organization-id (per-tenant feed), both ordered by
    invoked-at DESC.
    """

    __tablename__ = "algorithm_invocation"
    __table_args__ = (
        Index(
            "algorithm_invocation_algorithm_invoked_idx",
            "algorithm_id",
            "invoked_at",
        ),
        Index(
            "algorithm_invocation_org_invoked_idx",
            "organization_id",
            "invoked_at",
        ),
    )
    id: str = Field(primary_key=True)
    algorithm_id: str = Field(index=True)
    organization_id: str = Field(index=True)
    invoked_at: datetime = Field(default_factory=_utcnow)
    resolved_at: Optional[datetime] = Field(default=None)
    correctness: Optional[str] = Field(default=None)
    payload_json: str = ""


class StoredAlgorithmInputObservation(SQLModel, table=True):
    """Audit trail for a single (invocation, input_name) pair.

    Records which observability source provided the value at the
    moment the algorithm fired. Founders consult these to answer
    "where did this number come from?" without re-running the runtime.
    """

    __tablename__ = "algorithm_input_observation"
    id: str = Field(primary_key=True)
    invocation_id: str = Field(index=True)
    input_name: str = Field(index=True)
    value_json: str = ""
    observed_at: datetime = Field(default_factory=_utcnow)
    source_artifact_id: Optional[str] = Field(default=None, index=True)
    source_url: Optional[str] = Field(default=None)


class StoredAlgorithmCalibrationSnapshot(SQLModel, table=True):
    """Append-only calibration snapshot for an algorithm.

    One row per (algorithm, snapshot_at). The latest row is what the
    operator triage UI and the public detail page read; the full
    time-series is what the calibration chart renders.
    """

    __tablename__ = "algorithm_calibration_snapshot"
    __table_args__ = (
        Index(
            "algorithm_calibration_snapshot_algo_at_idx",
            "algorithm_id",
            "snapshot_at",
        ),
    )
    id: str = Field(primary_key=True)
    algorithm_id: str = Field(index=True)
    organization_id: str = Field(index=True)
    snapshot_at: datetime = Field(default_factory=_utcnow)

    total_invocations: int = Field(default=0)
    resolved_invocations: int = Field(default=0)
    accuracy: Optional[float] = Field(default=None)
    mean_brier: Optional[float] = Field(default=None)
    mean_horizon_error: Optional[float] = Field(default=None)
    directional_accuracy: Optional[float] = Field(default=None)
    confidence_calibration_drift: Optional[float] = Field(default=None)
    last_30d_accuracy: Optional[float] = Field(default=None)
    last_30d_resolved: int = Field(default=0)
    probabilistic_resolved: int = Field(default=0)
    directional_resolved: int = Field(default=0)
    confidence_band_resolved: int = Field(default=0)


class StoredAlgorithmTriageRecommendation(SQLModel, table=True):
    """Pending / accepted / rejected calibration triage row."""

    __tablename__ = "algorithm_triage_recommendation"
    __table_args__ = (
        Index(
            "algorithm_triage_recommendation_status_idx",
            "organization_id",
            "status",
        ),
    )
    id: str = Field(primary_key=True)
    algorithm_id: str = Field(index=True)
    organization_id: str = Field(index=True)
    recommended_at: datetime = Field(default_factory=_utcnow)
    recommended_action: str = Field(default="NONE")
    trigger_reasons_json: str = Field(default="[]")
    recommended_multiplier: float = Field(default=1.0)
    narrative: str = Field(default="")
    status: str = Field(default="PENDING", index=True)
    resolved_by: Optional[str] = Field(default=None)
    resolved_at: Optional[datetime] = Field(default=None)
    resolution_note: Optional[str] = Field(default=None)


class StoredContradictionResult(SQLModel, table=True):
    """Persisted output of the canonical contradiction engine (R19/p06).

    Mirrors the Prisma ``Contradiction`` table's new columns
    (``score``, ``confidence_low``, ``confidence_high``, ``axis``,
    ``human_explanation``, ``detection_method``). Lives in the noosphere
    store so CLI sweeps and tests can persist without depending on the
    Codex DB. Legacy contradictions written by the six-heuristic vote
    are NOT migrated into this table — they stay on the Prisma side
    with their heuristic provenance.
    """

    __tablename__ = "contradiction_result"
    __table_args__ = (
        Index(
            "contradiction_result_pair_idx",
            "principle_a_id",
            "principle_b_id",
        ),
        Index(
            "contradiction_result_method_at_idx",
            "detection_method",
            "detected_at",
        ),
    )
    id: str = Field(primary_key=True)
    principle_a_id: str = Field(index=True)
    principle_b_id: str = Field(index=True)
    score: float = Field(default=0.0)
    confidence_low: float = Field(default=0.0)
    confidence_high: float = Field(default=0.0)
    verdict: str = Field(default="INDEPENDENT", index=True)
    axis: Optional[str] = Field(default=None)
    human_explanation: Optional[str] = Field(default=None)
    detection_method: str = Field(default="", index=True)
    detected_at: datetime = Field(default_factory=_utcnow)
    raw_sparsity: float = Field(default=0.0)
    direction_method: str = Field(default="")
    extras_json: str = Field(default="{}")
    status: str = Field(default="active", index=True)
    dispute_count: int = Field(default=0)
    last_dispute_at: Optional[datetime] = Field(default=None)


class StoredContradictionDispute(SQLModel, table=True):
    """Founder DISPUTE on a ContradictionResult. Multiple disputes on the
    same ``detection_method`` trigger a calibration review (handled outside
    this module; the count threshold lives in the operator UI).
    """

    __tablename__ = "contradiction_dispute"
    __table_args__ = (
        Index(
            "contradiction_dispute_method_at_idx",
            "detection_method",
            "created_at",
        ),
    )
    id: str = Field(primary_key=True)
    contradiction_result_id: str = Field(index=True)
    detection_method: str = Field(default="", index=True)
    disputed_by: str = Field(default="")
    reason: str = Field(default="")
    created_at: datetime = Field(default_factory=_utcnow)


class StoredContradictionLifecycle(SQLModel, table=True):
    """Lifecycle of one contradiction (Round 19 prompt 19).

    A contradiction is created in DETECTED, then transitions through
    STANDING / WEAKENED / RESOLVED_BY_SOURCE based on subsequent source
    ingestion, or terminates in DISPUTED_AS_ERROR (founder rejected the
    engine's verdict) or SUBSUMED_BY_SYNTHESIS (a new synthesis principle
    supersedes both sides; requires explicit founder confirmation).

    ``events_json`` is the append-only event log; every transition adds
    one record but never overwrites earlier ones. The denormalised
    ``current_status`` / ``last_transition_at`` columns mirror the tail
    of the log so the lifecycle queue is a cheap range scan.
    """

    __tablename__ = "contradiction_lifecycle"
    __table_args__ = (
        Index(
            "contradiction_lifecycle_status_idx",
            "current_status",
            "last_transition_at",
        ),
        Index(
            "contradiction_lifecycle_target_idx",
            "contradiction_id",
        ),
    )
    id: str = Field(primary_key=True)
    contradiction_id: str = Field(index=True)
    current_status: str = Field(default="DETECTED", index=True)
    last_transition_at: datetime = Field(default_factory=_utcnow)
    events_json: str = Field(default="[]")
    supported_principle_id: Optional[str] = Field(default=None)
    subsuming_principle_id: Optional[str] = Field(default=None)
    pending_subsumption_principle_id: Optional[str] = Field(default=None)


# ── Round 19 prompt 07: cluster index for contradiction-test scheduling ────


class StoredPrincipleCluster(SQLModel, table=True):
    """Cluster assignment for one Principle. Versioned by ``assignment_method``
    so a replay query ("which cluster was P in on date Y") is a range scan.
    """

    __tablename__ = "principle_cluster"
    __table_args__ = (
        Index(
            "principle_cluster_cluster_idx", "cluster_id", "assigned_at"
        ),
    )
    principle_id: str = Field(primary_key=True)
    cluster_id: str = Field(index=True)
    assigned_at: datetime = Field(default_factory=_utcnow)
    assignment_method: str = Field(default="incremental/v1")


class StoredClusterCentroid(SQLModel, table=True):
    """Per-cluster centroid (float32 packed) + member count."""

    __tablename__ = "principle_cluster_centroid"
    cluster_id: str = Field(primary_key=True)
    centroid_vec: bytes = Field(default=b"")
    dim: int = Field(default=0)
    member_count: int = Field(default=0)
    assignment_method: str = Field(default="incremental/v1")
    updated_at: datetime = Field(default_factory=_utcnow)


class StoredContradictionTestTask(SQLModel, table=True):
    """Work queue entry: one pair scheduled for the contradiction engine.

    ``pair_key`` is the deterministic ``stable_pair_id(a,b)`` so dedupe is a
    string equality lookup; ``priority`` orders the drain, ``status`` tracks
    lifecycle. Append-only; result_id points to the ContradictionResult once
    detection runs.
    """

    __tablename__ = "contradiction_test_task"
    __table_args__ = (
        Index(
            "contradiction_test_task_status_priority_idx",
            "status",
            "priority",
            "enqueued_at",
        ),
        Index(
            "contradiction_test_task_pair_idx",
            "pair_key",
            "enqueued_at",
        ),
    )
    id: str = Field(primary_key=True)
    principle_a_id: str = Field(index=True)
    principle_b_id: str = Field(index=True)
    pair_key: str = Field(index=True, default="")
    priority: str = Field(default="NORMAL", index=True)
    status: str = Field(default="PENDING", index=True)
    enqueued_at: datetime = Field(default_factory=_utcnow)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)
    result_id: Optional[str] = Field(default=None)
    last_error: Optional[str] = Field(default=None)


class StoredClusterReindexProposal(SQLModel, table=True):
    """Resweep proposal — operator-acknowledged row when drift > threshold."""

    __tablename__ = "cluster_reindex_proposal"
    id: str = Field(primary_key=True)
    proposed_at: datetime = Field(default_factory=_utcnow)
    drift: float = Field(default=0.0)
    cluster_count_before: int = Field(default=0)
    cluster_count_after: int = Field(default=0)
    summary_json: str = Field(default="{}")
    status: str = Field(default="PENDING", index=True)
    resolved_by: Optional[str] = Field(default=None)
    resolved_at: Optional[datetime] = Field(default=None)


class StoredSynthesizerTask(SQLModel, table=True):
    """Queue row for one synthesis task (prompt 10).

    PENDING rows are drained by the scheduler's ``synthesizer_tick``.
    Operator-initiated queries typically bypass the queue and run
    inline; algorithm- and currents-triggered tasks enqueue here so
    the producing tick is not blocked by the synthesizer's LLM round-
    trip.
    """

    __tablename__ = "synthesizer_task"
    __table_args__ = (
        Index(
            "synthesizer_task_status_enqueued_idx",
            "status",
            "enqueued_at",
        ),
        Index(
            "synthesizer_task_org_status_idx",
            "organization_id",
            "status",
        ),
    )
    id: str = Field(primary_key=True)
    organization_id: str = Field(index=True)
    trigger: str = Field(default="OPERATOR", index=True)
    status: str = Field(default="PENDING", index=True)
    enqueued_at: datetime = Field(default_factory=_utcnow)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)
    invocation_id: Optional[str] = Field(default=None, index=True)
    current_event_id: Optional[str] = Field(default=None, index=True)
    memo_id: Optional[str] = Field(default=None)
    outcome: Optional[str] = Field(default=None)
    payload_json: str = Field(default="{}")


class StoredSynthesizerMemo(SQLModel, table=True):
    """Persisted synthesizer memo — the audit-shaped conclusion.

    Prompt 11 will replace the inline memo body with the full
    investment-memo format; both shapes share this row's ``id`` and
    the JSON payload's ``conclusion`` key so consumers don't need to
    be rewritten when prompt 11 lands.
    """

    __tablename__ = "synthesizer_memo"
    __table_args__ = (
        Index(
            "synthesizer_memo_org_created_idx",
            "organization_id",
            "created_at",
        ),
    )
    id: str = Field(primary_key=True)
    organization_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow)
    synthesizer_version: str = Field(default="synthesizer/v1", index=True)
    question: str = Field(default="")
    payload_json: str = Field(default="{}")


class StoredInvestmentMemo(SQLModel, table=True):
    """Persisted investment memo (Round 19 prompt 11).

    The full, structured memo addressed to a portfolio agent or human
    reviewer. Distinct from :class:`StoredSynthesizerMemo`, which is the
    raw audit payload the synthesizer engine emits; this row carries
    the rendered 10-section body, the lifecycle status, and the file
    paths under ``docs/memos/<yyyy>/<mm>/``.
    """

    __tablename__ = "investment_memo"
    __table_args__ = (
        Index(
            "investment_memo_org_status_idx",
            "organization_id",
            "status",
        ),
        Index(
            "investment_memo_org_created_idx",
            "organization_id",
            "created_at",
        ),
        Index(
            "investment_memo_slug_idx",
            "slug",
        ),
    )
    id: str = Field(primary_key=True)
    organization_id: str = Field(index=True)
    synthesizer_result_id: Optional[str] = Field(default=None, index=True)
    title: str = Field(default="")
    slug: str = Field(default="", index=True)
    status: str = Field(default="DRAFT", index=True)
    addressee: str = Field(default="")
    question_type: str = Field(default="EXPLANATORY")
    md_path: Optional[str] = Field(default=None)
    pdf_path: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    sent_at: Optional[datetime] = Field(default=None)
    acknowledged_at: Optional[datetime] = Field(default=None)
    published_at: Optional[datetime] = Field(default=None)
    archived_at: Optional[datetime] = Field(default=None)
    synthesizer_version: str = Field(default="synthesizer/v1")
    payload_json: str = Field(default="{}")


class StoredPortfolioAgent(SQLModel, table=True):
    """Persisted :class:`noosphere.models.PortfolioAgent` row (prompt 12).

    The subscriptions list, default ceiling, and other fields all
    round-trip through ``payload_json`` so the Pydantic shape can
    evolve without a migration. Indexed columns are the ones the
    router consults at dispatch time.
    """

    __tablename__ = "portfolio_agent"
    __table_args__ = (
        Index(
            "portfolio_agent_org_status_idx",
            "organization_id",
            "status",
        ),
    )
    id: str = Field(primary_key=True)
    organization_id: str = Field(index=True)
    name: str = Field(default="")
    kind: str = Field(default="HUMAN", index=True)
    status: str = Field(default="ACTIVE", index=True)
    default_bet_ceiling_usd: float = Field(default=50.0)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    payload_json: str = Field(default="{}")


class StoredMemoDispatch(SQLModel, table=True):
    """Persisted :class:`noosphere.models.MemoDispatch` row (prompt 12).

    Each row records one delivery of one memo to one portfolio
    agent. ``outcome_action`` carries the lifecycle state — PENDING
    rows are the HUMAN-mode inbox; the other states are terminal (or
    DEFERRED, which moves back to PENDING when the deferred-until
    timestamp passes).
    """

    __tablename__ = "memo_dispatch"
    __table_args__ = (
        Index(
            "memo_dispatch_agent_outcome_idx",
            "agent_id",
            "outcome_action",
        ),
        Index(
            "memo_dispatch_org_dispatched_idx",
            "organization_id",
            "dispatched_at",
        ),
        Index(
            "memo_dispatch_memo_idx",
            "memo_id",
        ),
    )
    id: str = Field(primary_key=True)
    organization_id: str = Field(index=True)
    memo_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    dispatched_at: datetime = Field(default_factory=_utcnow)
    outcome_action: str = Field(default="PENDING", index=True)
    bet_link: Optional[str] = Field(default=None)
    bet_link_kind: Optional[str] = Field(default=None)
    acknowledged_by: str = Field(default="")
    acknowledged_at: Optional[datetime] = Field(default=None)
    rationale: str = Field(default="")
    deferred_until: Optional[datetime] = Field(default=None)
    failure_reason: str = Field(default="")
    payload_json: str = Field(default="{}")


class StoredGraphSnapshot(SQLModel, table=True):
    """Append-only snapshot of a knowledge-graph build (prompt 13).

    The graph is a *projection* over the principle / algorithm / memo /
    contradiction tables — those remain authoritative. Snapshots are
    versioned and persisted so the public ``/knowledge-graph`` view can
    serve the latest pre-computed shape at low latency, and so an
    operator can audit how the graph evolved over time.
    """

    __tablename__ = "graph_snapshot"
    __table_args__ = (
        Index(
            "graph_snapshot_org_snapat_idx",
            "organization_id",
            "snapshot_at",
        ),
    )
    id: str = Field(primary_key=True)
    organization_id: str = Field(index=True)
    snapshot_at: datetime = Field(default_factory=_utcnow, index=True)
    version: str = Field(default="kg/v1")
    nodes_json: str = Field(default="[]")
    edges_json: str = Field(default="[]")
    node_count: int = Field(default=0)
    edge_count: int = Field(default=0)
    notes: str = Field(default="")


class StoredGraphEdgeReasoning(SQLModel, table=True):
    """Cached agent reasoning over a graph edge (prompt 13).

    Operators can pre-compute reasoning for the top-N highest-degree
    edges so a public click feels instant. Keyed by (src, dst, kind)
    so the panel can look up a hit in O(1).
    """

    __tablename__ = "graph_edge_reasoning"
    __table_args__ = (
        Index(
            "graph_edge_reasoning_triple_idx",
            "organization_id",
            "src",
            "dst",
            "kind",
        ),
    )
    id: str = Field(primary_key=True)
    organization_id: str = Field(index=True)
    src: str = Field(index=True)
    dst: str = Field(index=True)
    kind: str = Field(index=True)
    payload_json: str = Field(default="{}")
    generated_at: datetime = Field(default_factory=_utcnow)


# ── Round 19 prompt 14: Dialectic live recording ────────────────────────────


class StoredDialecticSession(SQLModel, table=True):
    """A recorded conversation (podcast / meeting). See models.DialecticSession."""

    __tablename__ = "dialectic_session"
    __table_args__ = (
        Index("dialectic_session_org_status_idx", "organization_id", "status"),
        Index("dialectic_session_started_idx", "started_at"),
    )
    id: str = Field(primary_key=True)
    organization_id: str = Field(index=True)
    title: str = Field(default="")
    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: Optional[datetime] = Field(default=None)
    participants_json: str = Field(default="[]")
    audio_path: str = Field(default="")
    transcript_path: str = Field(default="")
    status: str = Field(default="RECORDING")
    visibility: str = Field(default="PRIVATE")
    live_contradictions_detected: int = Field(default=0)
    principles_extracted: int = Field(default=0)
    summary_memo_id: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class StoredDialecticUtterance(SQLModel, table=True):
    """One transcribed speaker-turn. See models.DialecticUtterance."""

    __tablename__ = "dialectic_utterance"
    __table_args__ = (
        Index(
            "dialectic_utterance_session_start_idx",
            "session_id",
            "start_time",
        ),
        Index("dialectic_utterance_speaker_idx", "speaker_id"),
    )
    id: str = Field(primary_key=True)
    session_id: str = Field(index=True)
    speaker_id: str = Field(index=True)
    start_time: float = Field(default=0.0)
    end_time: float = Field(default=0.0)
    text: str = Field(default="")
    extracted_claim_ids_json: str = Field(default="[]")
    derived_principle_ids_json: str = Field(default="[]")
    live_contradiction_flags_json: str = Field(default="[]")
    created_at: datetime = Field(default_factory=_utcnow)


class StoredDialecticContradictionFlag(SQLModel, table=True):
    """Contradiction event fired during live recording.

    See models.DialecticContradictionFlag.
    """

    __tablename__ = "dialectic_contradiction_flag"
    __table_args__ = (
        Index(
            "dialectic_contradiction_flag_utterance_idx",
            "utterance_id",
        ),
        Index(
            "dialectic_contradiction_flag_kind_idx",
            "flag_kind",
        ),
    )
    id: str = Field(primary_key=True)
    utterance_id: str = Field(index=True)
    flag_kind: str = Field(default="INTRA_SESSION")
    prior_utterance_id: Optional[str] = Field(default=None)
    prior_principle_id: Optional[str] = Field(default=None)
    prior_speaker_id: Optional[str] = Field(default=None)
    contradiction_score: float = Field(default=0.0)
    axis: Optional[str] = Field(default=None)
    human_explanation: Optional[str] = Field(default=None)
    detection_method: str = Field(default="")
    acknowledged_at: Optional[datetime] = Field(default=None)
    acknowledged_by: Optional[str] = Field(default=None)
    acknowledgment_note: Optional[str] = Field(default=None)
    detected_at: datetime = Field(default_factory=_utcnow)


# ── Round 19 prompt 15: Polymorphic bet abstraction ─────────────────────────


class StoredBetSpec(SQLModel, table=True):
    """Persisted :class:`noosphere.bets.spec.BetSpec`.

    The kind-specific sub-spec (market / advisory / strategic /
    scientific) is round-tripped through ``payload_json``; the indexed
    columns are the ones the lifecycle ticker and CLI consult at scan
    time. See ``noosphere.bets.spec`` for the canonical shape.
    """

    __tablename__ = "bet_spec"
    __table_args__ = (
        Index("bet_spec_org_kind_status_idx", "organization_id", "kind", "status"),
        Index("bet_spec_horizon_idx", "horizon_at"),
        Index("bet_spec_memo_idx", "created_by_memo_id"),
    )
    id: str = Field(primary_key=True)
    organization_id: str = Field(default="", index=True)
    kind: str = Field(default="MARKET_BET", index=True)
    status: str = Field(default="PROPOSED", index=True)
    proposition: str = Field(default="")
    resolution_criterion: str = Field(default="")
    horizon_at: datetime = Field(default_factory=_utcnow)
    created_by_memo_id: Optional[str] = Field(default=None, index=True)
    originating_algorithm_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    resolved_at: Optional[datetime] = Field(default=None)
    outcome: Optional[str] = Field(default=None)
    outcome_note: Optional[str] = Field(default=None)
    payload_json: str = Field(default="{}")


class StoredBetResolution(SQLModel, table=True):
    """Append-only resolution record (one row per BetSpec resolution)."""

    __tablename__ = "bet_resolution"
    __table_args__ = (
        Index("bet_resolution_spec_idx", "bet_spec_id"),
        Index("bet_resolution_resolved_idx", "resolved_at"),
    )
    id: str = Field(primary_key=True)
    bet_spec_id: str = Field(index=True)
    resolved_at: datetime = Field(default_factory=_utcnow)
    outcome: str = Field(default="UNDETERMINED")
    evidence_note: str = Field(default="")
    resolved_by: str = Field(default="agent")
    pnl_usd: Optional[float] = Field(default=None)
    cost_realized: Optional[float] = Field(default=None)
    accuracy_score: Optional[float] = Field(default=None)
    audience_response: Optional[str] = Field(default=None)
    payload_json: str = Field(default="{}")


def _sqlite_migrate_provenance_columns(engine: Engine) -> None:
    """Backfill the prompt-09 provenance columns on legacy SQLite databases.

    The Alembic migration handles fresh deploys + Postgres; this keeps
    test fixtures and developer databases from breaking on the next boot
    after upgrade. All existing rows default to PROPRIETARY — the
    founder reviews them via the triage flow.
    """
    if not str(engine.url).startswith("sqlite"):
        return
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    targets = {
        "artifact": [
            ("provenance", "VARCHAR NOT NULL DEFAULT 'PROPRIETARY'"),
            ("provenance_rationale", "VARCHAR NOT NULL DEFAULT ''"),
        ],
        "claim": [
            ("provenance", "VARCHAR NOT NULL DEFAULT 'PROPRIETARY'"),
        ],
        "conclusion": [
            ("provenance", "VARCHAR NOT NULL DEFAULT 'PROPRIETARY'"),
        ],
        "logical_algorithm": [
            ("provenance", "VARCHAR NOT NULL DEFAULT 'PROPRIETARY'"),
        ],
    }
    with engine.begin() as conn:
        for table, columns in targets.items():
            if table not in tables:
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for col, spec in columns:
                if col not in existing:
                    conn.execute(
                        text(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {spec}')
                    )


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
            conn.execute(
                text(
                    "ALTER TABLE artifact ADD COLUMN license_status VARCHAR DEFAULT 'unknown'"
                )
            )
        if "literature_connector" not in acols:
            conn.execute(
                text(
                    "ALTER TABLE artifact ADD COLUMN literature_connector VARCHAR DEFAULT ''"
                )
            )


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
            conn.execute(
                text(
                    "ALTER TABLE artifact ADD COLUMN effective_at_inferred BOOLEAN DEFAULT 1"
                )
            )


def _sqlite_migrate_forecast_columns(engine: Engine) -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    insp = inspect(engine)
    tables = insp.get_table_names()
    with engine.begin() as conn:
        if "ForecastPortfolioState" in tables:
            cols = {c["name"] for c in insp.get_columns("ForecastPortfolioState")}
            if "totalResolved" not in cols:
                conn.execute(
                    text(
                        'ALTER TABLE "ForecastPortfolioState" ADD COLUMN "totalResolved" INTEGER NOT NULL DEFAULT 0'
                    )
                )
        if "ForecastResolution" in tables:
            cols = {c["name"] for c in insp.get_columns("ForecastResolution")}
            if "source" not in cols:
                conn.execute(
                    text(
                        'ALTER TABLE "ForecastResolution" ADD COLUMN "source" VARCHAR NOT NULL DEFAULT \'VENUE\''
                    )
                )
            if "sourceUrl" not in cols:
                conn.execute(
                    text('ALTER TABLE "ForecastResolution" ADD COLUMN "sourceUrl" TEXT')
                )
        # Round 19 prompt 15: betSpecId on ForecastBet / EquityPosition.
        for table in ("ForecastBet", "EquityPosition"):
            if table in tables:
                cols = {c["name"] for c in insp.get_columns(table)}
                if "betSpecId" not in cols:
                    conn.execute(
                        text(f'ALTER TABLE "{table}" ADD COLUMN "betSpecId" VARCHAR')
                    )


def _sqlite_migrate_publication_columns(engine: Engine) -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    insp = inspect(engine)
    tables = insp.get_table_names()
    if "PublishedConclusion" not in tables:
        return
    cols = {c["name"] for c in insp.get_columns("PublishedConclusion")}
    with engine.begin() as conn:
        if "kind" not in cols:
            conn.execute(
                text(
                    'ALTER TABLE "PublishedConclusion" ADD COLUMN "kind" VARCHAR NOT NULL DEFAULT \'CONCLUSION\''
                )
            )


def _sqlite_migrate_currents_columns(engine: Engine) -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    insp = inspect(engine)
    tables = insp.get_table_names()
    if "OpinionCitation" not in tables:
        return
    cols = {c["name"] for c in insp.get_columns("OpinionCitation")}
    with engine.begin() as conn:
        if "revokedAt" not in cols:
            conn.execute(
                text('ALTER TABLE "OpinionCitation" ADD COLUMN "revokedAt" DATETIME')
            )


def _sqlite_migrate_algorithm_calibration_columns(engine: Engine) -> None:
    """Backfill the prompt-05 calibration columns on existing SQLite DBs.

    Adds ``weighting_multiplier`` to ``logical_algorithm`` so older
    rows can be read back without breaking. The two new tables
    (``algorithm_calibration_snapshot``, ``algorithm_triage_recommendation``)
    are created by ``SQLModel.metadata.create_all``; this helper is
    only for the additive column.
    """

    if not str(engine.url).startswith("sqlite"):
        return
    insp = inspect(engine)
    tables = insp.get_table_names()
    if "logical_algorithm" not in tables:
        return
    cols = {c["name"] for c in insp.get_columns("logical_algorithm")}
    if "weighting_multiplier" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE logical_algorithm "
                    "ADD COLUMN weighting_multiplier FLOAT DEFAULT 1.0"
                )
            )


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

    with engine.begin() as conn:
        existing_id = conn.execute(
            text("SELECT id FROM embedding_model_version LIMIT 1")
        ).scalar_one_or_none()
        if existing_id is not None:
            return
        conn.execute(
            text(
                """
                INSERT INTO embedding_model_version
                    (id, effective_from, model_name, notes)
                VALUES
                    (:id, :effective_from, :model_name, :notes)
                """
            ),
            {
                "id": "seed-embedding-default",
                "effective_from": datetime(2020, 1, 1, tzinfo=timezone.utc),
                "model_name": get_settings().embedding_model_name,
                "notes": "Auto-seed: replace with dated rows when upgrading encoders.",
            },
        )


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
        engine_url = _psycopg2_compatible_url(url.strip())
        eng = create_engine(
            engine_url,
            connect_args=connect_args,
            **_engine_kwargs_for_url(engine_url),
        )
        SQLModel.metadata.create_all(eng)
        _sqlite_migrate_temporal_columns(eng)
        _sqlite_migrate_literature_columns(eng)
        _sqlite_migrate_currents_columns(eng)
        _sqlite_migrate_forecast_columns(eng)
        _sqlite_migrate_publication_columns(eng)
        _sqlite_migrate_algorithm_calibration_columns(eng)
        _sqlite_migrate_provenance_columns(eng)
        _backfill_artifact_effective_times(eng)
        _seed_embedding_model_versions(eng)
        return cls(eng)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        with Session(self.engine, expire_on_commit=False) as s:
            try:
                yield s
            except Exception:
                s.rollback()
                raise
            # The Session context manager closes the session and returns any
            # checked-out connection to the pool. Do not rollback successful
            # read-only sessions here: SQLAlchemy expires ORM attributes on
            # rollback, and many Store methods intentionally return detached
            # model objects to callers.

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
        # ProvenanceKind enums survive Pydantic serialization as the
        # string value; coerce defensively so callers can pass either.
        prov_value = getattr(a.provenance, "value", a.provenance) or "PROPRIETARY"
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
            provenance=str(prov_value),
            provenance_rationale=a.provenance_rationale or "",
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
            from noosphere.models import ProvenanceKind, coerce_provenance

            prov = coerce_provenance(getattr(r, "provenance", None))
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
                literature_connector=str(
                    getattr(r, "literature_connector", None) or ""
                ),
                provenance=prov,
                provenance_rationale=str(
                    getattr(r, "provenance_rationale", None) or ""
                ),
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
        prov_value = str(getattr(c.provenance, "value", c.provenance) or "PROPRIETARY")
        row = StoredClaim(
            id=c.id,
            payload_json=c.model_dump_json(),
            provenance=prov_value,
        )
        with self.session() as s:
            existing = s.get(StoredClaim, c.id)
            if existing:
                existing.payload_json = row.payload_json
                existing.provenance = prov_value
                s.add(existing)
            else:
                s.add(row)
            s.commit()
        try:
            from noosphere.claim_extractor import run_scaled_coherence_for_claim

            run_scaled_coherence_for_claim(c, self)
        except Exception:
            pass

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
            raise ImportError(
                "NumPy is required for embedding persistence"
            ) from _NUMPY_IMPORT_ERROR
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
            raise ImportError(
                "NumPy is required for embedding persistence"
            ) from _NUMPY_IMPORT_ERROR
        with self.session() as s:
            r = s.get(StoredEmbedding, embedding_id)
            if r is None:
                return None
            arr = np.frombuffer(r.vector, dtype=np.float32)
            return arr.astype(float).tolist()

    def active_embedding_model_name(self, *, as_of: datetime | None = None) -> str:
        """Return the embedding model version active at ``as_of``."""
        from noosphere.config import get_settings

        cutoff = as_of or _utcnow()
        with self.engine.connect() as conn:
            model_name = conn.execute(
                text(
                    """
                    SELECT model_name
                    FROM embedding_model_version
                    WHERE effective_from <= :cutoff
                    ORDER BY effective_from DESC
                    LIMIT 1
                    """
                ),
                {"cutoff": cutoff},
            ).scalar_one_or_none()
            if model_name:
                return str(model_name)
        return get_settings().embedding_model_name

    def has_current_embedding(
        self,
        *,
        source_id: str,
        model_name: str,
        text_sha256: str,
    ) -> bool:
        with self.session() as s:
            row = s.exec(
                select(StoredEmbedding)
                .where(StoredEmbedding.ref_claim_id == source_id)
                .where(StoredEmbedding.model_name == model_name)
                .where(StoredEmbedding.text_sha256 == text_sha256)
            ).first()
            return row is not None

    def queue_embedding_retry(
        self,
        *,
        source_kind: str,
        source_id: str,
        model_name: str,
        text_sha256: str,
        error: str,
    ) -> None:
        retry_id = f"retry_{source_kind}_{source_id}_{model_name}"
        with self.session() as s:
            row = s.get(StoredEmbeddingRetry, retry_id)
            now = _utcnow()
            if row is None:
                row = StoredEmbeddingRetry(
                    id=retry_id,
                    source_kind=source_kind,
                    source_id=source_id,
                    model_name=model_name,
                    text_sha256=text_sha256,
                    attempts=1,
                    last_error=error[:1000],
                    updated_at=now,
                )
            else:
                row.text_sha256 = text_sha256
                row.attempts += 1
                row.last_error = error[:1000]
                row.updated_at = now
            s.add(row)
            s.commit()

    def clear_embedding_retry(
        self,
        *,
        source_kind: str,
        source_id: str,
        model_name: str,
    ) -> None:
        retry_id = f"retry_{source_kind}_{source_id}_{model_name}"
        with self.session() as s:
            row = s.get(StoredEmbeddingRetry, retry_id)
            if row is not None:
                s.delete(row)
                s.commit()

    def list_conclusions_missing_embeddings(
        self,
        *,
        model_name: str,
        limit: int = 1000,
    ) -> list[Conclusion]:
        """Return stored/Prisma conclusions lacking a current-model embedding."""
        import hashlib

        missing: list[Conclusion] = []
        for conclusion in self.list_conclusions():
            text_sha256 = hashlib.sha256(conclusion.text.encode("utf-8")).hexdigest()
            if self.has_current_embedding(
                source_id=conclusion.id,
                model_name=model_name,
                text_sha256=text_sha256,
            ):
                continue
            missing.append(conclusion)
            if len(missing) >= limit:
                break
        return missing

    def count_conclusions_total(self) -> int:
        return len(self.list_conclusions())

    def count_conclusions_missing_embeddings(self, *, model_name: str) -> int:
        import hashlib

        n = 0
        for conclusion in self.list_conclusions():
            text_sha256 = hashlib.sha256(conclusion.text.encode("utf-8")).hexdigest()
            if not self.has_current_embedding(
                source_id=conclusion.id,
                model_name=model_name,
                text_sha256=text_sha256,
            ):
                n += 1
        return n

    def update_prisma_conclusion_embedding_json(
        self,
        conclusion_id: str,
        vector: list[float],
    ) -> None:
        """Mirror the canonical StoredEmbedding vector onto Prisma Conclusion if present."""
        inspector = inspect(self.engine)
        if not inspector.has_table("Conclusion"):
            return
        columns = {column["name"] for column in inspector.get_columns("Conclusion")}
        if "embeddingJson" not in columns:
            return
        payload = json.dumps([float(v) for v in vector], separators=(",", ":"))
        sql = text('UPDATE "Conclusion" SET "embeddingJson" = :payload WHERE id = :id')
        with self.engine.begin() as conn:
            conn.execute(sql, {"payload": payload, "id": conclusion_id})

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

    # --- Contradiction engine (R19/p06) ---
    def put_contradiction_result(
        self,
        *,
        result_id: str,
        principle_a_id: str,
        principle_b_id: str,
        score: float,
        confidence_low: float,
        confidence_high: float,
        verdict: str,
        axis: Optional[str],
        human_explanation: Optional[str],
        detection_method: str,
        detected_at: datetime,
        raw_sparsity: float,
        direction_method: str,
        extras: Optional[dict[str, Any]] = None,
    ) -> None:
        import json as _json

        row = StoredContradictionResult(
            id=result_id,
            principle_a_id=principle_a_id,
            principle_b_id=principle_b_id,
            score=score,
            confidence_low=confidence_low,
            confidence_high=confidence_high,
            verdict=verdict,
            axis=axis,
            human_explanation=human_explanation,
            detection_method=detection_method,
            detected_at=detected_at,
            raw_sparsity=raw_sparsity,
            direction_method=direction_method,
            extras_json=_json.dumps(extras or {}, default=str),
        )
        with self.session() as s:
            existing = s.get(StoredContradictionResult, result_id)
            if existing:
                for k, v in row.model_dump(
                    exclude={"id", "status", "dispute_count", "last_dispute_at"}
                ).items():
                    setattr(existing, k, v)
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_contradiction_result(
        self, result_id: str
    ) -> Optional[StoredContradictionResult]:
        with self.session() as s:
            return s.get(StoredContradictionResult, result_id)

    def list_contradiction_results(
        self,
        *,
        method: Optional[str] = None,
        verdict: Optional[str] = None,
        limit: int = 200,
    ) -> list[StoredContradictionResult]:
        with self.session() as s:
            stmt = select(StoredContradictionResult)
            if method is not None:
                stmt = stmt.where(
                    StoredContradictionResult.detection_method == method
                )
            if verdict is not None:
                stmt = stmt.where(
                    StoredContradictionResult.verdict == verdict
                )
            rows = list(s.exec(stmt).all())
            rows.sort(key=lambda r: r.detected_at, reverse=True)
            return rows[:limit]

    def record_contradiction_dispute(
        self,
        *,
        dispute_id: str,
        contradiction_result_id: str,
        disputed_by: str,
        reason: str,
    ) -> StoredContradictionDispute:
        with self.session() as s:
            target = s.get(
                StoredContradictionResult, contradiction_result_id
            )
            if target is None:
                raise ValueError(
                    f"unknown contradiction_result_id: {contradiction_result_id}"
                )
            dispute = StoredContradictionDispute(
                id=dispute_id,
                contradiction_result_id=contradiction_result_id,
                detection_method=target.detection_method,
                disputed_by=disputed_by,
                reason=reason,
            )
            target.dispute_count = (target.dispute_count or 0) + 1
            target.last_dispute_at = dispute.created_at
            target.status = "disputed"
            s.add(dispute)
            s.add(target)
            s.commit()
            s.refresh(dispute)
            return dispute

    def list_contradiction_disputes(
        self, *, method: Optional[str] = None, limit: int = 200
    ) -> list[StoredContradictionDispute]:
        with self.session() as s:
            stmt = select(StoredContradictionDispute)
            if method is not None:
                stmt = stmt.where(
                    StoredContradictionDispute.detection_method == method
                )
            rows = list(s.exec(stmt).all())
            rows.sort(key=lambda r: r.created_at, reverse=True)
            return rows[:limit]

    # --- Contradiction lifecycle (R19/p19) ---
    def put_contradiction_lifecycle(
        self,
        *,
        lifecycle_id: str,
        contradiction_id: str,
        current_status: str,
        last_transition_at: datetime,
        events_json: str,
        supported_principle_id: Optional[str] = None,
        subsuming_principle_id: Optional[str] = None,
        pending_subsumption_principle_id: Optional[str] = None,
    ) -> None:
        """Upsert one lifecycle row. The events column is append-only by
        contract — callers always pass the full serialized log; we never
        overwrite an existing log with a shorter one (callers that try
        will see a ValueError).
        """

        with self.session() as s:
            existing = s.get(StoredContradictionLifecycle, lifecycle_id)
            if existing is not None:
                # Append-only guard: the new payload must contain at least
                # as many events as what's already on disk.
                try:
                    on_disk = json.loads(existing.events_json or "[]")
                except (TypeError, ValueError):
                    on_disk = []
                try:
                    incoming = json.loads(events_json or "[]")
                except (TypeError, ValueError):
                    incoming = []
                if len(incoming) < len(on_disk):
                    raise ValueError(
                        "contradiction lifecycle events are append-only; "
                        f"refusing shorter log ({len(incoming)} < {len(on_disk)})"
                    )
                existing.current_status = current_status
                existing.last_transition_at = last_transition_at
                existing.events_json = events_json
                existing.supported_principle_id = supported_principle_id
                existing.subsuming_principle_id = subsuming_principle_id
                existing.pending_subsumption_principle_id = (
                    pending_subsumption_principle_id
                )
                s.add(existing)
            else:
                s.add(
                    StoredContradictionLifecycle(
                        id=lifecycle_id,
                        contradiction_id=contradiction_id,
                        current_status=current_status,
                        last_transition_at=last_transition_at,
                        events_json=events_json,
                        supported_principle_id=supported_principle_id,
                        subsuming_principle_id=subsuming_principle_id,
                        pending_subsumption_principle_id=pending_subsumption_principle_id,
                    )
                )
            s.commit()

    def get_contradiction_lifecycle(
        self, contradiction_id: str
    ) -> Optional[StoredContradictionLifecycle]:
        with self.session() as s:
            stmt = select(StoredContradictionLifecycle).where(
                StoredContradictionLifecycle.contradiction_id == contradiction_id
            )
            return s.exec(stmt).first()

    def list_contradiction_lifecycles(
        self,
        *,
        statuses: Optional[Iterable[str]] = None,
        limit: int = 500,
    ) -> list[StoredContradictionLifecycle]:
        with self.session() as s:
            stmt = select(StoredContradictionLifecycle)
            if statuses is not None:
                wanted = list(statuses)
                stmt = stmt.where(
                    StoredContradictionLifecycle.current_status.in_(wanted)  # type: ignore[attr-defined]
                )
            rows = list(s.exec(stmt).all())
            rows.sort(key=lambda r: r.last_transition_at, reverse=True)
            return rows[:limit]

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
        prov_value = str(getattr(c.provenance, "value", c.provenance) or "PROPRIETARY")
        row = StoredConclusion(
            id=c.id,
            payload_json=c.model_dump_json(),
            provenance=prov_value,
        )
        with self.session() as s:
            existing = s.get(StoredConclusion, c.id)
            if existing:
                existing.payload_json = row.payload_json
                existing.provenance = prov_value
                s.add(existing)
            else:
                s.add(row)
            s.commit()
        embedded = False
        try:
            from noosphere.embedding_pipeline import embed_conclusion_with_store

            embedded = embed_conclusion_with_store(self, c)
        except Exception:
            # Embedding is best-effort; the nightly backfill treats a missing
            # current-model embedding as the durable retry queue.
            pass
        if embedded:
            try:
                from noosphere.conclusions import run_scaled_coherence_for_conclusion

                run_scaled_coherence_for_conclusion(c, self)
            except Exception:
                pass

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

    def list_first_person_conclusions(self) -> list[Conclusion]:
        """Return conclusions whose text opens with a first-person pronoun.

        Backs the founder-confirmable re-extraction queue
        (`/extractor/re-extract`). The page UI is what actually drives
        the rewrite — this is the read side that produces the worklist.
        """

        from noosphere.conclusions import is_first_person_conclusion

        return [c for c in self.list_conclusions() if is_first_person_conclusion(c.text)]

    # --- Quantitative formalisations (prompt 63) ---
    def put_quantitative_formalisation(
        self, formalisation: QuantitativeFormalisation
    ) -> None:
        """Insert or replace a quantitative-formalisation row.

        ``status`` and ``principle_id`` are duplicated into indexed
        columns so the triage UI's per-principle and per-status reads
        do not have to scan payload-json.
        """
        formalisation.updated_at = datetime.now()
        status_value = (
            formalisation.status.value
            if hasattr(formalisation.status, "value")
            else formalisation.status
        )
        with self.session() as s:
            existing = s.get(
                StoredQuantitativeFormalisation, formalisation.id
            )
            if existing is not None:
                existing.principle_id = formalisation.principle_id
                existing.status = status_value
                existing.payload_json = formalisation.model_dump_json()
                existing.updated_at = formalisation.updated_at
                s.add(existing)
            else:
                row = StoredQuantitativeFormalisation(
                    id=formalisation.id,
                    principle_id=formalisation.principle_id,
                    status=status_value,
                    payload_json=formalisation.model_dump_json(),
                    created_at=formalisation.created_at,
                    updated_at=formalisation.updated_at,
                )
                s.add(row)
            s.commit()

    def get_quantitative_formalisation(
        self, formalisation_id: str
    ) -> Optional[QuantitativeFormalisation]:
        with self.session() as s:
            row = s.get(StoredQuantitativeFormalisation, formalisation_id)
            if row is None:
                return None
            return QuantitativeFormalisation.model_validate_json(row.payload_json)

    def get_quantitative_formalisations_for_principle(
        self, principle_id: str
    ) -> list[QuantitativeFormalisation]:
        with self.session() as s:
            rows = s.exec(
                select(StoredQuantitativeFormalisation).where(
                    StoredQuantitativeFormalisation.principle_id == principle_id
                )
            ).all()
            out: list[QuantitativeFormalisation] = []
            for r in rows:
                try:
                    out.append(
                        QuantitativeFormalisation.model_validate_json(r.payload_json)
                    )
                except Exception:
                    continue
            return out

    def list_quantitative_formalisations(
        self, *, status: Optional[str] = None
    ) -> list[QuantitativeFormalisation]:
        with self.session() as s:
            stmt = select(StoredQuantitativeFormalisation)
            if status is not None:
                stmt = stmt.where(StoredQuantitativeFormalisation.status == status)
            rows = s.exec(stmt).all()
            out: list[QuantitativeFormalisation] = []
            for r in rows:
                try:
                    out.append(
                        QuantitativeFormalisation.model_validate_json(r.payload_json)
                    )
                except Exception:
                    continue
            return out

    def upsert_quantitative_test_result(
        self, result: QuantitativeTestResult
    ) -> None:
        """Persist a runner pass.

        Idempotent on ``(formalisation_id, run_stamp)``: a second call
        with the same pair overwrites the prior row instead of stacking
        a duplicate. The runner guarantees a unique ``run_stamp`` per
        intended pass, so re-runs at the same stamp are explicit retries.
        """
        status_value = (
            result.status.value
            if hasattr(result.status, "value")
            else result.status
        )
        payload_json = result.model_dump_json()
        with self.session() as s:
            existing = s.exec(
                select(StoredQuantitativeTestResult).where(
                    StoredQuantitativeTestResult.formalisation_id
                    == result.formalisation_id,
                    StoredQuantitativeTestResult.run_stamp == result.run_stamp,
                )
            ).first()
            if existing is not None:
                existing.principle_id = result.principle_id
                existing.status = status_value
                existing.artifacts_path = result.artifacts_path
                existing.payload_json = payload_json
                s.add(existing)
            else:
                row = StoredQuantitativeTestResult(
                    id=result.id,
                    formalisation_id=result.formalisation_id,
                    principle_id=result.principle_id,
                    run_stamp=result.run_stamp,
                    status=status_value,
                    artifacts_path=result.artifacts_path,
                    payload_json=payload_json,
                    created_at=result.created_at,
                )
                s.add(row)
            s.commit()

    def get_latest_quantitative_test_result(
        self, formalisation_id: str
    ) -> Optional[QuantitativeTestResult]:
        with self.session() as s:
            row = s.exec(
                select(StoredQuantitativeTestResult)
                .where(
                    StoredQuantitativeTestResult.formalisation_id
                    == formalisation_id
                )
                .order_by(desc(StoredQuantitativeTestResult.created_at))
                .limit(1)
            ).first()
            if row is None:
                return None
            try:
                return QuantitativeTestResult.model_validate_json(row.payload_json)
            except Exception:
                return None

    def list_quantitative_test_results(
        self,
        *,
        formalisation_id: Optional[str] = None,
        principle_id: Optional[str] = None,
        limit: int = 200,
    ) -> list[QuantitativeTestResult]:
        with self.session() as s:
            stmt = select(StoredQuantitativeTestResult)
            if formalisation_id is not None:
                stmt = stmt.where(
                    StoredQuantitativeTestResult.formalisation_id == formalisation_id
                )
            if principle_id is not None:
                stmt = stmt.where(
                    StoredQuantitativeTestResult.principle_id == principle_id
                )
            stmt = stmt.order_by(
                desc(StoredQuantitativeTestResult.created_at)
            ).limit(limit)
            rows = s.exec(stmt).all()
            out: list[QuantitativeTestResult] = []
            for r in rows:
                try:
                    out.append(
                        QuantitativeTestResult.model_validate_json(r.payload_json)
                    )
                except Exception:
                    continue
            return out

    # ── Logical Algorithm layer (prompt 01, Round 19) ───────────────────────

    @staticmethod
    def _algorithm_status_value(status: AlgorithmStatus | str) -> str:
        return status.value if hasattr(status, "value") else str(status)

    def put_algorithm(
        self,
        algorithm: LogicalAlgorithm,
        *,
        revoked_principle_ids: Iterable[str] | None = None,
    ) -> None:
        """Insert or replace a LogicalAlgorithm row.

        Runs the full validator stack — inputs, output schema,
        reasoning chain, trigger predicate — and refuses to persist a
        promotion to ACTIVE while any source principle is revoked.
        ``revoked_principle_ids`` defaults to the empty set; callers
        outside tests should pass the live set fetched from the
        Codex ``Principle`` table.
        """

        validate_inputs(algorithm.inputs)
        validate_output_schema(algorithm.output)
        validate_reasoning_chain(
            algorithm.reasoning_chain,
            source_principle_ids=algorithm.source_principle_ids,
        )
        validate_trigger_predicate(
            algorithm.trigger_predicate,
            input_names=[inp.name for inp in algorithm.inputs],
        )

        algorithm.updated_at = datetime.now()
        status_value = self._algorithm_status_value(algorithm.status)

        with self.session() as s:
            existing = s.get(StoredLogicalAlgorithm, algorithm.id)
            previous_status = existing.status if existing is not None else None
            validate_promotion_to_active(
                current_status=previous_status or AlgorithmStatus.DRAFT,
                new_status=status_value,
                source_principle_ids=algorithm.source_principle_ids,
                revoked_principle_ids=revoked_principle_ids or (),
            )
            payload_json = algorithm.model_dump_json()
            multiplier = max(
                0.0, min(2.0, float(getattr(algorithm, "weighting_multiplier", 1.0)))
            )
            prov_value = str(
                getattr(algorithm.provenance, "value", algorithm.provenance)
                or "PROPRIETARY"
            )
            if existing is not None:
                existing.organization_id = algorithm.organization_id
                existing.name = algorithm.name
                existing.status = status_value
                existing.payload_json = payload_json
                existing.weighting_multiplier = multiplier
                existing.provenance = prov_value
                existing.updated_at = algorithm.updated_at
                existing.last_invoked_at = algorithm.last_invoked_at
                s.add(existing)
            else:
                row = StoredLogicalAlgorithm(
                    id=algorithm.id,
                    organization_id=algorithm.organization_id,
                    name=algorithm.name,
                    status=status_value,
                    payload_json=payload_json,
                    weighting_multiplier=multiplier,
                    provenance=prov_value,
                    created_at=algorithm.created_at,
                    updated_at=algorithm.updated_at,
                    last_invoked_at=algorithm.last_invoked_at,
                )
                s.add(row)
            try:
                s.commit()
            except IntegrityError as exc:
                s.rollback()
                raise AlgorithmValidationError(
                    f"LogicalAlgorithm ({algorithm.organization_id!r}, "
                    f"{algorithm.name!r}) violates compound unique key"
                ) from exc

    def get_algorithm(self, algorithm_id: str) -> Optional[LogicalAlgorithm]:
        with self.session() as s:
            row = s.get(StoredLogicalAlgorithm, algorithm_id)
            if row is None:
                return None
            try:
                return LogicalAlgorithm.model_validate_json(row.payload_json)
            except Exception:
                return None

    def list_algorithms_for_org(
        self,
        organization_id: str,
        *,
        status: Optional[AlgorithmStatus | str] = None,
    ) -> list[LogicalAlgorithm]:
        with self.session() as s:
            stmt = select(StoredLogicalAlgorithm).where(
                StoredLogicalAlgorithm.organization_id == organization_id
            )
            if status is not None:
                stmt = stmt.where(
                    StoredLogicalAlgorithm.status
                    == self._algorithm_status_value(status)
                )
            stmt = stmt.order_by(asc(StoredLogicalAlgorithm.created_at))
            rows = s.exec(stmt).all()
            out: list[LogicalAlgorithm] = []
            for r in rows:
                try:
                    out.append(
                        LogicalAlgorithm.model_validate_json(r.payload_json)
                    )
                except Exception:
                    continue
            return out

    def list_active_algorithms(
        self, *, organization_id: Optional[str] = None
    ) -> list[LogicalAlgorithm]:
        with self.session() as s:
            stmt = select(StoredLogicalAlgorithm).where(
                StoredLogicalAlgorithm.status == AlgorithmStatus.ACTIVE.value
            )
            if organization_id is not None:
                stmt = stmt.where(
                    StoredLogicalAlgorithm.organization_id == organization_id
                )
            stmt = stmt.order_by(asc(StoredLogicalAlgorithm.created_at))
            rows = s.exec(stmt).all()
            out: list[LogicalAlgorithm] = []
            for r in rows:
                try:
                    out.append(
                        LogicalAlgorithm.model_validate_json(r.payload_json)
                    )
                except Exception:
                    continue
            return out

    def set_algorithm_status(
        self,
        algorithm_id: str,
        new_status: AlgorithmStatus | str,
        *,
        revoked_principle_ids: Iterable[str] | None = None,
        retired_reason: Optional[str] = None,
    ) -> LogicalAlgorithm:
        """Promote / pause / retire an algorithm.

        Enforces both the generic status-transition rules and the
        revoked-principle guard. ``retired_reason`` is required when
        transitioning to RETIRED — the founder needs to capture *why*
        for the audit log.
        """

        new_value = self._algorithm_status_value(new_status)
        with self.session() as s:
            row = s.get(StoredLogicalAlgorithm, algorithm_id)
            if row is None:
                raise AlgorithmValidationError(
                    f"LogicalAlgorithm {algorithm_id!r} not found"
                )
            validate_status_transition(
                current_status=row.status, new_status=new_value
            )
            try:
                algorithm = LogicalAlgorithm.model_validate_json(row.payload_json)
            except Exception as exc:
                raise AlgorithmValidationError(
                    f"LogicalAlgorithm {algorithm_id!r} payload is malformed"
                ) from exc
            validate_promotion_to_active(
                current_status=row.status,
                new_status=new_value,
                source_principle_ids=algorithm.source_principle_ids,
                revoked_principle_ids=revoked_principle_ids or (),
            )
            if new_value == AlgorithmStatus.RETIRED.value:
                if not (retired_reason or "").strip():
                    raise AlgorithmValidationError(
                        "Retiring an algorithm requires a retired_reason"
                    )
                algorithm.retired_reason = retired_reason
            algorithm.status = new_value
            algorithm.updated_at = datetime.now()
            row.status = new_value
            row.payload_json = algorithm.model_dump_json()
            row.updated_at = algorithm.updated_at
            s.add(row)
            s.commit()
            return algorithm

    def put_invocation(self, invocation: AlgorithmInvocation) -> None:
        """Persist an AlgorithmInvocation and bump the algorithm's lastInvokedAt."""

        payload_json = invocation.model_dump_json()
        correctness_value = (
            invocation.correctness.value
            if hasattr(invocation.correctness, "value")
            else invocation.correctness
        )
        with self.session() as s:
            existing = s.get(StoredAlgorithmInvocation, invocation.id)
            if existing is not None:
                existing.algorithm_id = invocation.algorithm_id
                existing.organization_id = invocation.organization_id
                existing.invoked_at = invocation.invoked_at
                existing.resolved_at = invocation.resolved_at
                existing.correctness = correctness_value
                existing.payload_json = payload_json
                s.add(existing)
            else:
                row = StoredAlgorithmInvocation(
                    id=invocation.id,
                    algorithm_id=invocation.algorithm_id,
                    organization_id=invocation.organization_id,
                    invoked_at=invocation.invoked_at,
                    resolved_at=invocation.resolved_at,
                    correctness=correctness_value,
                    payload_json=payload_json,
                )
                s.add(row)
            # Bump lastInvokedAt on the parent algorithm so the surface
            # can sort "recently fired" without scanning the invocation
            # table — the algorithm row carries a denormalised pointer.
            algo_row = s.get(StoredLogicalAlgorithm, invocation.algorithm_id)
            if algo_row is not None:
                if (
                    algo_row.last_invoked_at is None
                    or invocation.invoked_at > algo_row.last_invoked_at
                ):
                    algo_row.last_invoked_at = invocation.invoked_at
                    try:
                        algorithm = LogicalAlgorithm.model_validate_json(
                            algo_row.payload_json
                        )
                        algorithm.last_invoked_at = invocation.invoked_at
                        algo_row.payload_json = algorithm.model_dump_json()
                    except Exception:
                        pass
                    s.add(algo_row)
            s.commit()

    def get_invocation(
        self, invocation_id: str
    ) -> Optional[AlgorithmInvocation]:
        with self.session() as s:
            row = s.get(StoredAlgorithmInvocation, invocation_id)
            if row is None:
                return None
            try:
                return AlgorithmInvocation.model_validate_json(row.payload_json)
            except Exception:
                return None

    def list_invocations_for_algorithm(
        self,
        algorithm_id: str,
        *,
        limit: int = 200,
    ) -> list[AlgorithmInvocation]:
        with self.session() as s:
            stmt = (
                select(StoredAlgorithmInvocation)
                .where(StoredAlgorithmInvocation.algorithm_id == algorithm_id)
                .order_by(desc(StoredAlgorithmInvocation.invoked_at))
                .limit(limit)
            )
            rows = s.exec(stmt).all()
            out: list[AlgorithmInvocation] = []
            for r in rows:
                try:
                    out.append(
                        AlgorithmInvocation.model_validate_json(r.payload_json)
                    )
                except Exception:
                    continue
            return out

    def list_unresolved_invocations(
        self,
        *,
        organization_id: Optional[str] = None,
        limit: int = 200,
    ) -> list[AlgorithmInvocation]:
        with self.session() as s:
            stmt = select(StoredAlgorithmInvocation).where(
                StoredAlgorithmInvocation.resolved_at.is_(None)
            )
            if organization_id is not None:
                stmt = stmt.where(
                    StoredAlgorithmInvocation.organization_id == organization_id
                )
            stmt = stmt.order_by(
                asc(StoredAlgorithmInvocation.invoked_at)
            ).limit(limit)
            rows = s.exec(stmt).all()
            out: list[AlgorithmInvocation] = []
            for r in rows:
                try:
                    out.append(
                        AlgorithmInvocation.model_validate_json(r.payload_json)
                    )
                except Exception:
                    continue
            return out

    def set_invocation_resolution(
        self,
        invocation_id: str,
        *,
        actual_outcome: dict[str, Any],
        correctness: AlgorithmCorrectness | str,
        brier_equivalent: Optional[float] = None,
        resolved_at: Optional[datetime] = None,
    ) -> AlgorithmInvocation:
        """Record reality's verdict on a previous invocation."""

        correctness_value = (
            correctness.value
            if hasattr(correctness, "value")
            else str(correctness)
        )
        with self.session() as s:
            row = s.get(StoredAlgorithmInvocation, invocation_id)
            if row is None:
                raise AlgorithmValidationError(
                    f"AlgorithmInvocation {invocation_id!r} not found"
                )
            try:
                invocation = AlgorithmInvocation.model_validate_json(
                    row.payload_json
                )
            except Exception as exc:
                raise AlgorithmValidationError(
                    f"AlgorithmInvocation {invocation_id!r} payload is malformed"
                ) from exc
            resolved_dt = resolved_at or datetime.now()
            invocation.resolved_at = resolved_dt
            invocation.actual_outcome = actual_outcome
            invocation.correctness = correctness_value
            invocation.brier_equivalent = brier_equivalent
            row.resolved_at = resolved_dt
            row.correctness = correctness_value
            row.payload_json = invocation.model_dump_json()
            s.add(row)
            s.commit()
            return invocation

    def put_input_observation(
        self, observation: AlgorithmInputObservation
    ) -> None:
        value_json = json.dumps(observation.value, default=str)
        with self.session() as s:
            existing = s.get(StoredAlgorithmInputObservation, observation.id)
            if existing is not None:
                existing.invocation_id = observation.invocation_id
                existing.input_name = observation.input_name
                existing.value_json = value_json
                existing.observed_at = observation.observed_at
                existing.source_artifact_id = observation.source_artifact_id
                existing.source_url = observation.source_url
                s.add(existing)
            else:
                row = StoredAlgorithmInputObservation(
                    id=observation.id,
                    invocation_id=observation.invocation_id,
                    input_name=observation.input_name,
                    value_json=value_json,
                    observed_at=observation.observed_at,
                    source_artifact_id=observation.source_artifact_id,
                    source_url=observation.source_url,
                )
                s.add(row)
            s.commit()

    def list_observations_for_invocation(
        self, invocation_id: str
    ) -> list[AlgorithmInputObservation]:
        with self.session() as s:
            stmt = (
                select(StoredAlgorithmInputObservation)
                .where(
                    StoredAlgorithmInputObservation.invocation_id
                    == invocation_id
                )
                .order_by(asc(StoredAlgorithmInputObservation.observed_at))
            )
            rows = s.exec(stmt).all()
            out: list[AlgorithmInputObservation] = []
            for r in rows:
                try:
                    value = json.loads(r.value_json) if r.value_json else None
                except json.JSONDecodeError:
                    value = None
                out.append(
                    AlgorithmInputObservation(
                        id=r.id,
                        invocation_id=r.invocation_id,
                        input_name=r.input_name,
                        value=value,
                        observed_at=r.observed_at,
                        source_artifact_id=r.source_artifact_id,
                        source_url=r.source_url,
                    )
                )
            return out

    # ── Synthesizer (prompt 10, Round 19) ────────────────────────────────────

    def put_synthesizer_task(self, task: SynthesizerTask) -> None:
        """Upsert one synthesis task on the queue."""

        payload_json = task.model_dump_json()
        with self.session() as s:
            existing = s.get(StoredSynthesizerTask, task.id)
            status = (
                task.status.value
                if hasattr(task.status, "value")
                else str(task.status)
            )
            trigger = (
                task.trigger.value
                if hasattr(task.trigger, "value")
                else str(task.trigger)
            )
            if existing is not None:
                existing.organization_id = task.organization_id
                existing.trigger = trigger
                existing.status = status
                existing.enqueued_at = task.enqueued_at
                existing.started_at = task.started_at
                existing.finished_at = task.finished_at
                existing.invocation_id = task.invocation_id
                existing.current_event_id = task.current_event_id
                existing.memo_id = task.memo_id
                existing.outcome = task.outcome
                existing.payload_json = payload_json
                s.add(existing)
            else:
                s.add(
                    StoredSynthesizerTask(
                        id=task.id,
                        organization_id=task.organization_id,
                        trigger=trigger,
                        status=status,
                        enqueued_at=task.enqueued_at,
                        started_at=task.started_at,
                        finished_at=task.finished_at,
                        invocation_id=task.invocation_id,
                        current_event_id=task.current_event_id,
                        memo_id=task.memo_id,
                        outcome=task.outcome,
                        payload_json=payload_json,
                    )
                )
            s.commit()

    def list_pending_synthesizer_tasks(
        self,
        *,
        organization_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[SynthesizerTask]:
        """Return PENDING synthesis tasks ordered by enqueued_at ASC."""

        with self.session() as s:
            stmt = select(StoredSynthesizerTask).where(
                StoredSynthesizerTask.status == "PENDING"
            )
            if organization_id is not None:
                stmt = stmt.where(
                    StoredSynthesizerTask.organization_id == organization_id
                )
            stmt = stmt.order_by(asc(StoredSynthesizerTask.enqueued_at)).limit(limit)
            rows = s.exec(stmt).all()
            out: list[SynthesizerTask] = []
            for row in rows:
                try:
                    out.append(SynthesizerTask.model_validate_json(row.payload_json))
                except Exception:
                    continue
            return out

    def put_synthesizer_memo(
        self,
        memo: Any,
    ) -> None:
        """Persist a synthesizer memo. Accepts a :class:`SynthesizerMemo`
        or a plain mapping with ``id``, ``organization_id``, ``question``,
        and a ``conclusion`` dict.
        """

        if isinstance(memo, SynthesizerMemo):
            data = memo
        else:
            payload = dict(memo)
            data = SynthesizerMemo(
                id=str(payload["id"]),
                organization_id=str(payload.get("organization_id") or ""),
                question=str(payload.get("question") or ""),
                conclusion_json=dict(payload.get("conclusion") or {}),
                synthesizer_version=str(
                    payload.get("synthesizer_version") or "synthesizer/v1"
                ),
            )
        row_payload = data.model_dump_json()
        with self.session() as s:
            existing = s.get(StoredSynthesizerMemo, data.id)
            if existing is not None:
                existing.organization_id = data.organization_id
                existing.created_at = data.created_at
                existing.synthesizer_version = data.synthesizer_version
                existing.question = data.question
                existing.payload_json = row_payload
                s.add(existing)
            else:
                s.add(
                    StoredSynthesizerMemo(
                        id=data.id,
                        organization_id=data.organization_id,
                        created_at=data.created_at,
                        synthesizer_version=data.synthesizer_version,
                        question=data.question,
                        payload_json=row_payload,
                    )
                )
            s.commit()

    def get_synthesizer_memo(self, memo_id: str) -> Optional[SynthesizerMemo]:
        with self.session() as s:
            row = s.get(StoredSynthesizerMemo, memo_id)
            if row is None:
                return None
            try:
                return SynthesizerMemo.model_validate_json(row.payload_json)
            except Exception:
                return None

    def list_synthesizer_memos(
        self,
        *,
        organization_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[SynthesizerMemo]:
        with self.session() as s:
            stmt = select(StoredSynthesizerMemo)
            if organization_id is not None:
                stmt = stmt.where(
                    StoredSynthesizerMemo.organization_id == organization_id
                )
            stmt = stmt.order_by(desc(StoredSynthesizerMemo.created_at)).limit(limit)
            rows = s.exec(stmt).all()
            out: list[SynthesizerMemo] = []
            for row in rows:
                try:
                    out.append(
                        SynthesizerMemo.model_validate_json(row.payload_json)
                    )
                except Exception:
                    continue
            return out

    # ── Investment memos (prompt 11, Round 19) ──────────────────────────────

    def put_investment_memo(self, memo: InvestmentMemo) -> InvestmentMemo:
        """Persist (insert or update) an :class:`InvestmentMemo` row."""

        memo.updated_at = _utcnow()
        payload = memo.model_dump_json()
        with self.session() as s:
            existing = s.get(StoredInvestmentMemo, memo.id)
            if existing is not None:
                existing.organization_id = memo.organization_id
                existing.synthesizer_result_id = memo.synthesizer_result_id
                existing.title = memo.title
                existing.slug = memo.slug
                existing.status = (
                    memo.status.value
                    if isinstance(memo.status, MemoStatus)
                    else str(memo.status)
                )
                existing.addressee = memo.addressee
                existing.question_type = (
                    memo.question_type.value
                    if hasattr(memo.question_type, "value")
                    else str(memo.question_type)
                )
                existing.md_path = memo.md_path
                existing.pdf_path = memo.pdf_path
                existing.updated_at = memo.updated_at
                existing.sent_at = memo.sent_at
                existing.acknowledged_at = memo.acknowledged_at
                existing.published_at = memo.published_at
                existing.archived_at = memo.archived_at
                existing.synthesizer_version = memo.synthesizer_version
                existing.payload_json = payload
                s.add(existing)
            else:
                s.add(
                    StoredInvestmentMemo(
                        id=memo.id,
                        organization_id=memo.organization_id,
                        synthesizer_result_id=memo.synthesizer_result_id,
                        title=memo.title,
                        slug=memo.slug,
                        status=(
                            memo.status.value
                            if isinstance(memo.status, MemoStatus)
                            else str(memo.status)
                        ),
                        addressee=memo.addressee,
                        question_type=(
                            memo.question_type.value
                            if hasattr(memo.question_type, "value")
                            else str(memo.question_type)
                        ),
                        md_path=memo.md_path,
                        pdf_path=memo.pdf_path,
                        created_at=memo.created_at,
                        updated_at=memo.updated_at,
                        sent_at=memo.sent_at,
                        acknowledged_at=memo.acknowledged_at,
                        published_at=memo.published_at,
                        archived_at=memo.archived_at,
                        synthesizer_version=memo.synthesizer_version,
                        payload_json=payload,
                    )
                )
            s.commit()
        return memo

    def get_investment_memo(self, memo_id: str) -> Optional[InvestmentMemo]:
        with self.session() as s:
            row = s.get(StoredInvestmentMemo, memo_id)
            if row is None:
                return None
            try:
                return InvestmentMemo.model_validate_json(row.payload_json)
            except Exception:
                return None

    def get_investment_memo_by_slug(self, slug: str) -> Optional[InvestmentMemo]:
        with self.session() as s:
            row = s.exec(
                select(StoredInvestmentMemo).where(
                    StoredInvestmentMemo.slug == slug
                )
            ).first()
            if row is None:
                return None
            try:
                return InvestmentMemo.model_validate_json(row.payload_json)
            except Exception:
                return None

    def list_investment_memos(
        self,
        *,
        organization_id: Optional[str] = None,
        status: Optional[MemoStatus] = None,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> list[InvestmentMemo]:
        with self.session() as s:
            stmt = select(StoredInvestmentMemo)
            if organization_id is not None:
                stmt = stmt.where(
                    StoredInvestmentMemo.organization_id == organization_id
                )
            if status is not None:
                value = (
                    status.value
                    if isinstance(status, MemoStatus)
                    else str(status)
                )
                stmt = stmt.where(StoredInvestmentMemo.status == value)
            if since is not None:
                stmt = stmt.where(StoredInvestmentMemo.created_at >= since)
            stmt = stmt.order_by(
                desc(StoredInvestmentMemo.created_at)
            ).limit(limit)
            rows = s.exec(stmt).all()
            out: list[InvestmentMemo] = []
            for row in rows:
                try:
                    out.append(
                        InvestmentMemo.model_validate_json(row.payload_json)
                    )
                except Exception:
                    continue
            return out

    def update_investment_memo_status(
        self,
        memo_id: str,
        status: MemoStatus,
        *,
        addressee: Optional[str] = None,
    ) -> Optional[InvestmentMemo]:
        """Transition a memo's lifecycle. Stamps the relevant timestamp.

        Lifecycle transitions are intentionally permissive — the
        operator surface enforces business rules (e.g. DRAFT → SENT
        requires an addressee). This helper only stamps timestamps.
        """

        memo = self.get_investment_memo(memo_id)
        if memo is None:
            return None
        memo.status = status
        now = _utcnow()
        if status == MemoStatus.SENT:
            memo.sent_at = now
        elif status == MemoStatus.PUBLIC:
            memo.published_at = now
        elif status == MemoStatus.ARCHIVED:
            memo.archived_at = now
        if addressee is not None:
            memo.addressee = addressee
        return self.put_investment_memo(memo)

    # ── Portfolio agents + memo dispatches (prompt 12, Round 19) ───────────

    def put_portfolio_agent(self, agent: PortfolioAgent) -> PortfolioAgent:
        """Persist (insert or update) a :class:`PortfolioAgent`."""

        agent.updated_at = _utcnow()
        payload = agent.model_dump_json()
        kind_value = (
            agent.kind.value
            if isinstance(agent.kind, PortfolioAgentKind)
            else str(agent.kind)
        )
        status_value = (
            agent.status.value
            if isinstance(agent.status, PortfolioAgentStatus)
            else str(agent.status)
        )
        with self.session() as s:
            existing = s.get(StoredPortfolioAgent, agent.id)
            if existing is not None:
                existing.organization_id = agent.organization_id
                existing.name = agent.name
                existing.kind = kind_value
                existing.status = status_value
                existing.default_bet_ceiling_usd = float(
                    agent.default_bet_ceiling_usd
                )
                existing.updated_at = agent.updated_at
                existing.payload_json = payload
                s.add(existing)
            else:
                s.add(
                    StoredPortfolioAgent(
                        id=agent.id,
                        organization_id=agent.organization_id,
                        name=agent.name,
                        kind=kind_value,
                        status=status_value,
                        default_bet_ceiling_usd=float(
                            agent.default_bet_ceiling_usd
                        ),
                        created_at=agent.created_at,
                        updated_at=agent.updated_at,
                        payload_json=payload,
                    )
                )
            s.commit()
        return agent

    def get_portfolio_agent(self, agent_id: str) -> Optional[PortfolioAgent]:
        with self.session() as s:
            row = s.get(StoredPortfolioAgent, agent_id)
            if row is None:
                return None
            try:
                return PortfolioAgent.model_validate_json(row.payload_json)
            except Exception:
                return None

    def list_portfolio_agents(
        self,
        *,
        organization_id: Optional[str] = None,
        status: Optional[PortfolioAgentStatus] = None,
        limit: int = 200,
    ) -> list[PortfolioAgent]:
        with self.session() as s:
            stmt = select(StoredPortfolioAgent)
            if organization_id is not None:
                stmt = stmt.where(
                    StoredPortfolioAgent.organization_id == organization_id
                )
            if status is not None:
                value = (
                    status.value
                    if isinstance(status, PortfolioAgentStatus)
                    else str(status)
                )
                stmt = stmt.where(StoredPortfolioAgent.status == value)
            stmt = stmt.order_by(
                desc(StoredPortfolioAgent.created_at)
            ).limit(limit)
            rows = s.exec(stmt).all()
            out: list[PortfolioAgent] = []
            for row in rows:
                try:
                    out.append(
                        PortfolioAgent.model_validate_json(row.payload_json)
                    )
                except Exception:
                    continue
            return out

    def put_memo_dispatch(self, dispatch: MemoDispatch) -> MemoDispatch:
        """Persist (insert or update) a :class:`MemoDispatch`."""

        payload = dispatch.model_dump_json()
        outcome_value = (
            dispatch.outcome_action.value
            if isinstance(dispatch.outcome_action, MemoDispatchOutcome)
            else str(dispatch.outcome_action)
        )
        bet_link_kind_value = None
        if dispatch.bet_link_kind is not None:
            bet_link_kind_value = (
                dispatch.bet_link_kind.value
                if isinstance(dispatch.bet_link_kind, MemoDispatchBetKind)
                else str(dispatch.bet_link_kind)
            )
        with self.session() as s:
            existing = s.get(StoredMemoDispatch, dispatch.id)
            if existing is not None:
                existing.organization_id = dispatch.organization_id
                existing.memo_id = dispatch.memo_id
                existing.agent_id = dispatch.agent_id
                existing.dispatched_at = dispatch.dispatched_at
                existing.outcome_action = outcome_value
                existing.bet_link = dispatch.bet_link
                existing.bet_link_kind = bet_link_kind_value
                existing.acknowledged_by = dispatch.acknowledged_by
                existing.acknowledged_at = dispatch.acknowledged_at
                existing.rationale = dispatch.rationale
                existing.deferred_until = dispatch.deferred_until
                existing.failure_reason = dispatch.failure_reason
                existing.payload_json = payload
                s.add(existing)
            else:
                s.add(
                    StoredMemoDispatch(
                        id=dispatch.id,
                        organization_id=dispatch.organization_id,
                        memo_id=dispatch.memo_id,
                        agent_id=dispatch.agent_id,
                        dispatched_at=dispatch.dispatched_at,
                        outcome_action=outcome_value,
                        bet_link=dispatch.bet_link,
                        bet_link_kind=bet_link_kind_value,
                        acknowledged_by=dispatch.acknowledged_by,
                        acknowledged_at=dispatch.acknowledged_at,
                        rationale=dispatch.rationale,
                        deferred_until=dispatch.deferred_until,
                        failure_reason=dispatch.failure_reason,
                        payload_json=payload,
                    )
                )
            s.commit()
        return dispatch

    def get_memo_dispatch(self, dispatch_id: str) -> Optional[MemoDispatch]:
        with self.session() as s:
            row = s.get(StoredMemoDispatch, dispatch_id)
            if row is None:
                return None
            try:
                return MemoDispatch.model_validate_json(row.payload_json)
            except Exception:
                return None

    def list_memo_dispatches(
        self,
        *,
        organization_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        memo_id: Optional[str] = None,
        outcome: Optional[MemoDispatchOutcome] = None,
        limit: int = 200,
    ) -> list[MemoDispatch]:
        with self.session() as s:
            stmt = select(StoredMemoDispatch)
            if organization_id is not None:
                stmt = stmt.where(
                    StoredMemoDispatch.organization_id == organization_id
                )
            if agent_id is not None:
                stmt = stmt.where(StoredMemoDispatch.agent_id == agent_id)
            if memo_id is not None:
                stmt = stmt.where(StoredMemoDispatch.memo_id == memo_id)
            if outcome is not None:
                value = (
                    outcome.value
                    if isinstance(outcome, MemoDispatchOutcome)
                    else str(outcome)
                )
                stmt = stmt.where(StoredMemoDispatch.outcome_action == value)
            stmt = stmt.order_by(
                desc(StoredMemoDispatch.dispatched_at)
            ).limit(limit)
            rows = s.exec(stmt).all()
            out: list[MemoDispatch] = []
            for row in rows:
                try:
                    out.append(
                        MemoDispatch.model_validate_json(row.payload_json)
                    )
                except Exception:
                    continue
            return out

    # ── Algorithm calibration loop (prompt 05, Round 19) ────────────────────

    def get_algorithm_weighting_multiplier(self, algorithm_id: str) -> float:
        """Return the persisted weighting_multiplier for the algorithm."""

        with self.session() as s:
            row = s.get(StoredLogicalAlgorithm, algorithm_id)
            if row is None:
                return 1.0
            return float(row.weighting_multiplier or 1.0)

    def set_algorithm_weighting_multiplier(
        self, algorithm_id: str, multiplier: float
    ) -> LogicalAlgorithm:
        """Update an algorithm's weighting_multiplier, bounded to [0, 2]."""

        bounded = max(0.0, min(2.0, float(multiplier)))
        with self.session() as s:
            row = s.get(StoredLogicalAlgorithm, algorithm_id)
            if row is None:
                raise AlgorithmValidationError(
                    f"LogicalAlgorithm {algorithm_id!r} not found"
                )
            try:
                algorithm = LogicalAlgorithm.model_validate_json(row.payload_json)
            except Exception as exc:
                raise AlgorithmValidationError(
                    f"LogicalAlgorithm {algorithm_id!r} payload is malformed"
                ) from exc
            algorithm.weighting_multiplier = bounded
            algorithm.updated_at = datetime.now()
            row.weighting_multiplier = bounded
            row.payload_json = algorithm.model_dump_json()
            row.updated_at = algorithm.updated_at
            s.add(row)
            s.commit()
            return algorithm

    def put_calibration_snapshot(
        self, snapshot: AlgorithmCalibrationSnapshot
    ) -> AlgorithmCalibrationSnapshot:
        """Persist an append-only calibration snapshot.

        Re-running calibration produces a NEW row; existing snapshots
        are never overwritten. The id field is preserved if the caller
        supplied one (deterministic tests), otherwise the model's
        default ``uuid4`` is used.
        """

        with self.session() as s:
            row = StoredAlgorithmCalibrationSnapshot(
                id=snapshot.id,
                algorithm_id=snapshot.algorithm_id,
                organization_id=snapshot.organization_id,
                snapshot_at=snapshot.snapshot_at,
                total_invocations=snapshot.total_invocations,
                resolved_invocations=snapshot.resolved_invocations,
                accuracy=snapshot.accuracy,
                mean_brier=snapshot.mean_brier,
                mean_horizon_error=snapshot.mean_horizon_error,
                directional_accuracy=snapshot.directional_accuracy,
                confidence_calibration_drift=snapshot.confidence_calibration_drift,
                last_30d_accuracy=snapshot.last_30d_accuracy,
                last_30d_resolved=snapshot.last_30d_resolved,
                probabilistic_resolved=snapshot.probabilistic_resolved,
                directional_resolved=snapshot.directional_resolved,
                confidence_band_resolved=snapshot.confidence_band_resolved,
            )
            s.add(row)
            s.commit()
            return snapshot

    def list_calibration_snapshots(
        self, algorithm_id: str, *, limit: int = 200
    ) -> list[AlgorithmCalibrationSnapshot]:
        """Time-series of snapshots for an algorithm, newest first."""

        with self.session() as s:
            stmt = (
                select(StoredAlgorithmCalibrationSnapshot)
                .where(
                    StoredAlgorithmCalibrationSnapshot.algorithm_id
                    == algorithm_id
                )
                .order_by(desc(StoredAlgorithmCalibrationSnapshot.snapshot_at))
                .limit(limit)
            )
            rows = s.exec(stmt).all()
            return [
                AlgorithmCalibrationSnapshot(
                    id=r.id,
                    algorithm_id=r.algorithm_id,
                    organization_id=r.organization_id,
                    snapshot_at=r.snapshot_at,
                    total_invocations=r.total_invocations,
                    resolved_invocations=r.resolved_invocations,
                    accuracy=r.accuracy,
                    mean_brier=r.mean_brier,
                    mean_horizon_error=r.mean_horizon_error,
                    directional_accuracy=r.directional_accuracy,
                    confidence_calibration_drift=r.confidence_calibration_drift,
                    last_30d_accuracy=r.last_30d_accuracy,
                    last_30d_resolved=r.last_30d_resolved,
                    probabilistic_resolved=r.probabilistic_resolved,
                    directional_resolved=r.directional_resolved,
                    confidence_band_resolved=r.confidence_band_resolved,
                )
                for r in rows
            ]

    def latest_calibration_snapshot(
        self, algorithm_id: str
    ) -> Optional[AlgorithmCalibrationSnapshot]:
        rows = self.list_calibration_snapshots(algorithm_id, limit=1)
        return rows[0] if rows else None

    def put_triage_recommendation(
        self, rec: AlgorithmTriageRecommendation
    ) -> AlgorithmTriageRecommendation:
        """Persist a calibration triage recommendation row."""

        with self.session() as s:
            existing = s.get(StoredAlgorithmTriageRecommendation, rec.id)
            action_value = (
                rec.recommended_action.value
                if hasattr(rec.recommended_action, "value")
                else str(rec.recommended_action)
            )
            status_value = (
                rec.status.value
                if hasattr(rec.status, "value")
                else str(rec.status)
            )
            reasons_json = json.dumps(rec.trigger_reasons)
            if existing is not None:
                existing.algorithm_id = rec.algorithm_id
                existing.organization_id = rec.organization_id
                existing.recommended_at = rec.recommended_at
                existing.recommended_action = action_value
                existing.trigger_reasons_json = reasons_json
                existing.recommended_multiplier = rec.recommended_multiplier
                existing.narrative = rec.narrative
                existing.status = status_value
                existing.resolved_by = rec.resolved_by
                existing.resolved_at = rec.resolved_at
                existing.resolution_note = rec.resolution_note
                s.add(existing)
            else:
                row = StoredAlgorithmTriageRecommendation(
                    id=rec.id,
                    algorithm_id=rec.algorithm_id,
                    organization_id=rec.organization_id,
                    recommended_at=rec.recommended_at,
                    recommended_action=action_value,
                    trigger_reasons_json=reasons_json,
                    recommended_multiplier=rec.recommended_multiplier,
                    narrative=rec.narrative,
                    status=status_value,
                    resolved_by=rec.resolved_by,
                    resolved_at=rec.resolved_at,
                    resolution_note=rec.resolution_note,
                )
                s.add(row)
            s.commit()
            return rec

    def list_triage_recommendations(
        self,
        *,
        organization_id: Optional[str] = None,
        status: Optional[TriageRecommendationStatus | str] = None,
        algorithm_id: Optional[str] = None,
        limit: int = 200,
    ) -> list[AlgorithmTriageRecommendation]:
        with self.session() as s:
            stmt = select(StoredAlgorithmTriageRecommendation)
            if organization_id is not None:
                stmt = stmt.where(
                    StoredAlgorithmTriageRecommendation.organization_id
                    == organization_id
                )
            if status is not None:
                status_value = (
                    status.value if hasattr(status, "value") else str(status)
                )
                stmt = stmt.where(
                    StoredAlgorithmTriageRecommendation.status == status_value
                )
            if algorithm_id is not None:
                stmt = stmt.where(
                    StoredAlgorithmTriageRecommendation.algorithm_id == algorithm_id
                )
            stmt = stmt.order_by(
                desc(StoredAlgorithmTriageRecommendation.recommended_at)
            ).limit(limit)
            rows = s.exec(stmt).all()
            return [self._triage_row_to_model(r) for r in rows]

    def get_triage_recommendation(
        self, recommendation_id: str
    ) -> Optional[AlgorithmTriageRecommendation]:
        with self.session() as s:
            row = s.get(StoredAlgorithmTriageRecommendation, recommendation_id)
            if row is None:
                return None
            return self._triage_row_to_model(row)

    @staticmethod
    def _triage_row_to_model(
        row: StoredAlgorithmTriageRecommendation,
    ) -> AlgorithmTriageRecommendation:
        try:
            reasons = json.loads(row.trigger_reasons_json or "[]")
            if not isinstance(reasons, list):
                reasons = []
        except json.JSONDecodeError:
            reasons = []
        return AlgorithmTriageRecommendation(
            id=row.id,
            algorithm_id=row.algorithm_id,
            organization_id=row.organization_id,
            recommended_at=row.recommended_at,
            recommended_action=row.recommended_action,
            trigger_reasons=reasons,
            recommended_multiplier=row.recommended_multiplier,
            narrative=row.narrative,
            status=row.status,
            resolved_by=row.resolved_by,
            resolved_at=row.resolved_at,
            resolution_note=row.resolution_note,
        )

    def resolve_triage_recommendation(
        self,
        recommendation_id: str,
        *,
        new_status: TriageRecommendationStatus | str,
        resolved_by: str,
        resolution_note: Optional[str] = None,
        resolved_at: Optional[datetime] = None,
    ) -> AlgorithmTriageRecommendation:
        """Accept / reject / defer a pending triage recommendation.

        REJECTED requires a resolution_note of >= 20 characters per
        the prompt spec — the founder must record *why* the agent's
        recommendation was overruled. Accept actions are applied by
        the caller (status change / multiplier bump) before the row
        is closed; this helper only owns the queue-row transition.
        """

        status_value = (
            new_status.value if hasattr(new_status, "value") else str(new_status)
        )
        if status_value == TriageRecommendationStatus.REJECTED.value:
            note = (resolution_note or "").strip()
            if len(note) < 20:
                raise ValueError(
                    "REJECT requires a resolution_note of at least 20 characters"
                )
        with self.session() as s:
            row = s.get(StoredAlgorithmTriageRecommendation, recommendation_id)
            if row is None:
                raise ValueError(
                    f"AlgorithmTriageRecommendation {recommendation_id!r} not found"
                )
            row.status = status_value
            row.resolved_by = resolved_by
            row.resolved_at = resolved_at or datetime.now()
            row.resolution_note = resolution_note
            s.add(row)
            s.commit()
            return self._triage_row_to_model(row)

    def list_principles(self) -> list[Principle]:
        """Return Principle objects derived from the Codex Principle table.

        Principles are Codex-owned (Prisma); a noosphere-only sqlite
        deployment will return an empty list, which the drafter
        treats as "nothing to formalise."
        """
        if not self._has_prisma_principle_table():
            return []
        try:
            sql = text(
                'SELECT id, text, "domainsJson" FROM "Principle" '
                'WHERE status = :status'
            )
            with self.engine.connect() as conn:
                rows = conn.execute(sql, {"status": "accepted"}).fetchall()
        except SQLAlchemyError:
            return []
        out: list[Principle] = []
        for row in rows:
            try:
                out.append(
                    Principle(
                        id=row[0],
                        text=row[1] or "",
                    )
                )
            except Exception:
                continue
        return out

    def _has_prisma_principle_table(self) -> bool:
        try:
            return "Principle" in set(inspect(self.engine).get_table_names())
        except Exception:
            return False

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
        if raw == "firm":
            return ConfidenceTier.HIGH
        if raw in {tier.value for tier in ConfidenceTier}:
            return ConfidenceTier(raw)
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

    def list_research_suggestions(
        self, *, limit: int = 500
    ) -> list[ResearchSuggestion]:
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
                select(CurrentEvent).where(
                    CurrentEvent.dedupe_hash == event.dedupe_hash
                )
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
                    select(CurrentEvent).where(
                        CurrentEvent.dedupe_hash == event.dedupe_hash
                    )
                ).first()
                if existing is None:
                    raise
                return existing.id
            return event_id

    def find_current_event_by_dedupe(self, hash: str) -> Optional[CurrentEvent]:
        with self.session() as s:
            event = s.exec(
                select(CurrentEvent).where(CurrentEvent.dedupe_hash == hash)
            ).first()
            if event is not None:
                s.expunge(event)
            return event

    def get_current_event(self, event_id: str) -> Optional[CurrentEvent]:
        with self.session() as s:
            event = s.get(CurrentEvent, event_id)
            if event is not None:
                s.expunge(event)
            return event

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
            if parsed_status == CurrentEventStatus.REVOKED and (note or "").startswith(
                "near_duplicate_of:"
            ):
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
            raise ValueError(
                f"unknown conclusion citation source: {citation.conclusion_id}"
            )
        if source_kind == "claim":
            if not citation.claim_id:
                raise ValueError("claim citation requires claim_id")
            row = s.get(StoredClaim, citation.claim_id)
            if row is None:
                raise ValueError(f"unknown claim citation source: {citation.claim_id}")
            return Claim.model_validate_json(row.payload_json).text
        raise ValueError(f"unsupported citation source_kind: {citation.source_kind}")

    def add_event_opinion(
        self, opinion: EventOpinion, citations: list[OpinionCitation]
    ) -> str:
        """Insert an opinion and citations atomically after verbatim-span checks."""
        opinion_id = opinion.id
        with self.session() as s:
            for citation in citations:
                citation.source_kind = citation.source_kind.lower()
                source_text = self._source_text_for_citation(s, citation)
                if citation.quoted_span not in source_text:
                    raise ValueError(
                        "quoted_span is not a verbatim substring of the cited source text"
                    )

            s.add(opinion)
            for citation in citations:
                citation.opinion_id = opinion_id
                s.add(citation)
            s.commit()
            return opinion_id

    def get_event_opinion(self, opinion_id: str) -> Optional[EventOpinion]:
        with self.session() as s:
            return s.get(EventOpinion, opinion_id)

    def latest_event_opinion_for_event(self, event_id: str) -> Optional[EventOpinion]:
        with self.session() as s:
            return s.exec(
                select(EventOpinion)
                .where(EventOpinion.event_id == event_id)
                .where(EventOpinion.revoked_at.is_(None))
                .order_by(desc(EventOpinion.generated_at))
                .limit(1)
            ).first()

    def list_opinion_citations(self, opinion_id: str) -> list[OpinionCitation]:
        with self.session() as s:
            return list(
                s.exec(
                    select(OpinionCitation).where(
                        OpinionCitation.opinion_id == opinion_id
                    )
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

    def revoke_citations_for_source(
        self, source_kind: str, source_id: str, reason: str
    ) -> int:
        source_kind_norm = source_kind.lower()
        forecast_source_type = source_kind_norm.upper()
        with self.session() as s:
            stmt = select(OpinionCitation).where(
                OpinionCitation.source_kind == source_kind_norm
            )
            if source_kind_norm == "conclusion":
                stmt = stmt.where(OpinionCitation.conclusion_id == source_id)
            elif source_kind_norm == "claim":
                stmt = stmt.where(OpinionCitation.claim_id == source_id)
            else:
                raise ValueError(f"unsupported citation source_kind: {source_kind}")

            rows = list(s.exec(stmt).all())
            revoked_at = _utcnow()
            affected_opinion_ids = {row.opinion_id for row in rows}
            for row in rows:
                row.is_revoked = True
                row.revoked_at = revoked_at
                row.revoked_reason = reason
                s.add(row)

            for opinion_id in affected_opinion_ids:
                citations = list(
                    s.exec(
                        select(OpinionCitation).where(
                            OpinionCitation.opinion_id == opinion_id
                        )
                    ).all()
                )
                if citations and all(c.is_revoked for c in citations):
                    opinion = s.get(EventOpinion, opinion_id)
                    if opinion is not None:
                        opinion.abstention_reason = AbstentionReason.REVOKED_SOURCES
                        s.add(opinion)

            forecast_rows = list(
                s.exec(
                    select(ForecastCitation)
                    .where(ForecastCitation.source_type == forecast_source_type)
                    .where(ForecastCitation.source_id == source_id)
                ).all()
            )
            for row in forecast_rows:
                row.is_revoked = True
                row.revoked_reason = reason
                s.add(row)

            s.commit()
            return len(rows) + len(forecast_rows)

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

    # --- Social publishing ---
    def find_social_post_by_source(
        self,
        *,
        platform: str,
        source: str,
        source_id: str | None,
    ) -> Optional[SocialPost]:
        with self.session() as s:
            query = (
                select(SocialPost)
                .where(SocialPost.platform == platform)
                .where(SocialPost.source == source)
            )
            if source_id is None:
                query = query.where(SocialPost.source_id.is_(None))
            else:
                query = query.where(SocialPost.source_id == source_id)
            return s.exec(query.order_by(desc(SocialPost.created_at)).limit(1)).first()

    def add_social_post(self, post: SocialPost) -> str:
        with self.session() as s:
            s.add(post)
            s.commit()
            return post.id

    def get_social_post(self, post_id: str) -> Optional[SocialPost]:
        with self.session() as s:
            return s.get(SocialPost, post_id)

    def count_social_posts_since(
        self,
        *,
        organization_id: str,
        platform: str,
        status: str,
        since: datetime,
    ) -> int:
        with self.session() as s:
            return len(
                s.exec(
                    select(SocialPost.id)
                    .where(SocialPost.organization_id == organization_id)
                    .where(SocialPost.platform == platform)
                    .where(SocialPost.status == status)
                    .where(SocialPost.posted_at.is_not(None))
                    .where(SocialPost.posted_at >= since)
                ).all()
            )

    def get_operator_state(
        self,
        organization_id: str,
        key: str,
    ) -> Optional[OperatorState]:
        with self.session() as s:
            return s.exec(
                select(OperatorState)
                .where(OperatorState.organization_id == organization_id)
                .where(OperatorState.key == key)
            ).first()

    def set_operator_state(
        self,
        organization_id: str,
        key: str,
        value: Any,
    ) -> OperatorState:
        with self.session() as s:
            row = s.exec(
                select(OperatorState)
                .where(OperatorState.organization_id == organization_id)
                .where(OperatorState.key == key)
            ).first()
            now = _utcnow()
            if row is None:
                row = OperatorState(
                    organization_id=organization_id,
                    key=key,
                    value=value,
                    created_at=now,
                    updated_at=now,
                )
            else:
                row.value = value
                row.updated_at = now
            s.add(row)
            s.commit()
            s.refresh(row)
            return row

    # --- Forecasts ---
    def put_forecast_market(self, market: ForecastMarket) -> str:
        """Upsert a ForecastMarket by id, falling back to source/external_id."""
        source_value = (
            market.source.value
            if hasattr(market.source, "value")
            else str(market.source)
        )
        with self.session() as s:
            existing = s.get(ForecastMarket, market.id)
            if existing is None:
                existing = s.exec(
                    select(ForecastMarket)
                    .where(ForecastMarket.source == source_value)
                    .where(ForecastMarket.external_id == market.external_id)
                ).first()
            market.updated_at = _utcnow()
            if existing is not None:
                _copy_sqlmodel_fields(existing, market, exclude={"id", "created_at"})
                s.add(existing)
                s.commit()
                return existing.id
            s.add(market)
            s.commit()
            return market.id

    def get_forecast_market(self, market_id: str) -> Optional[ForecastMarket]:
        with self.session() as s:
            return s.get(ForecastMarket, market_id)

    def list_open_forecast_markets(
        self,
        *,
        organization_id: str | None = None,
        limit: int = 100,
    ) -> list[ForecastMarket]:
        status_value = ForecastMarketStatus.OPEN.value
        with self.session() as s:
            stmt = select(ForecastMarket).where(ForecastMarket.status == status_value)
            if organization_id is not None:
                stmt = stmt.where(ForecastMarket.organization_id == organization_id)
            return list(
                s.exec(
                    stmt.order_by(
                        asc(ForecastMarket.close_time), asc(ForecastMarket.created_at)
                    ).limit(limit)
                ).all()
            )

    def put_forecast_prediction(self, prediction: ForecastPrediction) -> str:
        prediction.updated_at = _utcnow()
        with self.session() as s:
            existing = s.get(ForecastPrediction, prediction.id)
            if existing is not None:
                _copy_sqlmodel_fields(
                    existing, prediction, exclude={"id", "created_at"}
                )
                s.add(existing)
            else:
                s.add(prediction)
            self._ensure_forecast_trace_placeholder(s, existing or prediction)
            s.commit()
            return prediction.id if existing is None else existing.id

    def _ensure_forecast_trace_placeholder(
        self,
        s: Session,
        prediction: ForecastPrediction,
    ) -> None:
        """Guarantee every ForecastPrediction has a trace row, even for fixture/manual inserts."""

        existing = s.exec(
            select(ForecastTrace).where(ForecastTrace.prediction_id == prediction.id)
        ).first()
        if existing is not None:
            return
        market = s.get(ForecastMarket, prediction.market_id)
        probability = (
            float(prediction.probability_yes)
            if prediction.probability_yes is not None
            else None
        )
        market_price = (
            float(market.current_yes_price)
            if market is not None and market.current_yes_price is not None
            else None
        )
        side = None
        edge = None
        if probability is not None and market_price is not None:
            edge = round(probability - market_price, 6)
            side = "YES" if edge >= 0 else "NO"
        s.add(
            ForecastTrace(
                prediction_id=prediction.id,
                market_id=prediction.market_id,
                organization_id=prediction.organization_id,
                market_title=market.title if market is not None else "",
                principles_used=[],
                model_output={
                    "side": side,
                    "edge": edge,
                    "confidence": None,
                    "rationale": prediction.headline,
                },
                gate_results=[
                    {
                        "gateName": "trace_writer",
                        "passed": True,
                        "reason": "placeholder created when ForecastPrediction was persisted",
                    }
                ],
            )
        )

    def get_forecast_prediction(
        self, prediction_id: str
    ) -> Optional[ForecastPrediction]:
        with self.session() as s:
            return s.get(ForecastPrediction, prediction_id)

    def list_recent_forecast_predictions(
        self,
        *,
        since: datetime,
        limit: int,
    ) -> list[ForecastPrediction]:
        with self.session() as s:
            return list(
                s.exec(
                    select(ForecastPrediction)
                    .where(ForecastPrediction.created_at >= since)
                    .order_by(desc(ForecastPrediction.created_at))
                    .limit(limit)
                ).all()
            )

    def put_forecast_citation(self, citation: ForecastCitation) -> str:
        with self.session() as s:
            existing = s.get(ForecastCitation, citation.id)
            if existing is not None:
                _copy_sqlmodel_fields(existing, citation, exclude={"id", "created_at"})
                s.add(existing)
            else:
                s.add(citation)
            s.commit()
            return citation.id if existing is None else existing.id

    def list_forecast_citations(self, prediction_id: str) -> list[ForecastCitation]:
        with self.session() as s:
            return list(
                s.exec(
                    select(ForecastCitation)
                    .where(ForecastCitation.prediction_id == prediction_id)
                    .order_by(asc(ForecastCitation.created_at))
                ).all()
            )

    def put_forecast_trace(self, trace: ForecastTrace) -> str:
        trace.updated_at = _utcnow()
        with self.session() as s:
            existing = s.exec(
                select(ForecastTrace).where(
                    ForecastTrace.prediction_id == trace.prediction_id
                )
            ).first()
            if existing is not None:
                _copy_sqlmodel_fields(existing, trace, exclude={"id", "created_at"})
                s.add(existing)
                s.commit()
                return existing.id
            s.add(trace)
            s.commit()
            return trace.id

    def get_forecast_trace(self, prediction_id: str) -> Optional[ForecastTrace]:
        with self.session() as s:
            return s.exec(
                select(ForecastTrace).where(
                    ForecastTrace.prediction_id == prediction_id
                )
            ).first()

    def list_forecast_traces(
        self,
        *,
        organization_id: str | None = None,
        limit: int = 100,
    ) -> list[ForecastTrace]:
        with self.session() as s:
            stmt = select(ForecastTrace)
            if organization_id is not None:
                stmt = stmt.where(ForecastTrace.organization_id == organization_id)
            return list(
                s.exec(stmt.order_by(desc(ForecastTrace.created_at)).limit(limit)).all()
            )

    def put_forecast_resolution(self, resolution: ForecastResolution) -> str:
        """Append-only insert; a second resolution for the prediction is a no-op."""
        with self.session() as s:
            existing = s.exec(
                select(ForecastResolution).where(
                    ForecastResolution.prediction_id == resolution.prediction_id
                )
            ).first()
            if existing is not None:
                return existing.id
            s.add(resolution)
            s.commit()
            return resolution.id

    def get_forecast_resolution(
        self, prediction_id: str
    ) -> Optional[ForecastResolution]:
        with self.session() as s:
            return s.exec(
                select(ForecastResolution).where(
                    ForecastResolution.prediction_id == prediction_id
                )
            ).first()

    def get_unresolved_predictions_for_market(
        self, market_id: str
    ) -> list[ForecastPrediction]:
        with self.session() as s:
            resolved_ids = set(s.exec(select(ForecastResolution.prediction_id)).all())
            rows = s.exec(
                select(ForecastPrediction)
                .where(ForecastPrediction.market_id == market_id)
                .where(
                    ForecastPrediction.status
                    == ForecastPredictionStatus.PUBLISHED.value
                )
                .order_by(asc(ForecastPrediction.created_at))
            ).all()
            return [row for row in rows if row.id not in resolved_ids]

    def list_published_predictions_for_backfill(
        self,
        *,
        organization_id: str | None = None,
        source: Optional[Any] = None,
        since: datetime | None = None,
        limit: int = 1000,
        include_resolved: bool = True,
    ) -> list[ForecastPrediction]:
        """Predictions with status PUBLISHED, optionally including those
        with an existing ForecastResolution row.

        The resolution backfiller defaults to ``include_resolved=True``
        so it can detect venue drift and write a ``ResolutionRevision``
        when the venue now disagrees with the firm's stored resolution.
        Set ``include_resolved=False`` to limit scanning to predictions
        that have never been resolved.
        """

        status_value = ForecastPredictionStatus.PUBLISHED.value
        with self.session() as s:
            resolved_ids: set[str] = set()
            if not include_resolved:
                resolved_ids = set(
                    s.exec(select(ForecastResolution.prediction_id)).all()
                )
            stmt = (
                select(ForecastPrediction, ForecastMarket)
                .join(
                    ForecastMarket,
                    ForecastMarket.id == ForecastPrediction.market_id,
                )
                .where(ForecastPrediction.status == status_value)
            )
            if organization_id is not None:
                stmt = stmt.where(
                    ForecastPrediction.organization_id == organization_id
                )
            if source is not None:
                source_value = (
                    source.value if hasattr(source, "value") else str(source)
                )
                stmt = stmt.where(ForecastMarket.source == source_value)
            if since is not None:
                stmt = stmt.where(ForecastPrediction.created_at >= since)
            stmt = stmt.order_by(asc(ForecastPrediction.created_at))
            rows = list(s.exec(stmt).all())

        out: list[ForecastPrediction] = []
        for prediction, _market in rows:
            if not include_resolved and prediction.id in resolved_ids:
                continue
            out.append(prediction)
            if len(out) >= limit:
                break
        return out

    def get_resolution_override(
        self, prediction_id: str
    ) -> Optional[ResolutionOverride]:
        with self.session() as s:
            return s.exec(
                select(ResolutionOverride).where(
                    ResolutionOverride.prediction_id == prediction_id
                )
            ).first()

    def put_resolution_override(self, override: ResolutionOverride) -> str:
        """Append-only by predictionId — second write returns the existing id."""

        with self.session() as s:
            existing = s.exec(
                select(ResolutionOverride).where(
                    ResolutionOverride.prediction_id == override.prediction_id
                )
            ).first()
            if existing is not None:
                return existing.id
            s.add(override)
            s.commit()
            return override.id

    def put_resolution_mismatch(self, mismatch: ResolutionMismatch) -> str:
        """Append-only audit row; multiple mismatches per prediction are allowed."""

        with self.session() as s:
            s.add(mismatch)
            s.commit()
            return mismatch.id

    def list_resolution_mismatches(
        self,
        *,
        prediction_id: str | None = None,
        unreviewed_only: bool = False,
        limit: int = 200,
    ) -> list[ResolutionMismatch]:
        with self.session() as s:
            stmt = select(ResolutionMismatch)
            if prediction_id is not None:
                stmt = stmt.where(ResolutionMismatch.prediction_id == prediction_id)
            if unreviewed_only:
                stmt = stmt.where(ResolutionMismatch.reviewed_at.is_(None))
            stmt = stmt.order_by(desc(ResolutionMismatch.created_at)).limit(limit)
            return list(s.exec(stmt).all())

    def put_resolution_revision(self, revision: ResolutionRevision) -> str:
        with self.session() as s:
            s.add(revision)
            s.commit()
            return revision.id

    def list_resolution_revisions(
        self, resolution_id: str
    ) -> list[ResolutionRevision]:
        with self.session() as s:
            return list(
                s.exec(
                    select(ResolutionRevision)
                    .where(ResolutionRevision.resolution_id == resolution_id)
                    .order_by(asc(ResolutionRevision.created_at))
                ).all()
            )

    def put_forecast_bet(self, bet: ForecastBet) -> str:
        mode_value = bet.mode.value if hasattr(bet.mode, "value") else str(bet.mode)
        if mode_value == ForecastBetMode.LIVE.value and bet.live_authorized_at is None:
            raise ValueError("LIVE forecast bets require live_authorized_at")
        with self.session() as s:
            existing = s.get(ForecastBet, bet.id)
            if existing is not None:
                _copy_sqlmodel_fields(existing, bet, exclude={"id", "created_at"})
                s.add(existing)
            else:
                s.add(bet)
            s.commit()
            return bet.id if existing is None else existing.id

    def list_bets_for_prediction(self, prediction_id: str) -> list[ForecastBet]:
        with self.session() as s:
            return list(
                s.exec(
                    select(ForecastBet)
                    .where(ForecastBet.prediction_id == prediction_id)
                    .order_by(asc(ForecastBet.created_at))
                ).all()
            )

    def get_portfolio_state(
        self, organization_id: str
    ) -> Optional[ForecastPortfolioState]:
        with self.session() as s:
            return s.exec(
                select(ForecastPortfolioState).where(
                    ForecastPortfolioState.organization_id == organization_id
                )
            ).first()

    def set_portfolio_state(self, state: ForecastPortfolioState) -> str:
        state.updated_at = _utcnow()
        with self.session() as s:
            existing = s.exec(
                select(ForecastPortfolioState).where(
                    ForecastPortfolioState.organization_id == state.organization_id
                )
            ).first()
            if existing is not None:
                _copy_sqlmodel_fields(existing, state, exclude={"id"})
                s.add(existing)
                s.commit()
                return existing.id
            s.add(state)
            s.commit()
            return state.id

    def put_watched_market(self, watched: WatchedMarket) -> str:
        watched.updated_at = _utcnow()
        with self.session() as s:
            existing = s.exec(
                select(WatchedMarket)
                .where(WatchedMarket.organization_id == watched.organization_id)
                .where(WatchedMarket.url == watched.url)
            ).first()
            if existing is not None:
                _copy_sqlmodel_fields(existing, watched, exclude={"id", "created_at"})
                s.add(existing)
                s.commit()
                return existing.id
            s.add(watched)
            s.commit()
            return watched.id

    def list_watched_markets(
        self,
        *,
        organization_id: str,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[WatchedMarket]:
        with self.session() as s:
            stmt = select(WatchedMarket).where(
                WatchedMarket.organization_id == organization_id
            )
            if active_only:
                stmt = stmt.where(WatchedMarket.status == "ACTIVE")
            return list(
                s.exec(stmt.order_by(desc(WatchedMarket.created_at)).limit(limit)).all()
            )

    def add_forecast_followup_session(self, session: ForecastFollowUpSession) -> str:
        session.created_at = _as_utc_aware(session.created_at) or session.created_at
        session.last_activity_at = (
            _as_utc_aware(session.last_activity_at) or session.last_activity_at
        )
        with self.session() as s:
            s.add(session)
            s.commit()
            return session.id

    def get_forecast_followup_session(
        self, session_id: str
    ) -> Optional[ForecastFollowUpSession]:
        with self.session() as s:
            row = s.get(ForecastFollowUpSession, session_id)
            if row is not None:
                row.created_at = _as_utc_aware(row.created_at) or row.created_at
                row.last_activity_at = (
                    _as_utc_aware(row.last_activity_at) or row.last_activity_at
                )
            return row

    def add_forecast_followup_message(self, message: ForecastFollowUpMessage) -> str:
        message.created_at = _as_utc_aware(message.created_at) or message.created_at
        with self.session() as s:
            s.add(message)
            session = s.get(ForecastFollowUpSession, message.session_id)
            if session is not None:
                session.last_activity_at = message.created_at
                s.add(session)
            s.commit()
            return message.id

    def get_forecast_followup_message(
        self, message_id: str
    ) -> Optional[ForecastFollowUpMessage]:
        with self.session() as s:
            row = s.get(ForecastFollowUpMessage, message_id)
            if row is not None:
                row.created_at = _as_utc_aware(row.created_at) or row.created_at
            return row

    # ── Equities helpers ────────────────────────────────────────────────────

    def put_equity_instrument(self, instrument: EquityInstrument) -> str:
        """Upsert an EquityInstrument by id, falling back to (symbol, exchange)."""
        with self.session() as s:
            existing = s.get(EquityInstrument, instrument.id)
            if existing is None:
                existing = s.exec(
                    select(EquityInstrument)
                    .where(EquityInstrument.symbol == instrument.symbol)
                    .where(EquityInstrument.exchange == instrument.exchange)
                ).first()
            instrument.updated_at = _utcnow()
            if existing is not None:
                _copy_sqlmodel_fields(
                    existing, instrument, exclude={"id", "created_at"}
                )
                s.add(existing)
                s.commit()
                return existing.id
            s.add(instrument)
            s.commit()
            return instrument.id

    def get_equity_instrument(self, instrument_id: str) -> Optional[EquityInstrument]:
        with self.session() as s:
            return s.get(EquityInstrument, instrument_id)

    def get_equity_instrument_by_symbol(
        self, symbol: str, exchange: str
    ) -> Optional[EquityInstrument]:
        with self.session() as s:
            return s.exec(
                select(EquityInstrument)
                .where(EquityInstrument.symbol == symbol)
                .where(EquityInstrument.exchange == exchange)
            ).first()

    def list_equity_instruments(
        self, *, limit: int = 200
    ) -> list[EquityInstrument]:
        with self.session() as s:
            return list(
                s.exec(
                    select(EquityInstrument)
                    .order_by(asc(EquityInstrument.symbol))
                    .limit(limit)
                ).all()
            )

    def put_equity_price_tick(self, tick: EquityPriceTick) -> str:
        with self.session() as s:
            s.add(tick)
            s.commit()
            return tick.id

    def list_equity_price_ticks(
        self, instrument_id: str, *, limit: int = 200
    ) -> list[EquityPriceTick]:
        with self.session() as s:
            return list(
                s.exec(
                    select(EquityPriceTick)
                    .where(EquityPriceTick.instrument_id == instrument_id)
                    .order_by(desc(EquityPriceTick.ts))
                    .limit(limit)
                ).all()
            )

    def put_equity_signal(self, signal: EquitySignal) -> str:
        signal.updated_at = _utcnow()
        with self.session() as s:
            existing = s.get(EquitySignal, signal.id)
            if existing is not None:
                _copy_sqlmodel_fields(existing, signal, exclude={"id", "created_at"})
                s.add(existing)
                s.commit()
                return existing.id
            s.add(signal)
            s.commit()
            return signal.id

    def get_equity_signal(self, signal_id: str) -> Optional[EquitySignal]:
        with self.session() as s:
            return s.get(EquitySignal, signal_id)

    def list_open_signals(
        self,
        *,
        organization_id: str | None = None,
        limit: int = 100,
    ) -> list[EquitySignal]:
        """Published, non-revoked signals — feeds the position sizer."""
        status_value = EquitySignalStatus.PUBLISHED.value
        with self.session() as s:
            stmt = select(EquitySignal).where(EquitySignal.status == status_value)
            if organization_id is not None:
                stmt = stmt.where(EquitySignal.organization_id == organization_id)
            return list(
                s.exec(
                    stmt.order_by(desc(EquitySignal.created_at)).limit(limit)
                ).all()
            )

    def put_equity_signal_citation(
        self, citation: EquitySignalCitation
    ) -> str:
        with self.session() as s:
            existing = s.get(EquitySignalCitation, citation.id)
            if existing is not None:
                _copy_sqlmodel_fields(
                    existing, citation, exclude={"id", "created_at"}
                )
                s.add(existing)
            else:
                s.add(citation)
            s.commit()
            return citation.id if existing is None else existing.id

    def list_equity_signal_citations(
        self, signal_id: str
    ) -> list[EquitySignalCitation]:
        with self.session() as s:
            return list(
                s.exec(
                    select(EquitySignalCitation)
                    .where(EquitySignalCitation.signal_id == signal_id)
                    .order_by(asc(EquitySignalCitation.created_at))
                ).all()
            )

    def put_equity_position(self, position: EquityPosition) -> str:
        mode_value = (
            position.mode.value if hasattr(position.mode, "value") else str(position.mode)
        )
        if (
            mode_value == EquityPositionMode.LIVE.value
            and position.live_authorized_at is None
        ):
            raise ValueError("LIVE equity positions require live_authorized_at")
        position.updated_at = _utcnow()
        with self.session() as s:
            existing = s.get(EquityPosition, position.id)
            if existing is not None:
                _copy_sqlmodel_fields(
                    existing, position, exclude={"id", "created_at"}
                )
                s.add(existing)
                s.commit()
                return existing.id
            s.add(position)
            s.commit()
            return position.id

    def get_equity_position(self, position_id: str) -> Optional[EquityPosition]:
        with self.session() as s:
            return s.get(EquityPosition, position_id)

    def list_positions_for_signal(self, signal_id: str) -> list[EquityPosition]:
        with self.session() as s:
            return list(
                s.exec(
                    select(EquityPosition)
                    .where(EquityPosition.signal_id == signal_id)
                    .order_by(asc(EquityPosition.created_at))
                ).all()
            )

    def get_equity_portfolio_state(
        self, organization_id: str
    ) -> Optional[EquityPortfolioState]:
        with self.session() as s:
            return s.exec(
                select(EquityPortfolioState).where(
                    EquityPortfolioState.organization_id == organization_id
                )
            ).first()

    def set_equity_portfolio_state(self, state: EquityPortfolioState) -> str:
        state.updated_at = _utcnow()
        with self.session() as s:
            existing = s.exec(
                select(EquityPortfolioState).where(
                    EquityPortfolioState.organization_id == state.organization_id
                )
            ).first()
            if existing is not None:
                _copy_sqlmodel_fields(existing, state, exclude={"id"})
                s.add(existing)
                s.commit()
                return existing.id
            s.add(state)
            s.commit()
            return state.id

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
    def put_topic_cluster(
        self, t: Topic, *, centroid: list[float], params_hash: str
    ) -> None:
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
            stmt = select(StoredEntity).where(
                StoredEntity.canonical_key == canonical_key
            )
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
    def get_coherence_evaluation(
        self, evaluation_key: str
    ) -> Optional[CoherenceEvaluationPayload]:
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

    def get_adversarial_challenge(
        self, challenge_id: str
    ) -> Optional[AdversarialChallenge]:
        with self.session() as s:
            r = s.get(StoredAdversarialChallenge, challenge_id)
            if r is None:
                return None
            return AdversarialChallenge.model_validate_json(r.payload_json)

    def list_adversarial_challenges_for_conclusion(
        self, conclusion_id: str
    ) -> list[AdversarialChallenge]:
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

    def list_adversarial_challenges_for_fingerprint(
        self, fingerprint: str
    ) -> list[AdversarialChallenge]:
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

    def find_adversarial_challenge_by_content_hash(
        self, content_hash: str
    ) -> Optional[AdversarialChallenge]:
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
                    update={
                        "conclusion_id": conclusion_id,
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
                r.conclusion_id = conclusion_id
                r.payload_json = ch.model_dump_json()
                r.updated_at = datetime.now(timezone.utc)
                s.add(r)
            s.commit()

    # --- Chunks by artifact ---
    def list_chunks_for_artifact(self, artifact_id: str) -> list[Chunk]:
        with self.session() as s:
            rows = s.exec(
                select(StoredChunk).where(StoredChunk.artifact_id == artifact_id)
            ).all()
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
            rows = s.exec(
                select(StoredVoice).where(StoredVoice.canonical_key == canonical_key)
            ).all()
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
                select(StoredVoice)
                .order_by(asc(StoredVoice.canonical_key))
                .limit(limit)
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
            rows = s.exec(
                select(StoredVoicePhase).where(StoredVoicePhase.voice_id == voice_id)
            ).all()
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
            rows = s.exec(
                select(StoredCitation).where(StoredCitation.voice_id == voice_id)
            ).all()
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

    def get_relative_position_map(
        self, conclusion_id: str
    ) -> Optional[RelativePositionMap]:
        with self.session() as s:
            r = s.get(StoredRelativePositionMap, conclusion_id)
            if r is None:
                return None
            return RelativePositionMap.model_validate_json(r.payload_json)

    def list_relative_position_maps(
        self, *, limit: int = 300
    ) -> list[RelativePositionMap]:
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

    def list_reading_queue_entries(
        self, *, limit: int = 200
    ) -> list[ReadingQueueEntry]:
        with self.session() as s:
            rows = s.exec(
                select(StoredReadingQueue)
                .order_by(desc(StoredReadingQueue.created_at))
                .limit(limit)
            ).all()
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
        d["rationale"] = (
            e.rationale + (" | " if e.rationale and notes else "") + notes
        ).strip()
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
            rows = s.exec(
                select(StoredPredictiveClaim)
                .order_by(desc(StoredPredictiveClaim.created_at))
                .limit(limit)
            ).all()
            out: list[PredictiveClaim] = []
            for r in rows:
                try:
                    out.append(PredictiveClaim.model_validate_json(r.payload_json))
                except Exception:
                    continue
            return out

    def list_predictive_claims_for_claim(
        self, source_claim_id: str
    ) -> list[PredictiveClaim]:
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

    def get_prediction_resolution_for_claim(
        self, predictive_claim_id: str
    ) -> Optional[PredictionResolution]:
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
        row = StoredTemporalCut(cut_id=cut.cut_id, payload_json=cut.model_dump_json())
        with self.session() as s:
            s.add(row)
            for outcome in cut.outcomes:
                if not s.get(StoredOutcome, outcome.outcome_id):
                    s.add(
                        StoredOutcome(
                            outcome_id=outcome.outcome_id,
                            payload_json=outcome.model_dump_json(),
                        )
                    )
                assoc_id = f"{cut.cut_id}:{outcome.outcome_id}"
                if not s.get(StoredCutOutcome, assoc_id):
                    s.add(
                        StoredCutOutcome(
                            id=assoc_id,
                            cut_id=cut.cut_id,
                            outcome_id=outcome.outcome_id,
                        )
                    )
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
                s.add(
                    StoredOutcome(
                        outcome_id=outcome.outcome_id,
                        payload_json=outcome.model_dump_json(),
                    )
                )
            assoc_id = f"{cut_id}:{outcome.outcome_id}"
            if not s.get(StoredCutOutcome, assoc_id):
                s.add(
                    StoredCutOutcome(
                        id=assoc_id,
                        cut_id=cut_id,
                        outcome_id=outcome.outcome_id,
                    )
                )
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
        row = StoredBatteryRun(run_id=run.run_id, payload_json=run.model_dump_json())
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
                select(StoredRebuttal).where(StoredRebuttal.report_id == report_id)
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
            return [
                RevalidationResult.model_validate_json(r.payload_json) for r in rows
            ]

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

    # ── Round 19 prompt 07: cluster index + contradiction test queue ──────

    def upsert_principle_cluster(
        self,
        *,
        principle_id: str,
        cluster_id: str,
        assignment_method: str,
        assigned_at: datetime | None = None,
    ) -> None:
        row = StoredPrincipleCluster(
            principle_id=principle_id,
            cluster_id=cluster_id,
            assignment_method=assignment_method,
            assigned_at=assigned_at or _utcnow(),
        )
        with self.session() as s:
            existing = s.get(StoredPrincipleCluster, principle_id)
            if existing:
                existing.cluster_id = row.cluster_id
                existing.assignment_method = row.assignment_method
                existing.assigned_at = row.assigned_at
                s.add(existing)
            else:
                s.add(row)
            s.commit()

    def get_principle_cluster(self, principle_id: str) -> Optional[dict[str, Any]]:
        with self.session() as s:
            r = s.get(StoredPrincipleCluster, principle_id)
            if r is None:
                return None
            return {
                "principle_id": r.principle_id,
                "cluster_id": r.cluster_id,
                "assignment_method": r.assignment_method,
                "assigned_at": r.assigned_at,
            }

    def delete_principle_cluster(self, principle_id: str) -> bool:
        with self.session() as s:
            r = s.get(StoredPrincipleCluster, principle_id)
            if r is None:
                return False
            s.delete(r)
            s.commit()
            return True

    def list_principle_cluster_assignments(self) -> list[dict[str, Any]]:
        with self.session() as s:
            rows = s.exec(select(StoredPrincipleCluster)).all()
            return [
                {
                    "principle_id": r.principle_id,
                    "cluster_id": r.cluster_id,
                    "assignment_method": r.assignment_method,
                    "assigned_at": r.assigned_at,
                }
                for r in rows
            ]

    def upsert_cluster_centroid(
        self,
        *,
        cluster_id: str,
        centroid: list[float],
        member_count: int,
        assignment_method: str,
    ) -> None:
        blob = _float32_bytes(centroid)
        dim = len(centroid)
        with self.session() as s:
            existing = s.get(StoredClusterCentroid, cluster_id)
            if existing:
                existing.centroid_vec = blob
                existing.dim = dim
                existing.member_count = member_count
                existing.assignment_method = assignment_method
                existing.updated_at = _utcnow()
                s.add(existing)
            else:
                s.add(
                    StoredClusterCentroid(
                        cluster_id=cluster_id,
                        centroid_vec=blob,
                        dim=dim,
                        member_count=member_count,
                        assignment_method=assignment_method,
                    )
                )
            s.commit()

    def delete_cluster_centroid(self, cluster_id: str) -> bool:
        with self.session() as s:
            r = s.get(StoredClusterCentroid, cluster_id)
            if r is None:
                return False
            s.delete(r)
            s.commit()
            return True

    def list_cluster_centroids(self) -> list[dict[str, Any]]:
        with self.session() as s:
            rows = s.exec(select(StoredClusterCentroid)).all()
            return [
                {
                    "cluster_id": r.cluster_id,
                    "centroid": _float_vector(r.centroid_vec),
                    "dim": r.dim,
                    "member_count": r.member_count,
                    "assignment_method": r.assignment_method,
                    "updated_at": r.updated_at,
                }
                for r in rows
            ]

    def enqueue_contradiction_test_task(
        self,
        *,
        principle_a_id: str,
        principle_b_id: str,
        priority: str,
        pair_key: str,
        dedupe_window_hours: int = 24,
    ) -> Optional[str]:
        """Insert a new task; return its id, or None if a recent dupe exists.

        Dedupe key is ``pair_key`` within the trailing
        ``dedupe_window_hours`` (default 24h). The pair_key is computed by
        callers (``stable_pair_id`` over sorted ids), so (A,B) and (B,A)
        collide.
        """

        now = _utcnow()
        window_start = now - timedelta(hours=dedupe_window_hours)
        with self.session() as s:
            existing = s.exec(
                select(StoredContradictionTestTask)
                .where(StoredContradictionTestTask.pair_key == pair_key)
                .where(StoredContradictionTestTask.enqueued_at >= window_start)
                .limit(1)
            ).first()
            if existing is not None:
                return None
            task_id = str(uuid.uuid4())
            s.add(
                StoredContradictionTestTask(
                    id=task_id,
                    principle_a_id=principle_a_id,
                    principle_b_id=principle_b_id,
                    pair_key=pair_key,
                    priority=priority,
                    status="PENDING",
                    enqueued_at=now,
                )
            )
            s.commit()
            return task_id

    _PRIORITY_RANK = {"HIGH": 0, "NORMAL": 1, "LOW": 2}

    def list_pending_contradiction_test_tasks(
        self, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        with self.session() as s:
            rows = s.exec(
                select(StoredContradictionTestTask)
                .where(StoredContradictionTestTask.status == "PENDING")
                .limit(max(1, limit))
            ).all()
        ordered = sorted(
            rows,
            key=lambda r: (
                self._PRIORITY_RANK.get(r.priority, 9),
                r.enqueued_at,
            ),
        )
        return [
            {
                "id": r.id,
                "principle_a_id": r.principle_a_id,
                "principle_b_id": r.principle_b_id,
                "pair_key": r.pair_key,
                "priority": r.priority,
                "status": r.status,
                "enqueued_at": r.enqueued_at,
            }
            for r in ordered
        ]

    def mark_contradiction_test_task(
        self,
        task_id: str,
        *,
        status: str,
        result_id: Optional[str] = None,
        last_error: Optional[str] = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        with self.session() as s:
            r = s.get(StoredContradictionTestTask, task_id)
            if r is None:
                return
            r.status = status
            if result_id is not None:
                r.result_id = result_id
            if last_error is not None:
                r.last_error = last_error
            if started_at is not None:
                r.started_at = started_at
            if finished_at is not None:
                r.finished_at = finished_at
            s.add(r)
            s.commit()

    def contradiction_test_queue_stats(self) -> dict[str, int]:
        out = {
            "PENDING": 0,
            "RUNNING": 0,
            "DONE": 0,
            "FAILED": 0,
        }
        with self.session() as s:
            rows = s.exec(select(StoredContradictionTestTask)).all()
        for r in rows:
            out[r.status] = out.get(r.status, 0) + 1
        return out

    def insert_cluster_reindex_proposal(
        self,
        *,
        drift: float,
        cluster_count_before: int,
        cluster_count_after: int,
        summary: dict[str, Any],
    ) -> str:
        pid = str(uuid.uuid4())
        with self.session() as s:
            s.add(
                StoredClusterReindexProposal(
                    id=pid,
                    drift=float(drift),
                    cluster_count_before=int(cluster_count_before),
                    cluster_count_after=int(cluster_count_after),
                    summary_json=json.dumps(summary, default=str),
                )
            )
            s.commit()
        return pid

    def list_cluster_reindex_proposals(
        self, *, status: Optional[str] = None
    ) -> list[dict[str, Any]]:
        with self.session() as s:
            stmt = select(StoredClusterReindexProposal)
            if status:
                stmt = stmt.where(StoredClusterReindexProposal.status == status)
            rows = s.exec(stmt).all()
        return [
            {
                "id": r.id,
                "proposed_at": r.proposed_at,
                "drift": r.drift,
                "cluster_count_before": r.cluster_count_before,
                "cluster_count_after": r.cluster_count_after,
                "summary": json.loads(r.summary_json or "{}"),
                "status": r.status,
                "resolved_by": r.resolved_by,
                "resolved_at": r.resolved_at,
            }
            for r in rows
        ]

    # ── Provenance helpers (prompt 09) ────────────────────────────────────
    def set_artifact_provenance(
        self,
        artifact_id: str,
        provenance: str,
        *,
        rationale: str = "",
    ) -> bool:
        """Re-tag an artifact's provenance. CLI/UI only; never inferred.

        Returns True if the row was updated, False if no such artifact.
        Raises ValueError if the new provenance is not a known kind or if an
        external kind is set without a sufficient rationale.
        """
        from noosphere.models import (
            ProvenanceKind,
            coerce_provenance,
            validate_provenance_rationale,
        )

        kind = ProvenanceKind(str(provenance).upper())
        rationale = validate_provenance_rationale(kind, rationale)
        with self.session() as s:
            row = s.get(StoredArtifact, artifact_id)
            if row is None:
                return False
            row.provenance = kind.value
            row.provenance_rationale = rationale
            s.add(row)
            s.commit()
        return True

    def list_artifacts_by_provenance(
        self,
        provenance: str | None = None,
        *,
        limit: int = 500,
    ) -> list[Artifact]:
        """List artifacts, optionally filtered by provenance kind."""
        with self.session() as s:
            stmt = select(StoredArtifact)
            if provenance:
                stmt = stmt.where(StoredArtifact.provenance == str(provenance).upper())
            stmt = stmt.order_by(desc(StoredArtifact.created_at)).limit(limit)
            rows = list(s.exec(stmt).all())
        out: list[Artifact] = []
        for r in rows:
            art = self.get_artifact(r.id)
            if art is not None:
                out.append(art)
        return out

    def count_artifacts_by_provenance(self) -> dict[str, int]:
        """Return {provenance_kind_value: count} across all artifacts."""
        from noosphere.models import PROVENANCE_KIND_VALUES

        counts: dict[str, int] = {v: 0 for v in PROVENANCE_KIND_VALUES}
        with self.session() as s:
            rows = s.exec(select(StoredArtifact)).all()
        for r in rows:
            key = (r.provenance or "PROPRIETARY").upper()
            counts[key] = counts.get(key, 0) + 1
        return counts

    def list_conclusions_by_provenance(
        self, provenances: Iterable[str] | None = None, *, limit: int = 500
    ) -> list[Conclusion]:
        """Conclusion fetch filtered to the given provenance set (post-tag)."""
        wanted = (
            {str(p).upper() for p in provenances} if provenances is not None else None
        )
        with self.session() as s:
            stmt = select(StoredConclusion)
            if wanted is not None:
                stmt = stmt.where(StoredConclusion.provenance.in_(tuple(wanted)))
            stmt = stmt.limit(limit)
            rows = list(s.exec(stmt).all())
        out: list[Conclusion] = []
        for r in rows:
            try:
                out.append(Conclusion.model_validate_json(r.payload_json))
            except Exception:
                continue
        return out

    def list_claims_by_provenance(
        self, provenances: Iterable[str] | None = None, *, limit: int = 500
    ) -> list[Claim]:
        wanted = (
            {str(p).upper() for p in provenances} if provenances is not None else None
        )
        with self.session() as s:
            stmt = select(StoredClaim)
            if wanted is not None:
                stmt = stmt.where(StoredClaim.provenance.in_(tuple(wanted)))
            stmt = stmt.limit(limit)
            rows = list(s.exec(stmt).all())
        out: list[Claim] = []
        for r in rows:
            try:
                out.append(Claim.model_validate_json(r.payload_json))
            except Exception:
                continue
        return out

    def list_untagged_artifacts(self, *, limit: int = 500) -> list[Artifact]:
        """Founder triage helper: artifacts left at the PROPRIETARY default.

        Backfilled rows land here so the founder can review the count and
        re-tag any that should be external. Differs from
        ``list_artifacts_by_provenance("PROPRIETARY")`` only in intent —
        the migration's count-summary points here.
        """
        return self.list_artifacts_by_provenance("PROPRIETARY", limit=limit)

    # --- Knowledge graph snapshots (prompt 13) ---

    def put_graph_snapshot(self, snap) -> None:  # noqa: ANN001
        """Append a knowledge-graph snapshot. Append-only by contract.

        Callers pass a :class:`noosphere.models.GraphSnapshot`.
        """
        nodes_json = json.dumps(
            [n.model_dump(mode="json") for n in snap.nodes], ensure_ascii=False
        )
        edges_json = json.dumps(
            [e.model_dump(mode="json") for e in snap.edges], ensure_ascii=False
        )
        row = StoredGraphSnapshot(
            id=snap.id,
            organization_id=snap.organization_id,
            snapshot_at=snap.snapshot_at,
            version=snap.version,
            nodes_json=nodes_json,
            edges_json=edges_json,
            node_count=snap.node_count or len(snap.nodes),
            edge_count=snap.edge_count or len(snap.edges),
            notes=snap.notes or "",
        )
        with self.session() as s:
            s.add(row)
            s.commit()

    def get_latest_graph_snapshot(self, organization_id: str):  # noqa: ANN201
        from noosphere.models import GraphSnapshot, KGEdge, KGNode

        with self.session() as s:
            stmt = (
                select(StoredGraphSnapshot)
                .where(StoredGraphSnapshot.organization_id == organization_id)
                .order_by(desc(StoredGraphSnapshot.snapshot_at))
                .limit(1)
            )
            row = s.exec(stmt).first()
        if row is None:
            return None
        try:
            nodes = [KGNode.model_validate(n) for n in json.loads(row.nodes_json)]
        except Exception:
            nodes = []
        try:
            edges = [KGEdge.model_validate(e) for e in json.loads(row.edges_json)]
        except Exception:
            edges = []
        return GraphSnapshot(
            id=row.id,
            organization_id=row.organization_id,
            snapshot_at=row.snapshot_at,
            version=row.version,
            nodes=nodes,
            edges=edges,
            node_count=row.node_count,
            edge_count=row.edge_count,
            notes=row.notes,
        )

    def list_graph_snapshots(
        self,
        organization_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Lightweight summary list for the operator audit panel.

        Returns one dict per snapshot — does NOT decode the (potentially
        large) nodes/edges JSON, so the operator history is cheap to
        render even with hundreds of snapshots.
        """
        with self.session() as s:
            stmt = (
                select(StoredGraphSnapshot)
                .where(StoredGraphSnapshot.organization_id == organization_id)
                .order_by(desc(StoredGraphSnapshot.snapshot_at))
                .limit(limit)
            )
            rows = list(s.exec(stmt).all())
        return [
            {
                "id": r.id,
                "snapshot_at": r.snapshot_at,
                "version": r.version,
                "node_count": r.node_count,
                "edge_count": r.edge_count,
                "notes": r.notes,
            }
            for r in rows
        ]

    def put_edge_reasoning(
        self,
        organization_id: str,
        src: str,
        dst: str,
        kind: str,
        payload: dict[str, Any],
    ) -> str:
        from uuid import uuid4

        row_id = f"kgreason_{uuid4().hex[:24]}"
        row = StoredGraphEdgeReasoning(
            id=row_id,
            organization_id=organization_id,
            src=src,
            dst=dst,
            kind=str(kind),
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
        )
        with self.session() as s:
            s.add(row)
            s.commit()
        return row_id

    def get_edge_reasoning(
        self,
        organization_id: str,
        src: str,
        dst: str,
        kind: str,
    ) -> Optional[dict[str, Any]]:
        with self.session() as s:
            stmt = (
                select(StoredGraphEdgeReasoning)
                .where(StoredGraphEdgeReasoning.organization_id == organization_id)
                .where(StoredGraphEdgeReasoning.src == src)
                .where(StoredGraphEdgeReasoning.dst == dst)
                .where(StoredGraphEdgeReasoning.kind == str(kind))
                .order_by(desc(StoredGraphEdgeReasoning.generated_at))
                .limit(1)
            )
            row = s.exec(stmt).first()
        if row is None:
            return None
        try:
            return json.loads(row.payload_json)
        except Exception:
            return None

    # --- Dialectic live recording (prompt 14) ---

    def put_dialectic_session(self, session) -> None:  # noqa: ANN001
        """Insert or update a DialecticSession row."""

        participants = [
            p.model_dump(mode="json") if hasattr(p, "model_dump") else dict(p)
            for p in (session.participants or [])
        ]
        row = StoredDialecticSession(
            id=session.id,
            organization_id=session.organization_id,
            title=session.title or "",
            started_at=_dt(session.started_at) if session.started_at else _utcnow(),
            ended_at=_dt(session.ended_at) if session.ended_at else None,
            participants_json=json.dumps(participants, default=str),
            audio_path=session.audio_path or "",
            transcript_path=session.transcript_path or "",
            status=str(getattr(session.status, "value", session.status)),
            visibility=str(getattr(session.visibility, "value", session.visibility)),
            live_contradictions_detected=int(session.live_contradictions_detected or 0),
            principles_extracted=int(session.principles_extracted or 0),
            summary_memo_id=session.summary_memo_id,
            created_at=_dt(session.created_at) if session.created_at else _utcnow(),
            updated_at=_utcnow(),
        )
        with self.session() as s:
            existing = s.get(StoredDialecticSession, session.id)
            if existing is None:
                s.add(row)
            else:
                _copy_sqlmodel_fields(existing, row, exclude={"id", "created_at"})
            s.commit()

    def _hydrate_dialectic_session(self, row):  # noqa: ANN001
        from noosphere.models import (
            DialecticParticipant,
            DialecticSession,
            DialecticSessionStatus,
            DialecticVisibility,
        )

        try:
            participants_raw = json.loads(row.participants_json or "[]")
        except Exception:
            participants_raw = []
        participants = []
        for p in participants_raw:
            try:
                participants.append(DialecticParticipant.model_validate(p))
            except Exception:
                continue
        return DialecticSession(
            id=row.id,
            organization_id=row.organization_id,
            title=row.title,
            started_at=row.started_at,
            ended_at=row.ended_at,
            participants=participants,
            audio_path=row.audio_path,
            transcript_path=row.transcript_path,
            status=DialecticSessionStatus(row.status),
            visibility=DialecticVisibility(row.visibility),
            live_contradictions_detected=row.live_contradictions_detected,
            principles_extracted=row.principles_extracted,
            summary_memo_id=row.summary_memo_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def get_dialectic_session(self, session_id: str):  # noqa: ANN201
        with self.session() as s:
            row = s.get(StoredDialecticSession, session_id)
        return self._hydrate_dialectic_session(row) if row is not None else None

    def list_dialectic_sessions(
        self,
        organization_id: str,
        *,
        status: Optional[str] = None,
        limit: int = 50,
    ):
        with self.session() as s:
            stmt = select(StoredDialecticSession).where(
                StoredDialecticSession.organization_id == organization_id
            )
            if status:
                stmt = stmt.where(StoredDialecticSession.status == status)
            stmt = stmt.order_by(desc(StoredDialecticSession.started_at)).limit(limit)
            rows = list(s.exec(stmt).all())
        return [self._hydrate_dialectic_session(r) for r in rows]

    def put_dialectic_utterance(self, utterance) -> None:  # noqa: ANN001
        row = StoredDialecticUtterance(
            id=utterance.id,
            session_id=utterance.session_id,
            speaker_id=utterance.speaker_id,
            start_time=float(utterance.start_time or 0.0),
            end_time=float(utterance.end_time or 0.0),
            text=utterance.text or "",
            extracted_claim_ids_json=json.dumps(
                list(utterance.extracted_claim_ids or [])
            ),
            derived_principle_ids_json=json.dumps(
                list(utterance.derived_principle_ids or [])
            ),
            live_contradiction_flags_json=json.dumps(
                list(utterance.live_contradiction_flags or []),
                default=str,
            ),
            created_at=_dt(utterance.created_at) if utterance.created_at else _utcnow(),
        )
        with self.session() as s:
            existing = s.get(StoredDialecticUtterance, utterance.id)
            if existing is None:
                s.add(row)
            else:
                _copy_sqlmodel_fields(existing, row, exclude={"id", "created_at"})
            s.commit()

    def list_dialectic_utterances(self, session_id: str):
        from noosphere.models import DialecticUtterance

        with self.session() as s:
            stmt = (
                select(StoredDialecticUtterance)
                .where(StoredDialecticUtterance.session_id == session_id)
                .order_by(StoredDialecticUtterance.start_time)
            )
            rows = list(s.exec(stmt).all())

        def _safe_load(payload: str, fallback: Any) -> Any:
            try:
                return json.loads(payload)
            except Exception:
                return fallback

        return [
            DialecticUtterance(
                id=r.id,
                session_id=r.session_id,
                speaker_id=r.speaker_id,
                start_time=r.start_time,
                end_time=r.end_time,
                text=r.text,
                extracted_claim_ids=_safe_load(r.extracted_claim_ids_json, []),
                derived_principle_ids=_safe_load(r.derived_principle_ids_json, []),
                live_contradiction_flags=_safe_load(
                    r.live_contradiction_flags_json, []
                ),
                created_at=r.created_at,
            )
            for r in rows
        ]

    def put_dialectic_contradiction_flag(self, flag) -> None:  # noqa: ANN001
        row = StoredDialecticContradictionFlag(
            id=flag.id,
            utterance_id=flag.utterance_id,
            flag_kind=str(getattr(flag.flag_kind, "value", flag.flag_kind)),
            prior_utterance_id=flag.prior_utterance_id,
            prior_principle_id=flag.prior_principle_id,
            prior_speaker_id=flag.prior_speaker_id,
            contradiction_score=float(flag.contradiction_score or 0.0),
            axis=flag.axis,
            human_explanation=flag.human_explanation,
            detection_method=flag.detection_method or "",
            acknowledged_at=_dt(flag.acknowledged_at) if flag.acknowledged_at else None,
            acknowledged_by=flag.acknowledged_by,
            acknowledgment_note=flag.acknowledgment_note,
            detected_at=_dt(flag.detected_at) if flag.detected_at else _utcnow(),
        )
        with self.session() as s:
            existing = s.get(StoredDialecticContradictionFlag, flag.id)
            if existing is None:
                s.add(row)
            else:
                _copy_sqlmodel_fields(existing, row, exclude={"id"})
            s.commit()

    def list_dialectic_flags_for_session(self, session_id: str):
        from noosphere.models import (
            DialecticContradictionFlag,
            DialecticContradictionFlagKind,
        )

        with self.session() as s:
            stmt = (
                select(StoredDialecticContradictionFlag)
                .join(
                    StoredDialecticUtterance,
                    StoredDialecticUtterance.id
                    == StoredDialecticContradictionFlag.utterance_id,
                )
                .where(StoredDialecticUtterance.session_id == session_id)
                .order_by(StoredDialecticContradictionFlag.detected_at)
            )
            rows = list(s.exec(stmt).all())
        out = []
        for r in rows:
            out.append(
                DialecticContradictionFlag(
                    id=r.id,
                    utterance_id=r.utterance_id,
                    flag_kind=DialecticContradictionFlagKind(r.flag_kind),
                    prior_utterance_id=r.prior_utterance_id,
                    prior_principle_id=r.prior_principle_id,
                    prior_speaker_id=r.prior_speaker_id,
                    contradiction_score=r.contradiction_score,
                    axis=r.axis,
                    human_explanation=r.human_explanation,
                    detection_method=r.detection_method,
                    acknowledged_at=r.acknowledged_at,
                    acknowledged_by=r.acknowledged_by,
                    acknowledgment_note=r.acknowledgment_note,
                    detected_at=r.detected_at,
                )
            )
        return out

    def acknowledge_dialectic_flag(
        self,
        flag_id: str,
        *,
        acknowledged_by: str,
        note: str = "",
    ) -> bool:
        with self.session() as s:
            row = s.get(StoredDialecticContradictionFlag, flag_id)
            if row is None:
                return False
            row.acknowledged_at = _utcnow()
            row.acknowledged_by = acknowledged_by
            row.acknowledgment_note = note or None
            s.add(row)
            s.commit()
        return True

    def delete_dialectic_session_audio(self, session_id: str) -> bool:
        """Erase the audio for a session past its retention window.

        Transcript / utterances / flags are kept; only the binary blob path
        is cleared and the row is updated. Returns True if anything changed.
        """
        with self.session() as s:
            row = s.get(StoredDialecticSession, session_id)
            if row is None or not row.audio_path:
                return False
            audio_path = row.audio_path
            row.audio_path = ""
            row.updated_at = _utcnow()
            s.add(row)
            s.commit()
        try:
            from pathlib import Path as _Path
            p = _Path(audio_path)
            if p.exists() and p.is_file():
                p.unlink()
        except Exception:
            pass
        return True

    # ── Round 19 prompt 15: BetSpec / BetResolution ─────────────────────────

    def put_bet_spec(self, spec: Any) -> Any:
        """Persist (insert or update) a :class:`noosphere.bets.spec.BetSpec`."""

        from noosphere.bets.spec import BetSpec  # local import to avoid cycle

        if not isinstance(spec, BetSpec):
            raise TypeError(f"put_bet_spec expects BetSpec, got {type(spec)!r}")
        spec.updated_at = _utcnow()
        payload = spec.model_dump_json()
        kind = (
            spec.kind.value if hasattr(spec.kind, "value") else str(spec.kind)
        )
        status = (
            spec.status.value if hasattr(spec.status, "value") else str(spec.status)
        )
        outcome = (
            spec.outcome.value if hasattr(spec.outcome, "value") else spec.outcome
        )
        with self.session() as s:
            existing = s.get(StoredBetSpec, spec.id)
            if existing is not None:
                existing.organization_id = spec.organization_id
                existing.kind = kind
                existing.status = status
                existing.proposition = spec.proposition
                existing.resolution_criterion = spec.resolution_criterion
                existing.horizon_at = spec.horizon_at
                existing.created_by_memo_id = spec.created_by_memo_id
                existing.originating_algorithm_id = spec.originating_algorithm_id
                existing.updated_at = spec.updated_at
                existing.resolved_at = spec.resolved_at
                existing.outcome = outcome
                existing.outcome_note = spec.outcome_note
                existing.payload_json = payload
                s.add(existing)
            else:
                s.add(
                    StoredBetSpec(
                        id=spec.id,
                        organization_id=spec.organization_id,
                        kind=kind,
                        status=status,
                        proposition=spec.proposition,
                        resolution_criterion=spec.resolution_criterion,
                        horizon_at=spec.horizon_at,
                        created_by_memo_id=spec.created_by_memo_id,
                        originating_algorithm_id=spec.originating_algorithm_id,
                        created_at=spec.created_at,
                        updated_at=spec.updated_at,
                        resolved_at=spec.resolved_at,
                        outcome=outcome,
                        outcome_note=spec.outcome_note,
                        payload_json=payload,
                    )
                )
            s.commit()
        return spec

    def get_bet_spec(self, spec_id: str) -> Optional[Any]:
        from noosphere.bets.spec import BetSpec  # local import

        with self.session() as s:
            row = s.get(StoredBetSpec, spec_id)
            if row is None:
                return None
            try:
                return BetSpec.model_validate_json(row.payload_json)
            except Exception:
                return None

    def list_bet_specs(
        self,
        *,
        organization_id: Optional[str] = None,
        kind: Optional[str] = None,
        status: Optional[str] = None,
        memo_id: Optional[str] = None,
        limit: int = 200,
    ) -> list[Any]:
        from noosphere.bets.spec import BetSpec

        with self.session() as s:
            stmt = select(StoredBetSpec)
            if organization_id is not None:
                stmt = stmt.where(StoredBetSpec.organization_id == organization_id)
            if kind is not None:
                stmt = stmt.where(StoredBetSpec.kind == kind)
            if status is not None:
                stmt = stmt.where(StoredBetSpec.status == status)
            if memo_id is not None:
                stmt = stmt.where(StoredBetSpec.created_by_memo_id == memo_id)
            stmt = stmt.order_by(desc(StoredBetSpec.created_at)).limit(limit)
            rows = s.exec(stmt).all()
        out: list[BetSpec] = []
        for row in rows:
            try:
                out.append(BetSpec.model_validate_json(row.payload_json))
            except Exception:
                continue
        return out

    def put_bet_resolution(self, resolution: Any) -> Any:
        """Persist a :class:`noosphere.bets.spec.BetResolution` row."""

        from noosphere.bets.spec import BetResolution

        if not isinstance(resolution, BetResolution):
            raise TypeError(
                f"put_bet_resolution expects BetResolution, got {type(resolution)!r}"
            )
        payload = resolution.model_dump_json()
        outcome = (
            resolution.outcome.value
            if hasattr(resolution.outcome, "value")
            else str(resolution.outcome)
        )
        with self.session() as s:
            existing = s.get(StoredBetResolution, resolution.id)
            if existing is not None:
                existing.bet_spec_id = resolution.bet_spec_id
                existing.resolved_at = resolution.resolved_at
                existing.outcome = outcome
                existing.evidence_note = resolution.evidence_note
                existing.resolved_by = resolution.resolved_by
                existing.pnl_usd = resolution.pnl_usd
                existing.cost_realized = resolution.cost_realized
                existing.accuracy_score = resolution.accuracy_score
                existing.audience_response = resolution.audience_response
                existing.payload_json = payload
                s.add(existing)
            else:
                s.add(
                    StoredBetResolution(
                        id=resolution.id,
                        bet_spec_id=resolution.bet_spec_id,
                        resolved_at=resolution.resolved_at,
                        outcome=outcome,
                        evidence_note=resolution.evidence_note,
                        resolved_by=resolution.resolved_by,
                        pnl_usd=resolution.pnl_usd,
                        cost_realized=resolution.cost_realized,
                        accuracy_score=resolution.accuracy_score,
                        audience_response=resolution.audience_response,
                        payload_json=payload,
                    )
                )
            s.commit()
        return resolution

    def list_bet_resolutions(
        self,
        *,
        bet_spec_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[Any]:
        from noosphere.bets.spec import BetResolution

        with self.session() as s:
            stmt = select(StoredBetResolution)
            if bet_spec_id is not None:
                stmt = stmt.where(StoredBetResolution.bet_spec_id == bet_spec_id)
            stmt = stmt.order_by(desc(StoredBetResolution.resolved_at)).limit(limit)
            rows = s.exec(stmt).all()
        out: list[BetResolution] = []
        for row in rows:
            try:
                out.append(BetResolution.model_validate_json(row.payload_json))
            except Exception:
                continue
        return out

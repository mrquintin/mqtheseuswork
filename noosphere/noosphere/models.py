"""
Core data models for the Noosphere knowledge system.

Every model is a Pydantic BaseModel for serialization, validation, and
JSON round-tripping to disk. The fundamental unit is the Claim — an atomic
proposition extracted from a transcript, attributed to a speaker, and
positioned in embedding space.
"""

from __future__ import annotations
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Any, Literal, NewType
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import (
    Boolean as SABoolean,
    CheckConstraint,
    Column,
    DateTime as SADateTime,
    Float as SAFloat,
    Index,
    Integer as SAInteger,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import JSON, TypeDecorator
from sqlmodel import Field as SQLField, SQLModel
import uuid


# ── Enums ────────────────────────────────────────────────────────────────────

class RelationType(str, Enum):
    """Semantic relationship between two claims or principles."""
    SUPPORTS = "supports"           # A provides evidence/reasoning for B
    CONTRADICTS = "contradicts"     # A is logically incompatible with B
    REFINES = "refines"             # A is a more precise version of B
    INSTANTIATES = "instantiates"   # A is a specific case of general B
    EXTENDS = "extends"             # A adds new scope to B
    ANALOGIZES = "analogizes"       # A draws structural parallel to B
    PRESUPPOSES = "presupposes"     # A requires B to be true
    QUALIFIES = "qualifies"         # A limits or conditions B


class Discipline(str, Enum):
    """Knowledge domains tracked by Theseus."""
    PHILOSOPHY = "Philosophy"
    PHYSICS = "Physics"
    AI = "AI"
    ENTREPRENEURSHIP = "Entrepreneurship"
    VC = "VC"
    ART = "Art & Film"
    LITERATURE = "Literature"
    MATHEMATICS = "Mathematics"
    ECONOMICS = "Economics"
    HISTORY = "History"
    EPISTEMOLOGY = "Epistemology"
    ETHICS = "Ethics"
    POLITICAL_PHILOSOPHY = "Political Philosophy"
    STRATEGY = "Strategy"


class ConvictionLevel(str, Enum):
    """How strongly a principle is held, inferred from discourse patterns."""
    AXIOM = "axiom"                 # Foundational, never questioned
    STRONG = "strong"               # Consistently asserted with emphasis
    MODERATE = "moderate"           # Asserted but open to refinement
    EXPLORATORY = "exploratory"     # Tentatively proposed, being tested
    CONTESTED = "contested"         # Actively debated among founders


# ── Round 3: Freshness & Decay (defined early for use in existing models) ────

class Freshness(str, Enum):
    """Freshness status for revalidation tracking."""
    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"
    RETIRED = "retired"


class CurrentEventStatus(str, Enum):
    OBSERVED = "OBSERVED"
    ENRICHED = "ENRICHED"
    OPINED = "OPINED"
    ABSTAINED = "ABSTAINED"
    REVOKED = "REVOKED"


class CurrentEventSource(str, Enum):
    X_TWITTER = "X_TWITTER"
    RSS = "RSS"
    MANUAL = "MANUAL"


class OpinionStance(str, Enum):
    AGREES = "AGREES"
    DISAGREES = "DISAGREES"
    COMPLICATES = "COMPLICATES"
    ABSTAINED = "ABSTAINED"


class AbstentionReason(str, Enum):
    INSUFFICIENT_SOURCES = "INSUFFICIENT_SOURCES"
    NEAR_DUPLICATE = "NEAR_DUPLICATE"
    BUDGET = "BUDGET"
    CITATION_FABRICATION = "CITATION_FABRICATION"
    REVOKED_SOURCES = "REVOKED_SOURCES"


class FollowUpRole(str, Enum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class ForecastSource(str, Enum):
    POLYMARKET = "POLYMARKET"
    KALSHI = "KALSHI"


class ForecastMarketStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"


class ForecastPredictionStatus(str, Enum):
    PUBLISHED = "PUBLISHED"
    ABSTAINED_INSUFFICIENT_SOURCES = "ABSTAINED_INSUFFICIENT_SOURCES"
    ABSTAINED_MARKET_EXPIRED = "ABSTAINED_MARKET_EXPIRED"
    ABSTAINED_NEAR_DUPLICATE = "ABSTAINED_NEAR_DUPLICATE"
    ABSTAINED_BUDGET = "ABSTAINED_BUDGET"
    ABSTAINED_CITATION_FABRICATION = "ABSTAINED_CITATION_FABRICATION"
    ABSTAINED_REVOKED_SOURCES = "ABSTAINED_REVOKED_SOURCES"


class ForecastSupportLabel(str, Enum):
    DIRECT = "DIRECT"
    INDIRECT = "INDIRECT"
    CONTRARY = "CONTRARY"


class ForecastOutcome(str, Enum):
    YES = "YES"
    NO = "NO"
    CANCELLED = "CANCELLED"
    AMBIGUOUS = "AMBIGUOUS"


class ForecastBetMode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class ForecastExchange(str, Enum):
    POLYMARKET = "POLYMARKET"
    KALSHI = "KALSHI"


class ForecastBetSide(str, Enum):
    YES = "YES"
    NO = "NO"


class ForecastBetStatus(str, Enum):
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    CONFIRMED = "CONFIRMED"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    SETTLED = "SETTLED"
    FAILED = "FAILED"


class ForecastFollowUpRole(str, Enum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


def _new_cuid() -> str:
    """Prisma-compatible textual id shape for Python-created Currents rows."""
    return f"c{uuid.uuid4().hex[:24]}"


def _now() -> datetime:
    return datetime.now()


class _StringListType(TypeDecorator):
    """Postgres text[] in production, JSON in SQLite-backed tests."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.ARRAY(Text()))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return []
        return [str(v) for v in value]

    def process_result_value(self, value, dialect):
        if value is None:
            return []
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                return [value]
            if isinstance(decoded, list):
                return [str(v) for v in decoded]
            return []
        return [str(v) for v in value]


# ── Pre-existing enums (needed by store / coherence) ────────────────────────

class CoherenceVerdict(str, Enum):
    COHERE = "cohere"
    CONTRADICT = "contradict"
    UNRESOLVED = "unresolved"


class ConfidenceTier(str, Enum):
    FOUNDER = "founder"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    SPECULATIVE = "speculative"


class AdversarialChallengeStatus(str, Enum):
    PENDING = "pending"
    EVALUATED = "evaluated"
    ADDRESSED = "addressed"
    FATAL = "fatal"
    SURVIVED = "survived"
    FALLEN = "fallen"


class PredictiveClaimStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    RESOLVED = "resolved"
    EXPIRED = "expired"


# ── Pre-existing data models (needed by store / coherence / adversarial) ────


class SixLayerScore(BaseModel):
    consistency: float = 0.0
    argumentation: float = 0.0
    probabilistic: float = 0.0
    geometric: float = 0.0
    information: float = 0.0
    judge: float = 0.0


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    uri: str = ""
    mime_type: str = ""
    byte_length: int = 0
    content_sha256: str = ""
    title: str = ""
    author: str = ""
    source_date: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.now)
    effective_at: Optional[datetime] = None
    superseded_at: Optional[datetime] = None
    effective_at_inferred: bool = True
    license_status: Optional[str] = "unknown"
    literature_connector: Optional[str] = ""


class Chunk(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    artifact_id: str = ""
    start_offset: int = 0
    end_offset: int = 0
    text: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


class CoherenceEvaluationPayload(BaseModel):
    final_verdict: CoherenceVerdict = CoherenceVerdict.UNRESOLVED
    aggregator_verdict: CoherenceVerdict = CoherenceVerdict.UNRESOLVED
    prior_scores: SixLayerScore = Field(default_factory=SixLayerScore)
    layer_verdicts: dict[str, str] = Field(default_factory=dict)


class DriftEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_id: str = ""
    observed_at: date = Field(default_factory=date.today)
    drift_score: float = 0.0


class Entity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    canonical_key: Optional[str] = None
    label: str = ""
    entity_type: str = ""


class ResearchSuggestion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    summary: str = ""


class ReviewItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    claim_a_id: str = ""
    claim_b_id: str = ""
    reason: str = ""
    status: str = "open"
    created_at: datetime = Field(default_factory=datetime.now)


class AdversarialChallenge(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conclusion_id: str = ""
    cluster_fingerprint: str = ""
    content_hash: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class VoiceProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    canonical_name: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class VoicePhaseRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    voice_id: str = ""


class CitationRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    firm_claim_id: str = ""
    voice_id: str = ""


class RelativePositionMap(BaseModel):
    conclusion_id: str = ""


class ReadingQueueEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "queued"
    rationale: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class PredictiveClaim(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    author_key: Optional[str] = ""
    artifact_id: Optional[str] = ""
    status: PredictiveClaimStatus = PredictiveClaimStatus.DRAFT
    source_claim_id: str = ""
    voice_id: str = ""
    created_at: datetime = Field(default_factory=datetime.now)


class PredictionResolution(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    predictive_claim_id: str = ""
    resolved_at: datetime = Field(default_factory=datetime.now)


def voice_canonical_key(name: str) -> str:
    return name.lower().strip().replace(" ", "_")


# ─────────────────────────────────────────────────────────────────────────────
# Reconstructed models
#
# The following block was missing from models.py but heavily imported across
# coherence/, adversarial.py, voices.py, founders.py, predictive_extractor.py,
# and retrieval.py. Without them, every `from noosphere.coherence ...` raised
# ImportError at package-load time, so real CLI commands (synthesize, ask,
# coherence-eval) crashed before running anything.
#
# Each class here is defined from concrete usage in the consuming modules —
# I traced every constructor call and attribute access. Enum values come
# from the literal strings passed to the constructors and compared against in
# conditionals. For a few complex holders (e.g. AdversarialGeneratorBundle)
# I've used `extra='allow'` so downstream JSON-schema consumers don't break
# if the LLM returns additional fields.
# ─────────────────────────────────────────────────────────────────────────────


class StrictModel(BaseModel):
    """Base class for models that must strictly match their declared schema.

    Used by predictive_extractor._Draft and PredictiveExtractionBundle to
    validate LLM output — the goal there is to catch hallucinated fields
    rather than silently accept them.
    """
    model_config = ConfigDict(strict=True, extra='forbid')


class ClaimType(str, Enum):
    """High-level semantic type of a Claim.

    ClaimTypeVerifier iterates ``[e.value for e in ClaimType]`` and passes
    them to a zero-shot NLI classifier as candidate labels, so the values
    are intentionally plain English adjectives the classifier can reason
    about ("This statement is {factual}.").
    """
    FACTUAL = "factual"
    METHODOLOGICAL = "methodological"
    NORMATIVE = "normative"
    PREDICTIVE = "predictive"
    DEFINITIONAL = "definitional"
    INTERPRETIVE = "interpretive"


class ClaimOrigin(str, Enum):
    """Provenance of a Claim — who or what surfaced it.

    Values are derived from the set of origins referenced throughout the
    codebase (see adversarial.py, voices.py, literature.py, retrieval.py).
    """
    FOUNDER = "founder"
    # Text in the upload that isn't the founder's own assertion —
    # interview prompts, debate positions being argued against, quoted
    # opposing views, rhetorical challenges. Surfaced so downstream
    # systems (coherence, contradictions, codex sync) can drop or tag
    # them rather than treat them as founder beliefs.
    EXTERNAL = "external"
    LITERATURE = "literature"
    ADVERSARIAL = "adversarial"
    VOICE = "voice"
    SYSTEM = "system"


class JudgePriorScoreRef(BaseModel):
    """A single (layer, score) reference cited by the LLM judge.

    Emitted by the judge to indicate which prior layer scores it
    consulted when arriving at its verdict. `coherence.redteam` asserts
    the judge's explanation actually cites these layers by name + value.
    """
    layer: str
    value: float


class LLMJudgeVerdictPacket(BaseModel):
    """Structured output from the LLM judge on a coherence pair.

    Fields mirror the schema the judge prompt asks the model to produce.
    ``cited_prior_scores`` feeds the rationalisation check in
    ``coherence.redteam.explanation_cites_prior_layers``.
    """
    verdict: CoherenceVerdict
    confidence: float
    explanation: str
    cited_prior_scores: list[JudgePriorScoreRef] = []


class EngagementPointer(BaseModel):
    """A pointer from an adversarial conclusion back into the firm's own claims.

    Generated by ``adversarial.find_engagement_pointers`` when a new
    objection overlaps terminologically with existing firm claims — so
    founders can quickly jump from a critique to the material they
    already wrote on the same topic.
    """
    claim_id: str
    artifact_uri: str = ""
    excerpt: str = ""
    relevance_note: str = ""


class _AtomicObjectionClaim(BaseModel):
    """Individual stripped-down claim within an AdversarialObjectionDraft."""
    model_config = ConfigDict(extra='allow')
    text: str = ""


class AdversarialObjectionDraft(BaseModel):
    """One objection as drafted by the adversarial LLM pipeline.

    Used as input to ``adversarial.persist_objection_claims`` and to the
    Round-3 AdversarialChallenge builder. ``extra='allow'`` so we don't
    reject extra fields the model adds for its own bookkeeping.
    """
    model_config = ConfigDict(extra='allow')
    tradition: str = ""
    primary_attack_vector: str = ""
    objection_text: str = ""
    atomic_claims: list[str] = []
    cited_thinkers: list[str] = []
    citation_style: str = ""


class AdversarialGeneratorBundle(BaseModel):
    """LLM output envelope containing a list of AdversarialObjectionDrafts.

    ``adversarial._generator_schema_json()`` passes this model's schema
    to the LLM as the expected output shape, so changes here change the
    prompt contract.
    """
    model_config = ConfigDict(extra='allow')
    objections: list[AdversarialObjectionDraft] = []


class HumanAdversarialOverride(BaseModel):
    """Manual founder override on an adversarial challenge.

    ``ch.human_override.kind`` is checked against "addressed" and "fatal"
    in the gate logic — those are the two meaningful states. A plain str
    is used rather than an enum to match the existing on-disk audit
    payloads.
    """
    model_config = ConfigDict(extra='allow')
    kind: str = ""
    rationale: str = ""
    author: str = ""
    at: Optional[datetime] = None


class RelativePositionEntry(BaseModel):
    """One voice's stance relative to the firm's firm-held principles.

    Built by ``voices.compute_relative_positions`` — one entry per voice
    we could score against the current principles.
    """
    voice_id: str
    voice_name: str
    verdict_vs_firm: str
    confidence: float = 0.0
    representative_voice_claim_ids: list[str] = []
    summary: str = ""


class FounderIntellectualView(BaseModel):
    """Snapshot of one founder's intellectual position across topics.

    Built by ``founders.build_founder_intellectual_view``. Largely a view
    model — stored as JSON, not relational — so structural drift is
    tolerated via ``extra='allow'``.
    """
    model_config = ConfigDict(extra='allow')
    founder_id: str
    founder_name: str = ""
    positions_by_topic: dict[str, Any] = {}
    drift_event_ids: list[str] = []
    cross_founder_contradiction_edges: list[Any] = []
    sole_dissenter_topics: list[str] = []


# ── Core Data Models ─────────────────────────────────────────────────────────

class Speaker(BaseModel):
    """A participant in the podcast."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    role: str = "founder"  # founder | guest | moderator


class InputSourceType(str, Enum):
    """Type of input source."""
    TRANSCRIPT = "transcript"
    WRITTEN = "written"
    EXTERNAL = "external"


class InputSource(BaseModel):
    """An input source (transcript, written document, etc.)."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_type: InputSourceType = InputSourceType.TRANSCRIPT
    title: str = ""
    episode_id: str = ""
    date: Optional[date] = None
    file_path: str = ""
    author_id: str = ""
    author_name: str = ""
    description: str = ""

    model_config = ConfigDict(extra='forbid')


class FounderProfile(BaseModel):
    """A stable identity for a podcast founder, persisted across episodes."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    speaker_id: Optional[str] = None
    role: str = "founder"
    primary_domains: list = Field(default_factory=list)
    claim_count: int = 0
    written_input_count: int = 0
    methodological_claim_count: int = 0
    substantive_claim_count: int = 0
    methodological_orientation: float = 0.5
    principle_ids: list[str] = Field(default_factory=list)
    last_active: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(extra='forbid')


class TranscriptSegment(BaseModel):
    """A contiguous segment of speech from one speaker."""
    speaker: Speaker
    text: str
    start_time: Optional[float] = None   # seconds from episode start
    end_time: Optional[float] = None
    episode_id: str = ""


class Claim(BaseModel):
    """
    An atomic proposition extracted from a transcript segment.

    This is the fundamental unit of analysis. A claim is a single
    assertoric sentence that can be true or false, attributed to a
    speaker, and positioned in embedding space.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str                                   # The proposition itself
    speaker: Speaker                            # Who said it
    episode_id: str                             # Which episode
    episode_date: date                          # When
    segment_context: str = ""                   # Surrounding paragraph for disambiguation
    disciplines: list[Discipline] = []          # Relevant domains
    embedding: Optional[list[float]] = None     # SBERT embedding vector
    confidence: float = 1.0                     # Extraction confidence (0-1)
    timestamp_seconds: Optional[float] = None   # Position in episode
    source_id: str = ""                         # Source artifact or chunk ID
    voice_id: str = ""                          # Voice profile ID
    # Round 3 additions
    freshness: Freshness = Freshness.FRESH
    last_validated_at: Optional[datetime] = None
    # Classification — pydantic v2 defaults to `extra='ignore'`, which means
    # constructor calls like `Claim(claim_type=ClaimType.METHODOLOGICAL, ...)`
    # scattered across voices.py, adversarial.py, literature.py were
    # silently dropping the field. ClaimTypeVerifier even sets
    # `claim.claim_type_verified` / `claim.claim_type_disagreement` at
    # runtime, which would AttributeError on read without these.
    claim_type: ClaimType = ClaimType.FACTUAL
    claim_origin: ClaimOrigin = ClaimOrigin.FOUNDER
    claim_type_verified: Optional[ClaimType] = None
    claim_type_disagreement: bool = False
    # Per-claim "because/see also" pointers. Concretely these are the
    # contradiction-pair IDs (Dialectic session ingest), citation anchors
    # (Papers / PDFs), or transcript segment IDs that originally grounded
    # the extraction. Omitted from the schema caused silent data loss:
    # `ingest_artifacts.ingest_dialectic_session_jsonl` was already
    # passing `evidence_pointers=…` to this constructor, but pydantic v2
    # drops unknown fields by default, so the round-trip lost them.
    evidence_pointers: list[str] = []
    # Transcript alignment — used by ingest_papers and ingest_dialectic
    # to thread claims back to their source chunks for traceability.
    chunk_id: str = ""


class Principle(BaseModel):
    """
    A distilled, stable belief held by the firm.

    Principles are derived from clusters of claims across multiple episodes.
    They represent the firm's enduring intellectual commitments — the things
    the founders believe deeply enough to act on repeatedly.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str                                   # Canonical statement
    description: str = ""                       # Elaborated explanation
    disciplines: list[Discipline] = []
    conviction: ConvictionLevel = ConvictionLevel.MODERATE
    conviction_score: float = 0.5               # Continuous 0-1
    embedding: Optional[list[float]] = None

    # Evidence trail
    supporting_claims: list[str] = []           # Claim IDs
    first_appeared: Optional[date] = None
    last_reinforced: Optional[date] = None
    mention_count: int = 0

    # Coherence metrics (from the 6-layer engine)
    coherence_score: Optional[float] = None     # Composite Coh(Γ)
    consistency_score: Optional[float] = None   # S₁: formal consistency
    argumentation_score: Optional[float] = None # S₂: grounded extension ratio
    probabilistic_score: Optional[float] = None # S₃: Roche's measure
    geometric_score: Optional[float] = None     # S₄: embedding coherence
    compression_score: Optional[float] = None   # S₅: information-theoretic

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    tags: list[str] = []


class Relationship(BaseModel):
    """A directed edge in the knowledge graph."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str                              # Principle or Claim ID
    target_id: str
    relation: RelationType
    strength: float = 1.0                       # 0-1, how strong the relationship
    evidence: str = ""                          # Why this relationship exists
    detected_by: str = "extraction"             # extraction | coherence | geometric | manual
    created_at: datetime = Field(default_factory=datetime.now)


class Episode(BaseModel):
    """Metadata for a single podcast episode."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    number: int
    date: date
    title: str = ""
    duration_seconds: Optional[float] = None
    transcript_path: str = ""
    speakers: list[Speaker] = []
    claim_count: int = 0
    new_principles: list[str] = []              # Principle IDs first appearing
    reinforced_principles: list[str] = []       # Principle IDs mentioned again


class ContradictionFinding(BaseModel):
    """One high-severity contradiction pair surfaced by the coherence engine.

    Emitted by ``CoherenceEngine._identify_contradictions``; consumed by
    ``cli.py`` (renders the "Detected Contradictions" table) and by
    ``orchestrator`` when promoting findings into the store.

    Kept intentionally minimal — if callers need more context they can
    look up the underlying propositions by id.
    """
    id_a: str                                   # proposition / claim id (first)
    id_b: str                                   # proposition / claim id (second)
    severity: float                             # contradiction score ∈ [0, 1]


class CoherenceReport(BaseModel):
    """Output of the 6-layer coherence engine on a set of principles.

    Field note: ``contradictions_found`` used to be declared as
    ``list[tuple[str, str, float]]`` but the engine (see
    ``coherence/engine.py::_identify_contradictions``) always builds
    ``ContradictionFinding`` objects. The tuple form was never emitted —
    the declaration was stale. Any importer of ``noosphere.coherence``
    was also tripping an ``ImportError`` because the engine imports
    ``ContradictionFinding`` from this module, so the whole package was
    un-importable. Both ends are now aligned.
    """
    principle_ids: list[str]
    composite_score: float                      # Coh(Γ) ∈ [0, 1]
    layer_scores: dict[str, float]              # S₁ through S₆
    contradictions_found: list[ContradictionFinding] = []
    weakest_links: list[str] = []               # Principle IDs with lowest support
    six_layer: Optional[SixLayerScore] = None   # Full six-layer breakdown
    generated_at: datetime = Field(default_factory=datetime.now)


class InferenceQuery(BaseModel):
    """A question posed to the inference engine."""
    question: str
    context: str = ""                           # Additional context
    disciplines: list[Discipline] = []          # Scope the answer
    require_coherence: bool = True              # Must be consistent with principles


class InferenceResult(BaseModel):
    """The inference engine's response."""
    query: InferenceQuery
    answer: str
    reasoning_chain: list[str] = []             # Step-by-step from principles
    principles_used: list[str] = []             # Principle IDs grounding the answer
    confidence: float = 0.0                     # How well-grounded in principles
    coherence_with_corpus: float = 0.0          # Alignment score
    caveats: list[str] = []                     # Where principles are silent or ambiguous


class TemporalSnapshot(BaseModel):
    """State of a principle at a point in time."""
    principle_id: str
    episode_id: str
    date: date
    conviction_score: float
    mention_count_cumulative: int
    embedding: Optional[list[float]] = None     # For tracking drift
    drift_from_origin: Optional[float] = None   # Cosine distance from first embedding


# ── Round 3: New models (Conclusion, Topic) ──────────────────────────────────

class Topic(BaseModel):
    """A topic in the knowledge graph."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    label: str = ""
    cluster_version: str = ""
    description: str = ""
    disciplines: list[Discipline] = []
    embedding: Optional[list[float]] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    # Round 3 additions
    freshness: Freshness = Freshness.FRESH
    last_validated_at: Optional[datetime] = None


class Conclusion(BaseModel):
    """A reasoned conclusion drawn from principles and claims."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    reasoning: str = ""
    confidence_tier: ConfidenceTier = ConfidenceTier.MODERATE
    principles_used: list[str] = []
    claims_used: list[str] = []
    confidence: float = 0.0
    disciplines: list[Discipline] = []
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    # Round 3 additions
    freshness: Freshness = Freshness.FRESH
    last_validated_at: Optional[datetime] = None


class CurrentEvent(SQLModel, table=True):
    """External event observed by the Currents pipeline.

    Attribute names are Pythonic snake_case; Column(name=...) preserves the
    camelCase Prisma column names in the shared database.
    """

    __tablename__ = "CurrentEvent"
    __table_args__ = (
        UniqueConstraint("dedupeHash", name="CurrentEvent_dedupeHash_key"),
        Index("CurrentEvent_organizationId_observedAt_idx", "organizationId", "observedAt"),
        Index("CurrentEvent_organizationId_status_idx", "organizationId", "status"),
    )

    id: str = SQLField(default_factory=_new_cuid, primary_key=True)
    organization_id: str = SQLField(sa_column=Column("organizationId", String, nullable=False))
    source: CurrentEventSource = SQLField(sa_column=Column("source", String, nullable=False))
    external_id: str = SQLField(sa_column=Column("externalId", String, nullable=False))
    author_handle: Optional[str] = SQLField(default=None, sa_column=Column("authorHandle", String, nullable=True))
    text: str = SQLField(sa_column=Column("text", Text, nullable=False))
    url: Optional[str] = SQLField(default=None, sa_column=Column("url", String, nullable=True))
    captured_at: datetime = SQLField(default_factory=_now, sa_column=Column("capturedAt", SADateTime, nullable=False))
    observed_at: datetime = SQLField(sa_column=Column("observedAt", SADateTime, nullable=False))
    topic_hint: Optional[str] = SQLField(default=None, sa_column=Column("topicHint", String, nullable=True))
    is_near_duplicate: bool = SQLField(default=False, sa_column=Column("isNearDuplicate", SABoolean, nullable=False))
    embedding: Optional[bytes] = SQLField(default=None, sa_column=Column("embedding", LargeBinary, nullable=True))
    status: CurrentEventStatus = SQLField(
        default=CurrentEventStatus.OBSERVED,
        sa_column=Column("status", String, nullable=False),
    )
    dedupe_hash: str = SQLField(sa_column=Column("dedupeHash", String, nullable=False))
    created_at: datetime = SQLField(default_factory=_now, sa_column=Column("createdAt", SADateTime, nullable=False))
    updated_at: datetime = SQLField(default_factory=_now, sa_column=Column("updatedAt", SADateTime, nullable=False))


class EventOpinion(SQLModel, table=True):
    """Firm opinion generated from a CurrentEvent and grounded in citations."""

    __tablename__ = "EventOpinion"
    __table_args__ = (
        Index("EventOpinion_organizationId_generatedAt_idx", "organizationId", "generatedAt"),
        Index("EventOpinion_eventId_idx", "eventId"),
    )

    id: str = SQLField(default_factory=_new_cuid, primary_key=True)
    organization_id: str = SQLField(sa_column=Column("organizationId", String, nullable=False))
    event_id: str = SQLField(sa_column=Column("eventId", String, nullable=False))
    stance: OpinionStance = SQLField(sa_column=Column("stance", String, nullable=False))
    confidence: float = SQLField(sa_column=Column("confidence", SAFloat, nullable=False))
    headline: str = SQLField(sa_column=Column("headline", String(140), nullable=False))
    body_markdown: str = SQLField(sa_column=Column("bodyMarkdown", Text, nullable=False))
    uncertainty_notes: list[str] = SQLField(
        default_factory=list,
        sa_column=Column("uncertaintyNotes", _StringListType(), nullable=False),
    )
    topic_hint: Optional[str] = SQLField(default=None, sa_column=Column("topicHint", String, nullable=True))
    model_name: str = SQLField(sa_column=Column("modelName", String, nullable=False))
    prompt_tokens: int = SQLField(default=0, sa_column=Column("promptTokens", SAInteger, nullable=False))
    completion_tokens: int = SQLField(default=0, sa_column=Column("completionTokens", SAInteger, nullable=False))
    abstention_reason: Optional[AbstentionReason] = SQLField(
        default=None,
        sa_column=Column("abstentionReason", String, nullable=True),
    )
    generated_at: datetime = SQLField(default_factory=_now, sa_column=Column("generatedAt", SADateTime, nullable=False))
    revoked_at: Optional[datetime] = SQLField(default=None, sa_column=Column("revokedAt", SADateTime, nullable=True))
    revoked_reason: Optional[str] = SQLField(default=None, sa_column=Column("revokedReason", String, nullable=True))


class OpinionCitation(SQLModel, table=True):
    """Verbatim source span grounding one EventOpinion."""

    __tablename__ = "OpinionCitation"
    __table_args__ = (
        Index("OpinionCitation_opinionId_idx", "opinionId"),
        Index("OpinionCitation_conclusionId_idx", "conclusionId"),
        Index("OpinionCitation_claimId_idx", "claimId"),
    )

    id: str = SQLField(default_factory=_new_cuid, primary_key=True)
    opinion_id: str = SQLField(sa_column=Column("opinionId", String, nullable=False))
    source_kind: str = SQLField(sa_column=Column("sourceKind", String, nullable=False))
    conclusion_id: Optional[str] = SQLField(default=None, sa_column=Column("conclusionId", String, nullable=True))
    claim_id: Optional[str] = SQLField(default=None, sa_column=Column("claimId", String, nullable=True))
    quoted_span: str = SQLField(sa_column=Column("quotedSpan", Text, nullable=False))
    retrieval_score: float = SQLField(sa_column=Column("retrievalScore", SAFloat, nullable=False))
    is_revoked: bool = SQLField(default=False, sa_column=Column("isRevoked", SABoolean, nullable=False))
    revoked_at: Optional[datetime] = SQLField(default=None, sa_column=Column("revokedAt", SADateTime, nullable=True))
    revoked_reason: Optional[str] = SQLField(default=None, sa_column=Column("revokedReason", String, nullable=True))


class PublishedConclusion(SQLModel, table=True):
    """Public `/c/[slug]` snapshot shared by conclusions and generated articles."""

    __tablename__ = "PublishedConclusion"
    __table_args__ = (
        UniqueConstraint("slug", "version", name="PublishedConclusion_slug_version_key"),
        Index("PublishedConclusion_organizationId_idx", "organizationId"),
        Index("PublishedConclusion_slug_idx", "slug"),
        Index("PublishedConclusion_kind_publishedAt_idx", "kind", "publishedAt"),
    )

    id: str = SQLField(default_factory=_new_cuid, primary_key=True)
    organization_id: str = SQLField(sa_column=Column("organizationId", String, nullable=False))
    source_conclusion_id: str = SQLField(sa_column=Column("sourceConclusionId", String, nullable=False))
    slug: str = SQLField(sa_column=Column("slug", String, nullable=False))
    version: int = SQLField(default=1, sa_column=Column("version", SAInteger, nullable=False))
    kind: str = SQLField(default="CONCLUSION", sa_column=Column("kind", String, nullable=False))
    discounted_confidence: float = SQLField(sa_column=Column("discountedConfidence", SAFloat, nullable=False))
    stated_confidence: float = SQLField(default=0.0, sa_column=Column("statedConfidence", SAFloat, nullable=False))
    calibration_discount_reason: str = SQLField(default="", sa_column=Column("calibrationDiscountReason", String, nullable=False))
    payload_json: str = SQLField(default="{}", sa_column=Column("payloadJson", Text, nullable=False))
    doi: str = SQLField(default="", sa_column=Column("doi", String, nullable=False))
    zenodo_record_id: str = SQLField(default="", sa_column=Column("zenodoRecordId", String, nullable=False))
    published_at: datetime = SQLField(default_factory=_now, sa_column=Column("publishedAt", SADateTime, nullable=False))


class FollowUpSession(SQLModel, table=True):
    """Anonymous follow-up chat session keyed by a rotating fingerprint."""

    __tablename__ = "FollowUpSession"
    __table_args__ = (
        Index("FollowUpSession_opinionId_lastActivityAt_idx", "opinionId", "lastActivityAt"),
        Index("FollowUpSession_clientFingerprint_createdAt_idx", "clientFingerprint", "createdAt"),
    )

    id: str = SQLField(default_factory=_new_cuid, primary_key=True)
    opinion_id: str = SQLField(sa_column=Column("opinionId", String, nullable=False))
    client_fingerprint: str = SQLField(sa_column=Column("clientFingerprint", String, nullable=False))
    created_at: datetime = SQLField(default_factory=_now, sa_column=Column("createdAt", SADateTime, nullable=False))
    last_activity_at: datetime = SQLField(default_factory=_now, sa_column=Column("lastActivityAt", SADateTime, nullable=False))


class FollowUpMessage(SQLModel, table=True):
    """One message in an anonymous follow-up session."""

    __tablename__ = "FollowUpMessage"
    __table_args__ = (
        Index("FollowUpMessage_sessionId_createdAt_idx", "sessionId", "createdAt"),
    )

    id: str = SQLField(default_factory=_new_cuid, primary_key=True)
    session_id: str = SQLField(sa_column=Column("sessionId", String, nullable=False))
    role: FollowUpRole = SQLField(sa_column=Column("role", String, nullable=False))
    content: str = SQLField(sa_column=Column("content", Text, nullable=False))
    citations: Optional[Any] = SQLField(default=None, sa_column=Column("citations", JSON, nullable=True))
    created_at: datetime = SQLField(default_factory=_now, sa_column=Column("createdAt", SADateTime, nullable=False))


class ForecastMarket(SQLModel, table=True):
    """External prediction-market mirror owned by the Forecasts pipeline."""

    __tablename__ = "ForecastMarket"
    __table_args__ = (
        UniqueConstraint("source", "externalId", name="ForecastMarket_source_externalId_key"),
        Index("ForecastMarket_organizationId_status_closeTime_idx", "organizationId", "status", "closeTime"),
        Index("ForecastMarket_source_category_idx", "source", "category"),
        Index("ForecastMarket_updatedAt_idx", "updatedAt"),
    )

    id: str = SQLField(default_factory=_new_cuid, primary_key=True)
    organization_id: str = SQLField(sa_column=Column("organizationId", String, nullable=False))
    source: ForecastSource = SQLField(sa_column=Column("source", String, nullable=False))
    external_id: str = SQLField(sa_column=Column("externalId", String, nullable=False))
    title: str = SQLField(sa_column=Column("title", String(280), nullable=False))
    description: Optional[str] = SQLField(default=None, sa_column=Column("description", Text, nullable=True))
    resolution_criteria: Optional[str] = SQLField(default=None, sa_column=Column("resolutionCriteria", Text, nullable=True))
    category: Optional[str] = SQLField(default=None, sa_column=Column("category", String, nullable=True))
    current_yes_price: Optional[Decimal] = SQLField(default=None, sa_column=Column("currentYesPrice", Numeric(8, 6), nullable=True))
    current_no_price: Optional[Decimal] = SQLField(default=None, sa_column=Column("currentNoPrice", Numeric(8, 6), nullable=True))
    volume: Optional[Decimal] = SQLField(default=None, sa_column=Column("volume", Numeric(18, 4), nullable=True))
    open_time: Optional[datetime] = SQLField(default=None, sa_column=Column("openTime", SADateTime, nullable=True))
    close_time: Optional[datetime] = SQLField(default=None, sa_column=Column("closeTime", SADateTime, nullable=True))
    resolved_at: Optional[datetime] = SQLField(default=None, sa_column=Column("resolvedAt", SADateTime, nullable=True))
    resolved_outcome: Optional[ForecastOutcome] = SQLField(default=None, sa_column=Column("resolvedOutcome", String, nullable=True))
    raw_payload: dict[str, Any] = SQLField(default_factory=dict, sa_column=Column("rawPayload", JSON, nullable=False))
    status: ForecastMarketStatus = SQLField(
        default=ForecastMarketStatus.OPEN,
        sa_column=Column("status", String, nullable=False),
    )
    created_at: datetime = SQLField(default_factory=_now, sa_column=Column("createdAt", SADateTime, nullable=False))
    updated_at: datetime = SQLField(default_factory=_now, sa_column=Column("updatedAt", SADateTime, nullable=False))


class ForecastPrediction(SQLModel, table=True):
    """Source-grounded probability forecast for one external market."""

    __tablename__ = "ForecastPrediction"
    __table_args__ = (
        Index("ForecastPrediction_organizationId_status_createdAt_idx", "organizationId", "status", "createdAt"),
        Index("ForecastPrediction_marketId_createdAt_idx", "marketId", "createdAt"),
        Index("ForecastPrediction_liveAuthorizedAt_idx", "liveAuthorizedAt"),
    )

    id: str = SQLField(default_factory=_new_cuid, primary_key=True)
    market_id: str = SQLField(sa_column=Column("marketId", String, nullable=False))
    organization_id: str = SQLField(sa_column=Column("organizationId", String, nullable=False))
    probability_yes: Optional[Decimal] = SQLField(default=None, sa_column=Column("probabilityYes", Numeric(8, 6), nullable=True))
    confidence_low: Optional[Decimal] = SQLField(default=None, sa_column=Column("confidenceLow", Numeric(8, 6), nullable=True))
    confidence_high: Optional[Decimal] = SQLField(default=None, sa_column=Column("confidenceHigh", Numeric(8, 6), nullable=True))
    headline: str = SQLField(sa_column=Column("headline", String(140), nullable=False))
    reasoning: str = SQLField(sa_column=Column("reasoning", Text, nullable=False))
    status: ForecastPredictionStatus = SQLField(sa_column=Column("status", String, nullable=False))
    abstention_reason: Optional[str] = SQLField(default=None, sa_column=Column("abstentionReason", String, nullable=True))
    topic_hint: Optional[str] = SQLField(default=None, sa_column=Column("topicHint", String, nullable=True))
    model_name: str = SQLField(sa_column=Column("modelName", String, nullable=False))
    prompt_tokens: int = SQLField(default=0, sa_column=Column("promptTokens", SAInteger, nullable=False))
    completion_tokens: int = SQLField(default=0, sa_column=Column("completionTokens", SAInteger, nullable=False))
    live_authorized_at: Optional[datetime] = SQLField(default=None, sa_column=Column("liveAuthorizedAt", SADateTime, nullable=True))
    live_authorized_by: Optional[str] = SQLField(default=None, sa_column=Column("liveAuthorizedBy", String, nullable=True))
    created_at: datetime = SQLField(default_factory=_now, sa_column=Column("createdAt", SADateTime, nullable=False))
    updated_at: datetime = SQLField(default_factory=_now, sa_column=Column("updatedAt", SADateTime, nullable=False))


class ForecastCitation(SQLModel, table=True):
    """Verbatim source span grounding one ForecastPrediction."""

    __tablename__ = "ForecastCitation"
    __table_args__ = (
        Index("ForecastCitation_predictionId_idx", "predictionId"),
        Index("ForecastCitation_sourceType_sourceId_idx", "sourceType", "sourceId"),
    )

    id: str = SQLField(default_factory=_new_cuid, primary_key=True)
    prediction_id: str = SQLField(sa_column=Column("predictionId", String, nullable=False))
    source_type: str = SQLField(sa_column=Column("sourceType", String, nullable=False))
    source_id: str = SQLField(sa_column=Column("sourceId", String, nullable=False))
    quoted_span: str = SQLField(sa_column=Column("quotedSpan", Text, nullable=False))
    support_label: ForecastSupportLabel = SQLField(sa_column=Column("supportLabel", String, nullable=False))
    retrieval_score: Optional[float] = SQLField(default=None, sa_column=Column("retrievalScore", SAFloat, nullable=True))
    is_revoked: bool = SQLField(default=False, sa_column=Column("isRevoked", SABoolean, nullable=False))
    revoked_reason: Optional[str] = SQLField(default=None, sa_column=Column("revokedReason", String, nullable=True))
    created_at: datetime = SQLField(default_factory=_now, sa_column=Column("createdAt", SADateTime, nullable=False))


class ForecastResolution(SQLModel, table=True):
    """Terminal settlement and calibration score for one prediction."""

    __tablename__ = "ForecastResolution"
    __table_args__ = (
        UniqueConstraint("predictionId", name="ForecastResolution_predictionId_key"),
        Index("ForecastResolution_resolvedAt_idx", "resolvedAt"),
        Index("ForecastResolution_calibrationBucket_idx", "calibrationBucket"),
    )

    id: str = SQLField(default_factory=_new_cuid, primary_key=True)
    prediction_id: str = SQLField(sa_column=Column("predictionId", String, nullable=False))
    market_outcome: ForecastOutcome = SQLField(sa_column=Column("marketOutcome", String, nullable=False))
    brier_score: Optional[float] = SQLField(default=None, sa_column=Column("brierScore", SAFloat, nullable=True))
    log_loss: Optional[float] = SQLField(default=None, sa_column=Column("logLoss", SAFloat, nullable=True))
    calibration_bucket: Optional[Decimal] = SQLField(default=None, sa_column=Column("calibrationBucket", Numeric(3, 1), nullable=True))
    resolved_at: datetime = SQLField(sa_column=Column("resolvedAt", SADateTime, nullable=False))
    justification: str = SQLField(sa_column=Column("justification", Text, nullable=False))
    raw_settlement: Optional[Any] = SQLField(default=None, sa_column=Column("rawSettlement", JSON, nullable=True))
    created_at: datetime = SQLField(default_factory=_now, sa_column=Column("createdAt", SADateTime, nullable=False))


class ForecastBet(SQLModel, table=True):
    """Paper or gated-live bet linked to one ForecastPrediction."""

    __tablename__ = "ForecastBet"
    __table_args__ = (
        CheckConstraint('"mode" != \'LIVE\' OR "liveAuthorizedAt" IS NOT NULL', name="ForecastBet_live_requires_authorizedAt_check"),
        Index("ForecastBet_organizationId_mode_createdAt_idx", "organizationId", "mode", "createdAt"),
        Index("ForecastBet_predictionId_status_idx", "predictionId", "status"),
        Index("ForecastBet_externalOrderId_idx", "externalOrderId"),
        Index("ForecastBet_clientOrderId_idx", "clientOrderId"),
    )

    id: str = SQLField(default_factory=_new_cuid, primary_key=True)
    prediction_id: str = SQLField(sa_column=Column("predictionId", String, nullable=False))
    organization_id: str = SQLField(sa_column=Column("organizationId", String, nullable=False))
    mode: ForecastBetMode = SQLField(default=ForecastBetMode.PAPER, sa_column=Column("mode", String, nullable=False))
    exchange: ForecastExchange = SQLField(sa_column=Column("exchange", String, nullable=False))
    side: ForecastBetSide = SQLField(sa_column=Column("side", String, nullable=False))
    stake_usd: Decimal = SQLField(sa_column=Column("stakeUsd", Numeric(12, 2), nullable=False))
    entry_price: Decimal = SQLField(sa_column=Column("entryPrice", Numeric(8, 6), nullable=False))
    exit_price: Optional[Decimal] = SQLField(default=None, sa_column=Column("exitPrice", Numeric(8, 6), nullable=True))
    status: ForecastBetStatus = SQLField(sa_column=Column("status", String, nullable=False))
    external_order_id: Optional[str] = SQLField(default=None, sa_column=Column("externalOrderId", String, nullable=True))
    client_order_id: Optional[str] = SQLField(default=None, sa_column=Column("clientOrderId", String, nullable=True))
    settlement_pnl_usd: Optional[Decimal] = SQLField(default=None, sa_column=Column("settlementPnlUsd", Numeric(12, 2), nullable=True))
    live_authorized_at: Optional[datetime] = SQLField(default=None, sa_column=Column("liveAuthorizedAt", SADateTime, nullable=True))
    confirmed_at: Optional[datetime] = SQLField(default=None, sa_column=Column("confirmedAt", SADateTime, nullable=True))
    submitted_at: Optional[datetime] = SQLField(default=None, sa_column=Column("submittedAt", SADateTime, nullable=True))
    created_at: datetime = SQLField(default_factory=_now, sa_column=Column("createdAt", SADateTime, nullable=False))
    settled_at: Optional[datetime] = SQLField(default=None, sa_column=Column("settledAt", SADateTime, nullable=True))


class ForecastPortfolioState(SQLModel, table=True):
    """Singleton-per-organization bankroll, loss, and calibration state."""

    __tablename__ = "ForecastPortfolioState"
    __table_args__ = (
        UniqueConstraint("organizationId", name="ForecastPortfolioState_organizationId_key"),
    )

    id: str = SQLField(default_factory=_new_cuid, primary_key=True)
    organization_id: str = SQLField(sa_column=Column("organizationId", String, nullable=False))
    paper_balance_usd: Decimal = SQLField(sa_column=Column("paperBalanceUsd", Numeric(12, 2), nullable=False))
    live_balance_usd: Optional[Decimal] = SQLField(default=None, sa_column=Column("liveBalanceUsd", Numeric(12, 2), nullable=True))
    daily_loss_usd: Decimal = SQLField(default=Decimal("0"), sa_column=Column("dailyLossUsd", Numeric(12, 2), nullable=False))
    daily_loss_reset_at: datetime = SQLField(sa_column=Column("dailyLossResetAt", SADateTime, nullable=False))
    kill_switch_engaged: bool = SQLField(default=False, sa_column=Column("killSwitchEngaged", SABoolean, nullable=False))
    kill_switch_reason: Optional[str] = SQLField(default=None, sa_column=Column("killSwitchReason", String, nullable=True))
    total_resolved: int = SQLField(default=0, sa_column=Column("totalResolved", SAInteger, nullable=False))
    mean_brier_90d: Optional[float] = SQLField(default=None, sa_column=Column("meanBrier90d", SAFloat, nullable=True))
    mean_log_loss_90d: Optional[float] = SQLField(default=None, sa_column=Column("meanLogLoss90d", SAFloat, nullable=True))
    updated_at: datetime = SQLField(default_factory=_now, sa_column=Column("updatedAt", SADateTime, nullable=False))


class ForecastFollowUpSession(SQLModel, table=True):
    """Anonymous follow-up chat session scoped to one prediction."""

    __tablename__ = "ForecastFollowUpSession"
    __table_args__ = (
        Index("ForecastFollowUpSession_predictionId_lastActivityAt_idx", "predictionId", "lastActivityAt"),
        Index("ForecastFollowUpSession_clientFingerprint_createdAt_idx", "clientFingerprint", "createdAt"),
    )

    id: str = SQLField(default_factory=_new_cuid, primary_key=True)
    prediction_id: str = SQLField(sa_column=Column("predictionId", String, nullable=False))
    client_fingerprint: str = SQLField(sa_column=Column("clientFingerprint", String, nullable=False))
    created_at: datetime = SQLField(default_factory=_now, sa_column=Column("createdAt", SADateTime, nullable=False))
    last_activity_at: datetime = SQLField(default_factory=_now, sa_column=Column("lastActivityAt", SADateTime, nullable=False))


class ForecastFollowUpMessage(SQLModel, table=True):
    """One message in a Forecasts follow-up session."""

    __tablename__ = "ForecastFollowUpMessage"
    __table_args__ = (
        Index("ForecastFollowUpMessage_sessionId_createdAt_idx", "sessionId", "createdAt"),
    )

    id: str = SQLField(default_factory=_new_cuid, primary_key=True)
    session_id: str = SQLField(sa_column=Column("sessionId", String, nullable=False))
    role: ForecastFollowUpRole = SQLField(sa_column=Column("role", String, nullable=False))
    content: str = SQLField(sa_column=Column("content", Text, nullable=False))
    citations: Optional[Any] = SQLField(default=None, sa_column=Column("citations", JSON, nullable=True))
    created_at: datetime = SQLField(default_factory=_now, sa_column=Column("createdAt", SADateTime, nullable=False))


# === Round 3 additions ===

# ── Round 3: Methods and Registry ────────────────────────────────────────────

class MethodType(str, Enum):
    """Type of method operation."""
    EXTRACTION = "extraction"
    JUDGMENT = "judgment"
    AGGREGATION = "aggregation"
    TRANSFORMATION = "transformation"
    CALIBRATION = "calibration"


class MethodImplRef(BaseModel):
    """Reference to a method implementation."""
    module: str
    fn_name: str
    git_sha: str
    image_digest: Optional[str] = None

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class Method(BaseModel):
    """A registered method with versioned specification."""
    method_id: str
    name: str
    version: str
    method_type: MethodType
    input_schema: dict
    output_schema: dict
    description: str
    rationale: str
    preconditions: list[str]
    postconditions: list[str]
    dependencies: list[tuple[str, str]]
    implementation: MethodImplRef
    owner: str
    status: Literal["experimental", "active", "deprecated", "retired"]
    nondeterministic: bool
    created_at: datetime

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class MethodRef(BaseModel):
    """Reference to a method by name and version."""
    name: str
    version: str

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class MethodInvocation(BaseModel):
    """Record of a method invocation for audit trail."""
    id: str
    method_id: str
    input_hash: str
    output_hash: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    succeeded: bool
    error_kind: Optional[str] = None
    correlation_id: str
    tenant_id: str

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


# ── Round 3: Ledger ──────────────────────────────────────────────────────────

class Actor(BaseModel):
    """An actor in the system: human, method, or agent."""
    kind: Literal["human", "method", "agent"]
    id: str
    display_name: str

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class ContextMeta(BaseModel):
    """Context metadata for ledger entries."""
    tenant_id: str
    correlation_id: str
    orchestrator_run_id: Optional[str] = None

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class LedgerEntry(BaseModel):
    """Immutable audit ledger entry."""
    entry_id: str
    prev_hash: str
    timestamp: datetime
    actor: Actor
    method_id: Optional[str] = None
    inputs_hash: str
    outputs_hash: str
    inputs_ref: str
    outputs_ref: str
    context: ContextMeta
    signature: str
    signer_key_id: str

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


# ── Round 3: Cascade ─────────────────────────────────────────────────────────

class CascadeNodeKind(str, Enum):
    """Type of node in the cascade graph."""
    ARTIFACT = "artifact"
    CHUNK = "chunk"
    CLAIM = "claim"
    PRINCIPLE = "principle"
    CLUSTER = "cluster"
    CONCLUSION = "conclusion"
    EXTERNAL_SOURCE = "external_source"


class CascadeNode(BaseModel):
    """A node in the cascade graph."""
    node_id: str
    kind: CascadeNodeKind
    ref: str
    attrs: dict

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class CascadeEdgeRelation(str, Enum):
    """Relation type for cascade edges."""
    EXTRACTED_FROM = "extracted_from"
    COHERES_WITH = "coheres_with"
    CONTRADICTS = "contradicts"
    AGGREGATES = "aggregates"
    REFORMULATES = "reformulates"
    GENERALIZES = "generalizes"
    SPECIALIZES = "specializes"
    PREDICTS = "predicts"
    SUPPORTS = "supports"
    REFUTES = "refutes"
    DEPENDS_ON = "depends_on"


class CascadeEdge(BaseModel):
    """
    A directed edge in the cascade graph.
    
    NOTE: This model is NOT frozen because retracted_at must be mutable
    for retraction operations.
    """
    edge_id: str
    src: str
    dst: str
    relation: CascadeEdgeRelation
    method_invocation_id: str
    confidence: float
    unresolved: bool
    established_at: datetime
    retracted_at: Optional[datetime] = None

    model_config = ConfigDict(strict=True, extra='forbid')


# ── Round 3: Evaluation ──────────────────────────────────────────────────────

class OutcomeKind(str, Enum):
    """Type of outcome for evaluation."""
    BINARY = "binary"
    INTERVAL = "interval"
    PREFERENCE = "preference"


class Outcome(BaseModel):
    """A resolved outcome for calibration evaluation."""
    outcome_id: str
    kind: OutcomeKind
    event_ref: str
    resolution_source: str
    resolved_at: datetime
    value: Any

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class CorpusSelector(BaseModel):
    """Selector for corpus slicing."""
    as_of: datetime
    tenant_id_filter: Optional[list[str]] = None
    artifact_kind_filter: Optional[list[str]] = None

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class TemporalCut(BaseModel):
    """A temporal slice of the corpus for evaluation."""
    cut_id: str
    as_of: datetime
    corpus_slice: CorpusSelector
    embargoed: CorpusSelector
    embedding_version_pin: str
    outcomes: list[Outcome]

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class CalibrationMetrics(BaseModel):
    """Calibration metrics for evaluation."""
    brier: float
    log_loss: float
    ece: float
    reliability_bins: list[dict]
    resolution: float
    coverage: float

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class CounterfactualEvalRun(BaseModel):
    """A counterfactual evaluation run."""
    run_id: str
    method_ref: MethodRef
    cut_id: str
    metrics: CalibrationMetrics
    prediction_refs: list[str]
    created_at: datetime

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


# ── Round 3: External Battery ────────────────────────────────────────────────

class LicenseTag(str, Enum):
    """License tags for external corpora."""
    GJP_PUBLIC = "gjp_public"
    METACULUS_PUBLIC = "metaculus_public"
    CLAIM_REVIEW = "claim_review"
    REPLICATION_PUBLIC = "replication_public"
    CUSTOM = "custom"


class CorpusBundle(BaseModel):
    """An external corpus bundle."""
    source: str
    content_hash: str
    local_path: str
    license: LicenseTag
    fetched_at: datetime

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class ExternalItem(BaseModel):
    """An item from an external corpus."""
    source: str
    source_id: str
    question_text: str
    as_of: datetime
    resolved_at: Optional[datetime] = None
    outcome_type: OutcomeKind
    metadata: dict

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class BatteryRunResult(BaseModel):
    """Result of running a battery test."""
    run_id: str
    corpus_name: str
    method_ref: MethodRef
    per_item_results: list[dict]
    metrics: CalibrationMetrics
    failures: dict

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


# ── Round 3: Inverse ─────────────────────────────────────────────────────────

class ResolvedEvent(BaseModel):
    """A resolved event for inverse queries."""
    event_id: str
    description: str
    resolved_at: datetime
    evidence_refs: list[str]

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class InverseQuery(BaseModel):
    """An inverse query to find implications."""
    event: ResolvedEvent
    as_of: datetime
    methods: list[MethodRef]
    k: int = 50

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class Implication(BaseModel):
    """An implication found by inverse query."""
    corpus_ref: str
    entailment_score: float
    refutation_score: float
    relevance_weight: float
    severity: Literal["mild", "moderate", "severe"]

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class BlindspotReport(BaseModel):
    """Blindspot analysis for inverse query."""
    missing_entities: list[str]
    missing_mechanisms: list[str]
    adjacent_empty_topics: list[str]

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class InverseResult(BaseModel):
    """Result of an inverse query."""
    supporting: list[Implication]
    refuted: list[Implication]
    irrelevant: list[str]
    blindspot: BlindspotReport

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


# ── Round 3: Peer Review ─────────────────────────────────────────────────────

class Finding(BaseModel):
    """A finding from peer review."""
    severity: Literal["info", "minor", "major", "blocker"]
    category: str
    detail: str
    evidence: list[str]
    suggested_action: str

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class ReviewReport(BaseModel):
    """A peer review report."""
    report_id: str
    reviewer: str
    conclusion_id: str
    findings: list[Finding]
    overall_verdict: Literal["accept", "revise", "reject"]
    confidence: float
    completed_at: datetime
    method_invocation_ids: list[str]

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class Rebuttal(BaseModel):
    """A rebuttal to a review finding."""
    finding_id: str
    form: Literal["accept_and_revise", "reject_with_reason", "defer_as_open_question"]
    rationale: str
    attached_edit_ref: Optional[str] = None
    by_actor: Actor

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class SwarmReport(BaseModel):
    """A swarm review report."""
    conclusion_id: str
    reviews: list[ReviewReport]
    rebuttals: list[Rebuttal]

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


# ── Round 3: Transfer / Docs / Interop ───────────────────────────────────────

DomainTag = NewType("DomainTag", str)


class DatasetRef(BaseModel):
    """Reference to a dataset."""
    content_hash: str
    path: str

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class TransferStudy(BaseModel):
    """A transfer learning study."""
    study_id: str
    method_ref: MethodRef
    source_domain: DomainTag
    target_domain: DomainTag
    dataset: DatasetRef
    baseline_on_source: CalibrationMetrics
    result_on_target: CalibrationMetrics
    delta: dict
    qualitative_notes: str

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class MethodDoc(BaseModel):
    """Documentation for a method."""
    method_ref: MethodRef
    spec_md_path: str
    rationale_md_path: str
    examples_md_path: str
    calibration_md_path: str
    transfer_md_path: str
    operations_md_path: str
    doi: Optional[str] = None
    template_version: str
    signed_by: str

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class MIPManifest(BaseModel):
    """Method Interchange Package manifest."""
    name: str
    version: str
    methods: list[MethodRef]
    cascade_edge_schema: dict
    gate_check_schema: dict
    license: str
    content_hash: str
    signature: str

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


# ── Round 3: Decay ───────────────────────────────────────────────────────────

class DecayPolicyKind(str, Enum):
    """Type of decay policy."""
    FIXED_INTERVAL = "fixed_interval"
    EVIDENCE_CHANGED = "evidence_changed"
    METHOD_VERSION_BUMP = "method_version_bump"
    EMBEDDING_DRIFT = "embedding_drift"
    OUTCOME_OBSERVED = "outcome_observed"
    CALIBRATION_REGRESSION = "calibration_regression"
    ANY = "any"
    ALL = "all"


class DecayPolicy(BaseModel):
    """Policy for decay and revalidation."""
    policy_kind: DecayPolicyKind
    params: dict
    composition_children: list[DecayPolicy] = []

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class RevalidationResult(BaseModel):
    """Result of revalidation."""
    object_id: str
    outcome: Literal["confirmed", "disagreement", "refuted", "noop"]
    prior_tier: str
    new_tier: str
    ledger_entry_id: str

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


# ── Round 3: Rigor Gate ──────────────────────────────────────────────────────

class AuthorAttestation(BaseModel):
    """Author attestation for rigor gate submission."""
    author_id: str
    conflict_disclosures: list[str]
    acknowledgments: list[str]

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class CheckResult(BaseModel):
    """Result of a rigor gate check."""
    check_name: str
    pass_: bool
    detail: str
    ledger_entry_id: Optional[str] = None

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class RigorSubmission(BaseModel):
    """A submission to the rigor gate."""
    submission_id: str
    kind: Literal["conclusion", "method_doc", "eval_report", "dialectic_summary", "press_statement"]
    payload_ref: str
    author: Actor
    intended_venue: Literal["public_site", "rss", "social", "press_release", "api"]
    author_attestation: AuthorAttestation

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class RigorVerdict(BaseModel):
    """Verdict from the rigor gate."""
    verdict: Literal["pass", "fail", "pass_with_conditions"]
    checks_run: list[CheckResult]
    conditions: list[str]
    reviewed_by: list[Actor]
    ledger_entry_id: str

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class FounderOverride(BaseModel):
    """Founder override for rigor gate."""
    override_id: str
    submission_id: str
    founder_id: str
    overridden_checks: list[str]
    justification: str
    ledger_entry_id: str

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

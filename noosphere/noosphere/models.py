"""
Core data models for the Noosphere knowledge system.

Every model is a Pydantic BaseModel for serialization, validation, and
JSON round-tripping to disk. The fundamental unit is the Claim — an atomic
proposition extracted from a transcript, attributed to a speaker, and
positioned in embedding space.
"""

from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Optional, Any, Literal, NewType
from pydantic import BaseModel, Field, ConfigDict
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


class CoherenceReport(BaseModel):
    """Output of the 6-layer coherence engine on a set of principles."""
    principle_ids: list[str]
    composite_score: float                      # Coh(Γ) ∈ [0, 1]
    layer_scores: dict[str, float]              # S₁ through S₆
    contradictions_found: list[tuple[str, str, float]] = []  # (id_a, id_b, severity)
    weakest_links: list[str] = []               # Principle IDs with lowest support
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

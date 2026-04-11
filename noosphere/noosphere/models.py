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
from typing import Optional
from pydantic import BaseModel, Field
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


# ── Core Data Models ─────────────────────────────────────────────────────────

class Speaker(BaseModel):
    """A participant in the podcast."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    role: str = "founder"  # founder | guest | moderator


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

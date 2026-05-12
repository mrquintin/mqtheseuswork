"""Typed contract for empirical case studies extracted from sources.

The shape here is deliberately narrower than ``Conclusion`` /
``Claim``: a case is *observed situation* + *abstract logic it
instantiates*, not a free-form proposition. Future prompts need to
ask "did principle P, learned from case A, plausibly hold in case B?",
so the structure has to make actors, institutions, mechanism, and
outcome individually addressable.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CaseStudyKind(str, Enum):
    """How concretely a passage references a real-world case.

    The distinction matters because only the first two kinds are
    treated as empirical evidence. ``HYPOTHETICAL``, ``ANALOGY``, and
    ``ABSTRACT_CONCEPT`` are surfaced separately so downstream code
    can see what the passage was doing without confusing it with an
    observed case.
    """

    # A specific, named, real-world situation: "WeWork's 2019 IPO",
    # "the Hungarian forint crisis of 1995", "OpenAI's November 2023
    # board firing". Concrete enough that someone could go look it up.
    NAMED_CASE = "named_case"

    # An unnamed-but-observed case: "one mid-cap European bank we
    # advised through the 2011 stress tests". Real, but anonymized.
    BRIEF_EXAMPLE = "brief_example"

    # An invented situation used to illustrate a principle. "Imagine
    # a startup that..." Not evidence; structurally useful for
    # explanation only.
    HYPOTHETICAL = "hypothetical"

    # A structural parallel drawn between two domains. "Like a
    # central bank's reaction function..." Reasoning-by-similarity,
    # not an observed case.
    ANALOGY = "analogy"

    # A bare statement of principle with no situation attached.
    # "Markets punish overconfidence." No actor, no time, no
    # mechanism — just the rule.
    ABSTRACT_CONCEPT = "abstract_concept"


class EvidenceQuality(str, Enum):
    """How well-grounded the case is in the source itself.

    This is *not* a claim about the underlying world — it is a claim
    about the source passage. ``ASSERTED`` means the source states
    the case as fact; ``CITED`` means the source attributes it to a
    named external reference; ``ANECDOTAL`` means the source is the
    only witness; ``DISPUTED`` means the source notes ongoing
    disagreement about what happened.
    """

    CITED = "cited"
    ASSERTED = "asserted"
    ANECDOTAL = "anecdotal"
    DISPUTED = "disputed"
    UNKNOWN = "unknown"


class SourceSpan(BaseModel):
    """Pointer back into the source from which a case was extracted.

    ``source_quote`` is *verbatim* — the extractor refuses to emit a
    case whose ``source_quote`` is not literally present in the
    chunk text, which is how the "do not invent a case just because
    the source gestures at a theme" constraint is enforced.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = ""
    source_quote: str = ""
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None

    @field_validator("source_quote")
    @classmethod
    def _quote_is_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_quote must be a verbatim substring of the chunk text")
        return value


class AbstractPrincipleLink(BaseModel):
    """An abstract principle that a case instantiates.

    Kept structurally separate from the case so a single case can
    instantiate multiple principles (e.g. a bank failure may
    instantiate both "leverage punishes optimism" and "regulatory
    capture delays recognition") and so a principle drawn from case
    A can be tested against case B by structural match without
    re-reading prose.

    ``principle_text`` is required; ``principle_id`` is optional and
    populated only when the principle has already been linked to an
    existing ``Principle`` / ``Conclusion`` row in the registry.
    """

    model_config = ConfigDict(extra="forbid")

    principle_text: str
    principle_id: Optional[str] = None
    transfer_conditions: str = ""

    @field_validator("principle_text")
    @classmethod
    def _principle_text_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("principle_text must be non-empty")
        return value.strip()


class EmpiricalCaseStudy(BaseModel):
    """A grounded empirical case extracted from a source.

    Two layers are preserved deliberately:

    - the *concrete case* (``actors``, ``institutions``,
      ``time_period``, ``observed_mechanism``, ``outcome``) is what
      lets a later reader sanity-check whether the case actually
      happened as described;

    - the *abstract layer* (``stated_causal_claim``,
      ``linked_principles``) is what transfers to new situations.

    A case missing either layer is suspect: a "case" with no
    mechanism or outcome is a name-drop; a case with no principle
    link is decoration. The extractor refuses to emit either.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    kind: CaseStudyKind = CaseStudyKind.NAMED_CASE
    title: str = ""
    source_span: SourceSpan

    # Concrete case layer.
    actors: list[str] = Field(default_factory=list)
    institutions: list[str] = Field(default_factory=list)
    time_period: str = ""
    domain: str = ""
    observed_mechanism: str = ""
    outcome: str = ""

    # Abstract layer.
    stated_causal_claim: str = ""
    evidence_quality: EvidenceQuality = EvidenceQuality.UNKNOWN
    linked_principles: list[AbstractPrincipleLink] = Field(default_factory=list)

    def is_grounded(self) -> bool:
        """True iff both empirical-case and abstract layers are populated.

        Used by downstream readers to decide whether the case is
        comparable to another case (needs both layers) or only
        usable as illustration (only the concrete layer).
        """
        has_concrete = bool(
            self.observed_mechanism.strip()
            and self.outcome.strip()
            and (self.actors or self.institutions)
        )
        has_abstract = bool(self.stated_causal_claim.strip() or self.linked_principles)
        return has_concrete and has_abstract


class NonCaseMention(BaseModel):
    """A passage that mentions case-shaped material but is not a case.

    Recorded so the distinction between "no case here" and "case
    here but rejected" is auditable. A hypothetical that gets
    silently dropped looks identical to a passage with no case at
    all; recording it separately makes the extractor's behavior
    inspectable.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    kind: CaseStudyKind
    source_span: SourceSpan
    summary: str = ""


class CaseStudyExtraction(BaseModel):
    """All case-shaped material recovered from a single chunk.

    ``cases`` are the grounded empirical cases. ``non_case_mentions``
    are hypotheticals, analogies, and bare-abstract concepts that
    the extractor identified but is deliberately *not* treating as
    evidence.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = ""
    cases: list[EmpiricalCaseStudy] = Field(default_factory=list)
    non_case_mentions: list[NonCaseMention] = Field(default_factory=list)

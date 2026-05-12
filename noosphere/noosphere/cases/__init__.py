"""Empirical case-study extraction.

Sources frequently reference real-world cases (companies, founders,
institutions, political episodes, market events, technologies, schools,
media dynamics, historical examples). Treating each such mention as a
free-floating anecdote loses the structure that makes the case useful
later: the *abstract logic* a case instantiates is what transfers to
new situations, but only if the *concrete case* it came from stays
recoverable for sanity checks.

This package extracts cases as structured decision evidence with two
layers preserved:

1. the empirical case — actors, institutions, time period, observed
   mechanism, outcome, stated causal claim, evidence quality;
2. the abstract principle(s) the case instantiates, linked back so a
   later prompt can ask "does this principle plausibly transfer to
   case Y?" against a typed substrate rather than free text.

The extractor is deliberately conservative: a case is only emitted if
the LLM returns a verbatim ``source_quote`` that is literally present
in the chunk text. Themes, gestures, and "the author seems to be
thinking about Enron"-style fabrications are rejected. Hypotheticals,
analogies, and purely abstract concepts are classified into
``non_case_mentions`` so downstream code can see *why* a passage did
not produce a grounded case, rather than treating absence as silence.
"""

from noosphere.cases.models import (
    AbstractPrincipleLink,
    CaseStudyExtraction,
    CaseStudyKind,
    EmpiricalCaseStudy,
    EvidenceQuality,
    NonCaseMention,
    SourceSpan,
)
from noosphere.cases.extractor import CaseStudyExtractor

__all__ = [
    "AbstractPrincipleLink",
    "CaseStudyExtraction",
    "CaseStudyExtractor",
    "CaseStudyKind",
    "EmpiricalCaseStudy",
    "EvidenceQuality",
    "NonCaseMention",
    "SourceSpan",
]

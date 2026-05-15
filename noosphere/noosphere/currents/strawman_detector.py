"""Strawman detector for the Currents dialectic engine.

The reconciliation pass restates the firm's counter-claim in its
"strongest available form" before responding to it. The cardinal failure
mode is a restatement that *looks* like it engages the counter-claim but
quietly softens it — drops the counter-claim's load-bearing content,
shortens it to a vague gesture, or hedges it with diplomatic qualifiers
the firm's prior text never contained. A softened counter-claim is easy
to reconcile, and a too-easy reconciliation is exactly the dishonest
output this engine exists to prevent.

This module is the automated check that runs *after* a reconciliation is
generated. It compares the reconciliation's ``strongest_form_of_counter_
claim`` against the retrieved counter-claim's actual text and flags a
strawman when the restatement does not faithfully carry the counter.
``noosphere.currents.dialectic.generate_reconciliation`` calls
:func:`detect_strawman`; a positive verdict forces regeneration, and a
repeated strawman collapses to the honest "no canonical counter-claim"
note rather than persisting a soft reconciliation.

The detector is intentionally text-based and deterministic so the same
verdict is reproducible in the sample audit
(``noosphere/scripts/audit_currents_dialectic.py``) and in tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Thresholds are resolved from the unified config (Round 17 magic-number
# registry). These module constants are the documented fallback used only
# when the config layer is unavailable — they must mirror
# ``DialecticThresholds`` in ``noosphere.core.config``.
FALLBACK_CONTENT_COVERAGE_FLOOR = 0.50
FALLBACK_LENGTH_RATIO_FLOOR = 0.60

_TOKEN_RE = re.compile(r"[A-Za-z0-9]{3,}")

# Function words carry no contrastive content; including them in the
# coverage denominator would let a paraphrase score well by echoing
# connective tissue while dropping the claim's actual substance.
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "that",
        "this",
        "with",
        "from",
        "into",
        "for",
        "are",
        "was",
        "were",
        "has",
        "have",
        "had",
        "not",
        "but",
        "its",
        "his",
        "her",
        "their",
        "they",
        "them",
        "then",
        "than",
        "which",
        "what",
        "when",
        "where",
        "who",
        "whom",
        "will",
        "would",
        "could",
        "should",
        "can",
        "may",
        "might",
        "been",
        "being",
        "such",
        "also",
        "any",
        "all",
        "some",
        "more",
        "most",
        "very",
        "only",
        "over",
        "under",
        "about",
        "firm",
        "claim",
        "counter",
        "prior",
        "holds",
        "held",
        "view",
        "argues",
        "argued",
    }
)

# Hedges/qualifiers a softening paraphrase tends to introduce. Their
# presence is only a strawman signal when the prior text did not already
# use them — i.e. the restatement *added* the hedge to blunt the counter.
_SOFTENING_TERMS = (
    "arguably",
    "to some extent",
    "to a degree",
    "somewhat",
    "in some cases",
    "in certain cases",
    "may sometimes",
    "might sometimes",
    "could sometimes",
    "not entirely",
    "not necessarily",
    "not really",
    "does not fully",
    "doesn't fully",
    "on balance",
    "broadly speaking",
    "more or less",
    "a minor",
    "a limited",
    "a small",
    "relatively minor",
    "largely",
    "mostly",
    "for the most part",
    "some have suggested",
    "some argue",
    "some people",
    "certain observers",
    "one might think",
)


@dataclass(frozen=True)
class StrawmanVerdict:
    """The result of comparing a restatement against the real counter-claim.

    ``is_strawman`` is the veto the dialectic engine acts on. The remaining
    fields are surfaced into the reconciliation audit and the sample-audit
    report so a human can see *why* a restatement was rejected.
    """

    is_strawman: bool
    reason: str
    content_coverage: float
    length_ratio: float
    introduced_softeners: tuple[str, ...] = field(default_factory=tuple)
    counter_content_token_count: int = 0
    restatement_content_token_count: int = 0

    def as_audit_dict(self) -> dict[str, object]:
        return {
            "is_strawman": self.is_strawman,
            "reason": self.reason,
            "content_coverage": round(self.content_coverage, 4),
            "length_ratio": round(self.length_ratio, 4),
            "introduced_softeners": list(self.introduced_softeners),
            "counter_content_token_count": self.counter_content_token_count,
            "restatement_content_token_count": self.restatement_content_token_count,
        }


def _content_tokens(text: str) -> list[str]:
    """Lowercased content tokens — length >3, stopwords removed."""

    out: list[str] = []
    for match in _TOKEN_RE.finditer(text or ""):
        tok = match.group(0).lower()
        if len(tok) <= 3 or tok in _STOPWORDS:
            continue
        out.append(tok)
    return out


def _introduced_softeners(restatement: str, counter_text: str) -> tuple[str, ...]:
    """Softening phrases present in the restatement but not the prior text."""

    low_restatement = (restatement or "").lower()
    low_counter = (counter_text or "").lower()
    found: list[str] = []
    for term in _SOFTENING_TERMS:
        if term in low_restatement and term not in low_counter:
            found.append(term)
    return tuple(found)


def detect_strawman(
    *,
    counter_text: str,
    strongest_form: str,
    reconciliation_markdown: str = "",
    content_coverage_floor: float = FALLBACK_CONTENT_COVERAGE_FLOOR,
    length_ratio_floor: float = FALLBACK_LENGTH_RATIO_FLOOR,
) -> StrawmanVerdict:
    """Decide whether ``strongest_form`` faithfully restates ``counter_text``.

    Three independent softening signals, any one of which is a veto:

    1. **Dropped content.** The restatement preserves fewer than
       ``content_coverage_floor`` of the counter-claim's content tokens.
       A restatement that drops the claim's substance is not the claim.
    2. **Materially shortened.** The restatement has fewer content tokens
       than ``length_ratio_floor`` × the counter-claim's, *and* coverage
       is not near-total. A "strongest form" that is a terse gesture at
       the counter rather than its full force is a strawman even if every
       token it does keep is on-claim.
    3. **Introduced hedges.** The restatement adds diplomatic qualifiers
       ("arguably", "to some extent", "a minor", …) the firm's prior text
       did not use, *and* coverage is below total. Hedging the counter
       while paraphrasing it is the softening this engine forbids.

    ``reconciliation_markdown`` is accepted for symmetry with the audit
    record shape and reserved for future cross-checks; the verdict today
    is computed purely from the counter-claim text and its restatement.
    """

    restatement = (strongest_form or "").strip()
    counter = (counter_text or "").strip()

    if not counter:
        # Nothing to be faithful to — cannot be a strawman of an empty
        # counter-claim. The dialectic engine never reaches this path
        # with a real counter-claim, but guard it rather than divide by
        # zero.
        return StrawmanVerdict(
            is_strawman=False,
            reason="counter-claim text is empty; nothing to verify",
            content_coverage=1.0,
            length_ratio=1.0,
        )

    if not restatement:
        return StrawmanVerdict(
            is_strawman=True,
            reason=(
                "the reconciliation provided no strongest-form restatement "
                "of the counter-claim"
            ),
            content_coverage=0.0,
            length_ratio=0.0,
        )

    counter_tokens = _content_tokens(counter)
    restatement_tokens = _content_tokens(restatement)
    counter_token_set = set(counter_tokens)
    restatement_token_set = set(restatement_tokens)

    if not counter_tokens:
        # The counter-claim is all function words (degenerate); fall back
        # to a permissive verdict so we do not reject on a denominator
        # the detector cannot reason about.
        return StrawmanVerdict(
            is_strawman=False,
            reason="counter-claim carries no content tokens to verify against",
            content_coverage=1.0,
            length_ratio=1.0,
            counter_content_token_count=0,
            restatement_content_token_count=len(restatement_tokens),
        )

    overlap = len(counter_token_set & restatement_token_set)
    content_coverage = overlap / len(counter_token_set)
    length_ratio = len(restatement_tokens) / max(1, len(counter_tokens))
    introduced = _introduced_softeners(restatement, counter)

    # Signal 1 — dropped content.
    if content_coverage < content_coverage_floor:
        return StrawmanVerdict(
            is_strawman=True,
            reason=(
                f"restatement preserves only {content_coverage:.0%} of the "
                f"counter-claim's content (floor {content_coverage_floor:.0%}); "
                f"the strongest form drops the counter-claim's substance"
            ),
            content_coverage=content_coverage,
            length_ratio=length_ratio,
            introduced_softeners=introduced,
            counter_content_token_count=len(counter_tokens),
            restatement_content_token_count=len(restatement_tokens),
        )

    # Signal 2 — materially shortened. A near-total coverage restatement is
    # allowed to be tighter than the prior text (the firm may genuinely
    # state it more crisply); anything less must carry the counter's full
    # length.
    if length_ratio < length_ratio_floor and content_coverage < 0.85:
        return StrawmanVerdict(
            is_strawman=True,
            reason=(
                f"restatement is {length_ratio:.0%} the length of the "
                f"counter-claim (floor {length_ratio_floor:.0%}) without "
                f"near-total content coverage; the strongest form is a "
                f"terse gesture, not the counter-claim at full force"
            ),
            content_coverage=content_coverage,
            length_ratio=length_ratio,
            introduced_softeners=introduced,
            counter_content_token_count=len(counter_tokens),
            restatement_content_token_count=len(restatement_tokens),
        )

    # Signal 3 — introduced hedges.
    if introduced and content_coverage < 1.0:
        return StrawmanVerdict(
            is_strawman=True,
            reason=(
                "restatement introduces softening qualifiers the firm's "
                f"prior text did not use ({', '.join(introduced)}); a hedged "
                f"paraphrase is not the counter-claim at full force"
            ),
            content_coverage=content_coverage,
            length_ratio=length_ratio,
            introduced_softeners=introduced,
            counter_content_token_count=len(counter_tokens),
            restatement_content_token_count=len(restatement_tokens),
        )

    return StrawmanVerdict(
        is_strawman=False,
        reason=(
            f"restatement faithfully carries the counter-claim "
            f"(coverage {content_coverage:.0%}, length {length_ratio:.0%})"
        ),
        content_coverage=content_coverage,
        length_ratio=length_ratio,
        introduced_softeners=introduced,
        counter_content_token_count=len(counter_tokens),
        restatement_content_token_count=len(restatement_tokens),
    )


__all__ = [
    "FALLBACK_CONTENT_COVERAGE_FLOOR",
    "FALLBACK_LENGTH_RATIO_FLOOR",
    "StrawmanVerdict",
    "detect_strawman",
]

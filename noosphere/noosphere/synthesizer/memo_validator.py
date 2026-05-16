"""Memo body validator — the 10-section contract (prompt 11, Round 19).

Every :class:`~noosphere.models.InvestmentMemo` is rendered as a
structured markdown body. The body MUST contain ten sections in a
fixed order with section-specific length bounds. A memo missing any
section, or with a length violation, is rejected at build time — never
silently shipped.

The validator is pure: it operates on the rendered markdown body and
returns a :class:`ValidationResult`. The :func:`validate_memo_body`
function raises :class:`MemoValidationError` on rejection so the
builder can fail loudly; the underlying :func:`check_sections` returns
a structured report for surfaces that want to render the diff.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from noosphere.models import MEMO_SECTIONS


# ── Section anchors ────────────────────────────────────────────────


@dataclass(frozen=True)
class SectionSpec:
    """A single section of the 10-section memo contract.

    ``heading_pattern`` matches the section's H2 heading in the
    rendered markdown body. ``min_chars`` / ``max_chars`` enforce
    presence + soft length bounds; ``required`` is True for every
    section except IMPLIED_BET (which is omitted when the conclusion
    has no implied bet — the section heading still renders, but the
    body may be a single line stating that explicitly).
    """

    name: str
    heading: str
    heading_pattern: re.Pattern[str]
    min_chars: int
    max_chars: int
    required: bool = True


def _heading_re(text: str) -> re.Pattern[str]:
    # Tolerates a leading numeric prefix ("1. Header") that some renderers
    # insert when bullet-numbering memos.
    escaped = re.escape(text)
    return re.compile(
        rf"^##\s+(?:\d+\.\s+)?{escaped}\s*$",
        re.IGNORECASE | re.MULTILINE,
    )


SECTION_SPECS: tuple[SectionSpec, ...] = (
    SectionSpec(
        name="header",
        heading="Header",
        heading_pattern=_heading_re("Header"),
        min_chars=20,
        max_chars=2_000,
    ),
    SectionSpec(
        name="tldr",
        heading="TL;DR",
        heading_pattern=re.compile(
            r"^##\s+(?:\d+\.\s+)?TL;?\s*DR\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
        min_chars=20,
        # Spec: ≤ 80 words. 80 words ≈ 600 chars; we allow 800 to
        # accommodate citations and inline math.
        max_chars=800,
    ),
    SectionSpec(
        name="question_constituted",
        heading="Question constituted",
        heading_pattern=_heading_re("Question constituted"),
        min_chars=4,
        # Spec: ≤ 40 words.
        max_chars=400,
    ),
    SectionSpec(
        name="governing_principles",
        heading="Governing principles",
        heading_pattern=_heading_re("Governing principles"),
        min_chars=20,
        max_chars=8_000,
    ),
    SectionSpec(
        name="observed_inputs",
        heading="Observed inputs",
        heading_pattern=_heading_re("Observed inputs"),
        min_chars=4,
        max_chars=8_000,
    ),
    SectionSpec(
        name="reasoning_chain",
        heading="Reasoning chain",
        heading_pattern=_heading_re("Reasoning chain"),
        min_chars=40,
        max_chars=20_000,
    ),
    SectionSpec(
        name="implied_bet",
        heading="Implied bet",
        heading_pattern=_heading_re("Implied bet"),
        min_chars=4,
        max_chars=4_000,
        required=True,  # Section heading must exist even when the
        # body is a one-liner stating "no bet implied".
    ),
    SectionSpec(
        name="what_would_update_us",
        heading="What would update us",
        heading_pattern=_heading_re("What would update us"),
        min_chars=10,
        # Spec: ≤ 100 words.
        max_chars=1_000,
    ),
    SectionSpec(
        name="abstentions_and_caveats",
        heading="Abstentions and caveats",
        heading_pattern=_heading_re("Abstentions and caveats"),
        min_chars=4,
        # Spec: ≤ 80 words.
        max_chars=800,
    ),
    SectionSpec(
        name="provenance_audit",
        heading="Provenance audit",
        heading_pattern=_heading_re("Provenance audit"),
        min_chars=10,
        max_chars=4_000,
    ),
)


_SPEC_BY_NAME: dict[str, SectionSpec] = {s.name: s for s in SECTION_SPECS}
assert tuple(s.name for s in SECTION_SPECS) == MEMO_SECTIONS, (
    "SECTION_SPECS order must match models.MEMO_SECTIONS exactly"
)


# ── Result types ───────────────────────────────────────────────────


@dataclass
class SectionFinding:
    """Per-section result. ``found=False`` means the heading is missing."""

    name: str
    found: bool
    length: int = 0
    too_short: bool = False
    too_long: bool = False


@dataclass
class ValidationResult:
    ok: bool = True
    findings: list[SectionFinding] = field(default_factory=list)
    order_violation: Optional[str] = None
    errors: list[str] = field(default_factory=list)

    def first_error(self) -> Optional[str]:
        return self.errors[0] if self.errors else None


class MemoValidationError(ValueError):
    """Raised when a memo body fails the 10-section contract.

    The full :class:`ValidationResult` is attached as ``.result`` so a
    caller can render the diff (UI, CLI) without re-parsing the body.
    """

    def __init__(self, message: str, result: ValidationResult) -> None:
        super().__init__(message)
        self.result = result


# ── Core ───────────────────────────────────────────────────────────


def _section_bodies(body: str) -> dict[str, tuple[int, int]]:
    """Return ``{spec.name: (start, end)}`` for each heading found.

    Sections are delimited by the next heading in the document. Order
    is whatever order the body actually presents — the caller checks
    canonical order separately.
    """

    # Find every spec's heading position.
    hits: list[tuple[int, SectionSpec]] = []
    for spec in SECTION_SPECS:
        m = spec.heading_pattern.search(body)
        if m is not None:
            hits.append((m.start(), spec))
    if not hits:
        return {}
    hits.sort(key=lambda pair: pair[0])

    out: dict[str, tuple[int, int]] = {}
    for idx, (start, spec) in enumerate(hits):
        end = hits[idx + 1][0] if idx + 1 < len(hits) else len(body)
        out[spec.name] = (start, end)
    return out


def check_sections(body: str) -> ValidationResult:
    """Structured 10-section check. Pure function over the markdown body."""

    result = ValidationResult()
    if not body or not body.strip():
        result.ok = False
        result.errors.append("memo body is empty")
        return result

    positions = _section_bodies(body)

    # Per-section findings.
    for spec in SECTION_SPECS:
        if spec.name not in positions:
            result.findings.append(
                SectionFinding(name=spec.name, found=False)
            )
            if spec.required:
                result.ok = False
                result.errors.append(
                    f"missing required section: {spec.heading!r}"
                )
            continue
        start, end = positions[spec.name]
        section_body = body[start:end].strip()
        # Strip the heading line itself.
        lines = section_body.splitlines()
        if lines:
            section_body = "\n".join(lines[1:]).strip()
        length = len(section_body)
        too_short = length < spec.min_chars
        too_long = length > spec.max_chars
        result.findings.append(
            SectionFinding(
                name=spec.name,
                found=True,
                length=length,
                too_short=too_short,
                too_long=too_long,
            )
        )
        if too_short:
            result.ok = False
            result.errors.append(
                f"section {spec.heading!r} below minimum length "
                f"({length} < {spec.min_chars} chars)"
            )
        if too_long:
            result.ok = False
            result.errors.append(
                f"section {spec.heading!r} exceeds maximum length "
                f"({length} > {spec.max_chars} chars)"
            )

    # Canonical-order check.
    ordered_actual = sorted(
        (name for name in positions),
        key=lambda n: positions[n][0],
    )
    ordered_expected = [
        spec.name for spec in SECTION_SPECS if spec.name in positions
    ]
    if ordered_actual != ordered_expected:
        result.ok = False
        result.order_violation = (
            f"sections present out of order: "
            f"got {ordered_actual!r}, expected {ordered_expected!r}"
        )
        result.errors.append(result.order_violation)

    return result


def validate_memo_body(body: str) -> ValidationResult:
    """Validate a rendered memo body; raise :class:`MemoValidationError` on failure.

    Returns the :class:`ValidationResult` on success so callers that
    want to log per-section metrics (length, etc.) can do so without
    re-parsing.
    """

    result = check_sections(body)
    if not result.ok:
        raise MemoValidationError(
            result.first_error() or "memo body failed the 10-section contract",
            result=result,
        )
    return result


__all__ = [
    "MEMO_SECTIONS",
    "MemoValidationError",
    "SECTION_SPECS",
    "SectionFinding",
    "SectionSpec",
    "ValidationResult",
    "check_sections",
    "validate_memo_body",
]

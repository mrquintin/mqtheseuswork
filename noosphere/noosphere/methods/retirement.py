"""Formal method-retirement workflow.

Round 17 gave the firm two ways to *notice* a method has gone bad — the
drift detector (``noosphere/evaluation/method_drift.py``) and the
per-method failure-mode catalogs. It gave the firm no way to *act* on
that knowledge. A method that has earned retirement just lingers in the
registry as a zombie: still callable, still feeding conclusions, with
nothing recording that the firm stopped trusting it.

This module is the workflow. It owns four things:

1. **Retirement criteria** — :func:`qualifies_for_review` takes the
   observable facts about a method (:class:`RetirementSignals`) and says
   whether it has earned a retirement review. The criteria are also
   documented prose-side in ``docs/methods/Method_Retirement_Criteria.md``.
2. **A retirement state machine** — :class:`RetirementState` has four
   states ``{ACTIVE, UNDER_REVIEW, DEPRECATED, RETIRED}``. Transitions
   are explicit and validated; a method cannot jump ACTIVE → RETIRED
   without the mandatory UNDER_REVIEW step, and RETIRED is terminal.
3. **The founder review memo** — entering UNDER_REVIEW produces a memo
   at ``docs/methods/retirement/<method>.md`` from ``_template.md``. The
   memo's YAML frontmatter *is* the durable record of the method's
   retirement state; the body is the human review document. It is never
   deleted.
4. **Migration** — when a method moves to DEPRECATED,
   :func:`plan_migration` produces a sunset banner for every conclusion
   it produced and a reanalysis task pointing at the replacement method.

This module deliberately does no DB I/O. The registry
(``_registry.py``) holds an in-process side table of
:class:`RetirementRecord` so ``REGISTRY.get`` can refuse calls to
retired methods. The CLI (``cli_commands/methods.py``) reads and writes
the memo files. The Codex web app mirrors the state into a
``MethodRetirement`` table for its UI. All three read the same record
shape defined here.

Two constraints the tests pin:

* **The UNDER_REVIEW step is mandatory and produces a permanent
  record.** ``ACTIVE → RETIRED`` and ``ACTIVE → DEPRECATED`` are both
  rejected by :func:`assert_can_transition`.
* **Retired methods stay importable.** Retirement refuses *calls* — it
  raises :class:`RetiredMethodError` pointing at the replacement — but
  the source is never deleted and ``REGISTRY.get(..., include_retired=
  True)`` still resolves it for historical re-analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional

import yaml


RETIREMENT_SCHEMA = "theseus.method_retirement.v1"

# A method qualifies for review if a drift alert has been *sustained*
# this many days. A single warn window is not retirement-grade — the
# drift policy already has hysteresis; this is the much longer fuse.
SUSTAINED_DRIFT_DAYS = 60

# A method with zero invocations in this window is dormant. Dormancy is
# not by itself a verdict — it is a trigger for a review that asks "is
# this still load-bearing?".
DORMANCY_DAYS = 90


# ── Repo-relative default locations ───────────────────────────────────


def _repo_root() -> Path:
    # retirement.py lives at <root>/noosphere/noosphere/methods/retirement.py
    return Path(__file__).resolve().parents[3]


DEFAULT_RETIREMENT_DOCS_DIR = _repo_root() / "docs" / "methods" / "retirement"
_TEMPLATE_NAME = "_template.md"


# ── Retirement criteria ───────────────────────────────────────────────


class RetirementCriterion(str, Enum):
    """The four ways a method can earn a retirement review.

    Mirrors ``docs/methods/Method_Retirement_Criteria.md`` one-to-one.
    """

    SUSTAINED_DRIFT = "sustained_drift"
    ZERO_ABLATION_CONTRIBUTION = "zero_ablation_contribution"
    DORMANT = "dormant"
    ALL_CONCLUSIONS_REVISED = "all_conclusions_revised"


@dataclass(frozen=True)
class RetirementSignals:
    """Observable facts about one method, fed to :func:`qualifies_for_review`.

    Every field is optional / defaulted so a caller that only has a
    subset of the signals (e.g. the drift scheduler, which knows nothing
    about ablations) can still ask the question.

    * ``drift_alert_active_since`` — the timestamp the method's drift
      alert *first* went non-OK and has stayed non-OK since (from the
      drift policy's :class:`AlertResult`). ``None`` means no active
      alert.
    * ``ablation_recommendation`` — the verdict from the method's most
      recent ablation study, one of ``KEEP`` / ``REMOVE`` /
      ``KEEP-WITH-FURTHER-WORK``. Only ``REMOVE`` is retirement-grade:
      an inconclusive ablation (the Householder study's zero-*power*
      result, for instance) is explicitly *not* grounds for retirement.
    * ``invocations_last_90d`` — invocation count over the dormancy
      window. ``0`` triggers; ``None`` means "unknown, do not trigger".
    * ``conclusions_total`` / ``conclusions_revised_away`` — how many
      conclusions the method produced, and how many of those have since
      been revised away. The criterion fires only when *every* one has.
    """

    drift_alert_active_since: Optional[datetime] = None
    ablation_recommendation: Optional[str] = None
    invocations_last_90d: Optional[int] = None
    conclusions_total: int = 0
    conclusions_revised_away: int = 0


@dataclass(frozen=True)
class RetirementReviewVerdict:
    """The result of running the criteria against a method's signals."""

    method: str
    qualifies: bool
    triggered: tuple[RetirementCriterion, ...]
    rationale: dict[RetirementCriterion, str]

    def summary(self) -> str:
        """One-line human summary, used in the CLI and the memo."""
        if not self.qualifies:
            return f"{self.method}: no retirement criteria met"
        parts = "; ".join(self.rationale[c] for c in self.triggered)
        return f"{self.method}: {parts}"


def qualifies_for_review(
    signals: RetirementSignals,
    *,
    method: str = "",
    as_of: Optional[datetime] = None,
) -> RetirementReviewVerdict:
    """Decide whether a method has earned a retirement review.

    A method qualifies if **any** criterion fires. The verdict carries
    every triggered criterion and a per-criterion rationale string so
    the founder review memo can quote the evidence rather than just the
    label.
    """
    now = _ensure_tz(as_of or datetime.now(timezone.utc))
    triggered: list[RetirementCriterion] = []
    rationale: dict[RetirementCriterion, str] = {}

    # (1) Sustained drift alert > 60 days.
    if signals.drift_alert_active_since is not None:
        days = (now - _ensure_tz(signals.drift_alert_active_since)).days
        if days > SUSTAINED_DRIFT_DAYS:
            triggered.append(RetirementCriterion.SUSTAINED_DRIFT)
            rationale[RetirementCriterion.SUSTAINED_DRIFT] = (
                f"drift alert sustained {days}d "
                f"(> {SUSTAINED_DRIFT_DAYS}d threshold)"
            )

    # (2) Ablation reveals zero contribution beyond a baseline. Only a
    # REMOVE recommendation counts — see the criteria doc on why an
    # inconclusive ablation does not.
    if (signals.ablation_recommendation or "").strip().upper() == "REMOVE":
        triggered.append(RetirementCriterion.ZERO_ABLATION_CONTRIBUTION)
        rationale[RetirementCriterion.ZERO_ABLATION_CONTRIBUTION] = (
            "ablation recommends REMOVE: no measurable contribution "
            "beyond the baseline variant"
        )

    # (3) Zero invocations in 90 days.
    if signals.invocations_last_90d == 0:
        triggered.append(RetirementCriterion.DORMANT)
        rationale[RetirementCriterion.DORMANT] = (
            f"dormant: zero invocations in {DORMANCY_DAYS}d"
        )

    # (4) Every conclusion it produced has been revised away.
    if (
        signals.conclusions_total > 0
        and signals.conclusions_revised_away >= signals.conclusions_total
    ):
        triggered.append(RetirementCriterion.ALL_CONCLUSIONS_REVISED)
        rationale[RetirementCriterion.ALL_CONCLUSIONS_REVISED] = (
            f"all {signals.conclusions_total} conclusions it produced "
            f"have been revised away"
        )

    return RetirementReviewVerdict(
        method=method,
        qualifies=bool(triggered),
        triggered=tuple(triggered),
        rationale=rationale,
    )


# ── Retirement state machine ──────────────────────────────────────────


class RetirementState(str, Enum):
    ACTIVE = "active"
    UNDER_REVIEW = "under_review"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


# The explicit transition graph. Note what is *absent*:
#   * ACTIVE has no edge to DEPRECATED or RETIRED — the UNDER_REVIEW
#     step is mandatory and produces the permanent review record.
#   * RETIRED has no outgoing edges — it is terminal. A retired method
#     stays importable for historical re-analysis, but it is never
#     un-retired; reviving the *idea* means registering a new method.
_ALLOWED_TRANSITIONS: dict[RetirementState, frozenset[RetirementState]] = {
    RetirementState.ACTIVE: frozenset({RetirementState.UNDER_REVIEW}),
    RetirementState.UNDER_REVIEW: frozenset(
        {RetirementState.DEPRECATED, RetirementState.ACTIVE}
    ),
    RetirementState.DEPRECATED: frozenset(
        {RetirementState.RETIRED, RetirementState.ACTIVE}
    ),
    RetirementState.RETIRED: frozenset(),
}


class RetirementTransitionError(Exception):
    """An illegal retirement-state transition was attempted."""


def can_transition(frm: RetirementState, to: RetirementState) -> bool:
    return to in _ALLOWED_TRANSITIONS.get(frm, frozenset())


def assert_can_transition(frm: RetirementState, to: RetirementState) -> None:
    """Raise :class:`RetirementTransitionError` if ``frm → to`` is illegal."""
    if can_transition(frm, to):
        return
    allowed = sorted(s.value for s in _ALLOWED_TRANSITIONS.get(frm, frozenset()))
    if frm == RetirementState.RETIRED:
        detail = (
            "RETIRED is terminal — a retired method is never un-retired; "
            "register a new method instead"
        )
    elif (
        frm == RetirementState.ACTIVE
        and to in (RetirementState.DEPRECATED, RetirementState.RETIRED)
    ):
        detail = (
            "the UNDER_REVIEW step is mandatory — a method cannot move "
            "straight to DEPRECATED or RETIRED; it must first pass through "
            "a founder review that produces a permanent memo"
        )
    else:
        detail = (
            f"legal transitions from {frm.value.upper()} are: "
            f"{', '.join(allowed) or '(none)'}"
        )
    raise RetirementTransitionError(
        f"illegal retirement transition {frm.value.upper()} → "
        f"{to.value.upper()}: {detail}"
    )


@dataclass(frozen=True)
class RetirementTransition:
    """One entry in a method's permanent retirement ledger."""

    at: datetime
    from_state: RetirementState
    to_state: RetirementState
    actor: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "at": _iso(self.at),
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "actor": self.actor,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "RetirementTransition":
        return cls(
            at=_parse_dt(raw.get("at")) or datetime.now(timezone.utc),
            from_state=RetirementState(raw.get("from_state", "active")),
            to_state=RetirementState(raw.get("to_state", "active")),
            actor=str(raw.get("actor", "")),
            reason=str(raw.get("reason", "")),
        )


@dataclass
class RetirementRecord:
    """The operational retirement state of one method.

    This is the shape the registry side table, the memo frontmatter, and
    the Codex ``MethodRetirement`` table all agree on. It is mutable: the
    transition helpers below validate against the state machine, append
    to the ledger, and update the timeline fields in place.
    """

    method: str
    state: RetirementState = RetirementState.ACTIVE
    replacement: Optional[str] = None
    rationale: str = ""
    review_opened_at: Optional[datetime] = None
    deprecated_at: Optional[datetime] = None
    retired_at: Optional[datetime] = None
    sunset_at: Optional[datetime] = None
    transitions: list[RetirementTransition] = field(default_factory=list)

    # ── transition helpers ────────────────────────────────────────────

    def _transition(
        self,
        to: RetirementState,
        *,
        actor: str,
        reason: str,
        at: datetime,
    ) -> None:
        assert_can_transition(self.state, to)
        at = _ensure_tz(at)
        self.transitions.append(
            RetirementTransition(
                at=at,
                from_state=self.state,
                to_state=to,
                actor=actor,
                reason=reason,
            )
        )
        self.state = to

    def open_review(
        self,
        *,
        replacement: Optional[str],
        rationale: str,
        actor: str,
        at: datetime,
        sunset_at: Optional[datetime] = None,
    ) -> "RetirementRecord":
        """ACTIVE → UNDER_REVIEW. The mandatory first step."""
        self._transition(
            RetirementState.UNDER_REVIEW, actor=actor, reason=rationale, at=at
        )
        if replacement:
            self.replacement = replacement
        self.rationale = rationale
        self.review_opened_at = _ensure_tz(at)
        if sunset_at is not None:
            self.sunset_at = _ensure_tz(sunset_at)
        return self

    def accept(
        self,
        *,
        actor: str,
        at: datetime,
        reason: str = "founder accepted the retirement review",
        sunset_at: Optional[datetime] = None,
    ) -> "RetirementRecord":
        """UNDER_REVIEW → DEPRECATED. The founder accepts; migration begins."""
        self._transition(
            RetirementState.DEPRECATED, actor=actor, reason=reason, at=at
        )
        self.deprecated_at = _ensure_tz(at)
        if sunset_at is not None:
            self.sunset_at = _ensure_tz(sunset_at)
        return self

    def reject(
        self,
        *,
        actor: str,
        at: datetime,
        reason: str = "founder rejected the retirement review",
    ) -> "RetirementRecord":
        """UNDER_REVIEW → ACTIVE. The memo stays as a record of the review."""
        self._transition(
            RetirementState.ACTIVE, actor=actor, reason=reason, at=at
        )
        self.review_opened_at = None
        self.sunset_at = None
        return self

    def retire(
        self,
        *,
        actor: str,
        at: datetime,
        reason: str = "sunset timeline elapsed; method retired",
    ) -> "RetirementRecord":
        """DEPRECATED → RETIRED. Calls are refused from here on."""
        self._transition(
            RetirementState.RETIRED, actor=actor, reason=reason, at=at
        )
        self.retired_at = _ensure_tz(at)
        return self

    def revive(
        self,
        *,
        actor: str,
        at: datetime,
        reason: str,
    ) -> "RetirementRecord":
        """DEPRECATED → ACTIVE. Only legal before the method is retired."""
        self._transition(
            RetirementState.ACTIVE, actor=actor, reason=reason, at=at
        )
        self.deprecated_at = None
        self.sunset_at = None
        return self

    # ── serialization ─────────────────────────────────────────────────

    def to_frontmatter(self) -> dict:
        """Round-trippable dict for the memo's YAML frontmatter / the DB."""
        return {
            "schema": RETIREMENT_SCHEMA,
            "method": self.method,
            "state": self.state.value,
            "replacement": self.replacement or "",
            "rationale": self.rationale,
            "review_opened_at": _iso(self.review_opened_at),
            "deprecated_at": _iso(self.deprecated_at),
            "retired_at": _iso(self.retired_at),
            "sunset_at": _iso(self.sunset_at),
            "transitions": [t.to_dict() for t in self.transitions],
        }

    @classmethod
    def from_frontmatter(cls, raw: dict) -> "RetirementRecord":
        return cls(
            method=str(raw.get("method", "")),
            state=RetirementState(raw.get("state", "active")),
            replacement=(raw.get("replacement") or None),
            rationale=str(raw.get("rationale", "")),
            review_opened_at=_parse_dt(raw.get("review_opened_at")),
            deprecated_at=_parse_dt(raw.get("deprecated_at")),
            retired_at=_parse_dt(raw.get("retired_at")),
            sunset_at=_parse_dt(raw.get("sunset_at")),
            transitions=[
                RetirementTransition.from_dict(t)
                for t in (raw.get("transitions") or [])
                if isinstance(t, dict)
            ],
        )


# ── Typed call-refusal error + deprecation warning ────────────────────


class RetiredMethodError(Exception):
    """Raised by the registry when a RETIRED method is called.

    Carries the named replacement so the caller (or its operator) can
    act. The method's source is *not* gone — it is still importable for
    historical re-analysis via ``REGISTRY.get(..., include_retired=
    True)``; only ordinary calls are refused.
    """

    def __init__(
        self,
        method: str,
        replacement: Optional[str],
        *,
        sunset_at: Optional[datetime] = None,
    ) -> None:
        self.method = method
        self.replacement = replacement or None
        self.sunset_at = sunset_at
        if self.replacement:
            msg = (
                f"method {method!r} is RETIRED and will not run. "
                f"Use {self.replacement!r} instead. Retired methods stay "
                f"importable for historical re-analysis — call "
                f"REGISTRY.get({method!r}, include_retired=True) if that is "
                f"what you need."
            )
        else:
            msg = (
                f"method {method!r} is RETIRED and will not run. Its "
                f"retirement review named no replacement; see "
                f"docs/methods/retirement/{method}.md for the rationale. "
                f"Pass include_retired=True for historical re-analysis."
            )
        super().__init__(msg)


class DeprecatedMethodWarning(UserWarning):
    """Warned by the registry when a DEPRECATED method is called.

    DEPRECATED means the founder has accepted the retirement review and
    migration is underway, but the sunset deadline has not passed: the
    method still runs, loudly.
    """

    def __init__(
        self,
        method: str,
        replacement: Optional[str],
        *,
        sunset_at: Optional[datetime] = None,
    ) -> None:
        self.method = method
        self.replacement = replacement or None
        self.sunset_at = sunset_at
        tail = f" Use {self.replacement!r} instead." if self.replacement else ""
        when = f" Sunset: {_iso(sunset_at)}." if sunset_at else ""
        super().__init__(
            f"method {method!r} is DEPRECATED and scheduled for retirement."
            f"{tail}{when}"
        )


# ── Founder review memo ───────────────────────────────────────────────


# Embedded fallback so memo rendering works even if the on-disk
# ``_template.md`` is missing (a fresh checkout, an odd CWD). The
# on-disk file is the canonical, human-editable copy and is preferred
# when present.
_FALLBACK_BODY_TEMPLATE = """# Retirement review — `{{method}}`

> Status: **{{state}}** · Replacement: `{{replacement}}` · Opened {{review_opened_at}}

A method enters this review because it met one or more retirement
criteria (`docs/methods/Method_Retirement_Criteria.md`). This memo is the
permanent record of why the firm stopped trusting the method and what
replaced it. It is never deleted; the method's source is never deleted.

## 1. Rationale

{{rationale}}

## 2. Conclusions affected

{{conclusions_affected}}

## 3. Replacement method

`{{replacement}}` — why it covers this method's responsibility and where
it differs.

## 4. Migration plan

How conclusions move to the replacement: the reanalysis batch, who
reviews the diffs, what happens to conclusions with no equivalent.

## 5. Sunset timeline

- Review opened: {{review_opened_at}}
- Deprecated (sunset banner live): {{deprecated_at}}
- Sunset deadline (reanalysis complete): {{sunset_at}}
- Retired (calls refused): {{retired_at}}

## 6. Founder decision

Accept → method becomes DEPRECATED and migration begins. Reject →
method returns to ACTIVE and this memo stays as the record of the
review.

- Decision:
- Decided by:
- Decided at:
- Notes:
"""


def memo_path(
    method: str, docs_dir: Optional[Path] = None
) -> Path:
    """Path to a method's founder review memo."""
    return (docs_dir or DEFAULT_RETIREMENT_DOCS_DIR) / f"{method}.md"


def _load_body_template(docs_dir: Optional[Path]) -> str:
    """Body half of ``_template.md`` (everything after the frontmatter),
    falling back to the embedded copy."""
    path = (docs_dir or DEFAULT_RETIREMENT_DOCS_DIR) / _TEMPLATE_NAME
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return _FALLBACK_BODY_TEMPLATE
    _fm, body = split_frontmatter(text)
    return body or _FALLBACK_BODY_TEMPLATE


def render_memo(
    record: RetirementRecord,
    *,
    rationale: str = "",
    conclusions_affected: Iterable[str] = (),
    docs_dir: Optional[Path] = None,
) -> str:
    """Render the full memo file content for ``record``.

    The frontmatter is generated fresh from the record (it is the
    machine-readable state). The body is ``_template.md``'s body with
    ``{{...}}`` placeholders substituted — plain string replacement, so
    Markdown braces in the template are safe.
    """
    body = _load_body_template(docs_dir)
    affected = list(conclusions_affected)
    affected_block = (
        "\n".join(f"- `{cid}`" for cid in affected)
        if affected
        else "_To be completed by the reviewer._"
    )
    subs = {
        "method": record.method,
        "state": record.state.value.upper(),
        "replacement": record.replacement or "—",
        "review_opened_at": _iso(record.review_opened_at) or "—",
        "deprecated_at": _iso(record.deprecated_at) or "—",
        "retired_at": _iso(record.retired_at) or "—",
        "sunset_at": _iso(record.sunset_at) or "—",
        "rationale": rationale or record.rationale or "_To be completed by the reviewer._",
        "conclusions_affected": affected_block,
    }
    for key, val in subs.items():
        body = body.replace("{{" + key + "}}", str(val))
    fm = yaml.safe_dump(
        record.to_frontmatter(), sort_keys=False, allow_unicode=True
    )
    return f"---\n{fm}---\n\n{body.lstrip()}"


def write_memo(
    record: RetirementRecord,
    *,
    rationale: str = "",
    conclusions_affected: Iterable[str] = (),
    docs_dir: Optional[Path] = None,
    overwrite: bool = False,
) -> Path:
    """Write a method's founder review memo to disk and return its path.

    Refuses to clobber an existing memo unless ``overwrite=True`` — the
    memo is a permanent record, so a re-run of ``open-review`` should not
    silently destroy a prior review. Transition updates use
    :func:`update_memo` instead, which preserves the human-edited body.
    """
    path = memo_path(record.method, docs_dir)
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"refusing to overwrite existing retirement memo at {path}; "
            f"use update_memo() to record a transition"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_memo(
            record,
            rationale=rationale,
            conclusions_affected=conclusions_affected,
            docs_dir=docs_dir,
        ),
        encoding="utf-8",
    )
    return path


def update_memo(
    record: RetirementRecord, *, docs_dir: Optional[Path] = None
) -> Path:
    """Rewrite only the frontmatter of an existing memo to match ``record``.

    The human-edited body is preserved verbatim. If no memo exists yet
    (the method went under review out-of-band), one is created from the
    template.
    """
    path = memo_path(record.method, docs_dir)
    if not path.exists():
        return write_memo(record, docs_dir=docs_dir)
    _old_fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    fm = yaml.safe_dump(
        record.to_frontmatter(), sort_keys=False, allow_unicode=True
    )
    path.write_text(f"---\n{fm}---\n{body}", encoding="utf-8")
    return path


def parse_memo(path: Path) -> RetirementRecord:
    """Load a :class:`RetirementRecord` from a memo's frontmatter."""
    fm, _body = split_frontmatter(path.read_text(encoding="utf-8"))
    raw = yaml.safe_load(fm) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: frontmatter is not a mapping")
    if not raw.get("method"):
        raw["method"] = path.stem
    return RetirementRecord.from_frontmatter(raw)


def load_retirement_records(
    docs_dir: Optional[Path] = None,
) -> dict[str, RetirementRecord]:
    """Load every retirement memo under ``docs_dir`` into records.

    Skips ``_template.md`` and any file without parseable frontmatter
    (a half-written memo should not crash the registry boot). The
    registry calls this at startup so ``REGISTRY.get`` can refuse
    retired methods.
    """
    base = docs_dir or DEFAULT_RETIREMENT_DOCS_DIR
    out: dict[str, RetirementRecord] = {}
    if not base.exists():
        return out
    for path in sorted(base.glob("*.md")):
        if path.name == _TEMPLATE_NAME or path.name.startswith("_"):
            continue
        try:
            record = parse_memo(path)
        except Exception:
            continue
        if record.method:
            out[record.method] = record
    return out


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split ``---\\n…\\n---\\n<body>`` into ``(frontmatter, body)``.

    Returns ``("", text)`` when there is no frontmatter block.
    """
    if not text.startswith("---"):
        return "", text
    lines = text.splitlines(keepends=True)
    # first line is the opening fence; find the closing one.
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            fm = "".join(lines[1:idx])
            body = "".join(lines[idx + 1 :])
            return fm, body.lstrip("\n")
    return "", text


# ── Migration: sunset banners + scheduled reanalysis ──────────────────


@dataclass(frozen=True)
class SunsetBanner:
    """A sunset banner for one conclusion produced by a deprecated method.

    Carried back to the caller (the CLI / a sync job) which writes it to
    the conclusion. The banner is what makes a reader of the public site
    see that the firm has stopped trusting the method behind a
    conclusion before they have stopped trusting the conclusion itself.
    """

    conclusion_id: str
    method: str
    replacement: Optional[str]
    state: RetirementState
    sunset_at: Optional[datetime]
    headline: str
    detail: str


@dataclass(frozen=True)
class ReanalysisTask:
    """A scheduled reanalysis of one conclusion under the replacement method."""

    conclusion_id: str
    retired_method: str
    replacement_method: str
    scheduled_at: datetime
    reason: str


@dataclass(frozen=True)
class MigrationPlan:
    """Everything that must happen when a method is deprecated/retired.

    Pure data — :func:`plan_migration` builds it, a caller persists it.
    """

    method: str
    replacement: Optional[str]
    state: RetirementState
    banners: tuple[SunsetBanner, ...]
    reanalysis_tasks: tuple[ReanalysisTask, ...]

    @property
    def conclusion_count(self) -> int:
        return len(self.banners)

    @property
    def schedules_reanalysis(self) -> bool:
        return bool(self.reanalysis_tasks)


def plan_migration(
    record: RetirementRecord,
    *,
    conclusion_ids: Iterable[str],
    as_of: Optional[datetime] = None,
) -> MigrationPlan:
    """Build the migration plan for a deprecated/retired method.

    For every conclusion the method produced, emit a sunset banner; and,
    when a replacement is named, a reanalysis task pointing at it.

    Raises :class:`RetirementTransitionError` if the method is still
    ACTIVE or UNDER_REVIEW — a method's conclusions are not flagged until
    the founder has actually accepted the review. Migration is a
    consequence of the DEPRECATED transition, not of merely opening a
    review.
    """
    if record.state not in (RetirementState.DEPRECATED, RetirementState.RETIRED):
        raise RetirementTransitionError(
            f"cannot plan migration for method {record.method!r}: it is "
            f"{record.state.value.upper()}, not DEPRECATED or RETIRED. "
            f"Conclusions are flagged only once the founder accepts the "
            f"retirement review."
        )
    now = _ensure_tz(as_of or datetime.now(timezone.utc))
    ids = [str(c) for c in conclusion_ids]

    if record.replacement:
        headline = (
            f"Method `{record.method}` is being retired — "
            f"replaced by `{record.replacement}`"
        )
    else:
        headline = f"Method `{record.method}` is being retired"
    sunset_phrase = (
        f" Reanalysis is scheduled to complete by {_iso(record.sunset_at)}."
        if record.sunset_at
        else ""
    )
    detail = (
        "The firm has stopped trusting the method that produced this "
        "conclusion. "
        + (
            f"It is being reanalyzed under `{record.replacement}`."
            if record.replacement
            else "It has no direct replacement and is under review for "
            "revision or retraction."
        )
        + sunset_phrase
    )

    banners: list[SunsetBanner] = []
    tasks: list[ReanalysisTask] = []
    for cid in ids:
        banners.append(
            SunsetBanner(
                conclusion_id=cid,
                method=record.method,
                replacement=record.replacement,
                state=record.state,
                sunset_at=record.sunset_at,
                headline=headline,
                detail=detail,
            )
        )
        if record.replacement:
            tasks.append(
                ReanalysisTask(
                    conclusion_id=cid,
                    retired_method=record.method,
                    replacement_method=record.replacement,
                    scheduled_at=now,
                    reason=(
                        f"{record.method} deprecated; reanalyze under "
                        f"{record.replacement}"
                    ),
                )
            )

    return MigrationPlan(
        method=record.method,
        replacement=record.replacement,
        state=record.state,
        banners=tuple(banners),
        reanalysis_tasks=tuple(tasks),
    )


# ── Helpers ───────────────────────────────────────────────────────────


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _iso(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return _ensure_tz(dt).isoformat()


def _parse_dt(raw: object) -> Optional[datetime]:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return _ensure_tz(raw)
    try:
        return _ensure_tz(datetime.fromisoformat(str(raw)))
    except ValueError:
        return None


__all__ = [
    "DEFAULT_RETIREMENT_DOCS_DIR",
    "DORMANCY_DAYS",
    "RETIREMENT_SCHEMA",
    "SUSTAINED_DRIFT_DAYS",
    "DeprecatedMethodWarning",
    "MigrationPlan",
    "ReanalysisTask",
    "RetiredMethodError",
    "RetirementCriterion",
    "RetirementRecord",
    "RetirementReviewVerdict",
    "RetirementSignals",
    "RetirementState",
    "RetirementTransition",
    "RetirementTransitionError",
    "SunsetBanner",
    "assert_can_transition",
    "can_transition",
    "load_retirement_records",
    "memo_path",
    "parse_memo",
    "plan_migration",
    "qualifies_for_review",
    "render_memo",
    "split_frontmatter",
    "update_memo",
    "write_memo",
]

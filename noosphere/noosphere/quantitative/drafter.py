"""LLM-assisted drafter for ``QuantitativeFormalisation`` specs.

For every principle that does not yet have a formalisation, the drafter
proposes one. Two design constraints make this non-trivial:

1. **No fabrication.** The drafter must refuse rather than invent
   datasets it cannot name. The system prompt formalises this; the
   refusal is materialised as a structured ``UNFORMALISABLE`` row so
   the founder can still triage it.

2. **Idempotence per principle.** Re-running the drafter against the
   same store must not duplicate work — the run skips principles that
   already have any non-RETIRED formalisation.

The drafter never marks a row ``APPROVED``. Founder review is the
only path to approval; the model schema validator enforces that
contract end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Protocol

from noosphere.llm import LLMClient
from noosphere.models import (
    FormalisationStatus,
    Principle,
    QuantitativeFormalisation,
)
from noosphere.observability import get_logger
from noosphere.quantitative.formalisation import (
    FewShotExample,
    SchemaConformanceError,
    load_fewshot_examples,
    load_system_prompt,
    parse_drafter_json,
    validate_schema,
)

logger = get_logger(__name__)


class _FormalisationStore(Protocol):
    """The slice of ``Store`` the drafter relies on.

    Spelled out as a Protocol so tests can pass a lightweight fake.
    """

    def list_principles(self) -> list[Principle]: ...

    def list_quantitative_formalisations(
        self,
    ) -> list[QuantitativeFormalisation]: ...

    def get_quantitative_formalisations_for_principle(
        self, principle_id: str
    ) -> list[QuantitativeFormalisation]: ...

    def put_quantitative_formalisation(
        self, formalisation: QuantitativeFormalisation
    ) -> None: ...


class DrafterRefusal(Exception):
    """Raised when the drafter declines to formalise a principle.

    Carries the structured reason so callers can persist an
    ``UNFORMALISABLE`` row instead of silently dropping the principle.
    """

    def __init__(self, principle_id: str, reason: str) -> None:
        super().__init__(f"unformalisable principle {principle_id}: {reason}")
        self.principle_id = principle_id
        self.reason = reason


@dataclass
class DrafterReport:
    drafted_ids: list[str]
    refused_ids: list[str]
    skipped_ids: list[str]


def _format_user_prompt(
    principle: Principle,
    examples: list[FewShotExample],
) -> str:
    parts: list[str] = []
    if examples:
        parts.append("Here are examples of approved formalisations in the firm's house style.")
        parts.append("")
        for i, ex in enumerate(examples, start=1):
            parts.append(f"### Example {i} — principle")
            parts.append(ex.principle_text.strip())
            parts.append("")
            parts.append(f"### Example {i} — formalisation")
            parts.append(ex.formalisation_json.strip())
            parts.append("")
        parts.append("---")
        parts.append("")
    parts.append("Principle to formalise:")
    parts.append(principle.text.strip())
    if principle.description:
        parts.append("")
        parts.append("Elaboration:")
        parts.append(principle.description.strip())
    parts.append("")
    parts.append(
        "Return the JSON object now. No prose around it. If the principle is "
        "not quantifiable with real, accessible data, return the refusal "
        "shape with status='UNFORMALISABLE'."
    )
    return "\n".join(parts)


class QuantitativeFormalisationDrafter:
    """Drafter that proposes formalisations for un-formalised principles.

    Parameters
    ----------
    store:
        A `_FormalisationStore` providing the small CRUD slice the
        drafter needs.
    llm:
        Any `LLMClient`. The drafter calls ``complete`` once per
        principle.
    drafter_model:
        Free-form label persisted on the row so the founder triage UI
        can show which model drafted the spec.
    max_fewshot:
        Maximum number of approved formalisations to include as
        few-shot examples.
    """

    def __init__(
        self,
        store: _FormalisationStore,
        llm: LLMClient,
        *,
        drafter_model: str = "anthropic/claude",
        max_fewshot: int = 3,
        system_prompt_loader: Callable[[], str] = load_system_prompt,
    ) -> None:
        self._store = store
        self._llm = llm
        self._drafter_model = drafter_model
        self._max_fewshot = max_fewshot
        self._system_prompt_loader = system_prompt_loader

    # ── Idempotence helpers ─────────────────────────────────────────

    def _has_active_formalisation(self, principle_id: str) -> bool:
        existing = self._store.get_quantitative_formalisations_for_principle(
            principle_id
        )
        for row in existing:
            status = row.status
            status_value = (
                status.value if hasattr(status, "value") else status
            )
            if status_value != FormalisationStatus.RETIRED.value:
                return True
        return False

    def _approved_examples(self) -> list[QuantitativeFormalisation]:
        approved: list[QuantitativeFormalisation] = []
        for row in self._store.list_quantitative_formalisations():
            status_value = (
                row.status.value if hasattr(row.status, "value") else row.status
            )
            if status_value == FormalisationStatus.APPROVED.value:
                approved.append(row)
        return approved

    # ── Public API ─────────────────────────────────────────────────

    def draft_for_principle(
        self,
        principle: Principle,
    ) -> QuantitativeFormalisation:
        """Draft one formalisation for ``principle``.

        Persists the result (either DRAFT or UNFORMALISABLE) on the
        store and returns the row. Raises ``RuntimeError`` only on
        unrecoverable schema-conformance failures after a retry — those
        are LLM bugs the founder will see in the queue regardless.
        """

        if self._has_active_formalisation(principle.id):
            existing = self._store.get_quantitative_formalisations_for_principle(
                principle.id
            )
            logger.info(
                "quantitative.drafter.skip_existing",
                principle_id=principle.id,
            )
            return existing[0]

        principle_text_by_id = {
            ex.principle_id: ""  # filled below per-example
            for ex in self._approved_examples()
        }
        # Build {id: text} from store — the drafter needs principle text
        # to render examples readably.
        try:
            id_to_text = {p.id: p.text for p in self._store.list_principles()}
        except Exception:  # pragma: no cover - defensive
            id_to_text = {}
        for pid in principle_text_by_id:
            principle_text_by_id[pid] = id_to_text.get(pid, "")

        examples = load_fewshot_examples(
            self._approved_examples(),
            principle_text_by_id,
            max_examples=self._max_fewshot,
        )
        system_prompt = self._system_prompt_loader()
        user_prompt = _format_user_prompt(principle, examples)

        raw = self._llm.complete(
            system=system_prompt,
            user=user_prompt,
            max_tokens=2000,
            temperature=0.0,
        )

        try:
            payload = parse_drafter_json(raw)
            formalisation = validate_schema(payload, principle_id=principle.id)
        except SchemaConformanceError as exc:
            logger.warning(
                "quantitative.drafter.schema_failed",
                principle_id=principle.id,
                error=str(exc),
            )
            # Persist a structured refusal so the founder can see and
            # repair / re-run rather than silently losing the row.
            formalisation = QuantitativeFormalisation(
                principle_id=principle.id,
                status=FormalisationStatus.UNFORMALISABLE,
                unformalisable_reason=f"drafter_schema_error: {exc}",
                drafter_model=self._drafter_model,
                drafter_notes="Drafter output did not match schema.",
            )

        # The drafter must never self-approve. Coerce defensively.
        status_value = (
            formalisation.status.value
            if hasattr(formalisation.status, "value")
            else formalisation.status
        )
        if status_value == FormalisationStatus.APPROVED.value:
            raise RuntimeError(
                f"drafter returned APPROVED for principle {principle.id}; "
                f"this is a contract violation"
            )

        formalisation.drafter_model = self._drafter_model
        self._store.put_quantitative_formalisation(formalisation)
        logger.info(
            "quantitative.drafter.persisted",
            principle_id=principle.id,
            status=status_value,
        )
        return formalisation

    def draft_missing(
        self,
        principles: Optional[Iterable[Principle]] = None,
    ) -> DrafterReport:
        """Draft formalisations for every principle without one.

        Idempotent per principle — already-formalised principles are
        skipped, so this can run repeatedly (e.g. nightly) without
        creating duplicates.
        """

        if principles is None:
            principles = self._store.list_principles()
        drafted: list[str] = []
        refused: list[str] = []
        skipped: list[str] = []
        for principle in principles:
            if self._has_active_formalisation(principle.id):
                skipped.append(principle.id)
                continue
            row = self.draft_for_principle(principle)
            status_value = (
                row.status.value if hasattr(row.status, "value") else row.status
            )
            if status_value == FormalisationStatus.UNFORMALISABLE.value:
                refused.append(principle.id)
            else:
                drafted.append(principle.id)
        return DrafterReport(
            drafted_ids=drafted,
            refused_ids=refused,
            skipped_ids=skipped,
        )

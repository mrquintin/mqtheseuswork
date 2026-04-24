"""Founder override flow for the rigor gate."""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING

from noosphere.models import Actor, ContextMeta, FounderOverride

if TYPE_CHECKING:
    from noosphere.ledger import Ledger


def create_override(
    store: object,
    *,
    submission_id: str,
    founder_id: str,
    overridden_checks: list[str],
    justification: str,
    ledger: "Ledger | None" = None,
) -> FounderOverride:
    override_id = str(uuid.uuid4())

    if ledger is not None:
        entry_id = ledger.append(
            actor=Actor(kind="human", id=founder_id, display_name=founder_id),
            method_id=None,
            inputs_hash=hashlib.sha256(submission_id.encode()).hexdigest(),
            outputs_hash=hashlib.sha256(justification.encode()).hexdigest(),
            inputs_ref=f"rigor_override:{override_id}",
            outputs_ref=f"submission:{submission_id}",
            context=ContextMeta(
                tenant_id="rigor_gate",
                correlation_id=submission_id,
            ),
        )
    else:
        entry_id = f"override-{override_id}"

    override = FounderOverride(
        override_id=override_id,
        submission_id=submission_id,
        founder_id=founder_id,
        overridden_checks=overridden_checks,
        justification=justification,
        ledger_entry_id=entry_id,
    )

    store.insert_founder_override(override)  # type: ignore[union-attr]
    return override

"""Submit adopter transfer studies through the rigor gate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from noosphere.models import (
    Actor,
    AuthorAttestation,
    RigorSubmission,
    TransferStudy,
)
from noosphere.rigor_gate.gate import Gate

if TYPE_CHECKING:
    from noosphere.models import RigorVerdict


def submit_transfer_study(
    study: TransferStudy,
    store: object,
    *,
    author: Actor | None = None,
    ledger: object | None = None,
) -> RigorVerdict:
    if author is None:
        author = Actor(
            kind="human",
            id=f"adopter-{study.study_id}",
            display_name="MIP Adopter",
        )

    submission = RigorSubmission(
        submission_id=f"transfer-{study.study_id}",
        kind="eval_report",
        payload_ref=f"transfer_study:{study.study_id}",
        author=author,
        intended_venue="public_site",
        author_attestation=AuthorAttestation(
            author_id=author.id,
            conflict_disclosures=[],
            acknowledgments=[
                f"Transfer study from {study.source_domain} to {study.target_domain} "
                f"using method {study.method_ref.name} v{study.method_ref.version}.",
            ],
        ),
    )

    gate = Gate(store, ledger=ledger)
    return gate.submit(submission)

"""@gated decorator — wraps publication handlers with the rigor gate."""

from __future__ import annotations

import functools
import uuid
from typing import Any

from noosphere.models import Actor, AuthorAttestation, RigorSubmission
from noosphere.rigor_gate.gate import Gate, GateBlocked

__all__ = ["GateBlocked", "configure_store", "gated"]

_store: Any = None


def configure_store(store: Any) -> None:
    global _store
    _store = store


def _build_submission_from_args(
    kind: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> RigorSubmission:
    if "submission" in kwargs:
        return kwargs.pop("submission")

    submission_id = kwargs.pop("submission_id", str(uuid.uuid4()))
    payload_ref = kwargs.pop("payload_ref", "")
    author = kwargs.pop(
        "author",
        Actor(kind="agent", id="system", display_name="system"),
    )
    intended_venue = kwargs.pop("intended_venue", "public_site")
    attestation = kwargs.pop(
        "author_attestation",
        AuthorAttestation(
            author_id=author.id,
            conflict_disclosures=[],
            acknowledgments=[],
        ),
    )

    return RigorSubmission(
        submission_id=submission_id,
        kind=kind,
        payload_ref=payload_ref,
        author=author,
        intended_venue=intended_venue,
        author_attestation=attestation,
    )


def gated(*, kind: str):  # noqa: ANN201
    def deco(handler):  # noqa: ANN001, ANN202
        @functools.wraps(handler)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            store = kwargs.pop("_gate_store", _store)
            if store is None:
                raise RuntimeError(
                    "Rigor gate store not configured; call configure_store() first"
                )
            submission = _build_submission_from_args(kind, args, kwargs)
            verdict = Gate(store).submit(submission)
            if verdict.verdict == "fail":
                raise GateBlocked(verdict)
            return handler(*args, **kwargs)

        return wrapped

    return deco

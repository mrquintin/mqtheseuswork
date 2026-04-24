from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from pydantic import BaseModel

from noosphere.models import Actor, ContextMeta, Method, MethodInvocation
from noosphere.storage_client import storage_client_from_env
from noosphere.ledger.keys import KeyRing
from noosphere.methods._decorator import _get_store

logger = logging.getLogger(__name__)

_seen_invocations: set[str] = set()

_invocation_refs: dict[str, dict[str, str]] = {}


def _canonical_json(obj: Any) -> str:
    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _pre_capture_inputs(spec: Method, inv: MethodInvocation, input_data: Any) -> None:
    if inv.id in _seen_invocations:
        return
    storage = storage_client_from_env()
    serialized = _canonical_json(input_data).encode()
    key = f"ledger/inputs/{hashlib.sha256(serialized).hexdigest()}"
    blob_ref = storage.put_bytes(key=key, data=serialized, content_type="application/json")
    _invocation_refs[inv.id] = {"inputs_ref": blob_ref}


def _post_append(spec: Method, inv: MethodInvocation, input_data: Any, result: Any) -> None:
    if inv.id in _seen_invocations:
        return
    _seen_invocations.add(inv.id)

    store = _get_store()
    if store is None:
        logger.warning("No store available for ledger append")
        return

    storage = storage_client_from_env()
    serialized = _canonical_json(result).encode()
    key = f"ledger/outputs/{hashlib.sha256(serialized).hexdigest()}"
    outputs_blob_ref = storage.put_bytes(key=key, data=serialized, content_type="application/json")

    refs = _invocation_refs.pop(inv.id, {})
    inputs_ref = refs.get("inputs_ref", "")

    try:
        keyring = KeyRing()
    except Exception:
        logger.warning("Ledger keyring not configured, skipping append")
        return

    from noosphere.ledger.ledger import Ledger

    ledger = Ledger(store, keyring)
    ledger.append(
        actor=Actor(kind="method", id=spec.method_id, display_name=spec.name),
        method_id=spec.method_id,
        inputs_hash=inv.input_hash,
        outputs_hash=inv.output_hash,
        inputs_ref=inputs_ref,
        outputs_ref=outputs_blob_ref,
        context=ContextMeta(
            tenant_id=inv.tenant_id,
            correlation_id=inv.correlation_id,
        ),
    )


def _on_failure_append(spec: Method, inv: MethodInvocation, input_data: Any, exc: BaseException) -> None:
    if inv.id in _seen_invocations:
        return
    _seen_invocations.add(inv.id)

    store = _get_store()
    if store is None:
        logger.warning("No store available for ledger failure append")
        return

    refs = _invocation_refs.pop(inv.id, {})
    inputs_ref = refs.get("inputs_ref", "")

    try:
        keyring = KeyRing()
    except Exception:
        logger.warning("Ledger keyring not configured, skipping failure append")
        return

    from noosphere.ledger.ledger import Ledger

    ledger = Ledger(store, keyring)
    ledger.append(
        actor=Actor(kind="method", id=spec.method_id, display_name=spec.name),
        method_id=spec.method_id,
        inputs_hash=inv.input_hash,
        outputs_hash="",
        inputs_ref=inputs_ref,
        outputs_ref="",
        context=ContextMeta(
            tenant_id=inv.tenant_id,
            correlation_id=inv.correlation_id,
        ),
    )


def register_ledger_hooks() -> None:
    from noosphere.methods import register_pre_hook, register_post_hook, register_failure_hook

    register_pre_hook("ledger.capture_inputs", _pre_capture_inputs)
    register_post_hook("ledger.append", _post_append)
    register_failure_hook("ledger.append_on_failure", _on_failure_append)

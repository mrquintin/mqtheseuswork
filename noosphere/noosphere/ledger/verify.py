from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from noosphere.models import LedgerEntry
from noosphere.ledger.keys import KeyRing
from noosphere.methods._registry import REGISTRY

logger = logging.getLogger(__name__)


@dataclass
class EntryIssue:
    entry_id: str
    issue_type: str
    detail: str


@dataclass
class ReplayResult:
    entry_id: str
    method_id: str
    expected_output_hash: str
    actual_output_hash: str
    matched: bool
    skip_reason: str = ""


@dataclass
class VerifyReport:
    total_entries: int = 0
    chain_valid: bool = True
    signatures_valid: bool = True
    issues: list[EntryIssue] = field(default_factory=list)
    replay_results: list[ReplayResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.chain_valid and self.signatures_valid and len(self.issues) == 0


def verify(
    store: Any,
    keyring: KeyRing,
    *,
    since: Optional[str] = None,
    until: Optional[str] = None,
    replay: bool = False,
    storage_client: Any = None,
) -> VerifyReport:
    report = VerifyReport()
    prev_hash = ""
    prev_entry_id: Optional[str] = None

    if since is not None:
        before = store.get_ledger_entry(since)
        if before is not None:
            prev_hash = before.prev_hash

    entries: list[LedgerEntry] = list(store.iter_ledger(from_id=since, to_id=until))
    report.total_entries = len(entries)

    for i, entry in enumerate(entries):
        expected_prev = prev_hash if i == 0 and since is None else (
            entries[i - 1].entry_id if i > 0 else prev_hash
        )
        if entry.prev_hash != expected_prev:
            report.chain_valid = False
            report.issues.append(EntryIssue(
                entry_id=entry.entry_id,
                issue_type="chain_break",
                detail=f"prev_hash {entry.prev_hash!r} != expected {expected_prev!r}",
            ))

        sig_ok = keyring.verify(
            entry.entry_id.encode(),
            bytes.fromhex(entry.signature),
            entry.signer_key_id,
        )
        if not sig_ok:
            report.signatures_valid = False
            report.issues.append(EntryIssue(
                entry_id=entry.entry_id,
                issue_type="bad_signature",
                detail=f"Signature verification failed for key_id {entry.signer_key_id!r}",
            ))

        if replay and entry.method_id and storage_client is not None:
            _try_replay(entry, report, storage_client)

    return report


def _try_replay(
    entry: LedgerEntry,
    report: VerifyReport,
    storage_client: Any,
) -> None:
    try:
        spec, fn = _find_method_by_id(REGISTRY, entry.method_id)
    except Exception:
        report.replay_results.append(ReplayResult(
            entry_id=entry.entry_id,
            method_id=entry.method_id or "",
            expected_output_hash=entry.outputs_hash,
            actual_output_hash="",
            matched=False,
            skip_reason="method_not_found",
        ))
        return

    if spec.nondeterministic:
        report.replay_results.append(ReplayResult(
            entry_id=entry.entry_id,
            method_id=entry.method_id or "",
            expected_output_hash=entry.outputs_hash,
            actual_output_hash="",
            matched=False,
            skip_reason="nondeterministic",
        ))
        return

    try:
        import json
        raw = storage_client.open_read(key=_ref_to_key(entry.inputs_ref)).read()
        input_data = json.loads(raw)
        result = fn(input_data)
        import json as _json
        from pydantic import BaseModel
        if isinstance(result, BaseModel):
            result = result.model_dump(mode="json")
        actual_hash = hashlib.sha256(
            _json.dumps(result, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        report.replay_results.append(ReplayResult(
            entry_id=entry.entry_id,
            method_id=entry.method_id or "",
            expected_output_hash=entry.outputs_hash,
            actual_output_hash=actual_hash,
            matched=(actual_hash == entry.outputs_hash),
        ))
        if actual_hash != entry.outputs_hash:
            report.issues.append(EntryIssue(
                entry_id=entry.entry_id,
                issue_type="replay_mismatch",
                detail=f"expected {entry.outputs_hash}, got {actual_hash}",
            ))
    except Exception as e:
        report.replay_results.append(ReplayResult(
            entry_id=entry.entry_id,
            method_id=entry.method_id or "",
            expected_output_hash=entry.outputs_hash,
            actual_output_hash="",
            matched=False,
            skip_reason=f"replay_error: {e}",
        ))


def _find_method_by_id(registry: Any, method_id: str) -> tuple:
    for spec in registry.list():
        if spec.method_id == method_id:
            return registry.get(spec.name, version=spec.version)
    raise LookupError(f"Method {method_id} not found in registry")


def _ref_to_key(ref: str) -> str:
    if ref.startswith("file://"):
        return ref[7:].split("/blobs/", 1)[-1] if "/blobs/" in ref else ref[7:]
    return ref

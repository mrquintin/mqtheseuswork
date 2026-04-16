from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

from noosphere.models import Actor, ContextMeta, LedgerEntry
from noosphere.ledger.keys import KeyRing

logger = logging.getLogger(__name__)


def _canonical_json(obj: Any) -> str:
    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _now_isoformat() -> str:
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    """Append-only signed, Merkle-chained audit log."""

    def __init__(self, store: Any, keyring: Optional[KeyRing] = None) -> None:
        self._store = store
        self._keyring = keyring

    @property
    def store(self) -> Any:
        return self._store

    @property
    def keyring(self) -> KeyRing:
        if self._keyring is None:
            raise RuntimeError("KeyRing not configured")
        return self._keyring

    def append(
        self,
        *,
        actor: Actor,
        method_id: str | None,
        inputs_hash: str,
        outputs_hash: str,
        inputs_ref: str,
        outputs_ref: str,
        context: ContextMeta,
    ) -> str:
        prev = self._store.ledger_tail()
        prev_hash = prev.entry_id if prev else ""
        payload = _canonical_json({
            "prev_hash": prev_hash,
            "timestamp": _now_isoformat(),
            "actor": actor.model_dump(mode="json"),
            "method_id": method_id,
            "inputs_hash": inputs_hash,
            "outputs_hash": outputs_hash,
            "inputs_ref": inputs_ref,
            "outputs_ref": outputs_ref,
            "context": context.model_dump(mode="json"),
        })
        entry_id = hashlib.sha256(
            prev_hash.encode() + payload.encode()
        ).hexdigest()
        signature_bytes = self.keyring.sign(entry_id.encode())
        entry = LedgerEntry(
            entry_id=entry_id,
            prev_hash=prev_hash,
            timestamp=datetime.now(timezone.utc),
            actor=actor,
            method_id=method_id,
            inputs_hash=inputs_hash,
            outputs_hash=outputs_hash,
            inputs_ref=inputs_ref,
            outputs_ref=outputs_ref,
            context=context,
            signature=signature_bytes.hex(),
            signer_key_id=self.keyring.active_key_id,
        )
        self._store.append_ledger_entry(entry)
        self._mirror_to_jsonl(entry)
        return entry_id

    def _mirror_to_jsonl(self, entry: LedgerEntry) -> None:
        mirror_dir = Path(
            os.environ.get("THESEUS_LEDGER_MIRROR_DIR", "~/.theseus/ledger")
        ).expanduser()
        try:
            mirror_dir.mkdir(parents=True, exist_ok=True)
            filename = entry.timestamp.strftime("%Y-%m") + ".jsonl"
            filepath = mirror_dir / filename
            with open(filepath, "a") as f:
                f.write(entry.model_dump_json() + "\n")
        except Exception:
            logger.warning("Failed to mirror ledger entry to JSONL", exc_info=True)

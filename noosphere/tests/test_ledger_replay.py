"""Tests for ledger deterministic replay verification."""
from __future__ import annotations

import hashlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional
from unittest.mock import patch, MagicMock

import pytest
from nacl.signing import SigningKey
from pydantic import BaseModel

from noosphere.models import (
    Actor,
    ContextMeta,
    LedgerEntry,
    Method,
    MethodImplRef,
    MethodType,
)
from noosphere.ledger.keys import KeyRing
from noosphere.ledger.ledger import Ledger
from noosphere.ledger.verify import verify


class InMemoryStore:
    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []

    def append_ledger_entry(self, entry: LedgerEntry) -> None:
        self._entries.append(entry)

    def ledger_tail(self) -> Optional[LedgerEntry]:
        return self._entries[-1] if self._entries else None

    def get_ledger_entry(self, entry_id: str) -> Optional[LedgerEntry]:
        for e in self._entries:
            if e.entry_id == entry_id:
                return e
        return None

    def iter_ledger(
        self, from_id: Optional[str] = None, to_id: Optional[str] = None
    ) -> Iterator[LedgerEntry]:
        started = from_id is None
        for e in self._entries:
            if not started:
                if e.entry_id == from_id:
                    started = True
                else:
                    continue
            yield e
            if to_id is not None and e.entry_id == to_id:
                return


def _make_keyring(tmp_path: Path) -> KeyRing:
    sk = SigningKey.generate()
    sk_path = tmp_path / "signing.key"
    sk_path.write_bytes(bytes(sk))
    vk_dir = tmp_path / "vkeys"
    vk_dir.mkdir(exist_ok=True)
    (vk_dir / "k.pub").write_bytes(bytes(sk.verify_key))
    return KeyRing(signing_key_path=sk_path, verification_keys_dir=vk_dir)


def _canonical_json(obj: Any) -> str:
    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _make_method_spec(
    *, method_id: str = "replay_m1", name: str = "replay_method",
    nondeterministic: bool = False,
) -> Method:
    return Method(
        method_id=method_id,
        name=name,
        version="1.0.0",
        method_type=MethodType.EXTRACTION,
        input_schema={},
        output_schema={},
        description="test",
        rationale="test",
        preconditions=[],
        postconditions=[],
        dependencies=[],
        implementation=MethodImplRef(
            module="test", fn_name="test", git_sha="abc", image_digest=None
        ),
        owner="test",
        status="active",
        nondeterministic=nondeterministic,
        created_at=datetime.now(timezone.utc),
    )


class TestLedgerReplay:
    def test_deterministic_replay_matches(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _make_keyring(tmp_path)
        ledger = Ledger(store, keyring)
        mirror_dir = tmp_path / "mirror"

        input_data = {"value": 42}
        result_data = {"doubled": 84}
        input_json = _canonical_json(input_data)
        result_json = _canonical_json(result_data)
        inputs_hash = hashlib.sha256(input_json.encode()).hexdigest()
        outputs_hash = hashlib.sha256(result_json.encode()).hexdigest()

        spec = _make_method_spec(nondeterministic=False)

        with patch.dict(os.environ, {"THESEUS_LEDGER_MIRROR_DIR": str(mirror_dir)}):
            ledger.append(
                actor=Actor(kind="method", id=spec.method_id, display_name=spec.name),
                method_id=spec.method_id,
                inputs_hash=inputs_hash,
                outputs_hash=outputs_hash,
                inputs_ref="ledger/inputs/abc",
                outputs_ref="ledger/outputs/def",
                context=ContextMeta(tenant_id="t1", correlation_id="c1"),
            )

        mock_storage = MagicMock()
        mock_storage.open_read.return_value = io.BytesIO(input_json.encode())

        def double_fn(data: Any) -> dict:
            return {"doubled": data["value"] * 2}

        mock_registry = MagicMock()
        mock_registry.list.return_value = [spec]
        mock_registry.get.return_value = (spec, double_fn)

        with patch("noosphere.ledger.verify.REGISTRY", mock_registry):
            report = verify(
                store, keyring, replay=True, storage_client=mock_storage,
            )

        assert report.ok
        assert len(report.replay_results) == 1
        assert report.replay_results[0].matched

    def test_nondeterministic_method_skipped(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _make_keyring(tmp_path)
        ledger = Ledger(store, keyring)
        mirror_dir = tmp_path / "mirror"

        spec = _make_method_spec(method_id="nd_m1", name="nd_method", nondeterministic=True)

        with patch.dict(os.environ, {"THESEUS_LEDGER_MIRROR_DIR": str(mirror_dir)}):
            ledger.append(
                actor=Actor(kind="method", id=spec.method_id, display_name=spec.name),
                method_id=spec.method_id,
                inputs_hash="ihash",
                outputs_hash="ohash",
                inputs_ref="ref:in",
                outputs_ref="ref:out",
                context=ContextMeta(tenant_id="t1", correlation_id="c1"),
            )

        mock_storage = MagicMock()
        mock_registry = MagicMock()
        mock_registry.list.return_value = [spec]
        mock_registry.get.return_value = (spec, lambda x: x)

        with patch("noosphere.ledger.verify.REGISTRY", mock_registry):
            report = verify(
                store, keyring, replay=True, storage_client=mock_storage,
            )

        assert report.ok
        assert len(report.replay_results) == 1
        assert report.replay_results[0].skip_reason == "nondeterministic"
        assert not report.replay_results[0].matched

    def test_replay_mismatch_flagged(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _make_keyring(tmp_path)
        ledger = Ledger(store, keyring)
        mirror_dir = tmp_path / "mirror"

        input_data = {"value": 42}
        input_json = _canonical_json(input_data)
        inputs_hash = hashlib.sha256(input_json.encode()).hexdigest()

        spec = _make_method_spec(nondeterministic=False)

        with patch.dict(os.environ, {"THESEUS_LEDGER_MIRROR_DIR": str(mirror_dir)}):
            ledger.append(
                actor=Actor(kind="method", id=spec.method_id, display_name=spec.name),
                method_id=spec.method_id,
                inputs_hash=inputs_hash,
                outputs_hash="original_output_hash",
                inputs_ref="ledger/inputs/abc",
                outputs_ref="ledger/outputs/def",
                context=ContextMeta(tenant_id="t1", correlation_id="c1"),
            )

        mock_storage = MagicMock()
        mock_storage.open_read.return_value = io.BytesIO(input_json.encode())

        def changed_fn(data: Any) -> dict:
            return {"doubled": data["value"] * 3}

        mock_registry = MagicMock()
        mock_registry.list.return_value = [spec]
        mock_registry.get.return_value = (spec, changed_fn)

        with patch("noosphere.ledger.verify.REGISTRY", mock_registry):
            report = verify(
                store, keyring, replay=True, storage_client=mock_storage,
            )

        assert not report.ok
        assert len(report.replay_results) == 1
        assert not report.replay_results[0].matched
        assert any(i.issue_type == "replay_mismatch" for i in report.issues)

    def test_method_not_found_skipped(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _make_keyring(tmp_path)
        ledger = Ledger(store, keyring)
        mirror_dir = tmp_path / "mirror"

        with patch.dict(os.environ, {"THESEUS_LEDGER_MIRROR_DIR": str(mirror_dir)}):
            ledger.append(
                actor=Actor(kind="method", id="unknown_m", display_name="Unknown"),
                method_id="unknown_m",
                inputs_hash="ih",
                outputs_hash="oh",
                inputs_ref="ref:in",
                outputs_ref="ref:out",
                context=ContextMeta(tenant_id="t1", correlation_id="c1"),
            )

        mock_storage = MagicMock()
        mock_registry = MagicMock()
        mock_registry.list.return_value = []

        with patch("noosphere.ledger.verify.REGISTRY", mock_registry):
            report = verify(
                store, keyring, replay=True, storage_client=mock_storage,
            )

        assert len(report.replay_results) == 1
        assert report.replay_results[0].skip_reason == "method_not_found"

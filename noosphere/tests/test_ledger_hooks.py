"""Tests for ledger hooks registering with the method decorator."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterator, Optional
from unittest.mock import patch

import pytest
from nacl.signing import SigningKey
from pydantic import BaseModel

from noosphere.models import (
    Actor,
    ContextMeta,
    LedgerEntry,
    Method,
    MethodInvocation,
    MethodType,
)
from noosphere.ledger.hooks import (
    _invocation_refs,
    _on_failure_append,
    _post_append,
    _pre_capture_inputs,
    _seen_invocations,
    register_ledger_hooks,
)
from noosphere.ledger.keys import KeyRing
from noosphere.storage_client import LocalDiskStorage


class InMemoryStore:
    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []
        self._invocations: list[MethodInvocation] = []

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

    def insert_method(self, spec: Method) -> None:
        pass

    def insert_method_invocation(self, inv: MethodInvocation) -> None:
        self._invocations.append(inv)


def _setup_keyring(tmp_path: Path) -> KeyRing:
    sk = SigningKey.generate()
    sk_path = tmp_path / "signing.key"
    sk_path.write_bytes(bytes(sk))
    vk_dir = tmp_path / "vkeys"
    vk_dir.mkdir()
    (vk_dir / "k.pub").write_bytes(bytes(sk.verify_key))
    return KeyRing(signing_key_path=sk_path, verification_keys_dir=vk_dir)


def _canonical_json(obj: Any) -> str:
    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


class TestLedgerHooks:
    def setup_method(self) -> None:
        _seen_invocations.clear()
        _invocation_refs.clear()

    def test_pre_hook_stores_input_blob(self, tmp_path: Path) -> None:
        storage_root = tmp_path / "blobs"
        storage = LocalDiskStorage(storage_root)

        from noosphere.models import MethodImplRef
        from datetime import datetime, timezone

        spec = Method(
            method_id="meth001",
            name="test_method",
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
            nondeterministic=False,
            created_at=datetime.now(timezone.utc),
        )

        inv = MethodInvocation(
            id="inv-001",
            method_id="meth001",
            input_hash="hash1",
            output_hash="",
            started_at=datetime.now(timezone.utc),
            succeeded=False,
            correlation_id="corr1",
            tenant_id="tenant1",
        )

        input_data = {"text": "hello"}

        with patch("noosphere.ledger.hooks.storage_client_from_env", return_value=storage):
            _pre_capture_inputs(spec, inv, input_data)

        assert "inv-001" in _invocation_refs
        assert "inputs_ref" in _invocation_refs["inv-001"]

    def test_post_hook_creates_ledger_entry(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _setup_keyring(tmp_path)
        storage_root = tmp_path / "blobs"
        storage = LocalDiskStorage(storage_root)
        mirror_dir = tmp_path / "mirror"

        from noosphere.models import MethodImplRef
        from datetime import datetime, timezone

        spec = Method(
            method_id="meth002",
            name="test_method_2",
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
            nondeterministic=False,
            created_at=datetime.now(timezone.utc),
        )

        inv = MethodInvocation(
            id="inv-002",
            method_id="meth002",
            input_hash="ihash2",
            output_hash="ohash2",
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            succeeded=True,
            correlation_id="corr2",
            tenant_id="tenant2",
        )

        _invocation_refs["inv-002"] = {"inputs_ref": "file:///tmp/input_blob"}

        result_data = {"score": 0.95}

        with patch("noosphere.ledger.hooks.storage_client_from_env", return_value=storage), \
             patch("noosphere.ledger.hooks._get_store", return_value=store), \
             patch("noosphere.ledger.hooks.KeyRing", return_value=keyring), \
             patch.dict(os.environ, {"THESEUS_LEDGER_MIRROR_DIR": str(mirror_dir)}):
            _post_append(spec, inv, {"text": "hello"}, result_data)

        assert len(store._entries) == 1
        entry = store._entries[0]
        assert entry.method_id == "meth002"
        assert entry.inputs_hash == "ihash2"

    def test_hooks_idempotent_per_invocation(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _setup_keyring(tmp_path)
        storage_root = tmp_path / "blobs"
        storage = LocalDiskStorage(storage_root)
        mirror_dir = tmp_path / "mirror"

        from noosphere.models import MethodImplRef
        from datetime import datetime, timezone

        spec = Method(
            method_id="meth003",
            name="test_method_3",
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
            nondeterministic=False,
            created_at=datetime.now(timezone.utc),
        )

        inv = MethodInvocation(
            id="inv-003",
            method_id="meth003",
            input_hash="ihash3",
            output_hash="ohash3",
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            succeeded=True,
            correlation_id="corr3",
            tenant_id="tenant3",
        )

        _invocation_refs["inv-003"] = {"inputs_ref": "file:///tmp/input_blob"}

        with patch("noosphere.ledger.hooks.storage_client_from_env", return_value=storage), \
             patch("noosphere.ledger.hooks._get_store", return_value=store), \
             patch("noosphere.ledger.hooks.KeyRing", return_value=keyring), \
             patch.dict(os.environ, {"THESEUS_LEDGER_MIRROR_DIR": str(mirror_dir)}):
            _post_append(spec, inv, {}, {"result": "a"})
            _post_append(spec, inv, {}, {"result": "a"})
            _post_append(spec, inv, {}, {"result": "a"})

        assert len(store._entries) == 1

    def test_failure_hook_creates_entry_with_empty_outputs(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _setup_keyring(tmp_path)
        mirror_dir = tmp_path / "mirror"

        from noosphere.models import MethodImplRef
        from datetime import datetime, timezone

        spec = Method(
            method_id="meth004",
            name="test_method_4",
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
            nondeterministic=False,
            created_at=datetime.now(timezone.utc),
        )

        inv = MethodInvocation(
            id="inv-004",
            method_id="meth004",
            input_hash="ihash4",
            output_hash="",
            started_at=datetime.now(timezone.utc),
            succeeded=False,
            error_kind="ValueError",
            correlation_id="corr4",
            tenant_id="tenant4",
        )

        exc = ValueError("something broke")

        with patch("noosphere.ledger.hooks._get_store", return_value=store), \
             patch("noosphere.ledger.hooks.KeyRing", return_value=keyring), \
             patch.dict(os.environ, {"THESEUS_LEDGER_MIRROR_DIR": str(mirror_dir)}):
            _on_failure_append(spec, inv, {"x": 1}, exc)

        assert len(store._entries) == 1
        entry = store._entries[0]
        assert entry.outputs_hash == ""
        assert entry.outputs_ref == ""

    def test_register_ledger_hooks_registers_three_hooks(self) -> None:
        from noosphere.methods._hooks import _PRE_HOOKS, _POST_HOOKS, _FAILURE_HOOKS

        register_ledger_hooks()

        pre_names = [name for name, _ in _PRE_HOOKS]
        post_names = [name for name, _ in _POST_HOOKS]
        fail_names = [name for name, _ in _FAILURE_HOOKS]

        assert "ledger.capture_inputs" in pre_names
        assert "ledger.append" in post_names
        assert "ledger.append_on_failure" in fail_names

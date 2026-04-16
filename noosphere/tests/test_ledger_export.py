"""Tests for ledger export bundle creation and standalone verification."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional
from unittest.mock import patch, MagicMock

import pytest
from nacl.signing import SigningKey

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
from noosphere.ledger.export import export_bundle


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


def _populate_ledger(
    store: InMemoryStore, keyring: KeyRing, tmp_path: Path, count: int = 3,
) -> list[str]:
    ledger = Ledger(store, keyring)
    mirror_dir = tmp_path / "mirror"
    ids = []
    with patch.dict(os.environ, {"THESEUS_LEDGER_MIRROR_DIR": str(mirror_dir)}):
        for i in range(count):
            eid = ledger.append(
                actor=Actor(kind="method", id=f"m{i}", display_name=f"Method {i}"),
                method_id=f"m{i}",
                inputs_hash=f"ih{i}",
                outputs_hash=f"oh{i}",
                inputs_ref=f"ledger/inputs/blob{i}",
                outputs_ref=f"ledger/outputs/blob{i}",
                context=ContextMeta(tenant_id="t1", correlation_id=f"c{i}"),
            )
            ids.append(eid)
    return ids


class TestLedgerExport:
    def test_export_creates_tar_gz(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _make_keyring(tmp_path)
        ids = _populate_ledger(store, keyring, tmp_path)

        out_path = tmp_path / "bundle.tar.gz"
        export_bundle(
            store, keyring,
            from_id=ids[0], to_id=ids[-1],
            out_path=out_path,
        )

        assert out_path.exists()
        with tarfile.open(out_path, "r:gz") as tar:
            names = tar.getnames()
            assert any("ledger.jsonl" in n for n in names)
            assert any("keys" in n for n in names)
            assert any("verify_bundle.py" in n for n in names)

    def test_export_includes_all_entries(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _make_keyring(tmp_path)
        ids = _populate_ledger(store, keyring, tmp_path, count=5)

        out_path = tmp_path / "bundle.tar.gz"
        export_bundle(
            store, keyring,
            from_id=ids[0], to_id=ids[-1],
            out_path=out_path,
        )

        with tarfile.open(out_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith("ledger.jsonl"):
                    f = tar.extractfile(member)
                    assert f is not None
                    lines = f.read().decode().strip().split("\n")
                    assert len(lines) == 5

    def test_export_includes_blobs(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _make_keyring(tmp_path)
        ids = _populate_ledger(store, keyring, tmp_path, count=1)

        mock_storage = MagicMock()
        mock_storage.open_read.return_value = io.BytesIO(b"blob content")

        out_path = tmp_path / "bundle.tar.gz"
        export_bundle(
            store, keyring,
            from_id=ids[0], to_id=ids[0],
            out_path=out_path,
            storage_client=mock_storage,
        )

        with tarfile.open(out_path, "r:gz") as tar:
            names = tar.getnames()
            assert any("blobs" in n for n in names)

    def test_roundtrip_verify_bundle(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _make_keyring(tmp_path)
        ids = _populate_ledger(store, keyring, tmp_path, count=3)

        out_path = tmp_path / "bundle.tar.gz"
        export_bundle(
            store, keyring,
            from_id=ids[0], to_id=ids[-1],
            out_path=out_path,
        )

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        with tarfile.open(out_path, "r:gz") as tar:
            tar.extractall(path=extract_dir)

        verify_script = extract_dir / "bundle" / "verify_bundle.py"
        assert verify_script.exists()

        result = subprocess.run(
            [sys.executable, str(verify_script)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"Verify failed: {result.stderr}\n{result.stdout}"
        assert "OK" in result.stdout

    def test_verify_bundle_detects_tampered_chain(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _make_keyring(tmp_path)
        ids = _populate_ledger(store, keyring, tmp_path, count=3)

        out_path = tmp_path / "bundle.tar.gz"
        export_bundle(
            store, keyring,
            from_id=ids[0], to_id=ids[-1],
            out_path=out_path,
        )

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        with tarfile.open(out_path, "r:gz") as tar:
            tar.extractall(path=extract_dir)

        # Tamper with ledger.jsonl — change prev_hash of second entry
        ledger_file = extract_dir / "bundle" / "ledger.jsonl"
        lines = ledger_file.read_text().strip().split("\n")
        entry = json.loads(lines[1])
        entry["prev_hash"] = "TAMPERED"
        lines[1] = json.dumps(entry)
        ledger_file.write_text("\n".join(lines) + "\n")

        verify_script = extract_dir / "bundle" / "verify_bundle.py"
        result = subprocess.run(
            [sys.executable, str(verify_script)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode != 0
        assert "FAILED" in result.stdout or "Chain break" in result.stdout

"""Tests for ledger signature verification and key rotation."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, Optional
from unittest.mock import patch

import pytest
from nacl.signing import SigningKey

from noosphere.models import Actor, ContextMeta, LedgerEntry
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
    vk_dir = tmp_path / "verify_keys"
    vk_dir.mkdir(exist_ok=True)
    (vk_dir / "key0.pub").write_bytes(bytes(sk.verify_key))
    return KeyRing(signing_key_path=sk_path, verification_keys_dir=vk_dir)


def _make_actor() -> Actor:
    return Actor(kind="method", id="test_sig", display_name="Sig Test")


def _make_context() -> ContextMeta:
    return ContextMeta(tenant_id="t1", correlation_id="c1")


def _append_entry(ledger: Ledger, method_id: str = "m1") -> str:
    return ledger.append(
        actor=_make_actor(), method_id=method_id,
        inputs_hash="ih", outputs_hash="oh",
        inputs_ref="ref:in", outputs_ref="ref:out",
        context=_make_context(),
    )


class TestLedgerSignatures:
    def test_valid_signature_passes(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _make_keyring(tmp_path)
        ledger = Ledger(store, keyring)
        mirror_dir = tmp_path / "mirror"

        with patch.dict(os.environ, {"THESEUS_LEDGER_MIRROR_DIR": str(mirror_dir)}):
            _append_entry(ledger)

        report = verify(store, keyring)
        assert report.ok
        assert report.signatures_valid

    def test_wrong_key_fails_verification(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _make_keyring(tmp_path)
        ledger = Ledger(store, keyring)
        mirror_dir = tmp_path / "mirror"

        with patch.dict(os.environ, {"THESEUS_LEDGER_MIRROR_DIR": str(mirror_dir)}):
            _append_entry(ledger)

        # Create a different keyring with a different key
        other_dir = tmp_path / "other_keys"
        other_dir.mkdir()
        other_keyring = _make_keyring(other_dir)

        report = verify(store, other_keyring)
        assert not report.signatures_valid
        assert any(i.issue_type == "bad_signature" for i in report.issues)

    def test_swapped_key_without_rotation_fails(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _make_keyring(tmp_path)
        ledger = Ledger(store, keyring)
        mirror_dir = tmp_path / "mirror"

        with patch.dict(os.environ, {"THESEUS_LEDGER_MIRROR_DIR": str(mirror_dir)}):
            _append_entry(ledger, "m1")

        # Swap signing key WITHOUT rotation — new key not in verify keys
        new_sk = SigningKey.generate()
        new_sk_path = tmp_path / "new_signing.key"
        new_sk_path.write_bytes(bytes(new_sk))

        # Directly replace the signing key (bypassing rotate)
        keyring._signing_key = new_sk
        from noosphere.ledger.keys import _key_id
        keyring._active_key_id = _key_id(new_sk.verify_key)
        # Don't add to verify keys — simulates unauthorized swap

        with patch.dict(os.environ, {"THESEUS_LEDGER_MIRROR_DIR": str(mirror_dir)}):
            _append_entry(ledger, "m2")

        # Entry signed with new key won't verify because key not in verify set
        report = verify(store, keyring)
        assert not report.signatures_valid
        assert any(i.issue_type == "bad_signature" for i in report.issues)

    def test_legitimate_rotation_all_entries_verify(self, tmp_path: Path) -> None:
        store = InMemoryStore()
        keyring = _make_keyring(tmp_path)
        ledger = Ledger(store, keyring)
        mirror_dir = tmp_path / "mirror"

        with patch.dict(os.environ, {"THESEUS_LEDGER_MIRROR_DIR": str(mirror_dir)}):
            _append_entry(ledger, "m1")
            _append_entry(ledger, "m2")

            # Rotate to a new key (properly)
            new_sk = SigningKey.generate()
            new_sk_path = tmp_path / "rotated_signing.key"
            new_sk_path.write_bytes(bytes(new_sk))
            keyring.rotate(new_sk_path)

            _append_entry(ledger, "m3")
            _append_entry(ledger, "m4")

        report = verify(store, keyring)
        assert report.ok
        assert report.total_entries == 4

    def test_keyring_sign_and_verify_roundtrip(self, tmp_path: Path) -> None:
        keyring = _make_keyring(tmp_path)
        data = b"test payload"
        sig = keyring.sign(data)
        assert keyring.verify(data, sig, keyring.active_key_id)

    def test_keyring_verify_wrong_data_fails(self, tmp_path: Path) -> None:
        keyring = _make_keyring(tmp_path)
        sig = keyring.sign(b"original")
        assert not keyring.verify(b"tampered", sig, keyring.active_key_id)

    def test_keyring_verify_unknown_key_id_fails(self, tmp_path: Path) -> None:
        keyring = _make_keyring(tmp_path)
        sig = keyring.sign(b"data")
        assert not keyring.verify(b"data", sig, "nonexistent_key_id")

    def test_generate_keypair(self, tmp_path: Path) -> None:
        sk_path = KeyRing.generate_keypair(tmp_path / "gen")
        assert sk_path.exists()
        assert (tmp_path / "gen" / "verify.pub").exists()
        kr = KeyRing(signing_key_path=sk_path)
        sig = kr.sign(b"hello")
        assert kr.verify(b"hello", sig, kr.active_key_id)

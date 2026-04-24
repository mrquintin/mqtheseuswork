"""Tests: package() emits every required file; CHECKSUMS verifies; signature valid."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from noosphere.ledger.keys import KeyRing
from noosphere.models import MethodRef, MethodType
from noosphere.methods._decorator import register_method
from noosphere.methods._registry import REGISTRY
from noosphere.transfer.package_method import package
from noosphere.transfer.signing import verify_signed_checksums, compute_checksums


class _StubInput(BaseModel):
    text: str


class _StubOutput(BaseModel):
    score: float


_REGISTERED = False


def _ensure_stub_method():
    global _REGISTERED
    if _REGISTERED:
        return
    try:
        REGISTRY.get("_test_pkg_method", version="1.0.0")
        _REGISTERED = True
        return
    except Exception:
        pass

    @register_method(
        name="_test_pkg_method",
        version="1.0.0",
        method_type=MethodType.JUDGMENT,
        input_schema=_StubInput,
        output_schema=_StubOutput,
        description="Stub method for packaging tests.",
        rationale="Test rationale.",
        owner="test",
        status="active",
    )
    def _test_pkg_method(input_data):
        return _StubOutput(score=0.5)

    _REGISTERED = True


@pytest.fixture()
def keyring(tmp_path):
    sk_path = KeyRing.generate_keypair(tmp_path / "keys")
    return KeyRing(signing_key_path=sk_path, verification_keys_dir=tmp_path / "keys")


@pytest.fixture()
def packaged_dir(tmp_path, keyring):
    _ensure_stub_method()
    ref = MethodRef(name="_test_pkg_method", version="1.0.0")
    out = tmp_path / "pkg_out"
    package(ref, out, keyring)
    return out


REQUIRED_FILES = [
    "method.json",
    "rationale.md",
    "adapter.py",
    "Dockerfile",
    "CHECKSUMS",
    "CHECKSUMS.sig",
    "README.md",
    "EVAL_CARD.md",
    "LICENSE",
]


def test_all_required_files_present(packaged_dir):
    for fname in REQUIRED_FILES:
        assert (packaged_dir / fname).exists(), f"Missing: {fname}"
    assert (packaged_dir / "implementation").is_dir()


def test_method_json_valid(packaged_dir):
    data = json.loads((packaged_dir / "method.json").read_text())
    assert data["name"] == "_test_pkg_method"
    assert data["version"] == "1.0.0"


def test_checksums_cover_all_files(packaged_dir):
    checksums_text = (packaged_dir / "CHECKSUMS").read_text()
    lines = [l for l in checksums_text.strip().splitlines() if l.strip()]
    listed_files = {l.split("  ", 1)[1] for l in lines}

    for fname in REQUIRED_FILES:
        if fname in ("CHECKSUMS", "CHECKSUMS.sig"):
            continue
        assert fname in listed_files or any(
            fname in f for f in listed_files
        ), f"{fname} not in CHECKSUMS"


def test_checksums_hashes_correct(packaged_dir):
    checksums_text = (packaged_dir / "CHECKSUMS").read_text()
    for line in checksums_text.strip().splitlines():
        if not line.strip():
            continue
        expected_hash, rel_path = line.split("  ", 1)
        actual = hashlib.sha256((packaged_dir / rel_path).read_bytes()).hexdigest()
        assert actual == expected_hash, f"Hash mismatch for {rel_path}"


def test_signature_valid(packaged_dir, keyring):
    assert verify_signed_checksums(packaged_dir, keyring)


def test_signature_fails_on_tamper(packaged_dir, keyring):
    (packaged_dir / "README.md").write_text("tampered content")
    recomputed = compute_checksums(packaged_dir)
    original = (packaged_dir / "CHECKSUMS").read_text()
    assert recomputed != original, "CHECKSUMS should differ after tamper"
    # The existing signature should no longer match the tampered CHECKSUMS
    (packaged_dir / "CHECKSUMS").write_text(recomputed)
    assert not verify_signed_checksums(packaged_dir, keyring)


def test_adapter_no_noosphere_import(packaged_dir):
    adapter_text = (packaged_dir / "adapter.py").read_text()
    for line in adapter_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "from noosphere" not in stripped, (
            f"adapter.py must not import from noosphere: {stripped}"
        )
        assert "import noosphere" not in stripped, (
            f"adapter.py must not import noosphere: {stripped}"
        )


def test_license_is_apache(packaged_dir):
    text = (packaged_dir / "LICENSE").read_text()
    assert "Apache License" in text


def test_eval_card_stub(packaged_dir):
    text = (packaged_dir / "EVAL_CARD.md").read_text()
    assert "Evaluation Card" in text

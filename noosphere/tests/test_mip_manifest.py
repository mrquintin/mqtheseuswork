"""Tests: build MIP, verify manifest, checksum integrity, tamper detection."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from noosphere.ledger.keys import KeyRing
from noosphere.models import MethodRef


@pytest.fixture()
def keyring(tmp_path):
    sk_path = KeyRing.generate_keypair(tmp_path / "keys")
    return KeyRing(signing_key_path=sk_path, verification_keys_dir=tmp_path / "keys")


def _mock_package(ref: MethodRef, out_dir: Path, keyring, **kw):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "method.json").write_text(
        json.dumps({"name": ref.name, "version": ref.version})
    )
    (out_dir / "adapter.py").write_text("# stub adapter\n")
    (out_dir / "Dockerfile").write_text("FROM python:3.11\n")
    (out_dir / "README.md").write_text(f"# {ref.name}\n")
    impl = out_dir / "implementation"
    impl.mkdir(exist_ok=True)
    (impl / "main.py").write_text("pass\n")


def _mock_compile_doc(ref: MethodRef, out_dir: Path, keyring, **kw):
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("spec.md", "rationale.md", "examples.md", "calibration.md", "transfer.md", "operations.md"):
        (out_dir / name).write_text(f"# {name}\n")


@pytest.fixture()
def mip_dir(tmp_path, keyring):
    methods = [
        MethodRef(name="method_alpha", version="1.0.0"),
        MethodRef(name="method_beta", version="2.0.0"),
    ]
    with patch("noosphere.interop.builder.package_method", side_effect=_mock_package), \
         patch("noosphere.interop.builder.compile_method_doc", side_effect=_mock_compile_doc):
        from noosphere.interop.builder import build_mip
        return build_mip(
            methods=methods,
            include_gate_checks=True,
            name="test-bundle",
            version="0.1.0",
            out_dir=tmp_path / "mip_out",
            keyring=keyring,
        )


class TestManifestStructure:
    def test_manifest_exists(self, mip_dir):
        assert (mip_dir / "manifest.json").exists()

    def test_manifest_valid_json(self, mip_dir):
        manifest = json.loads((mip_dir / "manifest.json").read_text())
        assert manifest["name"] == "test-bundle"
        assert manifest["version"] == "0.1.0"
        assert manifest["mip_version"] == "1.0.0"

    def test_manifest_has_two_methods(self, mip_dir):
        manifest = json.loads((mip_dir / "manifest.json").read_text())
        assert len(manifest["methods"]) == 2
        names = {m["name"] for m in manifest["methods"]}
        assert names == {"method_alpha", "method_beta"}

    def test_manifest_has_docs(self, mip_dir):
        manifest = json.loads((mip_dir / "manifest.json").read_text())
        assert len(manifest["docs"]) == 2

    def test_manifest_has_signature(self, mip_dir):
        manifest = json.loads((mip_dir / "manifest.json").read_text())
        assert "signature" in manifest
        assert "signer_key_id" in manifest
        assert len(manifest["signature"]) > 0


class TestManifestVerification:
    def test_signature_verifies(self, mip_dir, keyring):
        from noosphere.interop.builder import verify_manifest
        assert verify_manifest(mip_dir, keyring)

    def test_checksums_verify(self, mip_dir):
        from noosphere.interop.builder import verify_checksums
        errors = verify_checksums(mip_dir)
        assert errors == []

    def test_tampered_method_fails_checksum(self, mip_dir):
        method_file = mip_dir / "methods" / "method_alpha" / "method.json"
        method_file.write_text('{"tampered": true}')

        from noosphere.interop.builder import verify_checksums
        errors = verify_checksums(mip_dir)
        assert len(errors) > 0
        assert "method_alpha" in errors[0]

    def test_tampered_manifest_fails_signature(self, mip_dir, keyring):
        manifest_path = mip_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["name"] = "hacked-bundle"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))

        from noosphere.interop.builder import verify_manifest
        assert not verify_manifest(mip_dir, keyring)


class TestBundleLayout:
    def test_license_exists(self, mip_dir):
        assert (mip_dir / "LICENSE").exists()

    def test_citation_exists(self, mip_dir):
        assert (mip_dir / "CITATION.cff").exists()

    def test_cascade_schema_exists(self, mip_dir):
        assert (mip_dir / "cascade" / "schema.json").exists()
        data = json.loads((mip_dir / "cascade" / "schema.json").read_text())
        assert "node_kinds" in data
        assert "edge_relations" in data

    def test_gate_checks_exists(self, mip_dir):
        assert (mip_dir / "gate" / "checks.json").exists()

    def test_ledger_genesis_exists(self, mip_dir):
        assert (mip_dir / "ledger" / "genesis.json").exists()
        genesis = json.loads((mip_dir / "ledger" / "genesis.json").read_text())
        assert genesis["mip_name"] == "test-bundle"

    def test_methods_dirs_exist(self, mip_dir):
        assert (mip_dir / "methods" / "method_alpha").is_dir()
        assert (mip_dir / "methods" / "method_beta").is_dir()

    def test_docs_dirs_exist(self, mip_dir):
        assert (mip_dir / "docs" / "method_alpha").is_dir()
        assert (mip_dir / "docs" / "method_beta").is_dir()

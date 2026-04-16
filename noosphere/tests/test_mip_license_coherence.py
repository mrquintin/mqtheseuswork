"""Tests: conflicting sub-licenses fail build unless declared."""
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


def _mock_package(ref, out_dir, keyring, **kw):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "method.json").write_text(json.dumps({"name": ref.name, "version": ref.version}))
    (out_dir / "adapter.py").write_text("# stub\n")
    (out_dir / "Dockerfile").write_text("FROM python:3.11\n")
    (out_dir / "README.md").write_text(f"# {ref.name}\n")
    impl = out_dir / "implementation"
    impl.mkdir(exist_ok=True)
    (impl / "main.py").write_text("pass\n")


def _mock_package_with_license(license_text):
    def _inner(ref, out_dir, keyring, **kw):
        _mock_package(ref, out_dir, keyring, **kw)
        (out_dir / "LICENSE").write_text(license_text)
    return _inner


def _mock_compile_doc(ref, out_dir, keyring, **kw):
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in ("spec.md", "rationale.md", "examples.md", "calibration.md", "transfer.md", "operations.md"):
        (out_dir / f).write_text(f"# {f}\n")


class TestLicenseCoherenceDeclared:
    def test_declared_sub_licenses_pass(self, tmp_path, keyring):
        methods = [
            MethodRef(name="gpl_method", version="1.0.0"),
            MethodRef(name="mit_method", version="1.0.0"),
        ]
        with patch("noosphere.interop.builder.package_method", side_effect=_mock_package), \
             patch("noosphere.interop.builder.compile_method_doc", side_effect=_mock_compile_doc):
            from noosphere.interop.builder import build_mip
            mip = build_mip(
                methods=methods,
                include_gate_checks=False,
                name="license-ok",
                version="1.0.0",
                out_dir=tmp_path / "mip_ok",
                keyring=keyring,
                license_spdx="Apache-2.0",
                sub_licenses={
                    "gpl_method": "GPL-3.0-only",
                    "mit_method": "MIT",
                },
            )
        manifest = json.loads((mip / "manifest.json").read_text())
        assert manifest["sub_licenses"]["gpl_method"] == "GPL-3.0-only"
        assert manifest["sub_licenses"]["mit_method"] == "MIT"

    def test_manifest_records_top_license(self, tmp_path, keyring):
        methods = [MethodRef(name="m1", version="1.0.0")]
        with patch("noosphere.interop.builder.package_method", side_effect=_mock_package), \
             patch("noosphere.interop.builder.compile_method_doc", side_effect=_mock_compile_doc):
            from noosphere.interop.builder import build_mip
            mip = build_mip(
                methods=methods,
                include_gate_checks=False,
                name="lic-test",
                version="1.0.0",
                out_dir=tmp_path / "mip_lic",
                keyring=keyring,
                license_spdx="MIT",
            )
        manifest = json.loads((mip / "manifest.json").read_text())
        assert manifest["license"] == "MIT"


class TestLicenseConflictDetection:
    def test_conflicting_license_in_method_detected(self, tmp_path, keyring):
        """A method whose LICENSE file says GPL but is not declared in sub_licenses."""
        methods = [
            MethodRef(name="sneaky_gpl", version="1.0.0"),
        ]

        def _pkg_with_gpl(ref, out_dir, keyring, **kw):
            _mock_package(ref, out_dir, keyring, **kw)
            (out_dir / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE\nVersion 3\n")

        with patch("noosphere.interop.builder.package_method", side_effect=_pkg_with_gpl), \
             patch("noosphere.interop.builder.compile_method_doc", side_effect=_mock_compile_doc):
            from noosphere.interop.builder import build_mip
            mip = build_mip(
                methods=methods,
                include_gate_checks=False,
                name="conflict-test",
                version="1.0.0",
                out_dir=tmp_path / "mip_conflict",
                keyring=keyring,
                license_spdx="Apache-2.0",
            )

        manifest = json.loads((mip / "manifest.json").read_text())
        assert manifest["license"] == "Apache-2.0"
        method_license_path = mip / "methods" / "sneaky_gpl" / "LICENSE"
        assert method_license_path.exists()
        content = method_license_path.read_text()
        assert "GNU" in content
        assert "sneaky_gpl" not in manifest.get("sub_licenses", {})


class TestLeakCheckBlocksSecrets:
    def test_signing_key_in_bundle_fails(self, tmp_path, keyring):
        methods = [MethodRef(name="clean_method", version="1.0.0")]

        def _pkg_with_secret(ref, out_dir, keyring_arg, **kw):
            _mock_package(ref, out_dir, keyring_arg, **kw)
            (out_dir / "signing.key").write_text("FAKE SIGNING KEY DATA")

        with patch("noosphere.interop.builder.package_method", side_effect=_pkg_with_secret), \
             patch("noosphere.interop.builder.compile_method_doc", side_effect=_mock_compile_doc):
            from noosphere.interop.builder import build_mip
            from noosphere.interop.leak_check import LeakDetected
            with pytest.raises(LeakDetected):
                build_mip(
                    methods=methods,
                    include_gate_checks=False,
                    name="leak-test",
                    version="1.0.0",
                    out_dir=tmp_path / "mip_leak",
                    keyring=keyring,
                )

    def test_private_identifier_in_file_fails(self, tmp_path, keyring):
        methods = [MethodRef(name="tainted", version="1.0.0")]

        def _pkg_with_private(ref, out_dir, keyring_arg, **kw):
            _mock_package(ref, out_dir, keyring_arg, **kw)
            readme = out_dir / "README.md"
            readme.write_text("This uses THESEUS_INTERNAL data structures.\n")

        with patch("noosphere.interop.builder.package_method", side_effect=_pkg_with_private), \
             patch("noosphere.interop.builder.compile_method_doc", side_effect=_mock_compile_doc):
            from noosphere.interop.builder import build_mip
            from noosphere.interop.leak_check import LeakDetected
            with pytest.raises(LeakDetected):
                build_mip(
                    methods=methods,
                    include_gate_checks=False,
                    name="leak-test2",
                    version="1.0.0",
                    out_dir=tmp_path / "mip_leak2",
                    keyring=keyring,
                )

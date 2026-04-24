"""Tests: scaffold_adoption produces a working adopter directory."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

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


def _mock_compile_doc(ref, out_dir, keyring, **kw):
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in ("spec.md", "rationale.md", "examples.md", "calibration.md", "transfer.md", "operations.md"):
        (out_dir / f).write_text(f"# {f}\n")


@pytest.fixture()
def mip_dir(tmp_path, keyring):
    methods = [
        MethodRef(name="method_a", version="1.0.0"),
        MethodRef(name="method_b", version="2.0.0"),
    ]
    with patch("noosphere.interop.builder.package_method", side_effect=_mock_package), \
         patch("noosphere.interop.builder.compile_method_doc", side_effect=_mock_compile_doc):
        from noosphere.interop.builder import build_mip
        return build_mip(
            methods=methods,
            include_gate_checks=False,
            name="adopt-test",
            version="0.1.0",
            out_dir=tmp_path / "mip",
            keyring=keyring,
        )


@pytest.fixture()
def adoption_dir(mip_dir, tmp_path):
    from noosphere.interop.adoption import scaffold_adoption
    return scaffold_adoption(mip_dir, tmp_path / "adopter")


class TestScaffoldStructure:
    def test_readme_exists(self, adoption_dir):
        assert (adoption_dir / "README.md").exists()

    def test_readme_has_methods(self, adoption_dir):
        readme = (adoption_dir / "README.md").read_text()
        assert "method_a" in readme
        assert "method_b" in readme

    def test_adapter_exists(self, adoption_dir):
        assert (adoption_dir / "adapter.py").exists()

    def test_adapter_has_methods(self, adoption_dir):
        adapter = (adoption_dir / "adapter.py").read_text()
        assert "method_a" in adapter
        assert "method_b" in adapter

    def test_example_workflow_exists(self, adoption_dir):
        assert (adoption_dir / "example_workflow.yaml").exists()

    def test_example_workflow_valid(self, adoption_dir):
        wf = yaml.safe_load((adoption_dir / "example_workflow.yaml").read_text())
        assert wf["name"] == "example"
        assert len(wf["steps"]) == 2
        assert wf["output"] == "step_1"

    def test_scoreboard_exists(self, adoption_dir):
        assert (adoption_dir / "scoreboard.json").exists()
        sb = json.loads((adoption_dir / "scoreboard.json").read_text())
        assert sb["mip"] == "adopt-test"
        assert sb["runs"] == []

    def test_run_script_exists(self, adoption_dir):
        assert (adoption_dir / "run.sh").exists()

    def test_run_script_executable(self, adoption_dir):
        import os
        mode = os.stat(adoption_dir / "run.sh").st_mode
        assert mode & 0o100


class TestScaffoldWorkflow:
    def test_workflow_validates_clean(self, adoption_dir, mip_dir):
        from noosphere.interop.workflow import validate
        manifest = json.loads((mip_dir / "manifest.json").read_text())
        available = [m["name"] for m in manifest["methods"]]
        wf_yaml = (adoption_dir / "example_workflow.yaml").read_text()
        errors = validate(wf_yaml, available)
        assert errors == []


class TestCitationPresent:
    def test_readme_includes_citation(self, adoption_dir):
        readme = (adoption_dir / "README.md").read_text()
        assert "Citation" in readme or "cite" in readme.lower()

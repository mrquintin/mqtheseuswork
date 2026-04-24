"""Tests: MIP runner — workflow execution, report generation, no network calls."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

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


def _mock_compile_doc(ref, out_dir, keyring, **kw):
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in ("spec.md", "rationale.md", "examples.md", "calibration.md", "transfer.md", "operations.md"):
        (out_dir / f).write_text(f"# {f}\n")


@pytest.fixture()
def mip_dir(tmp_path, keyring):
    methods = [
        MethodRef(name="extract", version="1.0.0"),
        MethodRef(name="judge", version="1.0.0"),
    ]
    with patch("noosphere.interop.builder.package_method", side_effect=_mock_package), \
         patch("noosphere.interop.builder.compile_method_doc", side_effect=_mock_compile_doc):
        from noosphere.interop.builder import build_mip
        mip = build_mip(
            methods=methods,
            include_gate_checks=False,
            name="runner-test",
            version="0.1.0",
            out_dir=tmp_path / "mip",
            keyring=keyring,
        )

    workflow_yaml = (
        "name: test_workflow\n"
        "steps:\n"
        "  - id: step1\n"
        "    method: extract\n"
        "    input: $input\n"
        "  - id: step2\n"
        "    method: judge\n"
        "    input: $steps.step1\n"
        "output: step2\n"
    )
    (mip / "workflows" / "test_workflow.yaml").write_text(workflow_yaml)
    return mip


def _fake_docker_run(method_dir, input_path, output_path):
    input_data = json.loads(input_path.read_text())
    result = {"processed": True, "source": method_dir.name, "input_echo": input_data}
    output_path.write_text(json.dumps(result))


class TestMIPRunner:
    def test_run_produces_report(self, mip_dir, tmp_path, keyring):
        out = tmp_path / "run_output"
        with patch("noosphere.interop.runner._run_docker_step", side_effect=_fake_docker_run):
            from noosphere.interop.runner import run_mip
            report = run_mip(mip_dir, "test_workflow", {"text": "hello"}, out, keyring)

        assert report["mip_name"] == "runner-test"
        assert report["workflow"] == "test_workflow"
        assert len(report["steps"]) == 2
        assert all(s["status"] == "success" for s in report["steps"])
        assert report["output"] is not None

    def test_report_file_written(self, mip_dir, tmp_path, keyring):
        out = tmp_path / "run_output2"
        with patch("noosphere.interop.runner._run_docker_step", side_effect=_fake_docker_run):
            from noosphere.interop.runner import run_mip
            run_mip(mip_dir, "test_workflow", {"text": "hello"}, out, keyring)

        report_path = out / "report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text())
        assert "run_id" in report
        assert report["ledger_entries"] == 2

    def test_ledger_entries_written(self, mip_dir, tmp_path, keyring):
        out = tmp_path / "run_output3"
        with patch("noosphere.interop.runner._run_docker_step", side_effect=_fake_docker_run):
            from noosphere.interop.runner import run_mip
            run_mip(mip_dir, "test_workflow", {}, out, keyring)

        ledger = json.loads((out / "ledger.json").read_text())
        assert len(ledger) == 2
        assert all(e["succeeded"] for e in ledger)

    def test_no_network_calls(self, mip_dir, tmp_path, keyring):
        out = tmp_path / "run_output4"
        with patch("noosphere.interop.runner._run_docker_step", side_effect=_fake_docker_run) as mock_docker, \
             patch("noosphere.interop.runner.subprocess") as mock_subprocess:
            mock_subprocess.run = MagicMock(side_effect=AssertionError("No subprocess should be called"))
            from noosphere.interop.runner import run_mip
            run_mip(mip_dir, "test_workflow", {}, out, keyring)
            mock_subprocess.run.assert_not_called()

    def test_invalid_signature_rejected(self, mip_dir, tmp_path, keyring):
        manifest_path = mip_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["name"] = "tampered"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))

        out = tmp_path / "run_output5"
        from noosphere.interop.runner import run_mip
        with pytest.raises(RuntimeError, match="signature verification failed"):
            run_mip(mip_dir, "test_workflow", {}, out, keyring)

    def test_missing_workflow_raises(self, mip_dir, tmp_path, keyring):
        out = tmp_path / "run_output6"
        from noosphere.interop.runner import run_mip
        with pytest.raises(FileNotFoundError):
            run_mip(mip_dir, "nonexistent", {}, out, keyring)


class TestMIPRunnerWhenPredicate:
    def test_when_predicate_skips_step(self, mip_dir, tmp_path, keyring):
        workflow_yaml = (
            "name: conditional\n"
            "steps:\n"
            "  - id: step1\n"
            "    method: extract\n"
            "    input: $input\n"
            "  - id: step2\n"
            "    method: judge\n"
            "    input: $steps.step1\n"
            "    when:\n"
            "      field: status\n"
            "      equals: ready\n"
            "output: step1\n"
        )
        (mip_dir / "workflows" / "conditional.yaml").write_text(workflow_yaml)

        out = tmp_path / "run_cond"
        with patch("noosphere.interop.runner._run_docker_step", side_effect=_fake_docker_run):
            from noosphere.interop.runner import run_mip
            report = run_mip(mip_dir, "conditional", {"status": "not_ready"}, out, keyring)

        step2 = [s for s in report["steps"] if s["step_id"] == "step2"][0]
        assert step2["status"] == "skipped"

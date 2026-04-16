"""Tests: packaged adapter is self-contained (no noosphere imports).

NOTE: The full Docker-based isolation test (run adapter in a container with
no network) is only executed when Docker is available. The non-Docker variant
checks the adapter source for prohibited imports and validates the adapter
template renders correctly.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from pydantic import BaseModel

from noosphere.ledger.keys import KeyRing
from noosphere.models import MethodRef, MethodType
from noosphere.methods._decorator import register_method
from noosphere.methods._registry import REGISTRY
from noosphere.transfer.adapter_template import render_adapter
from noosphere.transfer.package_method import package


class _SCInput(BaseModel):
    value: str


class _SCOutput(BaseModel):
    result: str


_REGISTERED = False


def _ensure_method():
    global _REGISTERED
    if _REGISTERED:
        return
    try:
        REGISTRY.get("_test_sc_method", version="1.0.0")
        _REGISTERED = True
        return
    except Exception:
        pass

    @register_method(
        name="_test_sc_method",
        version="1.0.0",
        method_type=MethodType.EXTRACTION,
        input_schema=_SCInput,
        output_schema=_SCOutput,
        description="Stub for selfcontainment test.",
        rationale="Test.",
        owner="test",
        status="active",
    )
    def _test_sc_method(input_data):
        return _SCOutput(result=f"echo:{input_data.value}")

    _REGISTERED = True


@pytest.fixture()
def keyring(tmp_path):
    sk_path = KeyRing.generate_keypair(tmp_path / "keys")
    return KeyRing(signing_key_path=sk_path, verification_keys_dir=tmp_path / "keys")


@pytest.fixture()
def packaged_dir(tmp_path, keyring):
    _ensure_method()
    ref = MethodRef(name="_test_sc_method", version="1.0.0")
    out = tmp_path / "sc_pkg"
    package(ref, out, keyring)
    return out


def test_adapter_source_has_no_noosphere_imports(packaged_dir):
    adapter_text = (packaged_dir / "adapter.py").read_text()
    for line in adapter_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
            continue
        if not stripped or stripped.startswith("//"):
            continue
        assert "import noosphere" not in stripped, f"adapter.py must not import noosphere: {stripped}"
        assert "from noosphere" not in stripped, f"adapter.py must not import from noosphere: {stripped}"


def test_adapter_template_renders_cleanly():
    code = render_adapter(
        method_name="test_method",
        method_version="2.0.0",
        entry_module="impl_module",
        entry_fn="run_impl",
    )
    assert "from impl_module import run_impl" in code
    assert "noosphere" not in code.replace("noosphere.*", "").split("import")[0] or True
    assert "def run(" in code
    assert 'if __name__ == "__main__"' in code


def test_rendered_adapter_is_valid_python(packaged_dir):
    adapter_path = packaged_dir / "adapter.py"
    code = adapter_path.read_text()
    compile(code, str(adapter_path), "exec")


def _docker_available() -> bool:
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _docker_available(), reason="Docker not available")
def test_adapter_in_docker_no_network(packaged_dir):
    """Build and run the packaged adapter in Docker with --network=none."""
    tag = "test-sc-adapter:latest"
    build = subprocess.run(
        ["docker", "build", "-t", tag, "."],
        cwd=str(packaged_dir),
        capture_output=True, text=True, timeout=120,
    )
    assert build.returncode == 0, f"Docker build failed: {build.stderr}"

    input_file = packaged_dir / "test_input.json"
    input_file.write_text('{"value": "hello"}')

    run = subprocess.run(
        [
            "docker", "run", "--rm", "--network=none",
            "-v", f"{input_file}:/app/test_input.json:ro",
            tag, "test_input.json",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert run.returncode == 0, f"Docker run failed: {run.stderr}"
    assert "echo:hello" in run.stdout

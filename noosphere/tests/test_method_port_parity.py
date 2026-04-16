"""Test parity between ported methods and their legacy equivalents."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

_PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "port_parity"
METHODS_DIR = _PROJECT_DIR / "noosphere" / "methods"
LEGACY_DIR = METHODS_DIR / "_legacy"


def _ensure_registry_populated() -> None:
    for py in sorted(METHODS_DIR.glob("*.py")):
        if py.name.startswith("_") or py.name == "__init__.py":
            continue
        try:
            importlib.import_module(f"noosphere.methods.{py.stem}")
        except Exception:
            pass


def _discover_parity_pairs() -> list:
    _ensure_registry_populated()
    from noosphere.methods._registry import REGISTRY

    pairs = []
    for spec in REGISTRY.list():
        name = spec.name
        legacy_file = LEGACY_DIR / f"{name}.py"
        fixture_file = FIXTURES_DIR / name / "case1.json"
        if legacy_file.exists() and fixture_file.exists():
            pairs.append(pytest.param(name, id=name))
    return pairs


def _find_input_class(method_name: str, spec):
    mod = importlib.import_module(f"noosphere.methods.{method_name}")
    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if (
            isinstance(attr, type)
            and issubclass(attr, BaseModel)
            and attr is not BaseModel
        ):
            try:
                if attr.model_json_schema() == spec.input_schema:
                    return attr
            except Exception:
                pass
    return None


def _to_dict(obj):
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    return obj


@pytest.mark.parametrize("method_name", _discover_parity_pairs())
def test_method_port_parity(method_name: str) -> None:
    from noosphere.methods._registry import REGISTRY

    spec, ported_fn = REGISTRY.get(method_name)

    fixture_path = FIXTURES_DIR / method_name / "case1.json"
    fixture_data = json.loads(fixture_path.read_text())

    if spec.nondeterministic and "seed" not in fixture_data:
        pytest.skip(
            f"Method '{method_name}' is nondeterministic and fixture has no pinned seed"
        )

    input_cls = _find_input_class(method_name, spec)
    if input_cls is None:
        pytest.skip(f"Cannot determine input class for '{method_name}'")

    input_obj = input_cls(**fixture_data)

    legacy_mod_name = f"noosphere.methods._legacy.{method_name}"
    try:
        legacy_mod = importlib.import_module(legacy_mod_name)
    except ImportError:
        pytest.skip(f"Legacy module {legacy_mod_name} not importable")
        return

    legacy_fn = getattr(legacy_mod, method_name, None)
    if legacy_fn is None or not callable(legacy_fn):
        pytest.skip(
            f"No callable '{method_name}' found in {legacy_mod_name}"
        )
        return

    ported_result = ported_fn(input_obj)
    legacy_result = legacy_fn(input_obj)

    assert _to_dict(ported_result) == _to_dict(legacy_result), (
        f"Parity mismatch for {method_name}:\n"
        f"  Ported: {_to_dict(ported_result)}\n"
        f"  Legacy: {_to_dict(legacy_result)}"
    )

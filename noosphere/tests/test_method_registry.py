"""Tests for the method registry."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from noosphere.models import Method, MethodImplRef, MethodType
from noosphere.methods._registry import (
    REGISTRY,
    MethodCollisionError,
    MethodNotFoundError,
    MethodRegistry,
)
from noosphere.methods._decorator import _canonical_json, register_method
from noosphere.methods._hooks import (
    _POST_HOOKS,
    _PRE_HOOKS,
    _FAILURE_HOOKS,
    unregister_hook,
)


def _make_impl() -> MethodImplRef:
    return MethodImplRef(
        module="test", fn_name="test_fn", git_sha="abc123", image_digest=None
    )


def _make_method(
    name: str, version: str, status: str = "active"
) -> Method:
    return Method(
        method_id=f"{name}_{version}_{status}",
        name=name,
        version=version,
        method_type=MethodType.EXTRACTION,
        input_schema={},
        output_schema={},
        description="test",
        rationale="test",
        preconditions=[],
        postconditions=[],
        dependencies=[],
        implementation=_make_impl(),
        owner="test",
        status=status,
        nondeterministic=False,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture(autouse=True)
def _fresh_registry():
    """Give each test a clean registry."""
    reg = MethodRegistry()
    yield reg


class TestMethodRegistry:
    def test_register_two_versions(self):
        reg = MethodRegistry()
        m1 = _make_method("extractor", "1.0.0")
        m2 = _make_method("extractor", "2.0.0")
        reg.register(m1, lambda x: x)
        reg.register(m2, lambda x: x)
        assert len(reg.list()) == 2

    def test_get_latest_returns_highest_semver(self):
        reg = MethodRegistry()
        m1 = _make_method("extractor", "1.0.0")
        m2 = _make_method("extractor", "2.0.0")
        m3 = _make_method("extractor", "1.5.0")
        reg.register(m1, lambda x: x)
        reg.register(m2, lambda x: x)
        reg.register(m3, lambda x: x)
        spec, _fn = reg.get("extractor", "latest")
        assert spec.version == "2.0.0"

    def test_retired_not_returned_by_default(self):
        reg = MethodRegistry()
        m_active = _make_method("judge", "1.0.0", status="active")
        m_retired = _make_method("judge", "2.0.0", status="retired")
        reg.register(m_active, lambda x: x)
        reg.register(m_retired, lambda x: x)
        spec, _ = reg.get("judge", "latest")
        assert spec.version == "1.0.0"

    def test_retired_returned_with_flag(self):
        reg = MethodRegistry()
        m_retired = _make_method("judge", "2.0.0", status="retired")
        reg.register(m_retired, lambda x: x)
        spec, _ = reg.get("judge", "latest", include_retired=True)
        assert spec.version == "2.0.0"

    def test_collision_error(self):
        reg = MethodRegistry()
        m1 = _make_method("dup", "1.0.0")
        reg.register(m1, lambda x: x)
        m2 = _make_method("dup", "1.0.0")
        with pytest.raises(MethodCollisionError):
            reg.register(m2, lambda x: x)

    def test_not_found_error(self):
        reg = MethodRegistry()
        with pytest.raises(MethodNotFoundError):
            reg.get("unknown")

    def test_list_with_status_filter(self):
        reg = MethodRegistry()
        reg.register(_make_method("a", "1.0.0", "active"), lambda x: x)
        reg.register(_make_method("b", "1.0.0", "deprecated"), lambda x: x)
        active = reg.list(status_filter="active")
        assert len(active) == 1
        assert active[0].name == "a"

    def test_canonical_input_hashing(self):
        """Two calls with equal payloads produce equal input_hash."""
        payload_a = {"key": "value", "nested": {"b": 2, "a": 1}}
        payload_b = {"nested": {"a": 1, "b": 2}, "key": "value"}
        hash_a = _canonical_json(payload_a)
        hash_b = _canonical_json(payload_b)
        assert hash_a == hash_b

    def test_emits_edges_side_table(self):
        from noosphere.models import CascadeEdgeRelation

        reg = MethodRegistry()
        edges = [CascadeEdgeRelation.EXTRACTED_FROM]
        reg.set_emits_edges("m1", edges)
        assert reg.get_emits_edges("m1") == edges
        assert reg.get_emits_edges("nonexistent") == []

"""Tests for the method hooks and the decorator's hook pipeline."""
from __future__ import annotations

import hashlib
import os

import pytest

from noosphere.models import MethodType
from noosphere.methods._decorator import _canonical_json, register_method
from noosphere.methods._hooks import (
    _FAILURE_HOOKS,
    _POST_HOOKS,
    _PRE_HOOKS,
    register_failure_hook,
    register_post_hook,
    register_pre_hook,
    unregister_hook,
)
from noosphere.methods._registry import MethodRegistry, REGISTRY


@pytest.fixture(autouse=True)
def _clean_hooks():
    """Clear all hooks and reset the global registry before each test."""
    _PRE_HOOKS.clear()
    _POST_HOOKS.clear()
    _FAILURE_HOOKS.clear()
    saved_specs = dict(REGISTRY._specs)
    saved_fns = dict(REGISTRY._fns)
    REGISTRY._specs.clear()
    REGISTRY._fns.clear()
    yield
    _PRE_HOOKS.clear()
    _POST_HOOKS.clear()
    _FAILURE_HOOKS.clear()
    REGISTRY._specs.clear()
    REGISTRY._fns.clear()
    REGISTRY._specs.update(saved_specs)
    REGISTRY._fns.update(saved_fns)


def _make_identity(name: str, version: str = "1.0.0"):
    """Register a trivial identity method and return the wrapped function."""
    @register_method(
        name=name,
        version=version,
        method_type=MethodType.EXTRACTION,
        input_schema={},
        output_schema={},
        description="test method",
        rationale="testing",
        owner="test",
    )
    def identity(data):
        return data

    return identity


class TestPreHooks:
    def test_fire_in_registration_order(self):
        order: list[str] = []
        register_pre_hook("first", lambda _s, _i, _d: order.append("first"))
        register_pre_hook("second", lambda _s, _i, _d: order.append("second"))
        fn = _make_identity("ordered_pre")
        fn({"x": 1})
        assert order == ["first", "second"]

    def test_pre_hook_raising_aborts_execution(self):
        body_called = False

        def boom(_s, _i, _d):
            raise RuntimeError("pre-hook failure")

        register_pre_hook("boom", boom)

        failure_invocations: list = []
        register_failure_hook(
            "capture",
            lambda _s, inv, _d, _e: failure_invocations.append(inv),
        )

        @register_method(
            name="abort_test",
            version="1.0.0",
            method_type=MethodType.EXTRACTION,
            input_schema={},
            output_schema={},
            description="test",
            rationale="test",
            owner="test",
        )
        def tracked(data):
            nonlocal body_called
            body_called = True
            return data

        with pytest.raises(RuntimeError, match="pre-hook failure"):
            tracked({"a": 1})

        assert not body_called
        assert len(failure_invocations) == 1
        assert failure_invocations[0].succeeded is False
        assert failure_invocations[0].error_kind == "RuntimeError"


class TestPostHooks:
    def test_fire_in_registration_order(self):
        order: list[str] = []
        register_post_hook(
            "first", lambda _s, _i, _d, _r: order.append("first")
        )
        register_post_hook(
            "second", lambda _s, _i, _d, _r: order.append("second")
        )
        fn = _make_identity("ordered_post")
        fn({"x": 1})
        assert order == ["first", "second"]

    def test_post_hook_raising_does_not_reraise(self):
        def boom(_s, _i, _d, _r):
            raise ValueError("post-hook explosion")

        register_post_hook("boom", boom)
        fn = _make_identity("post_boom")
        result = fn({"value": 42})
        assert result == {"value": 42}


class TestFailureHooks:
    def test_failure_hooks_fire_on_body_exception(self):
        captured: list = []
        register_failure_hook(
            "capture",
            lambda _s, inv, _d, exc: captured.append((inv, exc)),
        )

        @register_method(
            name="failing_body",
            version="1.0.0",
            method_type=MethodType.JUDGMENT,
            input_schema={},
            output_schema={},
            description="test",
            rationale="test",
            owner="test",
        )
        def bad_fn(data):
            raise ValueError("body error")

        with pytest.raises(ValueError, match="body error"):
            bad_fn({"x": 1})

        assert len(captured) == 1
        inv, exc = captured[0]
        assert inv.succeeded is False
        assert inv.error_kind == "ValueError"
        assert isinstance(exc, ValueError)


class TestUnregisterHook:
    def test_unregister_removes_cleanly(self):
        called = False

        def hook(_s, _i, _d):
            nonlocal called
            called = True

        register_pre_hook("removable", hook)
        unregister_hook("removable")
        fn = _make_identity("unreg_test")
        fn({})
        assert not called

    def test_unregister_absent_is_noop(self):
        unregister_hook("nonexistent")


class TestReplaceHook:
    def test_re_register_replaces_in_place(self):
        order: list[str] = []
        register_pre_hook("a", lambda _s, _i, _d: order.append("a_v1"))
        register_pre_hook("b", lambda _s, _i, _d: order.append("b"))
        register_pre_hook("a", lambda _s, _i, _d: order.append("a_v2"))

        fn = _make_identity("replace_test")
        fn({})
        assert order == ["a_v2", "b"]


class TestCanonicalHashing:
    def test_equal_payloads_produce_equal_hashes(self):
        fn = _make_identity("hash_test")

        hashes: list[str] = []

        def capture_hash(_s, inv, _d, _r):
            hashes.append(inv.input_hash)

        register_post_hook("capture", capture_hash)

        fn({"key": "value", "nested": {"b": 2, "a": 1}})
        fn({"nested": {"a": 1, "b": 2}, "key": "value"})

        assert len(hashes) == 2
        assert hashes[0] == hashes[1]

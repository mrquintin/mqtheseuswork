"""Tests: retrieval with decay pre-hook hides stale objects by default."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from noosphere.models import Freshness, Method, MethodImplRef, MethodInvocation, MethodType
from noosphere.decay.hooks import _pre_decay_watch


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_inv() -> MethodInvocation:
    return MethodInvocation(
        id="inv1",
        method_id="m1",
        input_hash="ih",
        output_hash="oh",
        started_at=_now(),
        ended_at=None,
        succeeded=True,
        error_kind=None,
        correlation_id="c1",
        tenant_id="t1",
    )


def _make_spec() -> Method:
    return Method(
        method_id="m1",
        name="retrieve",
        version="1.0",
        method_type=MethodType.EXTRACTION,
        input_schema={},
        output_schema={},
        description="d",
        rationale="r",
        preconditions=[],
        postconditions=[],
        dependencies=[],
        implementation=MethodImplRef(module="m", fn_name="f", git_sha="x"),
        owner="o",
        status="active",
        nondeterministic=False,
        created_at=_now(),
    )


class TestStaleHiddenByDefault:
    def test_stale_objects_filtered_from_results(self):
        spec = _make_spec()
        inv = _make_inv()
        input_data = {
            "results": [
                {"id": "a", "freshness": "fresh"},
                {"id": "b", "freshness": "stale"},
                {"id": "c", "freshness": "retired"},
                {"id": "d", "freshness": "aging"},
            ]
        }
        _pre_decay_watch(spec, inv, input_data)
        ids = [r["id"] for r in input_data["results"]]
        assert "a" in ids
        assert "d" in ids
        assert "b" not in ids
        assert "c" not in ids

    def test_include_non_fresh_bypasses_filter(self):
        spec = _make_spec()
        inv = _make_inv()
        input_data = {
            "include_non_fresh": True,
            "results": [
                {"id": "a", "freshness": "fresh"},
                {"id": "b", "freshness": "stale"},
                {"id": "c", "freshness": "retired"},
            ],
        }
        _pre_decay_watch(spec, inv, input_data)
        ids = [r["id"] for r in input_data["results"]]
        assert len(ids) == 3
        assert "b" in ids
        assert "c" in ids

    def test_items_key_also_filtered(self):
        spec = _make_spec()
        inv = _make_inv()
        input_data = {
            "items": [
                {"id": "x", "freshness": "fresh"},
                {"id": "y", "freshness": "stale"},
            ]
        }
        _pre_decay_watch(spec, inv, input_data)
        ids = [r["id"] for r in input_data["items"]]
        assert "x" in ids
        assert "y" not in ids

    def test_non_dict_input_is_noop(self):
        spec = _make_spec()
        inv = _make_inv()
        _pre_decay_watch(spec, inv, "not a dict")

    def test_model_objects_filtered_by_freshness(self):
        spec = _make_spec()
        inv = _make_inv()
        fresh_obj = MagicMock()
        fresh_obj.freshness = Freshness.FRESH
        stale_obj = MagicMock()
        stale_obj.freshness = Freshness.STALE
        input_data = {"results": [fresh_obj, stale_obj]}
        _pre_decay_watch(spec, inv, input_data)
        assert len(input_data["results"]) == 1
        assert input_data["results"][0].freshness == Freshness.FRESH

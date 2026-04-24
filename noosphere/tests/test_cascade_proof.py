"""Tests for proof bundle export and verification."""
from __future__ import annotations

import json
import tarfile
import tempfile
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from noosphere.models import CascadeEdgeRelation, MethodInvocation
from noosphere.store import Store
from noosphere.cascade.graph import CascadeGraph
from noosphere.cascade.export import export_proof


def _uid() -> str:
    return str(_uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _make_inv(**kw) -> MethodInvocation:
    d = dict(
        id=_uid(), method_id=_uid(),
        input_hash="ih", output_hash="oh",
        started_at=_now(), ended_at=_now(),
        succeeded=True, error_kind=None,
        correlation_id=_uid(), tenant_id="t1",
    )
    d.update(kw)
    return MethodInvocation(**d)


def _setup():
    store = _store()
    inv = _make_inv()
    store.insert_method_invocation(inv)
    graph = CascadeGraph(store)
    return store, graph, inv


class TestProofExport:
    def test_basic_proof_bundle(self, tmp_path):
        store, graph, inv = _setup()
        graph.add_edge(
            src="evidence", dst="conclusion",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.95,
        )

        out = tmp_path / "proof.tar.gz"
        result = export_proof(store, "conclusion", out)

        assert result == out
        assert out.exists()

        with tarfile.open(out, "r:gz") as tar:
            names = tar.getnames()
            assert "proof.json" in names
            assert "edges.json" in names
            assert "nodes.json" in names
            assert "methods.json" in names

            proof = json.load(tar.extractfile("proof.json"))
            assert proof["conclusion_id"] == "conclusion"
            assert proof["total_edges"] == 1
            assert proof["total_nodes"] == 2

            edges = json.load(tar.extractfile("edges.json"))
            assert len(edges) == 1
            assert edges[0]["src"] == "evidence"
            assert edges[0]["dst"] == "conclusion"

    def test_transitive_evidence_chain(self, tmp_path):
        store, graph, inv = _setup()
        graph.add_edge(
            src="raw_data", dst="claim",
            relation=CascadeEdgeRelation.EXTRACTED_FROM,
            method_invocation_id=inv.id,
            confidence=1.0,
        )
        graph.add_edge(
            src="claim", dst="principle",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.9,
        )
        graph.add_edge(
            src="principle", dst="conclusion",
            relation=CascadeEdgeRelation.AGGREGATES,
            method_invocation_id=inv.id,
            confidence=0.85,
        )

        out = tmp_path / "chain.tar.gz"
        export_proof(store, "conclusion", out)

        with tarfile.open(out, "r:gz") as tar:
            proof = json.load(tar.extractfile("proof.json"))
            assert proof["total_edges"] == 3
            assert proof["total_nodes"] == 4

            edges = json.load(tar.extractfile("edges.json"))
            assert len(edges) == 3

    def test_redact_private_removes_input_hash(self, tmp_path):
        store, graph, inv = _setup()
        graph.add_edge(
            src="ev", dst="conc",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.9,
        )

        out = tmp_path / "redacted.tar.gz"
        export_proof(store, "conc", out, redact_private=True)

        with tarfile.open(out, "r:gz") as tar:
            methods = json.load(tar.extractfile("methods.json"))
            for m in methods:
                assert "input_hash" not in m

    def test_no_redaction_keeps_input_hash(self, tmp_path):
        store, graph, inv = _setup()
        graph.add_edge(
            src="ev", dst="conc",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.9,
        )

        out = tmp_path / "full.tar.gz"
        export_proof(store, "conc", out, redact_private=False)

        with tarfile.open(out, "r:gz") as tar:
            methods = json.load(tar.extractfile("methods.json"))
            assert any("input_hash" in m for m in methods)

    def test_proof_methods_reference_invocations(self, tmp_path):
        store, graph, inv = _setup()
        graph.add_edge(
            src="a", dst="b",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=inv.id,
            confidence=0.8,
        )

        out = tmp_path / "methods.tar.gz"
        export_proof(store, "b", out)

        with tarfile.open(out, "r:gz") as tar:
            methods = json.load(tar.extractfile("methods.json"))
            assert len(methods) == 1
            assert methods[0]["id"] == inv.id

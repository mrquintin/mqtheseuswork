"""Tests for cascade edge declaration parity checks."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from noosphere.models import CascadeEdgeRelation
from noosphere.cascade.hooks import CascadeEdgeDeclarationError, check_declaration_parity


class OutputWithTargets(BaseModel):
    supports_targets: list[str] = []
    refutes_targets: list[str] = []
    confidence: float = 1.0


class OutputMissingField(BaseModel):
    confidence: float = 1.0


class OutputWithEmittedEdges(BaseModel):
    emitted_edges: list[dict] = []
    confidence: float = 1.0


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "cascade_decl"


class TestDeclarationParity:
    def test_matching_output_passes(self):
        check_declaration_parity(
            OutputWithTargets,
            [CascadeEdgeRelation.SUPPORTS, CascadeEdgeRelation.REFUTES],
        )

    def test_missing_field_raises(self):
        with pytest.raises(CascadeEdgeDeclarationError, match="supports_targets"):
            check_declaration_parity(
                OutputMissingField,
                [CascadeEdgeRelation.SUPPORTS],
            )

    def test_empty_declarations_passes(self):
        check_declaration_parity(OutputMissingField, [])

    def test_emitted_edges_field_bypasses_check(self):
        check_declaration_parity(
            OutputWithEmittedEdges,
            [CascadeEdgeRelation.SUPPORTS, CascadeEdgeRelation.REFUTES],
        )

    def test_dict_schema_matching(self):
        schema = {
            "properties": {
                "supports_targets": {"type": "array"},
                "confidence": {"type": "number"},
            }
        }
        check_declaration_parity(
            schema,
            [CascadeEdgeRelation.SUPPORTS],
        )

    def test_dict_schema_missing(self):
        schema = {
            "properties": {
                "confidence": {"type": "number"},
            }
        }
        with pytest.raises(CascadeEdgeDeclarationError):
            check_declaration_parity(
                schema,
                [CascadeEdgeRelation.SUPPORTS],
            )


class TestFixtureParity:
    def test_nli_scorer_fixture(self):
        fixture_path = FIXTURES_DIR / "nli_scorer.json"
        data = json.loads(fixture_path.read_text())
        declared = [CascadeEdgeRelation(r) for r in data["emits_edges"]]
        output_fields = set(data["output_fields"])

        for rel in declared:
            expected = f"{rel.value}_targets"
            assert expected in output_fields or "emitted_edges" in output_fields, (
                f"Fixture declares edge '{rel.value}' but output lacks '{expected}'"
            )

    def test_claim_extractor_fixture(self):
        fixture_path = FIXTURES_DIR / "claim_extractor.json"
        data = json.loads(fixture_path.read_text())
        declared = [CascadeEdgeRelation(r) for r in data["emits_edges"]]
        output_fields = set(data["output_fields"])

        for rel in declared:
            expected = f"{rel.value}_targets"
            assert expected in output_fields or "emitted_edges" in output_fields, (
                f"Fixture declares edge '{rel.value}' but output lacks '{expected}'"
            )

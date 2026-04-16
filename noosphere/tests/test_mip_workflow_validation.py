"""Tests: workflow YAML validation — malformed, unknown method, disallowed keys."""
from __future__ import annotations

import pytest

from noosphere.interop.workflow import validate

METHODS = ["extract", "judge", "aggregate"]


class TestValidWorkflow:
    def test_valid_workflow_no_errors(self):
        yaml_str = (
            "name: my_workflow\n"
            "steps:\n"
            "  - id: s1\n"
            "    method: extract\n"
            "    input: $input\n"
            "  - id: s2\n"
            "    method: judge\n"
            "    input: $steps.s1\n"
            "output: s2\n"
        )
        errors = validate(yaml_str, METHODS)
        assert errors == []

    def test_valid_workflow_with_when(self):
        yaml_str = (
            "name: conditional\n"
            "steps:\n"
            "  - id: s1\n"
            "    method: extract\n"
            "    input: $input\n"
            "    when:\n"
            "      field: status\n"
            "      equals: ready\n"
            "output: s1\n"
        )
        errors = validate(yaml_str, METHODS)
        assert errors == []


class TestMissingFields:
    def test_missing_name(self):
        yaml_str = (
            "steps:\n"
            "  - id: s1\n"
            "    method: extract\n"
            "    input: x\n"
            "output: s1\n"
        )
        errors = validate(yaml_str, METHODS)
        assert any("name" in e for e in errors)

    def test_missing_steps(self):
        yaml_str = "name: test\noutput: s1\n"
        errors = validate(yaml_str, METHODS)
        assert any("steps" in e for e in errors)

    def test_missing_output(self):
        yaml_str = (
            "name: test\n"
            "steps:\n"
            "  - id: s1\n"
            "    method: extract\n"
            "    input: x\n"
        )
        errors = validate(yaml_str, METHODS)
        assert any("output" in e for e in errors)

    def test_missing_step_id(self):
        yaml_str = (
            "name: test\n"
            "steps:\n"
            "  - method: extract\n"
            "    input: x\n"
            "output: s1\n"
        )
        errors = validate(yaml_str, METHODS)
        assert any("id" in e for e in errors)

    def test_missing_step_method(self):
        yaml_str = (
            "name: test\n"
            "steps:\n"
            "  - id: s1\n"
            "    input: x\n"
            "output: s1\n"
        )
        errors = validate(yaml_str, METHODS)
        assert any("method" in e for e in errors)

    def test_missing_step_input(self):
        yaml_str = (
            "name: test\n"
            "steps:\n"
            "  - id: s1\n"
            "    method: extract\n"
            "output: s1\n"
        )
        errors = validate(yaml_str, METHODS)
        assert any("input" in e for e in errors)


class TestDisallowedKeys:
    def test_disallowed_top_level_key(self):
        yaml_str = (
            "name: test\n"
            "steps:\n"
            "  - id: s1\n"
            "    method: extract\n"
            "    input: x\n"
            "output: s1\n"
            "shell: /bin/bash\n"
        )
        errors = validate(yaml_str, METHODS)
        assert any("disallowed" in e.lower() or "Disallowed" in e for e in errors)
        assert any("shell" in e for e in errors)

    def test_disallowed_step_key(self):
        yaml_str = (
            "name: test\n"
            "steps:\n"
            "  - id: s1\n"
            "    method: extract\n"
            "    input: x\n"
            "    loop: 5\n"
            "output: s1\n"
        )
        errors = validate(yaml_str, METHODS)
        assert any("disallowed" in e.lower() or "Disallowed" in e for e in errors)
        assert any("loop" in e for e in errors)

    def test_disallowed_when_key(self):
        yaml_str = (
            "name: test\n"
            "steps:\n"
            "  - id: s1\n"
            "    method: extract\n"
            "    input: x\n"
            "    when:\n"
            "      field: status\n"
            "      equals: ready\n"
            "      operator: gt\n"
            "output: s1\n"
        )
        errors = validate(yaml_str, METHODS)
        assert any("operator" in e for e in errors)


class TestUnknownMethod:
    def test_unknown_method_error(self):
        yaml_str = (
            "name: test\n"
            "steps:\n"
            "  - id: s1\n"
            "    method: nonexistent_method\n"
            "    input: x\n"
            "output: s1\n"
        )
        errors = validate(yaml_str, METHODS)
        assert any("unknown method" in e.lower() or "nonexistent_method" in e for e in errors)


class TestOutputRef:
    def test_output_references_unknown_step(self):
        yaml_str = (
            "name: test\n"
            "steps:\n"
            "  - id: s1\n"
            "    method: extract\n"
            "    input: x\n"
            "output: s99\n"
        )
        errors = validate(yaml_str, METHODS)
        assert any("s99" in e for e in errors)


class TestMalformedYAML:
    def test_invalid_yaml(self):
        errors = validate("steps:\n  - id: [unterminated", METHODS)
        assert any("parse error" in e.lower() or "YAML" in e for e in errors)

    def test_non_mapping(self):
        errors = validate("- just a list\n", METHODS)
        assert any("mapping" in e.lower() for e in errors)

    def test_empty_steps(self):
        yaml_str = "name: test\nsteps: []\noutput: s1\n"
        errors = validate(yaml_str, METHODS)
        assert any("non-empty" in e.lower() or "steps" in e for e in errors)

    def test_duplicate_step_ids(self):
        yaml_str = (
            "name: test\n"
            "steps:\n"
            "  - id: dup\n"
            "    method: extract\n"
            "    input: x\n"
            "  - id: dup\n"
            "    method: judge\n"
            "    input: y\n"
            "output: dup\n"
        )
        errors = validate(yaml_str, METHODS)
        assert any("duplicate" in e.lower() for e in errors)

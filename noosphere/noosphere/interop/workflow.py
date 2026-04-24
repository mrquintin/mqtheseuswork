"""Minimal YAML workflow parser and validator for MIP bundles."""

from __future__ import annotations

from typing import Any

import yaml

_ALLOWED_TOP_KEYS = {"name", "steps", "output"}
_ALLOWED_STEP_KEYS = {"id", "method", "input", "when"}
_ALLOWED_WHEN_KEYS = {"field", "equals"}


def validate(workflow_yaml: str, available_methods: list[str]) -> list[str]:
    errors: list[str] = []

    try:
        doc = yaml.safe_load(workflow_yaml)
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]

    if not isinstance(doc, dict):
        return ["Workflow must be a YAML mapping"]

    extra_keys = set(doc.keys()) - _ALLOWED_TOP_KEYS
    if extra_keys:
        errors.append(f"Disallowed top-level keys: {sorted(extra_keys)}")

    if "name" not in doc:
        errors.append("Missing required key: name")
    elif not isinstance(doc["name"], str):
        errors.append("'name' must be a string")

    if "steps" not in doc:
        errors.append("Missing required key: steps")
        return errors

    steps = doc["steps"]
    if not isinstance(steps, list) or len(steps) == 0:
        errors.append("'steps' must be a non-empty list")
        return errors

    if "output" not in doc:
        errors.append("Missing required key: output")

    step_ids: set[str] = set()
    for i, step in enumerate(steps):
        prefix = f"steps[{i}]"
        if not isinstance(step, dict):
            errors.append(f"{prefix}: must be a mapping")
            continue

        step_extra = set(step.keys()) - _ALLOWED_STEP_KEYS
        if step_extra:
            errors.append(f"{prefix}: disallowed keys: {sorted(step_extra)}")

        if "id" not in step:
            errors.append(f"{prefix}: missing required key 'id'")
        elif not isinstance(step["id"], str):
            errors.append(f"{prefix}: 'id' must be a string")
        else:
            if step["id"] in step_ids:
                errors.append(f"{prefix}: duplicate step id '{step['id']}'")
            step_ids.add(step["id"])

        if "method" not in step:
            errors.append(f"{prefix}: missing required key 'method'")
        elif step["method"] not in available_methods:
            errors.append(f"{prefix}: unknown method '{step['method']}'")

        if "input" not in step:
            errors.append(f"{prefix}: missing required key 'input'")

        if "when" in step:
            errors.extend(_validate_when(step["when"], prefix))

    if "output" in doc and doc["output"] not in step_ids:
        errors.append(f"output references unknown step id '{doc['output']}'")

    return errors


def parse(workflow_yaml: str) -> dict[str, Any]:
    return yaml.safe_load(workflow_yaml)


def _validate_when(when: Any, prefix: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(when, dict):
        errors.append(f"{prefix}.when: must be a mapping")
        return errors

    extra = set(when.keys()) - _ALLOWED_WHEN_KEYS
    if extra:
        errors.append(f"{prefix}.when: disallowed keys: {sorted(extra)}")

    if "field" not in when:
        errors.append(f"{prefix}.when: missing 'field'")
    if "equals" not in when:
        errors.append(f"{prefix}.when: missing 'equals'")

    return errors

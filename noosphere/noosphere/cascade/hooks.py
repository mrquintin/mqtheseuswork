"""Cascade post-hook: automatically emits cascade edges from method outputs.

Convention for edge emission from method outputs:

1. Standard methods (single source node):
   The method input is expected to have a `primary_src` or `node_id` field
   identifying the source node. The output must have `<relation>_targets`
   fields (e.g. `supports_targets: list[str]`) for each relation declared
   in the method's `emits_edges` spec.

2. Aggregator methods (multiple sources):
   When the input has no single source node, the output must provide
   `emitted_edges: list[dict]` where each dict has keys:
   {src, dst, relation, confidence}.
"""
from __future__ import annotations

import logging
from typing import Any

from noosphere.models import CascadeEdgeRelation, Method, MethodInvocation

logger = logging.getLogger(__name__)


class CascadeEdgeDeclarationError(Exception):
    """Method output schema lacks a declared <relation>_targets field."""


def _resolve_source(validated_input: Any) -> str | None:
    """Resolve the primary source node from a method's validated input."""
    if hasattr(validated_input, "primary_src"):
        return validated_input.primary_src
    if hasattr(validated_input, "node_id"):
        return validated_input.node_id
    if isinstance(validated_input, dict):
        return validated_input.get("primary_src") or validated_input.get("node_id")
    return None


def _emit_edges(
    spec: Method,
    inv: MethodInvocation,
    validated_input: Any,
    result: Any,
) -> None:
    from noosphere.cascade.graph import CascadeGraph
    from noosphere.methods._decorator import _get_store
    from noosphere.methods._registry import REGISTRY

    declared = REGISTRY.get_emits_edges(spec.method_id)
    if not declared:
        return

    store = _get_store()
    if store is None:
        logger.warning("No store available for cascade edge emission")
        return

    # Ensure the invocation exists in the store before inserting edges,
    # since post-hooks fire before the decorator persists the invocation.
    try:
        store.insert_method_invocation(inv)
    except Exception:
        pass  # already persisted or duplicate — fine

    if hasattr(result, "emitted_edges") and result.emitted_edges:
        graph = CascadeGraph(store)
        for entry in result.emitted_edges:
            if isinstance(entry, dict):
                rel = entry.get("relation", "")
                if isinstance(rel, str):
                    rel = CascadeEdgeRelation(rel)
                graph.add_edge(
                    src=entry["src"],
                    dst=entry["dst"],
                    relation=rel,
                    method_invocation_id=inv.id,
                    confidence=entry.get("confidence", 1.0),
                )
            else:
                graph.add_edge(
                    src=entry.src,
                    dst=entry.dst,
                    relation=entry.relation if isinstance(entry.relation, CascadeEdgeRelation) else CascadeEdgeRelation(entry.relation),
                    method_invocation_id=inv.id,
                    confidence=getattr(entry, "confidence", 1.0),
                )
        return

    src = _resolve_source(validated_input)
    if src is None:
        logger.warning(
            "Cannot resolve source node for method %s; skipping edge emission",
            spec.name,
        )
        return

    graph = CascadeGraph(store)
    confidence = getattr(result, "confidence", 1.0)
    if isinstance(confidence, property) or not isinstance(confidence, (int, float)):
        confidence = 1.0

    for relation in declared:
        field_name = f"{relation.value}_targets"
        if not hasattr(result, field_name):
            continue
        targets = getattr(result, field_name)
        if targets is None:
            continue
        for dst in targets:
            graph.add_edge(
                src=src,
                dst=dst,
                relation=relation,
                method_invocation_id=inv.id,
                confidence=confidence,
            )


def check_declaration_parity(output_schema: Any, declared_edges: list[CascadeEdgeRelation]) -> None:
    """Verify that the output schema has fields matching declared edge relations.

    Raises CascadeEdgeDeclarationError if a declared relation has no
    corresponding <relation>_targets field in the output schema.
    """
    if not declared_edges:
        return

    if hasattr(output_schema, "model_fields"):
        fields = set(output_schema.model_fields.keys())
    elif hasattr(output_schema, "__fields__"):
        fields = set(output_schema.__fields__.keys())
    elif isinstance(output_schema, dict):
        props = output_schema.get("properties", {})
        fields = set(props.keys())
    else:
        return

    if "emitted_edges" in fields:
        return

    for relation in declared_edges:
        expected_field = f"{relation.value}_targets"
        if expected_field not in fields:
            raise CascadeEdgeDeclarationError(
                f"Output schema {output_schema!r} missing field '{expected_field}' "
                f"for declared edge relation '{relation.value}'"
            )

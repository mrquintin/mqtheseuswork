"""Edge reasoner: "click an edge, ask the agent why" (prompt 13).

The reasoner explains *the existing edge*. It does not manufacture new
edges — that is the builder's job. The system prompt
(``_prompts/reasoner_system.md``) tells the model to flag weak
connections explicitly rather than confabulate a story.

The function is async so callers can fan-out reasoning over many edges
without serializing on the LLM client. The local fallback path is
synchronous; the caller's event loop is preserved.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from noosphere.models import (
    EdgeReasoning,
    KGEdge,
    KGEdgeKind,
    KGNode,
    KGNodeKind,
    SourceCitation,
)


GRAPH_REASONER_MAX_TOKENS_PER_EDGE_DEFAULT = 4000


def _max_tokens_default() -> int:
    raw = os.environ.get("GRAPH_REASONER_MAX_TOKENS_PER_EDGE", "")
    try:
        return max(256, int(raw))
    except (TypeError, ValueError):
        return GRAPH_REASONER_MAX_TOKENS_PER_EDGE_DEFAULT


def _load_system_prompt() -> str:
    path = Path(__file__).parent / "_prompts" / "reasoner_system.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return (
            "You explain why two nodes in the firm's knowledge graph "
            "are connected. You DO NOT manufacture connections that the "
            "data does not support. Every step in your reasoning cites "
            "a source or principle by id."
        )


def _node_summary(node: KGNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "kind": (
            node.kind.value if hasattr(node.kind, "value") else str(node.kind)
        ),
        "ref": node.ref,
        "label": node.label,
        "attrs": node.attrs,
    }


def _gather_citations_from_store(
    *,
    store,
    node_a: KGNode,
    node_b: KGNode,
    edge: KGEdge,
) -> list[SourceCitation]:
    """Build a short list of grounding citations from the authoritative tables.

    Used both as evidence in the prompt AND as the fallback citation
    list when the LLM either fails or is not configured.
    """
    citations: list[SourceCitation] = []
    seen: set[str] = set()

    def _add_source(ref: str) -> None:
        if not ref or ref in seen:
            return
        seen.add(ref)
        try:
            art = store.get_artifact(ref) if store is not None else None
        except Exception:
            art = None
        if art is not None:
            citations.append(
                SourceCitation(
                    ref=str(getattr(art, "id", ref)),
                    kind="SOURCE",
                    title=str(getattr(art, "title", "") or "")[:200],
                    excerpt=str(getattr(art, "uri", "") or "")[:200],
                )
            )
        else:
            citations.append(SourceCitation(ref=ref, kind="SOURCE"))

    def _add_principle(ref: str) -> None:
        if not ref or ref in seen:
            return
        seen.add(ref)
        principles = []
        try:
            principles = list(store.list_principles()) if store else []
        except Exception:
            principles = []
        match = next(
            (p for p in principles if str(getattr(p, "id", "")) == ref), None
        )
        if match is not None:
            citations.append(
                SourceCitation(
                    ref=ref,
                    kind="PRINCIPLE",
                    title=str(getattr(match, "text", "") or "")[:200],
                    excerpt=str(
                        getattr(match, "description", "")
                        or getattr(match, "text", "")
                        or ""
                    )[:200],
                )
            )
        else:
            citations.append(SourceCitation(ref=ref, kind="PRINCIPLE"))

    for n in (node_a, node_b):
        kind = n.kind if isinstance(n.kind, KGNodeKind) else KGNodeKind(n.kind)
        if kind == KGNodeKind.PRINCIPLE and n.ref:
            _add_principle(n.ref)
        elif kind == KGNodeKind.SOURCE and n.ref:
            _add_source(n.ref)

    contradiction_id = edge.attrs.get("contradiction_id") if isinstance(
        edge.attrs, dict
    ) else None
    if contradiction_id:
        citations.append(
            SourceCitation(
                ref=str(contradiction_id),
                kind="CONTRADICTION",
                title="contradiction lifecycle",
            )
        )
    return citations


_WEAK_PHRASE = "the connection is weak"


def _is_weak(text: str) -> bool:
    return _WEAK_PHRASE in (text or "").lower()


def _parse_llm_response(raw: str) -> Optional[dict[str, Any]]:
    """Best-effort: extract the first JSON object from an LLM response.

    Returns ``None`` if no parseable JSON object is found.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    # Fenced JSON block?
    fence = re.search(r"```(?:json)?\s*({.*?})\s*```", raw, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        first = raw.find("{")
        last = raw.rfind("}")
        if first == -1 or last == -1 or last <= first:
            return None
        candidate = raw[first : last + 1]
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _fallback_reasoning(
    *,
    node_a: KGNode,
    node_b: KGNode,
    edge: KGEdge,
    citations: list[SourceCitation],
) -> EdgeReasoning:
    """Produce a deterministic structural explanation without an LLM.

    Used when the LLM client is unavailable or the budget is exhausted.
    Surfaces only what we already know from the typed edge — never
    speculates.
    """
    a_label = node_a.label or node_a.ref
    b_label = node_b.label or node_b.ref
    a_kind = (
        node_a.kind.value
        if hasattr(node_a.kind, "value")
        else str(node_a.kind)
    )
    b_kind = (
        node_b.kind.value
        if hasattr(node_b.kind, "value")
        else str(node_b.kind)
    )
    edge_kind = (
        edge.kind.value if hasattr(edge.kind, "value") else str(edge.kind)
    )

    weak = False
    chain: list[str] = []

    if edge_kind == KGEdgeKind.DERIVED_FROM.value:
        chain.append(
            f"Principle '{a_label}' carries a source_artifact pointer to "
            f"'{b_label}' (id={node_b.ref}), so the projection lifts this "
            "directly from the authoritative principle row."
        )
        short = (
            f"'{a_label}' is the firm's distilled reading of the source "
            f"'{b_label}'."
        )
    elif edge_kind == KGEdgeKind.INVOKES.value:
        chain.append(
            f"Algorithm '{a_label}' lists '{node_b.ref}' on its "
            "source_principle_ids — the runtime applies this principle "
            "when the trigger predicate fires."
        )
        short = (
            f"The algorithm '{a_label}' fires by applying principle "
            f"'{b_label}'."
        )
    elif edge_kind == KGEdgeKind.CONTRADICTS.value:
        status = (
            edge.attrs.get("status") if isinstance(edge.attrs, dict) else ""
        )
        chain.append(
            f"The contradiction engine flagged '{a_label}' and '{b_label}' "
            f"with score {edge.weight:.2f} (status: {status})."
        )
        short = (
            f"'{a_label}' and '{b_label}' disagree on the firm's record "
            f"(contradiction score {edge.weight:.2f})."
        )
    elif edge_kind == KGEdgeKind.CITES.value:
        chain.append(
            f"Memo '{a_label}' lists '{node_b.ref}' on its citation set "
            "(governing_principle_ids or observed_input_ids)."
        )
        short = f"Memo '{a_label}' cites '{b_label}' as part of its reasoning chain."
    elif edge_kind == KGEdgeKind.SUPPORTS.value:
        chain.append(
            "An explicit support relationship has been recorded between "
            f"'{a_label}' and '{b_label}' (confidence {edge.weight:.2f})."
        )
        short = (
            f"'{a_label}' supports '{b_label}' — but the connection rests "
            "on the cited source rather than a deeper conceptual proof."
            if edge.weight < 0.75
            else f"'{a_label}' supports '{b_label}'."
        )
        weak = edge.weight < 0.5
    elif edge_kind == KGEdgeKind.APPLIES_TO.value:
        chain.append(
            f"Principle '{a_label}' lists '{b_label}' (or a near-substring) "
            "in its domain_of_applicability."
        )
        short = f"'{a_label}' applies to the topic '{b_label}'."
    elif edge_kind == KGEdgeKind.PREDICTS.value:
        chain.append(
            f"Algorithm '{a_label}' produces an output that names "
            f"'{b_label}' in its schema."
        )
        short = f"'{a_label}' projects outputs that bear on '{b_label}'."
    elif edge_kind == KGEdgeKind.MENTIONS.value:
        chain.append(
            f"Source '{a_label}' contains a named-entity reference to "
            f"'{b_label}' (NER-cached on the source row)."
        )
        short = f"'{a_label}' mentions '{b_label}' in its text."
        weak = edge.weight < 0.3
    else:
        chain.append(
            f"Edge ({a_kind} → {b_kind}) of kind {edge_kind} with weight "
            f"{edge.weight:.2f}."
        )
        short = f"'{a_label}' is linked to '{b_label}' via {edge_kind}."

    if weak:
        short = (
            "The connection is weak. The two are adjacent in our graph "
            f"because of {edge_kind.lower()} with weight {edge.weight:.2f}, "
            "but the conceptual link is shallow."
        )

    return EdgeReasoning(
        question_implied=f"Why are '{a_label}' and '{b_label}' connected?",
        short_answer=short,
        reasoning_chain=chain,
        citations=citations,
        confidence_low=0.4 if weak else 0.6,
        confidence_high=0.6 if weak else 0.85,
        generated_at=datetime.now(timezone.utc),
        weak_connection=weak,
    )


async def reason_about_edge(
    node_a: KGNode,
    node_b: KGNode,
    edge: KGEdge,
    *,
    store=None,  # noqa: ANN001
    llm=None,  # noqa: ANN001
    budget: Optional[int] = None,
    timeout_s: float = 30.0,
) -> EdgeReasoning:
    """Explain *why* the edge between ``node_a`` and ``node_b`` exists.

    If ``llm`` is None, the function returns a deterministic structural
    explanation (no model call). If an LLM client is provided, the
    response is constrained by the system prompt at
    ``_prompts/reasoner_system.md`` and the budget.
    """
    citations = _gather_citations_from_store(
        store=store, node_a=node_a, node_b=node_b, edge=edge
    )
    max_tokens = budget if budget is not None else _max_tokens_default()

    if llm is None:
        return _fallback_reasoning(
            node_a=node_a, node_b=node_b, edge=edge, citations=citations
        )

    system_prompt = _load_system_prompt()
    user_prompt = json.dumps(
        {
            "node_a": _node_summary(node_a),
            "node_b": _node_summary(node_b),
            "edge": {
                "kind": (
                    edge.kind.value
                    if hasattr(edge.kind, "value")
                    else str(edge.kind)
                ),
                "weight": edge.weight,
                "attrs": edge.attrs,
            },
            "grounding_citations": [c.model_dump() for c in citations],
        },
        ensure_ascii=False,
        indent=2,
    )

    raw = ""
    try:
        complete = getattr(llm, "complete", None)
        if complete is None:
            raise RuntimeError("LLM client does not implement complete()")
        # Synchronous LLM clients are the default in this codebase; we
        # still expose this function as async because callers may want
        # to fan-out across edges.
        raw = complete(
            system=system_prompt,
            user=user_prompt,
            max_tokens=max_tokens,
            temperature=0.0,
        )
    except Exception:
        return _fallback_reasoning(
            node_a=node_a, node_b=node_b, edge=edge, citations=citations
        )

    parsed = _parse_llm_response(raw)
    if parsed is None:
        return _fallback_reasoning(
            node_a=node_a, node_b=node_b, edge=edge, citations=citations
        )

    parsed_citations: list[SourceCitation] = []
    for c in parsed.get("citations", []) or []:
        try:
            parsed_citations.append(SourceCitation.model_validate(c))
        except Exception:
            continue

    short_answer = str(parsed.get("short_answer", "") or "").strip()
    weak = bool(parsed.get("weak_connection", False)) or _is_weak(
        short_answer
    )
    if not parsed_citations:
        parsed_citations = citations
    return EdgeReasoning(
        question_implied=str(
            parsed.get("question_implied", "")
            or f"Why are '{node_a.label}' and '{node_b.label}' connected?"
        ),
        short_answer=short_answer
        or f"'{node_a.label}' is linked to '{node_b.label}'.",
        reasoning_chain=[str(x) for x in parsed.get("reasoning_chain", [])],
        citations=parsed_citations,
        confidence_low=float(parsed.get("confidence_low", 0.5) or 0.5),
        confidence_high=float(parsed.get("confidence_high", 0.8) or 0.8),
        generated_at=datetime.now(timezone.utc),
        weak_connection=weak,
    )

"""Blindspot detection for inverse inference."""

from __future__ import annotations

import re
from typing import Any, Optional

import numpy as np

from noosphere.models import (
    BlindspotReport,
    CascadeEdgeRelation,
    MethodType,
    ResolvedEvent,
    ResearchSuggestion,
)
from noosphere.methods import register_method


def _extract_entities(text: str) -> list[str]:
    """Heuristic entity extraction: capitalised multi-word spans."""
    pattern = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b"
    matches = re.findall(pattern, text)
    seen: set[str] = set()
    result: list[str] = []
    for m in matches:
        key = m.lower()
        if key not in seen:
            seen.add(key)
            result.append(m)
    return result


def _extract_mechanisms_via_llm(
    text: str, llm_client: Any
) -> list[str]:
    """Use LLM to extract causal mechanism tags from the event description."""
    response = llm_client.complete(
        system=(
            "You are a research analyst. Extract the causal mechanisms "
            "mentioned in the following text. Return one mechanism per line, "
            "no numbering, no extra commentary."
        ),
        user=text,
        max_tokens=512,
        temperature=0.0,
    )
    return [
        line.strip()
        for line in response.strip().splitlines()
        if line.strip()
    ]


def _cosine(a: list[float], b: list[float]) -> float:
    a_arr = np.asarray(a, dtype=np.float64)
    b_arr = np.asarray(b, dtype=np.float64)
    norm_a = float(np.linalg.norm(a_arr))
    norm_b = float(np.linalg.norm(b_arr))
    if norm_a < 1e-10 or norm_b < 1e-10:
        return 0.0
    return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))


def compute_blindspot(
    *,
    event: ResolvedEvent,
    sliced_store: Any,
    embed_client: Any,
    llm_client: Any = None,
) -> BlindspotReport:
    """Analyse a resolved event against a temporal-sliced corpus
    to identify entities, mechanisms, and topics the corpus misses."""

    claim_ids = sliced_store.list_claim_ids()
    claims = []
    for cid in claim_ids:
        c = sliced_store.get_claim(cid)
        if c is not None:
            claims.append(c)

    corpus_text = " ".join(c.text for c in claims).lower()

    # -- missing entities --
    event_entities = _extract_entities(event.description)
    missing_entities = [
        e for e in event_entities if e.lower() not in corpus_text
    ]

    # -- missing mechanisms --
    missing_mechanisms: list[str] = []
    if llm_client is not None:
        event_mechanisms = _extract_mechanisms_via_llm(
            event.description, llm_client
        )
        for mech in event_mechanisms:
            if mech.lower() not in corpus_text:
                missing_mechanisms.append(mech)

    # -- adjacent-empty topics --
    adjacent_empty: list[str] = []
    if claims:
        event_emb = embed_client.encode([event.description])[0]
        claim_embeddings = []
        for c in claims:
            if c.embedding is not None:
                claim_embeddings.append(c.embedding)
            else:
                claim_embeddings.append(
                    embed_client.encode([c.text])[0]
                )

        adjacency_threshold = 0.3
        topic_labels = _discover_adjacent_topics(
            event_emb, claim_embeddings, adjacency_threshold
        )

        for label in topic_labels:
            if label.lower() not in corpus_text:
                adjacent_empty.append(label)

    return BlindspotReport(
        missing_entities=missing_entities,
        missing_mechanisms=missing_mechanisms,
        adjacent_empty_topics=adjacent_empty,
    )


def _discover_adjacent_topics(
    event_emb: list[float],
    claim_embeddings: list[list[float]],
    threshold: float,
) -> list[str]:
    """Find embedding-space 'directions' near the event that have zero claims.

    Returns synthetic topic labels of the form 'topic_dim_<N>' for each
    principal-component direction within *threshold* cosine distance of the
    event centroid that contains no claim embeddings.
    """
    if not claim_embeddings:
        return []

    mat = np.array(claim_embeddings, dtype=np.float64)
    ev = np.asarray(event_emb, dtype=np.float64)

    if mat.shape[0] < 2:
        return []

    centroid = mat.mean(axis=0)
    diff = ev - centroid
    norm = float(np.linalg.norm(diff))
    if norm < 1e-10:
        return []

    direction = diff / norm

    projections = mat @ direction
    event_proj = float(ev @ direction)

    if np.std(projections) < 1e-10:
        return []

    z_score = (event_proj - float(np.mean(projections))) / float(
        np.std(projections)
    )

    if abs(z_score) > 2.0:
        return [f"topic_dim_{hash(direction.tobytes()) % 10000:04d}"]

    return []


@register_method(
    name="suggest_research",
    version="1.0.0",
    method_type=MethodType.AGGREGATION,
    input_schema=BlindspotReport,
    output_schema={"type": "array", "items": ResearchSuggestion.model_json_schema()},
    description="Converts blindspot findings into actionable research suggestions.",
    rationale=(
        "Each missing entity, mechanism, or adjacent-empty topic becomes a "
        "ResearchSuggestion so downstream systems can propose reading lists."
    ),
    owner="founder",
    status="active",
    nondeterministic=False,
    emits_edges=[CascadeEdgeRelation.DEPENDS_ON],
)
def suggest_research(report: BlindspotReport) -> list[ResearchSuggestion]:
    suggestions: list[ResearchSuggestion] = []

    for entity in report.missing_entities:
        suggestions.append(
            ResearchSuggestion(
                title=f"Missing entity: {entity}",
                summary=(
                    f"The entity '{entity}' appears in the resolved event "
                    f"but has no coverage in the corpus. Consider ingesting "
                    f"sources that discuss {entity}."
                ),
            )
        )

    for mechanism in report.missing_mechanisms:
        suggestions.append(
            ResearchSuggestion(
                title=f"Missing mechanism: {mechanism}",
                summary=(
                    f"The causal mechanism '{mechanism}' is present in the "
                    f"event but absent from the corpus."
                ),
            )
        )

    for topic in report.adjacent_empty_topics:
        suggestions.append(
            ResearchSuggestion(
                title=f"Adjacent-empty topic: {topic}",
                summary=(
                    f"The embedding-adjacent topic '{topic}' has zero "
                    f"corpus claims despite proximity to the event."
                ),
            )
        )

    return suggestions

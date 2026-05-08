"""Registered method: contradiction-direction neighborhood probe."""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from noosphere.coherence.contradiction_direction import (
    predict_contradiction_location,
)
from noosphere.models import MethodType
from noosphere.methods._decorator import register_method

# Eager-import the dependency module so its decorator fires before ours
# does. The composition DAG validator (`validate_depends_on`) rejects
# names that are not yet registered, so the import order is part of the
# contract.
from noosphere.methods import contradiction_geometry as _dep_contradiction_geometry  # noqa: F401,E402


class ContradictionCandidate(BaseModel):
    proposition_id: str
    predicted_distance: float
    sparsity: float
    cosine_similarity: float
    verdict_layer: str = "candidate"


class ContradictionProbeInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    embedding: list[float]
    locality_index: Any = Field(default=None, exclude=True)
    k: int = 64
    radius: float | None = None
    exclude_ids: list[str] = Field(default_factory=list)
    exemplar_pairs: Any = Field(default=None, exclude=True)


class ContradictionProbeOutput(BaseModel):
    candidates: list[ContradictionCandidate]
    predicted_embedding: list[float]
    alpha: float
    direction_low_confidence: bool
    direction_method: str
    exemplar_count: int
    methodology: dict[str, Any] = Field(default_factory=dict)


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na <= 1e-12 or nb <= 1e-12:
        return 1.0
    return float(1.0 - np.dot(a, b) / (na * nb))


def _geometry_scores(
    query_embedding: np.ndarray,
    candidate_embedding: np.ndarray,
) -> tuple[float, float]:
    try:
        from noosphere.methods._legacy.contradiction_geometry import EmbeddingAnalyzer

        analyzer = EmbeddingAnalyzer()
        diff = analyzer.difference_vector(query_embedding, candidate_embedding)
        sparsity = analyzer.hoyer_sparsity(diff)
        cosine = analyzer.cosine_similarity(query_embedding, candidate_embedding)
        return float(sparsity), float(cosine)
    except ImportError:
        diff = np.asarray(query_embedding, dtype=float) - np.asarray(
            candidate_embedding, dtype=float
        )
        n = diff.size
        l2 = float(np.linalg.norm(diff))
        if n <= 1 or l2 <= 1e-12:
            sparsity = 0.0
        else:
            l1 = float(np.sum(np.abs(diff)))
            sparsity = (float(np.sqrt(n)) - l1 / l2) / (float(np.sqrt(n)) - 1.0)
        q_norm = float(np.linalg.norm(query_embedding))
        c_norm = float(np.linalg.norm(candidate_embedding))
        cosine = (
            float(np.dot(query_embedding, candidate_embedding) / (q_norm * c_norm))
            if q_norm > 1e-12 and c_norm > 1e-12
            else 0.0
        )
        return float(sparsity), float(cosine)


@register_method(
    name="contradiction_probe",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema=ContradictionProbeInput,
    output_schema=ContradictionProbeOutput,
    description=(
        "Predicts the embedding-space neighborhood where a new proposition's "
        "logical contradiction should lie, then surfaces nearby existing "
        "propositions as unconfirmed candidates."
    ),
    rationale=(
        "Contradiction direction is treated as a probabilistic search prior: "
        "the method nominates candidates near the predicted negation location, "
        "but emits no confirmed contradiction edge."
    ),
    owner="founder",
    status="active",
    nondeterministic=False,
    emits_edges=[],
    dependencies=[("contradiction_geometry", "1.0.0")],
    depends_on=["contradiction_geometry"],
)
def contradiction_probe(
    input_data: ContradictionProbeInput,
) -> ContradictionProbeOutput:
    if input_data.locality_index is None:
        raise ValueError("contradiction_probe requires a DomainLocalityIndex")
    locality = input_data.locality_index
    if not hasattr(locality, "neighbors") or not hasattr(locality, "vector_for"):
        raise TypeError("locality_index must provide neighbors() and vector_for()")

    query = np.asarray(input_data.embedding, dtype=float).reshape(-1)
    predicted, direction = predict_contradiction_location(
        query,
        exemplar_pairs=input_data.exemplar_pairs,
    )
    if np.linalg.norm(direction) <= 1e-12 or float(direction.alpha) <= 1e-12:
        return ContradictionProbeOutput(
            candidates=[],
            predicted_embedding=predicted.astype(float).tolist(),
            alpha=float(direction.alpha),
            direction_low_confidence=bool(direction.low_confidence),
            direction_method=str(direction.method),
            exemplar_count=int(direction.exemplar_count),
            methodology={
                "probe_k": int(input_data.k),
                "probe_radius": input_data.radius,
                "zero_direction": True,
            },
        )

    neighbor_result = locality.neighbors(
        predicted,
        k=max(0, int(input_data.k)),
        radius=input_data.radius,
        include_outside_sample=0,
    )
    excluded = {str(item) for item in input_data.exclude_ids}
    candidates: list[ContradictionCandidate] = []
    for pid in neighbor_result.local_ids:
        if pid in excluded:
            continue
        candidate_embedding = locality.vector_for(pid)
        if candidate_embedding is None:
            continue
        cand = np.asarray(candidate_embedding, dtype=float).reshape(-1)
        if cand.size != query.size:
            continue
        sparsity, cosine = _geometry_scores(query, cand)
        candidates.append(
            ContradictionCandidate(
                proposition_id=pid,
                predicted_distance=neighbor_result.local_distances.get(
                    pid, _cosine_distance(predicted, cand)
                ),
                sparsity=sparsity,
                cosine_similarity=cosine,
                verdict_layer="candidate",
            )
        )

    return ContradictionProbeOutput(
        candidates=candidates,
        predicted_embedding=predicted.astype(float).tolist(),
        alpha=float(direction.alpha),
        direction_low_confidence=bool(direction.low_confidence),
        direction_method=str(direction.method),
        exemplar_count=int(direction.exemplar_count),
        methodology={
            "probe_k": int(input_data.k),
            "probe_radius": input_data.radius,
            "locality": neighbor_result.methodology,
            "zero_direction": False,
        },
    )

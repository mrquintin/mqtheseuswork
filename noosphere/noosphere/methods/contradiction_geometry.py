"""
Registered method: Contradiction geometry via embedding difference-space analysis.

Wraps the legacy EmbeddingAnalyzer (Hoyer sparsity on difference vectors)
as a registered method with pydantic input/output models and invocation tracking.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from pydantic import BaseModel

from noosphere.models import CascadeEdgeRelation, MethodType
from noosphere.methods._decorator import register_method


class ContradictionGeometryInput(BaseModel):
    embedding_a: list[float]
    embedding_b: list[float]
    threshold: float = 0.35


class ContradictionGeometryOutput(BaseModel):
    is_contradiction: bool
    sparsity: float
    cosine_similarity: float


@register_method(
    name="contradiction_geometry",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema=ContradictionGeometryInput.model_json_schema(),
    output_schema=ContradictionGeometryOutput.model_json_schema(),
    description="Detects contradiction via Hoyer sparsity of embedding difference vectors.",
    rationale=(
        "Implements the Embedding Geometry Conjecture: logical contradiction manifests "
        "as sparse, dimension-concentrated difference vectors in embedding space."
    ),
    owner="founder",
    status="active",
    nondeterministic=False,
    emits_edges=[CascadeEdgeRelation.CONTRADICTS],
    dependencies=[],
)
def contradiction_geometry(
    input_data: ContradictionGeometryInput,
) -> ContradictionGeometryOutput:
    from noosphere.methods._legacy.contradiction_geometry import EmbeddingAnalyzer

    analyzer = EmbeddingAnalyzer()
    emb_a = np.asarray(input_data.embedding_a, dtype=float)
    emb_b = np.asarray(input_data.embedding_b, dtype=float)

    is_contra, sparsity = analyzer.detect_contradiction(
        emb_a, emb_b, threshold=input_data.threshold
    )
    cos_sim = analyzer.cosine_similarity(emb_a, emb_b)

    return ContradictionGeometryOutput(
        is_contradiction=is_contra,
        sparsity=sparsity,
        cosine_similarity=float(cos_sim),
    )

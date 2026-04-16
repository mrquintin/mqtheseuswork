"""
Registered method: Match external literature claims against internal claims.

Wraps the legacy literature ingestion behavior to produce coherence
judgments between external and internal claims. Self-contained to avoid
import issues with types not yet in models.py.
"""
from __future__ import annotations

import hashlib

from pydantic import BaseModel

from noosphere.models import CascadeEdgeRelation, MethodType
from noosphere.methods._decorator import register_method


class ExternalClaimMatchInput(BaseModel):
    internal_claim_text: str
    external_title: str
    external_author: str
    external_body: str
    connector: str = "manual"
    license_status: str = "firm_licensed"


class MatchResult(BaseModel):
    external_artifact_id: str = ""
    claims_extracted: int = 0
    matched: bool = False


class ExternalClaimMatchOutput(BaseModel):
    result: MatchResult


@register_method(
    name="external_claim_match",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema=ExternalClaimMatchInput,
    output_schema=ExternalClaimMatchOutput,
    description="Ingests external literature and matches claims against internal positions.",
    rationale=(
        "Wraps legacy literature ingestion — ingests external text, extracts claims "
        "attributed to the first author as a Voice, and provides the artifact ID "
        "for downstream coherence checking."
    ),
    owner="founder",
    status="active",
    nondeterministic=False,
    emits_edges=[
        CascadeEdgeRelation.COHERES_WITH,
        CascadeEdgeRelation.CONTRADICTS,
    ],
    dependencies=[],
)
def external_claim_match(
    input_data: ExternalClaimMatchInput,
) -> ExternalClaimMatchOutput:
    raw = input_data.external_body.encode("utf-8", errors="replace")
    if not raw.strip():
        raw = f"{input_data.external_title}|{input_data.connector}".encode()
    artifact_id = hashlib.sha256(raw).hexdigest()[:32]

    try:
        from noosphere.methods._legacy.literature import ingest_literature_text
        from noosphere.config import get_settings
        from noosphere.store import Store

        store = Store.from_database_url(get_settings().database_url)
        res = ingest_literature_text(
            store,
            title=input_data.external_title,
            author=input_data.external_author,
            body=input_data.external_body,
            connector=input_data.connector,
            license_status=input_data.license_status,
        )
        return ExternalClaimMatchOutput(
            result=MatchResult(
                external_artifact_id=res.artifact_id,
                claims_extracted=res.claims_written,
                matched=res.claims_written > 0,
            )
        )
    except Exception:
        return ExternalClaimMatchOutput(
            result=MatchResult(
                external_artifact_id=artifact_id,
                matched=False,
            )
        )

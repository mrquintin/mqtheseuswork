"""
Registered method: Decompose founder voice into intellectual profile.

Wraps the legacy FounderRegistry behavior as a registered method that
computes a founder's intellectual profile summary. Self-contained to avoid
import issues with types not yet in models.py.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from noosphere.models import MethodType
from noosphere.methods._decorator import register_method


class DecomposeVoiceInput(BaseModel):
    founder_name: str
    founder_role: str = "founder"
    primary_domains: list[str] = Field(default_factory=list)


class FounderVoiceProfile(BaseModel):
    founder_id: str
    name: str
    role: str
    claim_count: int = 0
    methodological_orientation: float = 0.0
    primary_domains: list[str] = Field(default_factory=list)


class DecomposeVoiceOutput(BaseModel):
    profile: FounderVoiceProfile


@register_method(
    name="decompose_voice",
    version="1.0.0",
    method_type=MethodType.TRANSFORMATION,
    input_schema=DecomposeVoiceInput,
    output_schema=DecomposeVoiceOutput,
    description="Decomposes a founder's voice into an intellectual profile with orientation scores.",
    rationale=(
        "Wraps legacy FounderRegistry — resolves or registers a founder and returns "
        "their intellectual profile including methodological orientation, domain "
        "distribution, and claim counts."
    ),
    owner="founder",
    status="active",
    nondeterministic=True,
    emits_edges=[],
    dependencies=[],
)
def decompose_voice(input_data: DecomposeVoiceInput) -> DecomposeVoiceOutput:
    import json
    import uuid
    from pathlib import Path

    norm = " ".join(input_data.founder_name.strip().lower().split())
    data_path = Path("founders_registry.json")

    founders = {}
    name_index = {}
    if data_path.exists():
        try:
            raw = json.loads(data_path.read_text(encoding="utf-8"))
            founders = raw.get("founders", {})
            name_index = raw.get("name_index", {})
        except Exception:
            pass

    if norm in name_index:
        fid = name_index[norm]
        fp = founders.get(fid, {})
        return DecomposeVoiceOutput(
            profile=FounderVoiceProfile(
                founder_id=fid,
                name=fp.get("name", input_data.founder_name),
                role=fp.get("role", input_data.founder_role),
                claim_count=fp.get("claim_count", 0),
                methodological_orientation=fp.get("methodological_orientation", 0.0),
                primary_domains=[
                    d.get("value", d) if isinstance(d, dict) else str(d)
                    for d in fp.get("primary_domains", [])
                ],
            )
        )

    fid = str(uuid.uuid4())
    return DecomposeVoiceOutput(
        profile=FounderVoiceProfile(
            founder_id=fid,
            name=input_data.founder_name,
            role=input_data.founder_role,
            claim_count=0,
            methodological_orientation=0.0,
            primary_domains=input_data.primary_domains,
        )
    )

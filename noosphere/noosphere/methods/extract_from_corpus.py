"""
Registered method: Extract method candidates from ingested transcripts.

Scans artifacts for passages describing a methodology and passes candidates
through an LLM for structured extraction. This is a NEW method, not a port.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from noosphere.models import MethodType
from noosphere.methods._decorator import register_method


METHOD_PATTERNS = [
    re.compile(r"the\s+way\s+to\s+tell", re.IGNORECASE),
    re.compile(r"the\s+test\s+we\s+use", re.IGNORECASE),
    re.compile(r"the\s+rule\s+of\s+thumb", re.IGNORECASE),
    re.compile(r"we\s+determine\s+\w+\s+by", re.IGNORECASE),
    re.compile(r"how\s+(?:we|you|I)\s+(?:evaluate|assess|judge|measure)", re.IGNORECASE),
    re.compile(r"the\s+(?:method|approach|procedure|process)\s+(?:is|for|we)", re.IGNORECASE),
    re.compile(r"(?:always|never)\s+(?:check|verify|test|validate)", re.IGNORECASE),
]


class MethodCandidate(BaseModel):
    name: str
    description: str
    rationale: str
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    source_artifact_ref: str = ""
    source_span: str = ""


class MethodExtractionInput(BaseModel):
    artifact_refs: list[str]
    window_chars: int = 2000


class MethodExtractionOutput(BaseModel):
    candidates: list[MethodCandidate] = Field(default_factory=list)


def _find_candidate_spans(text: str, window: int) -> list[str]:
    spans: list[str] = []
    seen_offsets: set[int] = set()
    for pattern in METHOD_PATTERNS:
        for m in pattern.finditer(text):
            start = max(0, m.start() - window // 4)
            bucket = start // (window // 2)
            if bucket in seen_offsets:
                continue
            seen_offsets.add(bucket)
            end = min(len(text), m.start() + window)
            spans.append(text[start:end])
    return spans


def _extract_via_llm(chunk: str) -> list[MethodCandidate]:
    import json

    try:
        from noosphere.llm import llm_client_from_settings
        llm = llm_client_from_settings()
    except Exception:
        return []

    system = (
        "You extract methodology descriptions from conversation transcripts. "
        "For each methodology found, output JSON: "
        '{"candidates":[{"name":str,"description":str,"rationale":str,'
        '"preconditions":[str],"postconditions":[str]}]}'
    )
    user = f"Transcript passage:\n\n{chunk}\n"

    try:
        raw = llm.complete(system=system, user=user, max_tokens=1500, temperature=0.0)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group(0))
        candidates = []
        for c in data.get("candidates", []):
            candidates.append(MethodCandidate(
                name=c.get("name", ""),
                description=c.get("description", ""),
                rationale=c.get("rationale", ""),
                preconditions=c.get("preconditions", []),
                postconditions=c.get("postconditions", []),
            ))
        return candidates
    except Exception:
        return []


def _try_persist_candidate(candidate: MethodCandidate) -> None:
    try:
        from noosphere.config import get_settings
        from noosphere.store import Store

        store = Store.from_database_url(get_settings().database_url)
        store.insert_method_candidate(candidate.model_dump())
    except (AttributeError, Exception):
        pass


@register_method(
    name="method_candidate_extractor",
    version="1.0.0",
    method_type=MethodType.EXTRACTION,
    input_schema=MethodExtractionInput,
    output_schema=MethodExtractionOutput,
    description=(
        "Scans ingested artifacts for passages describing a methodology and "
        "extracts structured method candidates via regex + LLM."
    ),
    rationale=(
        "Discovers implicit methodological knowledge in transcripts. Uses a regex "
        "catalog to identify candidate passages, then passes them through an LLM "
        "with a structured prompt to extract name, description, rationale, "
        "preconditions, and postconditions."
    ),
    owner="founder",
    status="active",
    nondeterministic=True,
    emits_edges=[],
    dependencies=[],
)
def method_candidate_extractor(
    input_data: MethodExtractionInput,
) -> MethodExtractionOutput:
    all_candidates: list[MethodCandidate] = []

    for ref in input_data.artifact_refs:
        try:
            from noosphere.config import get_settings
            from noosphere.store import Store

            store = Store.from_database_url(get_settings().database_url)
            artifact = store.get_artifact(ref)
            if artifact is None:
                continue
            chunks = store.get_chunks_for_artifact(ref)
            text = "\n\n".join(ch.text for ch in chunks)
        except Exception:
            text = ref

        spans = _find_candidate_spans(text, input_data.window_chars)
        for span in spans:
            candidates = _extract_via_llm(span)
            for c in candidates:
                c.source_artifact_ref = ref
                c.source_span = span[:200]
                _try_persist_candidate(c)
                all_candidates.append(c)

    return MethodExtractionOutput(candidates=all_candidates)

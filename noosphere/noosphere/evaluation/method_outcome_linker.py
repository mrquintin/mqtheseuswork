"""Method-outcome linker: which registered methods produced each Conclusion.

The linker walks every Conclusion that has at least one MethodologyProfile
and infers the registered methods that produced it. The candidate vocabulary
is closed: the LLM judge may only return method names that exist in the
registry. This is what turns the registry from a static catalog into a
measured artifact — the inferred links feed `method_track_record.py`, which
rolls up resolved ForecastPredictions per method.

The linker is idempotent: re-running it upserts `ConclusionMethod` rows on
the (conclusionId, methodName, methodVersion) unique key rather than
appending duplicates. Weights may move between runs if the judge changes
its mind; that is expected.

Two judge implementations are provided:

* `StubMethodLinkerJudge` — deterministic. Maps each profile's
  `pattern_type` to a registered method name when an exact match exists.
  Used by tests and by the `--judge stub` CLI path.
* The protocol contract (`MethodLinkerJudge`) lets production code wire an
  LLM-backed judge that consumes the registry vocabulary plus the
  conclusion text and methodology profiles.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Protocol

from pydantic import BaseModel, Field, field_validator

from noosphere.evaluation.mqs import MethodologyProfileSummary


LINKER_SCHEMA = "theseus.method_outcome_linker.v1"


def _clamp01(x: float) -> float:
    if x != x:  # NaN
        return 0.0
    return max(0.0, min(1.0, float(x)))


class LinkedMethod(BaseModel):
    """One inferred (method, weight, domain) attribution for a conclusion."""

    method_name: str
    method_version: str
    weight: float = Field(ge=0.0, le=1.0)
    domain: str = ""
    rationale: str = ""

    @field_validator("weight")
    @classmethod
    def _clamp(cls, v: float) -> float:
        return _clamp01(v)


class RegistryMethodView(BaseModel):
    """Registry projection passed to judges. Closed vocabulary: a judge
    that returns a name not in this list is rejected by `infer_links`."""

    name: str
    version: str
    description: str = ""


class MethodLinkerJudge(Protocol):
    """LLM-judge contract. Tests pass a stub; production wires the real LLM."""

    def judge(
        self,
        *,
        conclusion_id: str,
        conclusion_text: str,
        topic_hint: str,
        profiles: list[MethodologyProfileSummary],
        registry_methods: list[RegistryMethodView],
    ) -> list[dict[str, Any]]:
        """Return zero-or-more dicts of the shape
        {"method_name": str, "method_version": str, "weight": float in [0,1],
         "domain": str, "rationale": str}.

        A judge that returns a name not present in `registry_methods` will
        have that link dropped — the registry is the closed vocabulary."""
        ...


@dataclass
class StubMethodLinkerJudge:
    """Deterministic linker used by tests and the no-LLM CLI path.

    Default behaviour: case-insensitively match each MethodologyProfile's
    `pattern_type` to a registered method `name`. When a match exists, emit
    a link with weight = `profile.confidence` clamped into [0, 1] and a
    domain taken from the conclusion's `topic_hint` (falling back to
    `default_domain`).

    `responses` lets a test pin a per-conclusion answer set, bypassing the
    name-match heuristic entirely."""

    responses: dict[str, list[dict[str, Any]]] | None = None
    default_domain: str = ""

    def judge(
        self,
        *,
        conclusion_id: str,
        conclusion_text: str,
        topic_hint: str,
        profiles: list[MethodologyProfileSummary],
        registry_methods: list[RegistryMethodView],
    ) -> list[dict[str, Any]]:
        if self.responses and conclusion_id in self.responses:
            return list(self.responses[conclusion_id])

        by_name: dict[str, RegistryMethodView] = {}
        for m in registry_methods:
            by_name.setdefault(m.name.strip().lower(), m)

        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for p in profiles:
            key_str = (p.pattern_type or "").strip().lower()
            match = by_name.get(key_str)
            if match is None:
                continue
            key = (match.name, match.version)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "method_name": match.name,
                    "method_version": match.version,
                    "weight": _clamp01(p.confidence or 0.5),
                    "domain": (topic_hint or self.default_domain or "").strip(),
                    "rationale": f"stub: pattern_type={p.pattern_type}",
                }
            )
        return out


def infer_links(
    *,
    conclusion_id: str,
    conclusion_text: str,
    topic_hint: str,
    profiles: list[MethodologyProfileSummary],
    registry_methods: list[RegistryMethodView],
    judge: MethodLinkerJudge,
) -> list[LinkedMethod]:
    """Run the judge and return validated links. The registry is the closed
    vocabulary — links that name an unknown (method, version) are dropped
    silently."""
    if not profiles:
        return []
    raw = judge.judge(
        conclusion_id=conclusion_id,
        conclusion_text=conclusion_text,
        topic_hint=topic_hint,
        profiles=profiles,
        registry_methods=registry_methods,
    )
    valid_keys = {(m.name, m.version) for m in registry_methods}
    out: list[LinkedMethod] = []
    seen: set[tuple[str, str]] = set()
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("method_name") or "").strip()
        version = str(entry.get("method_version") or "").strip()
        if not name or not version:
            continue
        if (name, version) not in valid_keys:
            continue
        if (name, version) in seen:
            continue
        seen.add((name, version))
        try:
            out.append(
                LinkedMethod(
                    method_name=name,
                    method_version=version,
                    weight=float(entry.get("weight", 0.0) or 0.0),
                    domain=str(entry.get("domain") or "").strip(),
                    rationale=str(entry.get("rationale") or "")[:600],
                )
            )
        except Exception:
            continue
    return out


def registry_view() -> list[RegistryMethodView]:
    """Project the in-process method registry into the closed vocabulary
    the judge sees."""
    from noosphere.methods import REGISTRY

    out: list[RegistryMethodView] = []
    for spec in REGISTRY.list():
        if spec.status == "retired":
            continue
        out.append(
            RegistryMethodView(
                name=spec.name,
                version=spec.version,
                description=spec.description,
            )
        )
    return out


# ── Persistence helpers (psycopg2-style cursor) ─────────────────────────────


def upsert_links(
    cur,
    *,
    organization_id: str,
    conclusion_id: str,
    links: Iterable[LinkedMethod],
    now: Optional[datetime] = None,
) -> int:
    """Upsert ConclusionMethod rows. Returns the number of rows written.

    Idempotent on (conclusionId, methodName, methodVersion). Re-running with
    a different weight overwrites the prior row in place; re-running with
    the same weight is a no-op modulo `updatedAt`."""
    now = now or datetime.now(timezone.utc)
    written = 0
    for link in links:
        cur.execute(
            '''INSERT INTO "ConclusionMethod"
                (id, "organizationId", "conclusionId",
                 "methodName", "methodVersion",
                 weight, domain, rationale,
                 "createdAt", "updatedAt")
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT ("conclusionId", "methodName", "methodVersion")
               DO UPDATE SET
                 weight = EXCLUDED.weight,
                 domain = EXCLUDED.domain,
                 rationale = EXCLUDED.rationale,
                 "updatedAt" = EXCLUDED."updatedAt"''',
            (
                "cm_" + uuid.uuid4().hex[:24],
                organization_id,
                conclusion_id,
                link.method_name,
                link.method_version,
                float(link.weight),
                link.domain or "",
                link.rationale or "",
                now,
                now,
            ),
        )
        written += 1
    return written


def link_payload(links: list[LinkedMethod]) -> str:
    """JSON-serialize the inferred links for audit logging."""
    return json.dumps(
        {
            "schema": LINKER_SCHEMA,
            "links": [link.model_dump() for link in links],
        },
        sort_keys=True,
        default=str,
    )


__all__ = [
    "LINKER_SCHEMA",
    "LinkedMethod",
    "MethodLinkerJudge",
    "RegistryMethodView",
    "StubMethodLinkerJudge",
    "infer_links",
    "link_payload",
    "registry_view",
    "upsert_links",
]

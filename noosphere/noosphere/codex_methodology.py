"""Codex database helpers for MethodologyProfile rows."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Iterable

from noosphere.methodology import MethodologyProfileDraft


_DB_UNSAFE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufeff]")
_DB_SURROGATE = re.compile(r"[\ud800-\udfff]")


def db_safe(text: object, *, cap: int | None = None) -> str:
    value = "" if text is None else str(text)
    value = _DB_UNSAFE.sub("", value)
    value = _DB_SURROGATE.sub("", value)
    if cap is not None and len(value) > cap:
        value = value[:cap]
    return value


def methodology_dedupe_key(
    *,
    source_kind: str,
    source_id: str,
    pattern_type: str,
) -> str:
    return f"{source_kind.lower()}:{source_id}:{pattern_type}"


def upsert_methodology_profiles(
    cur,
    *,
    organization_id: str,
    profiles: Iterable[MethodologyProfileDraft],
    now: datetime,
    source_kind: str,
    upload_id: str | None = None,
    conclusion_id: str | None = None,
) -> int:
    """Insert or refresh deterministic methodology profiles.

    The unique `(organizationId, dedupeKey)` constraint makes reanalysis safe:
    rerunning the same upload updates the method profile in place instead of
    multiplying rows.
    """
    source_id = upload_id or conclusion_id
    if not source_id:
        raise ValueError("upload_id or conclusion_id is required")

    count = 0
    for profile in profiles:
        dedupe_key = methodology_dedupe_key(
            source_kind=source_kind,
            source_id=source_id,
            pattern_type=profile.pattern_type,
        )
        cur.execute(
            '''INSERT INTO "MethodologyProfile"
               (id, "organizationId", "uploadId", "conclusionId", "sourceKind",
                "patternType", title, summary, "reasoningMoves",
                "transferTargets", assumptions, "failureModes",
                "evidenceAnchors", confidence, "dedupeKey", "createdAt", "updatedAt")
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT ("organizationId", "dedupeKey") DO UPDATE SET
                 title = EXCLUDED.title,
                 summary = EXCLUDED.summary,
                 "reasoningMoves" = EXCLUDED."reasoningMoves",
                 "transferTargets" = EXCLUDED."transferTargets",
                 assumptions = EXCLUDED.assumptions,
                 "failureModes" = EXCLUDED."failureModes",
                 "evidenceAnchors" = EXCLUDED."evidenceAnchors",
                 confidence = EXCLUDED.confidence,
                 "updatedAt" = EXCLUDED."updatedAt"''',
            (
                "mp_" + uuid.uuid4().hex[:24],
                organization_id,
                upload_id,
                conclusion_id,
                db_safe(source_kind, cap=32),
                db_safe(profile.pattern_type, cap=80),
                db_safe(profile.title, cap=180),
                db_safe(profile.summary, cap=4_000),
                json.dumps(profile.reasoning_moves),
                json.dumps(profile.transfer_targets),
                json.dumps(profile.assumptions),
                json.dumps(profile.failure_modes),
                json.dumps(profile.evidence_anchors),
                float(profile.confidence),
                db_safe(dedupe_key, cap=500),
                now,
                now,
            ),
        )
        count += max(int(getattr(cur, "rowcount", 1) or 0), 0)
    return count

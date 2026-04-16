from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache


@dataclass(frozen=True)
class ApiKeyRecord:
    label: str
    sandbox_tenant_id: str
    secret: str


@lru_cache
def _parse_keys() -> dict[str, ApiKeyRecord]:
    """
    RESEARCHER_API_KEYS format (comma-separated):
      label:sandbox_tenant:secret,label2:tenant2:secret2
    """
    raw = os.environ.get("RESEARCHER_API_KEYS", "").strip()
    out: dict[str, ApiKeyRecord] = {}
    if not raw:
        return out
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.split(":")
        if len(bits) < 3:
            continue
        secret = bits[-1]
        tenant = bits[-2]
        label = ":".join(bits[:-2])
        out[secret] = ApiKeyRecord(label=label, sandbox_tenant_id=tenant, secret=secret)
    return out


def lookup_api_key(secret: str) -> ApiKeyRecord | None:
    return _parse_keys().get(secret)


def api_git_sha() -> str:
    return os.environ.get("THESEUS_GIT_SHA", "unknown").strip() or "unknown"


def audit_log_path() -> str:
    raw = os.environ.get(
        "THESEUS_RESEARCHER_AUDIT_LOG", "~/.theseus/researcher_api_audit.jsonl"
    )
    return str(Path(os.path.expandvars(raw)).expanduser())


def rate_limit_per_hour() -> int:
    return int(os.environ.get("RESEARCHER_API_RATE_LIMIT_PER_HOUR", "120"))


def allow_coherence_judge() -> bool:
    """Structured judge only; off by default (heavy + abuse surface)."""
    return os.environ.get("RESEARCHER_API_COHERENCE_JUDGE", "").lower() in ("1", "true", "yes")

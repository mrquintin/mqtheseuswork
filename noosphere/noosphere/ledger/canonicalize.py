"""Canonicalization for publication signatures.

The signer (noosphere CLI) and verifier (CLI + web) must agree byte-for-byte
on the bytes that get hashed. Anything tolerated as "the same publication"
(line-ending differences, trailing whitespace, JSON key order) has to be
normalized away here. Anything that should invalidate a signature (a
character change in the conclusion text, a swapped citation) must NOT be
normalized away.

Inputs to the canonical hash, per the publication signing spec:
    - conclusion text (markdown)
    - methodology profile id(s)
    - citation set
    - confidence (discounted + stated)
    - MQS composite + sub-scores (prompt 01)
    - publication timestamp
    - slug + version (so a re-publication under a new version can never
      collide with an older signed version)

The function returns the canonical JSON bytes that get fed to SHA-256.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional


SCHEMA = "theseus.publicationSignature.v1"


def normalize_markdown(text: str) -> str:
    """Normalize markdown so cosmetically-equivalent inputs hash the same.

    Rules:
      1. Unicode NFC normalization.
      2. CRLF / CR -> LF.
      3. Strip trailing whitespace from every line.
      4. Collapse runs of 3+ blank lines down to two newlines.
      5. Strip leading/trailing whitespace from the whole document.

    We deliberately do NOT render to HTML: a full Markdown-to-HTML pipeline
    would couple the signature to a parser version. The rules above cover
    the whitespace-equivalence cases the spec requires, while keeping the
    canonicalizer pure-Python and version-stable.
    """
    if text is None:
        return ""
    import unicodedata

    s = unicodedata.normalize("NFC", str(text))
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(line.rstrip() for line in s.split("\n"))
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def normalize_iso_timestamp(ts: Any) -> str:
    """Render any timestamp as ISO-8601 Z (UTC, second precision).

    Accepts datetimes, ISO strings, or anything str()-able. Strips sub-
    second components so tiny clock differences between a signing-time
    Date.now() and a serialized DB row don't break verification.
    """
    from datetime import datetime, timezone

    if ts is None:
        return ""
    if isinstance(ts, datetime):
        dt = ts
    else:
        s = str(ts)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return s
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm_citation(c: Any) -> dict[str, Any]:
    """Normalize a single citation entry to a stable dict."""
    if isinstance(c, str):
        return {"format": "raw", "block": normalize_markdown(c)}
    if isinstance(c, dict):
        fmt = str(c.get("format", "")).strip().lower()
        block = normalize_markdown(c.get("block", ""))
        return {"format": fmt, "block": block}
    return {"format": "raw", "block": normalize_markdown(str(c))}


def _canon_citations(citations: Optional[Iterable[Any]]) -> list[dict[str, Any]]:
    if not citations:
        return []
    out = [_norm_citation(c) for c in citations]
    # Sort by (format, block) so reorderings don't change the hash but
    # additions/removals do.
    out.sort(key=lambda d: (d["format"], d["block"]))
    return out


def _canon_methodology_ids(ids: Optional[Iterable[Any]]) -> list[str]:
    if not ids:
        return []
    cleaned = sorted({str(x).strip() for x in ids if str(x).strip()})
    return cleaned


@dataclass
class MqsSnapshot:
    composite: float
    progressivity: float = 0.0
    severity: float = 0.0
    aim_method_fit: float = 0.0
    compressibility: float = 0.0
    domain_sensitivity: float = 0.0
    prompt_version: str = ""

    def to_canonical(self) -> dict[str, Any]:
        def f(x: float) -> float:
            return round(float(x), 6)

        return {
            "aimMethodFit": f(self.aim_method_fit),
            "composite": f(self.composite),
            "compressibility": f(self.compressibility),
            "domainSensitivity": f(self.domain_sensitivity),
            "progressivity": f(self.progressivity),
            "promptVersion": self.prompt_version or "",
            "severity": f(self.severity),
        }


@dataclass
class PublicationCanonicalInput:
    """Concrete inputs to the publication-signature canonical hash."""

    slug: str
    version: int
    conclusion_text: str
    methodology_profile_ids: list[str] = field(default_factory=list)
    citations: list[Any] = field(default_factory=list)
    discounted_confidence: float = 0.0
    stated_confidence: float = 0.0
    mqs: Optional[MqsSnapshot] = None
    published_at: str = ""

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "citations": _canon_citations(self.citations),
            "conclusionText": normalize_markdown(self.conclusion_text),
            "discountedConfidence": round(float(self.discounted_confidence), 6),
            "methodologyProfileIds": _canon_methodology_ids(self.methodology_profile_ids),
            "mqs": self.mqs.to_canonical() if self.mqs is not None else None,
            "publishedAt": normalize_iso_timestamp(self.published_at),
            "schema": SCHEMA,
            "slug": str(self.slug),
            "statedConfidence": round(float(self.stated_confidence), 6),
            "version": int(self.version),
        }

    def to_canonical_bytes(self) -> bytes:
        return canonical_json(self.to_canonical_dict())

    def hash_hex(self) -> str:
        return hashlib.sha256(self.to_canonical_bytes()).hexdigest()


def canonical_json(obj: Any) -> bytes:
    """Deterministic JSON encoding: sorted keys, tight separators, UTF-8."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_input_from_dict(data: dict[str, Any]) -> PublicationCanonicalInput:
    """Build a canonical input from a loosely-typed dict (e.g. JSON from web)."""
    mqs_raw = data.get("mqs")
    mqs: Optional[MqsSnapshot] = None
    if isinstance(mqs_raw, dict):
        mqs = MqsSnapshot(
            composite=float(mqs_raw.get("composite", 0.0) or 0.0),
            progressivity=float(mqs_raw.get("progressivity", 0.0) or 0.0),
            severity=float(mqs_raw.get("severity", 0.0) or 0.0),
            aim_method_fit=float(mqs_raw.get("aimMethodFit", 0.0) or 0.0),
            compressibility=float(mqs_raw.get("compressibility", 0.0) or 0.0),
            domain_sensitivity=float(mqs_raw.get("domainSensitivity", 0.0) or 0.0),
            prompt_version=str(mqs_raw.get("promptVersion", "") or ""),
        )
    return PublicationCanonicalInput(
        slug=str(data.get("slug", "")),
        version=int(data.get("version", 0) or 0),
        conclusion_text=str(data.get("conclusionText", "") or ""),
        methodology_profile_ids=list(data.get("methodologyProfileIds") or []),
        citations=list(data.get("citations") or []),
        discounted_confidence=float(data.get("discountedConfidence", 0.0) or 0.0),
        stated_confidence=float(data.get("statedConfidence", 0.0) or 0.0),
        mqs=mqs,
        published_at=str(data.get("publishedAt", "") or ""),
    )


__all__ = [
    "SCHEMA",
    "MqsSnapshot",
    "PublicationCanonicalInput",
    "canonical_input_from_dict",
    "canonical_json",
    "normalize_iso_timestamp",
    "normalize_markdown",
]

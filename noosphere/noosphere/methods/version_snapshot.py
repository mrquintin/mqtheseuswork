"""Versioned method snapshots — content-addressed identifiers for a
specific release of a method.

A ``MethodVersion`` is the tuple ``(name, version, content_hash, source,
rationale, failures, domain_bound, captured_at)``. The hash is computed
over the *normalized* source content — line endings collapsed, trailing
whitespace stripped, the failures catalog re-serialized through a
canonical JSON ordering — so that two checkouts of the same git rev on
different OSes produce identical hashes. This is what the public
changelog and the digest hook key off.

The module is intentionally storage-agnostic. The capture function
returns a plain ``MethodVersionSnapshot`` dataclass; the codex DB row
(see ``MethodVersion`` in ``theseus-codex/prisma/schema.prisma``) is
written by callers that have a DB handle. Local development and tests
use the ``InMemoryMethodVersionStore``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

_METHODS_DIR = Path(__file__).parent


# ── Normalization ──────────────────────────────────────────────────────────


def _normalize_text(text: str) -> str:
    """Strip trailing whitespace per line and unify line endings.

    The hash must be stable across machines: a Windows checkout that
    writes CRLF must produce the same digest as a POSIX checkout. We
    also strip trailing spaces because some editors save them and
    others don't, and the *meaning* of the source doesn't depend on
    them.
    """
    out_lines: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        out_lines.append(line.rstrip())
    # Drop trailing blank lines so that a single trailing-newline
    # difference doesn't cause a hash drift.
    while out_lines and out_lines[-1] == "":
        out_lines.pop()
    return "\n".join(out_lines) + "\n"


def _canonical_yaml_dump(data) -> str:
    """Re-serialize a YAML-loaded structure through a canonical JSON
    ordering. Keys are sorted, lists preserve order. We use JSON rather
    than yaml.safe_dump because PyYAML's default flow choices vary by
    version; ``json.dumps(sort_keys=True)`` is stable."""
    return json.dumps(data, sort_keys=True, default=str)


# ── Snapshot ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MethodVersionSnapshot:
    """A captured release of a single method.

    ``failures_public`` lists only the failure-mode names with
    ``public: true``; the public diff renderer reads from this set so
    that private modes never leak into the changelog.
    """

    name: str
    version: str
    content_hash: str
    source: str
    rationale: str
    failures_yaml: str  # raw text (private)
    failures_public_yaml: str  # filtered (only public modes)
    domain_bound_json: str  # canonical JSON of the bound, "" if none
    captured_at: datetime
    source_path: str = ""
    rationale_path: str = ""
    failures_path: str = ""

    def short_hash(self) -> str:
        return self.content_hash[:12]

    def anchor_id(self) -> str:
        """Stable URL anchor used by the public changelog page.

        The anchor is the short hash of the *new* version. Two
        transitions to the same hash (e.g. revert) collide on purpose
        — they really are the same target.
        """
        return f"v-{self.short_hash()}"


# ── Capture ────────────────────────────────────────────────────────────────


def _read_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _filter_public_failures(raw_yaml: str) -> str:
    """Return a YAML-equivalent JSON blob with only ``public: true``
    modes. Empty string if the catalog is missing or has no public
    modes; the canonical JSON ordering means this string is hash-stable.
    """
    if not raw_yaml.strip():
        return ""
    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError:
        return ""
    if not isinstance(data, dict):
        return ""
    modes = data.get("modes") or []
    public_modes = [
        m for m in modes
        if isinstance(m, dict) and bool(m.get("public", False))
    ]
    public_view = {
        "method": data.get("method", ""),
        "modes": public_modes,
    }
    if data.get("failures") == "deliberately-empty":
        public_view["failures"] = "deliberately-empty"
        public_view["justification"] = data.get("justification", "")
    return _canonical_yaml_dump(public_view)


def _domain_bound_json(name: str) -> str:
    """Best-effort serialize the registered DomainBound for a method.

    Returns "" when no bound is declared. This is fully deterministic
    given the registered bound and the embedding model — both are
    inputs the registry holds locally.
    """
    try:
        from noosphere.methods._registry import REGISTRY

        bound = REGISTRY.get_domain_bound(name)
    except Exception:
        return ""
    if bound is None:
        return ""

    payload: dict = {"combinator": getattr(bound, "combinator", "any")}
    tag = getattr(bound, "tag_bound", None)
    if tag is not None:
        payload["tags"] = list(getattr(tag, "tags", ()) or ())
    anchor = getattr(bound, "anchor_bound", None)
    if anchor is not None:
        payload["anchors"] = {
            "embedding_model": getattr(anchor, "embedding_model", ""),
            "in_radius": float(getattr(anchor, "in_radius", 0.0)),
            "edge_radius": float(getattr(anchor, "edge_radius", 0.0)),
            "revision_id": getattr(anchor, "revision_id", ""),
            # Anchor vectors themselves are large; we hash a digest of
            # them rather than dumping every coordinate, so the
            # changelog stays compact while still detecting changes.
            "anchors_digest": _digest_anchor_vectors(
                getattr(anchor, "anchors", ()) or ()
            ),
        }
    return _canonical_yaml_dump(payload)


def _digest_anchor_vectors(vectors) -> str:
    h = hashlib.sha256()
    for vec in vectors:
        h.update(b"|")
        for x in vec:
            h.update(f"{float(x):.12g}".encode("utf-8"))
            h.update(b",")
    return h.hexdigest()[:16]


def _hash_content(parts: list[str]) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(b"\x00")
        h.update(part.encode("utf-8"))
    return "v_" + h.hexdigest()[:40]


def capture_snapshot(
    name: str,
    version: str,
    *,
    methods_dir: Optional[Path] = None,
    source_override: Optional[str] = None,
    rationale_override: Optional[str] = None,
    failures_override: Optional[str] = None,
    domain_bound_override: Optional[str] = None,
    captured_at: Optional[datetime] = None,
) -> MethodVersionSnapshot:
    """Capture the on-disk state of a method as a content-addressed
    snapshot.

    The override arguments exist for tests: callers can construct two
    synthetic versions of a stub method without touching the real
    method tree. In production the overrides are unused and the
    snapshot is read from ``noosphere/methods/<name>.{py,RATIONALE.md,
    FAILURES.yaml}``.
    """
    base = methods_dir or _METHODS_DIR
    src_path = base / f"{name}.py"
    rat_path = base / f"{name}.RATIONALE.md"
    fail_path = base / f"{name}.FAILURES.yaml"

    source = (
        source_override
        if source_override is not None
        else _read_if_exists(src_path)
    )
    rationale = (
        rationale_override
        if rationale_override is not None
        else _read_if_exists(rat_path)
    )
    failures = (
        failures_override
        if failures_override is not None
        else _read_if_exists(fail_path)
    )
    bound_json = (
        domain_bound_override
        if domain_bound_override is not None
        else _domain_bound_json(name)
    )

    norm_src = _normalize_text(source)
    norm_rat = _normalize_text(rationale)
    norm_fail = _normalize_text(failures)
    norm_bound = bound_json  # already canonical

    public_failures = _filter_public_failures(norm_fail)

    content_hash = _hash_content([
        f"name={name}",
        f"version={version}",
        norm_src,
        norm_rat,
        norm_fail,
        norm_bound,
    ])

    return MethodVersionSnapshot(
        name=name,
        version=version,
        content_hash=content_hash,
        source=norm_src,
        rationale=norm_rat,
        failures_yaml=norm_fail,
        failures_public_yaml=public_failures,
        domain_bound_json=norm_bound,
        captured_at=captured_at or datetime.now(timezone.utc),
        source_path=str(src_path),
        rationale_path=str(rat_path),
        failures_path=str(fail_path),
    )


# ── Storage ────────────────────────────────────────────────────────────────


@dataclass
class InMemoryMethodVersionStore:
    """Process-local store of captured snapshots, keyed by
    ``(name, version)``. Production callers persist to the codex DB
    instead — see ``MethodVersion`` in the prisma schema."""

    _by_key: dict[tuple[str, str], MethodVersionSnapshot] = field(
        default_factory=dict
    )
    _by_hash: dict[str, MethodVersionSnapshot] = field(
        default_factory=dict
    )

    def upsert(self, snap: MethodVersionSnapshot) -> MethodVersionSnapshot:
        """Insert or replace. Re-capturing a hash that already exists
        is a no-op so that a CI run on the same checkout doesn't
        churn the store."""
        key = (snap.name, snap.version)
        existing = self._by_key.get(key)
        if existing is not None and existing.content_hash == snap.content_hash:
            return existing
        self._by_key[key] = snap
        self._by_hash[snap.content_hash] = snap
        return snap

    def get(self, name: str, version: str) -> Optional[MethodVersionSnapshot]:
        return self._by_key.get((name, version))

    def get_by_hash(self, content_hash: str) -> Optional[MethodVersionSnapshot]:
        return self._by_hash.get(content_hash)

    def list_for(self, name: str) -> list[MethodVersionSnapshot]:
        snaps = [s for (n, _v), s in self._by_key.items() if n == name]
        snaps.sort(key=lambda s: s.captured_at)
        return snaps


__all__ = [
    "InMemoryMethodVersionStore",
    "MethodVersionSnapshot",
    "capture_snapshot",
]

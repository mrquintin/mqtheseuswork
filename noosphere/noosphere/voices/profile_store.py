"""Local-only persistence for per-speaker methodology profiles.

A :class:`SpeakerProfileRecord` is the union of:

* identity (display name, opt-in flag),
* a list of :class:`SessionFingerprint` records — one per analyzed session,
  each carrying method counts, characteristic premises, characteristic
  objections, and a per-utterance novelty mean,
* an exponential decay constant (``decay_lambda``, in inverse days) that
  weights distant sessions less when summarising the profile.

The aggregate distribution is *derived* from the fingerprint list rather than
stored separately — this keeps session exclusion (``excluded=True``)
fully reversible without retro-editing transcripts.

Persistence is JSON files on disk under a directory the founder controls
(:func:`default_profile_dir`). Profiles never leave that directory unless the
caller explicitly copies them; this module makes no network calls.
"""

from __future__ import annotations

import json
import math
import os
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


# ----------------------------------------------------------------------
# Records
# ----------------------------------------------------------------------


@dataclass
class SessionFingerprint:
    """A single session's contribution to a speaker's profile.

    ``method_counts`` keys are ``MethodPattern.pattern_type`` values from
    :mod:`noosphere.methodology` (e.g. ``"first_principles_decomposition"``).
    """

    session_id: str
    session_start: str  # ISO-8601 UTC
    method_counts: dict[str, float] = field(default_factory=dict)
    premises: list[str] = field(default_factory=list)
    objections: list[str] = field(default_factory=list)
    utterance_count: int = 0
    novelty_mean: float = 0.0
    excluded: bool = False
    note: str = ""

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "SessionFingerprint":
        return cls(
            session_id=str(d["session_id"]),
            session_start=str(d["session_start"]),
            method_counts={str(k): float(v) for k, v in dict(d.get("method_counts") or {}).items()},
            premises=[str(p) for p in (d.get("premises") or [])],
            objections=[str(o) for o in (d.get("objections") or [])],
            utterance_count=int(d.get("utterance_count") or 0),
            novelty_mean=float(d.get("novelty_mean") or 0.0),
            excluded=bool(d.get("excluded") or False),
            note=str(d.get("note") or ""),
        )


@dataclass
class SpeakerProfileRecord:
    """Persisted profile for a single named speaker."""

    speaker_id: str
    display_name: str
    opt_in: bool = False
    decay_lambda: float = 1.0 / 180.0  # half-life ~ 125 days
    sessions: list[SessionFingerprint] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # ---- aggregation helpers ----------------------------------------

    def _weight(self, fp: SessionFingerprint, *, now: Optional[datetime] = None) -> float:
        if fp.excluded:
            return 0.0
        try:
            t = datetime.fromisoformat(fp.session_start)
        except ValueError:
            return 1.0
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        now_dt = now or datetime.now(timezone.utc)
        age_days = max(0.0, (now_dt - t).total_seconds() / 86400.0)
        return math.exp(-self.decay_lambda * age_days)

    def aggregate_method_distribution(
        self, *, now: Optional[datetime] = None
    ) -> dict[str, float]:
        """Decay-weighted, normalised distribution across method patterns."""
        totals: dict[str, float] = {}
        for fp in self.sessions:
            w = self._weight(fp, now=now)
            if w == 0.0:
                continue
            for k, v in fp.method_counts.items():
                totals[k] = totals.get(k, 0.0) + w * float(v)
        s = sum(totals.values())
        if s <= 0:
            return {}
        return {k: v / s for k, v in totals.items()}

    def aggregate_premises(self, *, top_k: int = 10, now: Optional[datetime] = None) -> list[tuple[str, float]]:
        return self._top_strings([fp.premises for fp in self.sessions], top_k=top_k, now=now)

    def aggregate_objections(self, *, top_k: int = 10, now: Optional[datetime] = None) -> list[tuple[str, float]]:
        return self._top_strings([fp.objections for fp in self.sessions], top_k=top_k, now=now)

    def _top_strings(
        self,
        per_session: list[list[str]],
        *,
        top_k: int,
        now: Optional[datetime],
    ) -> list[tuple[str, float]]:
        bucket: dict[str, float] = {}
        for fp, items in zip(self.sessions, per_session):
            w = self._weight(fp, now=now)
            if w == 0.0:
                continue
            for s in items:
                key = _normalise(s)
                if not key:
                    continue
                bucket[key] = bucket.get(key, 0.0) + w
        return sorted(bucket.items(), key=lambda kv: kv[1], reverse=True)[:top_k]

    def novelty_baseline(self, *, now: Optional[datetime] = None) -> float:
        """Decay-weighted mean per-utterance novelty across non-excluded sessions."""
        num = 0.0
        den = 0.0
        for fp in self.sessions:
            w = self._weight(fp, now=now)
            if w == 0.0:
                continue
            num += w * float(fp.novelty_mean)
            den += w
        if den == 0.0:
            return 0.0
        return num / den

    def has_baseline(self) -> bool:
        return any(not fp.excluded for fp in self.sessions)

    # ---- mutation helpers -------------------------------------------

    def add_session(self, fp: SessionFingerprint) -> None:
        # Replace if same session_id already present (idempotent re-ingest).
        self.sessions = [s for s in self.sessions if s.session_id != fp.session_id]
        self.sessions.append(fp)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def exclude_session(self, session_id: str, *, note: str = "") -> bool:
        for s in self.sessions:
            if s.session_id == session_id:
                s.excluded = True
                if note:
                    s.note = note
                self.updated_at = datetime.now(timezone.utc).isoformat()
                return True
        return False

    def reinclude_session(self, session_id: str) -> bool:
        for s in self.sessions:
            if s.session_id == session_id:
                s.excluded = False
                self.updated_at = datetime.now(timezone.utc).isoformat()
                return True
        return False

    # ---- serialisation ----------------------------------------------

    def to_json(self) -> dict:
        return {
            "speaker_id": self.speaker_id,
            "display_name": self.display_name,
            "opt_in": self.opt_in,
            "decay_lambda": self.decay_lambda,
            "sessions": [s.to_json() for s in self.sessions],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_json(cls, d: dict) -> "SpeakerProfileRecord":
        return cls(
            speaker_id=str(d["speaker_id"]),
            display_name=str(d["display_name"]),
            opt_in=bool(d.get("opt_in") or False),
            decay_lambda=float(d.get("decay_lambda") or (1.0 / 180.0)),
            sessions=[SessionFingerprint.from_json(s) for s in (d.get("sessions") or [])],
            created_at=str(d.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=str(d.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        )


# ----------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------


def _normalise(s: str) -> str:
    return " ".join(s.strip().lower().split())


def speaker_canonical_key(display_name: str) -> str:
    return _normalise(display_name)


def default_profile_dir() -> Path:
    """Local-only path that never leaves the founder's machine.

    macOS: ``~/Library/Application Support/Dialectic/voice_profiles``
    Windows: ``%APPDATA%/Dialectic/voice_profiles``
    Other: ``~/.dialectic/voice_profiles``
    """
    if sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / "Dialectic"
    elif sys.platform == "win32":
        d = Path(os.environ.get("APPDATA", str(Path.home()))) / "Dialectic"
    else:
        d = Path.home() / ".dialectic"
    return d / "voice_profiles"


class SpeakerProfileStore:
    """JSON-on-disk store for :class:`SpeakerProfileRecord`.

    One file per speaker (``<canonical_key>.json``). Atomic writes via
    rename. Thread-safe across the in-process API surface.
    """

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root is not None else default_profile_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ---- helpers ----------------------------------------------------

    def _path_for(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        return self.root / f"{safe}.json"

    # ---- read -------------------------------------------------------

    def get(self, display_name: str) -> Optional[SpeakerProfileRecord]:
        key = speaker_canonical_key(display_name)
        p = self._path_for(key)
        if not p.is_file():
            return None
        try:
            return SpeakerProfileRecord.from_json(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def list_profiles(self) -> list[SpeakerProfileRecord]:
        out: list[SpeakerProfileRecord] = []
        for f in sorted(self.root.glob("*.json")):
            try:
                out.append(SpeakerProfileRecord.from_json(json.loads(f.read_text(encoding="utf-8"))))
            except Exception:
                continue
        return out

    # ---- write ------------------------------------------------------

    def upsert(self, profile: SpeakerProfileRecord) -> SpeakerProfileRecord:
        key = speaker_canonical_key(profile.display_name)
        path = self._path_for(key)
        tmp = path.with_suffix(".json.tmp")
        with self._lock:
            tmp.write_text(json.dumps(profile.to_json(), indent=2), encoding="utf-8")
            os.replace(tmp, path)
        return profile

    def ensure(
        self,
        display_name: str,
        *,
        opt_in: bool = False,
        decay_lambda: Optional[float] = None,
    ) -> SpeakerProfileRecord:
        existing = self.get(display_name)
        if existing is not None:
            changed = False
            if opt_in and not existing.opt_in:
                existing.opt_in = True
                changed = True
            if decay_lambda is not None and decay_lambda != existing.decay_lambda:
                existing.decay_lambda = decay_lambda
                changed = True
            if changed:
                existing.updated_at = datetime.now(timezone.utc).isoformat()
                self.upsert(existing)
            return existing
        rec = SpeakerProfileRecord(
            speaker_id=str(uuid.uuid4()),
            display_name=display_name.strip(),
            opt_in=opt_in,
            decay_lambda=decay_lambda if decay_lambda is not None else (1.0 / 180.0),
        )
        self.upsert(rec)
        return rec

    # ---- session lifecycle -----------------------------------------

    def apply_session(
        self,
        display_name: str,
        fingerprint: SessionFingerprint,
        *,
        require_opt_in: bool = True,
    ) -> Optional[SpeakerProfileRecord]:
        """Add a session fingerprint to the speaker's profile.

        Returns ``None`` if the speaker is not opted in (and ``require_opt_in``
        is left at its default), making the call a no-op — preserving the
        opt-in invariant.
        """
        rec = self.get(display_name)
        if rec is None:
            return None
        if require_opt_in and not rec.opt_in:
            return None
        rec.add_session(fingerprint)
        self.upsert(rec)
        return rec

    def exclude_session(
        self,
        display_name: str,
        session_id: str,
        *,
        note: str = "",
    ) -> Optional[SpeakerProfileRecord]:
        rec = self.get(display_name)
        if rec is None:
            return None
        if rec.exclude_session(session_id, note=note):
            self.upsert(rec)
        return rec

    def reinclude_session(
        self,
        display_name: str,
        session_id: str,
    ) -> Optional[SpeakerProfileRecord]:
        rec = self.get(display_name)
        if rec is None:
            return None
        if rec.reinclude_session(session_id):
            self.upsert(rec)
        return rec

    def delete(self, display_name: str) -> bool:
        key = speaker_canonical_key(display_name)
        p = self._path_for(key)
        if p.is_file():
            p.unlink()
            return True
        return False

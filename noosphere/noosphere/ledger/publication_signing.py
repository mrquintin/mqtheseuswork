"""Sign-and-verify primitives for public publications.

Goal: every public publication carries a cryptographically signed
provenance trail. A reader who fetches `signature.json` from the public
site can run `noosphere ledger verify-publication <slug>` and confirm
that the live database row hashes to the same canonical bytes that
were signed.

Key management
--------------
Publication keys live under ``~/.theseus/keys/publication/`` (override
with ``THESEUS_PUBLICATION_KEY_DIR``). Layout::

    ~/.theseus/keys/publication/
        active                           # text file, key fingerprint
        keys/<fingerprint>/signing.key   # 32-byte Ed25519 seed (private)
        keys/<fingerprint>/verify.pub    # 32-byte Ed25519 verify key
        keys/<fingerprint>/created_at    # ISO timestamp
        keys/<fingerprint>/revoked_at    # present iff revoked

Rotation: ``rotate()`` generates a new keypair, makes it active, and
leaves the old verify key in place so historical publications still
verify. ``revoke(fingerprint)`` writes a ``revoked_at`` marker — new
signatures by that key will fail, but historical signatures whose
``signedAt`` predates the revocation continue to verify. This matches
the spec: "old keys remain valid for verifying historical material."

Private keys NEVER leave this module's directory. The web app stores
signatures (the public artifact) and serves them; only the noosphere
CLI signs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from nacl.signing import SigningKey, VerifyKey

from noosphere.ledger.canonicalize import (
    PublicationCanonicalInput,
    canonical_input_from_dict,
)

logger = logging.getLogger(__name__)


SIGNATURE_SCHEMA = "theseus.publicationSignature.v1"


def _default_key_dir() -> Path:
    override = os.environ.get("THESEUS_PUBLICATION_KEY_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".theseus" / "keys" / "publication"


def fingerprint(verify_key: VerifyKey) -> str:
    """Stable short fingerprint for a verify key."""
    return hashlib.sha256(bytes(verify_key)).hexdigest()[:16]


@dataclass
class KeyMeta:
    fingerprint: str
    created_at: str
    revoked_at: Optional[str] = None
    is_active: bool = False

    @property
    def revoked(self) -> bool:
        return self.revoked_at is not None


class PublicationKeyring:
    """Filesystem-backed keyring for publication signing.

    Active key signs new publications; all known keys verify (subject to
    revocation rules). The directory layout is documented at module top.
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root is not None else _default_key_dir()
        self.keys_dir = self.root / "keys"
        self.active_pointer = self.root / "active"

    # ── lifecycle ────────────────────────────────────────────────────
    def ensure(self) -> str:
        """Ensure at least one publication key exists; return active fingerprint."""
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
            os.chmod(self.keys_dir, 0o700)
        except OSError:
            pass
        if not self.active_pointer.is_file() or not self._key_exists(
            self.active_pointer.read_text().strip()
        ):
            return self.generate()
        return self.active_pointer.read_text().strip()

    def generate(self) -> str:
        """Generate a new keypair and mark it active. Returns the fingerprint."""
        sk = SigningKey.generate()
        fp = fingerprint(sk.verify_key)
        d = self.keys_dir / fp
        d.mkdir(parents=True, exist_ok=True)
        sk_path = d / "signing.key"
        sk_path.write_bytes(bytes(sk))
        try:
            os.chmod(sk_path, 0o600)
        except OSError:
            pass
        (d / "verify.pub").write_bytes(bytes(sk.verify_key))
        (d / "created_at").write_text(_now_iso())
        self.active_pointer.write_text(fp)
        logger.info("Generated publication key %s", fp)
        return fp

    def rotate(self) -> str:
        """Rotate to a new active key. Old keys remain valid for verification."""
        return self.generate()

    def revoke(self, fp: str) -> None:
        """Mark a key as revoked. Does not delete it (we still verify history)."""
        d = self.keys_dir / fp
        if not d.is_dir():
            raise FileNotFoundError(f"Unknown key fingerprint: {fp}")
        (d / "revoked_at").write_text(_now_iso())
        # If we revoked the active key, force the caller to mint a new one.
        if self.active_fingerprint() == fp:
            self.active_pointer.unlink(missing_ok=True)

    # ── queries ──────────────────────────────────────────────────────
    def active_fingerprint(self) -> Optional[str]:
        if not self.active_pointer.is_file():
            return None
        fp = self.active_pointer.read_text().strip()
        return fp or None

    def list_keys(self) -> list[KeyMeta]:
        if not self.keys_dir.is_dir():
            return []
        active = self.active_fingerprint()
        out: list[KeyMeta] = []
        for d in sorted(self.keys_dir.iterdir()):
            if not d.is_dir():
                continue
            created = (d / "created_at").read_text().strip() if (d / "created_at").is_file() else ""
            revoked = (d / "revoked_at").read_text().strip() if (d / "revoked_at").is_file() else None
            out.append(KeyMeta(
                fingerprint=d.name,
                created_at=created,
                revoked_at=revoked,
                is_active=(d.name == active),
            ))
        return out

    def _key_exists(self, fp: str) -> bool:
        return bool(fp) and (self.keys_dir / fp / "signing.key").is_file()

    def signing_key(self, fp: Optional[str] = None) -> SigningKey:
        target = fp or self.active_fingerprint()
        if not target:
            raise RuntimeError(
                "No active publication key. Run `noosphere ledger publication-keygen`."
            )
        path = self.keys_dir / target / "signing.key"
        if not path.is_file():
            raise FileNotFoundError(f"Signing key not found: {target}")
        meta = self._meta_for(target)
        if meta and meta.revoked:
            raise RuntimeError(
                f"Key {target} is revoked; cannot sign new publications."
            )
        return SigningKey(path.read_bytes()[:32])

    def verify_key(self, fp: str) -> Optional[VerifyKey]:
        path = self.keys_dir / fp / "verify.pub"
        if not path.is_file():
            return None
        return VerifyKey(path.read_bytes()[:32])

    def _meta_for(self, fp: str) -> Optional[KeyMeta]:
        for k in self.list_keys():
            if k.fingerprint == fp:
                return k
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ── signing / verifying ──────────────────────────────────────────────


@dataclass
class PublicationSignature:
    """The artifact published alongside every signed PublishedConclusion."""

    schema: str
    slug: str
    version: int
    canonical_input: dict[str, Any]
    canonical_hash: str
    signature_hex: str
    key_fingerprint: str
    signed_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "slug": self.slug,
            "version": self.version,
            "canonicalInput": self.canonical_input,
            "canonicalHash": self.canonical_hash,
            "signatureHex": self.signature_hex,
            "keyFingerprint": self.key_fingerprint,
            "signedAt": self.signed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PublicationSignature":
        return cls(
            schema=str(data.get("schema") or SIGNATURE_SCHEMA),
            slug=str(data["slug"]),
            version=int(data["version"]),
            canonical_input=dict(data["canonicalInput"]),
            canonical_hash=str(data["canonicalHash"]),
            signature_hex=str(data["signatureHex"]),
            key_fingerprint=str(data["keyFingerprint"]),
            signed_at=str(data["signedAt"]),
        )


def sign_publication(
    canonical_input: PublicationCanonicalInput,
    keyring: PublicationKeyring,
    *,
    key_fingerprint: Optional[str] = None,
    signed_at: Optional[str] = None,
) -> PublicationSignature:
    """Sign a publication's canonical bytes with the active (or specified) key."""
    sk = keyring.signing_key(key_fingerprint)
    fp = key_fingerprint or keyring.active_fingerprint()
    if fp is None:
        raise RuntimeError("No active key to sign with")

    canonical_dict = canonical_input.to_canonical_dict()
    canonical_bytes = canonical_input.to_canonical_bytes()
    canonical_hash = hashlib.sha256(canonical_bytes).hexdigest()
    signed = sk.sign(bytes.fromhex(canonical_hash))
    return PublicationSignature(
        schema=SIGNATURE_SCHEMA,
        slug=canonical_input.slug,
        version=int(canonical_input.version),
        canonical_input=canonical_dict,
        canonical_hash=canonical_hash,
        signature_hex=signed.signature.hex(),
        key_fingerprint=fp,
        signed_at=signed_at or _now_iso(),
    )


@dataclass
class VerificationResult:
    ok: bool
    reason: str = ""
    expected_hash: str = ""
    actual_hash: str = ""
    key_fingerprint: str = ""
    key_revoked: bool = False
    issues: list[str] = field(default_factory=list)


def verify_signature(
    sig: PublicationSignature,
    keyring: PublicationKeyring,
    *,
    live_input: Optional[PublicationCanonicalInput] = None,
) -> VerificationResult:
    """Verify a publication signature.

    - If ``live_input`` is provided, recompute its canonical hash and check
      it matches ``sig.canonical_hash``. A mismatch means either the DB row
      drifted from what was signed, or the signature is stale.
    - Verify the Ed25519 signature against the verify key for
      ``sig.key_fingerprint``.
    - Honor revocation: if the key was revoked BEFORE ``sig.signed_at``,
      the signature is rejected. Signatures issued before the revocation
      timestamp continue to verify (historical material stays valid).
    """
    issues: list[str] = []
    expected_hash = sig.canonical_hash
    actual_hash = expected_hash

    if live_input is not None:
        actual_hash = live_input.hash_hex()
        if actual_hash != expected_hash:
            issues.append(
                f"canonical hash mismatch: signed={expected_hash} live={actual_hash}"
            )

    vk = keyring.verify_key(sig.key_fingerprint)
    if vk is None:
        issues.append(f"unknown key fingerprint {sig.key_fingerprint!r}")
        return VerificationResult(
            ok=False,
            reason="unknown_key",
            expected_hash=expected_hash,
            actual_hash=actual_hash,
            key_fingerprint=sig.key_fingerprint,
            issues=issues,
        )

    meta = keyring._meta_for(sig.key_fingerprint)
    revoked = bool(meta and meta.revoked)
    if revoked and meta and meta.revoked_at and sig.signed_at:
        try:
            from datetime import datetime as _dt

            r = _dt.fromisoformat(meta.revoked_at.replace("Z", "+00:00"))
            s = _dt.fromisoformat(sig.signed_at.replace("Z", "+00:00"))
            if s >= r:
                issues.append(
                    f"signature dated {sig.signed_at} >= key revocation {meta.revoked_at}"
                )
        except ValueError:
            issues.append("could not parse signed_at/revoked_at timestamps")

    try:
        vk.verify(bytes.fromhex(sig.canonical_hash), bytes.fromhex(sig.signature_hex))
    except Exception as exc:  # nacl raises BadSignatureError
        issues.append(f"signature failed to verify: {exc}")

    ok = len(issues) == 0
    return VerificationResult(
        ok=ok,
        reason="" if ok else issues[0],
        expected_hash=expected_hash,
        actual_hash=actual_hash,
        key_fingerprint=sig.key_fingerprint,
        key_revoked=revoked,
        issues=issues,
    )


def verify_dict(
    sig_dict: dict[str, Any],
    keyring: PublicationKeyring,
    *,
    live_dict: Optional[dict[str, Any]] = None,
) -> VerificationResult:
    """Convenience wrapper: verify from raw JSON-shaped dicts."""
    sig = PublicationSignature.from_dict(sig_dict)
    live = canonical_input_from_dict(live_dict) if live_dict is not None else None
    return verify_signature(sig, keyring, live_input=live)


__all__ = [
    "PublicationKeyring",
    "PublicationSignature",
    "SIGNATURE_SCHEMA",
    "VerificationResult",
    "fingerprint",
    "sign_publication",
    "verify_dict",
    "verify_signature",
]

"""Replication reproducibility certificate.

When an outside researcher's replication matches the firm's recorded
numbers within tolerance, the harness emits a small JSON artifact —
the *certificate* — that the firm signs with its publication signing
key. The certificate is then portable: the researcher keeps a copy,
the firm publishes it on `/methodology/replicators` (with consent),
and any third party can verify the signature against the firm's
public verify key.

What the certificate certifies
------------------------------
It certifies, narrowly, *that the harness reproduced the firm's
published numbers on the named replicator's hardware*. It does NOT
certify:

- that the firm's numbers are correct (the certificate is downstream
  of the firm's own publication; the firm can be wrong, and a
  certificate against a wrong baseline is still a valid certificate
  of "we matched what was published"),
- that the replicator's identity is verified (the name and
  affiliation are claimed by the replicator; the firm gates public
  display behind manual consent),
- that future runs of the same harness will continue to match (a
  certificate is a snapshot — model API drift can move cross-model
  numbers in either direction).

The page at `/methodology/replicators` is responsible for making
this distinction visible to readers; this module is responsible for
making the certificate's payload unambiguous about what it covers.

Key reuse
---------
The certificate signs with the same publication signing key the
firm uses for `PublishedConclusion` rows (see
`noosphere.ledger.publication_signing`). That key never leaves the
firm's keyring directory; the replicator's machine does not need a
signing key, and the verifier only needs the corresponding verify
key. Replicators send the firm their run directory; the firm signs
and returns the certificate.

Canonicalization
----------------
The certificate's signed payload is the canonical JSON of a fixed
schema (`CANONICAL_FIELDS`), with sorted keys and no surrounding
whitespace. Hash is sha256 over the canonical bytes. The signature
is Ed25519 over that hash, matching the publication-signing scheme.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)


CERTIFICATE_SCHEMA = "theseus.replicationCertificate.v1"
CERTIFICATE_FILENAME = "reproducibility_certificate.json"

# Fields included in the canonical signing payload, in stable order.
# Any field NOT in this list is metadata — present in the JSON file
# for human inspection but not covered by the signature. The split
# is deliberate: signing fewer fields means fewer accidental
# resignings when a non-load-bearing string changes wording.
CANONICAL_FIELDS: tuple[str, ...] = (
    "schema",
    "benchmark_version",
    "runner_set",
    "dataset_sha256",
    "models",
    "deterministic",
    "abs_tol",
    "rel_tol",
    "verdict",
    "metric_keys_compared",
    "firm_envelope_git_sha",
    "replicator_envelope_git_sha",
    "replicator_python_version",
    "replicator_platform",
    "replicator_name",
    "replicator_affiliation",
    "replicator_consent_public",
)


# ---------------------------------------------------------------------------
# Data class


@dataclasses.dataclass(frozen=True)
class ReplicationCertificate:
    """A signed certificate that a replication matched the firm's numbers."""

    # --- Canonical / signed fields ----------------------------------------
    schema: str
    benchmark_version: str
    runner_set: tuple[str, ...]
    dataset_sha256: str
    models: tuple[str, ...]
    deterministic: bool
    abs_tol: float
    rel_tol: float
    verdict: str  # always "match" when emitted
    metric_keys_compared: tuple[str, ...]
    firm_envelope_git_sha: str
    replicator_envelope_git_sha: str
    replicator_python_version: str
    replicator_platform: str
    replicator_name: str
    replicator_affiliation: str
    replicator_consent_public: bool

    # --- Non-canonical metadata (informational; not signed) ---------------
    signed_at: str
    signature_hex: str
    canonical_hash: str
    key_fingerprint: str
    firm_envelope: dict[str, Any] = dataclasses.field(default_factory=dict)
    replicator_envelope: dict[str, Any] = dataclasses.field(default_factory=dict)
    notes: str = ""

    # ── canonicalization ─────────────────────────────────────────────────

    def canonical_dict(self) -> dict[str, Any]:
        """Return the canonical signing payload as an ordered dict."""
        return {field: _normalise(getattr(self, field)) for field in CANONICAL_FIELDS}

    def canonical_bytes(self) -> bytes:
        """Canonical JSON bytes used for hashing/signing."""
        return json.dumps(
            self.canonical_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    def recompute_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    # ── I/O ──────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema": self.schema,
            "benchmarkVersion": self.benchmark_version,
            "runnerSet": list(self.runner_set),
            "datasetSha256": self.dataset_sha256,
            "models": list(self.models),
            "deterministic": self.deterministic,
            "absTol": self.abs_tol,
            "relTol": self.rel_tol,
            "verdict": self.verdict,
            "metricKeysCompared": list(self.metric_keys_compared),
            "firmEnvelopeGitSha": self.firm_envelope_git_sha,
            "replicatorEnvelopeGitSha": self.replicator_envelope_git_sha,
            "replicatorPythonVersion": self.replicator_python_version,
            "replicatorPlatform": self.replicator_platform,
            "replicatorName": self.replicator_name,
            "replicatorAffiliation": self.replicator_affiliation,
            "replicatorConsentPublic": self.replicator_consent_public,
            "signedAt": self.signed_at,
            "signatureHex": self.signature_hex,
            "canonicalHash": self.canonical_hash,
            "keyFingerprint": self.key_fingerprint,
            "firmEnvelope": self.firm_envelope,
            "replicatorEnvelope": self.replicator_envelope,
            "notes": self.notes,
        }
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReplicationCertificate":
        return cls(
            schema=str(data.get("schema") or CERTIFICATE_SCHEMA),
            benchmark_version=str(data["benchmarkVersion"]),
            runner_set=tuple(data.get("runnerSet") or ()),
            dataset_sha256=str(data["datasetSha256"]),
            models=tuple(data.get("models") or ()),
            deterministic=bool(data["deterministic"]),
            abs_tol=float(data["absTol"]),
            rel_tol=float(data["relTol"]),
            verdict=str(data["verdict"]),
            metric_keys_compared=tuple(data.get("metricKeysCompared") or ()),
            firm_envelope_git_sha=str(data.get("firmEnvelopeGitSha", "")),
            replicator_envelope_git_sha=str(
                data.get("replicatorEnvelopeGitSha", "")
            ),
            replicator_python_version=str(data.get("replicatorPythonVersion", "")),
            replicator_platform=str(data.get("replicatorPlatform", "")),
            replicator_name=str(data.get("replicatorName", "")),
            replicator_affiliation=str(data.get("replicatorAffiliation", "")),
            replicator_consent_public=bool(data.get("replicatorConsentPublic", False)),
            signed_at=str(data.get("signedAt", "")),
            signature_hex=str(data.get("signatureHex", "")),
            canonical_hash=str(data.get("canonicalHash", "")),
            key_fingerprint=str(data.get("keyFingerprint", "")),
            firm_envelope=dict(data.get("firmEnvelope") or {}),
            replicator_envelope=dict(data.get("replicatorEnvelope") or {}),
            notes=str(data.get("notes", "")),
        )


# ---------------------------------------------------------------------------
# Build & sign


def _normalise(value: Any) -> Any:
    """Normalise types so the canonical dict has stable encoding.

    Tuples become lists (JSON doesn't have tuples). Floats are passed
    through; `json.dumps` with stable separators handles the rest.
    """
    if isinstance(value, tuple):
        return list(value)
    return value


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_certificate(
    *,
    firm_envelope: Mapping[str, Any],
    replicator_envelope: Mapping[str, Any],
    verdict: str,
    abs_tol: float,
    rel_tol: float,
    metric_keys_compared: tuple[str, ...],
    replicator_name: str,
    replicator_affiliation: str,
    replicator_consent_public: bool,
    notes: str = "",
) -> ReplicationCertificate:
    """Build an *unsigned* certificate from two envelopes and a verdict.

    The function does not access any signing key. Signing is a
    separate step (:func:`sign_certificate`) so that a replicator can
    pre-stage the certificate locally and submit it to the firm for
    signing without ever needing the firm's private key.

    Raises ``ValueError`` if the verdict is not "match"; certificates
    are only issued for successful replications. A `mismatch` or
    `incompatible` outcome is data, but it is not a thing the firm
    signs.
    """
    if verdict != "match":
        raise ValueError(
            "certificates are only emitted for verdict='match'; "
            f"got {verdict!r}. A mismatch or incompatible run should "
            "be filed as an issue, not certified."
        )
    if not replicator_name.strip():
        raise ValueError(
            "replicator_name is required (the certificate is meaningless "
            "without the name of the person whose hardware it covers). "
            "Set --replicator-name on the CLI or pass it explicitly."
        )

    # We pull dataset/runner/model identity from the *firm's* envelope.
    # If the replicator envelope's structural fields disagreed, the
    # verifier would have returned "incompatible" already — we are
    # downstream of that check.
    return ReplicationCertificate(
        schema=CERTIFICATE_SCHEMA,
        benchmark_version=str(firm_envelope.get("benchmark_version", "")),
        runner_set=tuple([str(firm_envelope.get("runner", ""))]),
        dataset_sha256=str(firm_envelope.get("dataset_sha256", "")),
        models=tuple(firm_envelope.get("models") or ()),
        deterministic=bool(firm_envelope.get("deterministic", False)),
        abs_tol=float(abs_tol),
        rel_tol=float(rel_tol),
        verdict=verdict,
        metric_keys_compared=tuple(metric_keys_compared),
        firm_envelope_git_sha=str(firm_envelope.get("git_sha", "")),
        replicator_envelope_git_sha=str(replicator_envelope.get("git_sha", "")),
        replicator_python_version=str(
            replicator_envelope.get("python_version", "")
        ),
        replicator_platform=str(replicator_envelope.get("platform", "")),
        replicator_name=replicator_name.strip(),
        replicator_affiliation=replicator_affiliation.strip(),
        replicator_consent_public=bool(replicator_consent_public),
        signed_at="",
        signature_hex="",
        canonical_hash="",
        key_fingerprint="",
        firm_envelope=dict(firm_envelope),
        replicator_envelope=dict(replicator_envelope),
        notes=notes,
    )


def sign_certificate(
    cert: ReplicationCertificate,
    *,
    signing_key_bytes: Optional[bytes] = None,
    key_fingerprint: Optional[str] = None,
    signed_at: Optional[str] = None,
) -> ReplicationCertificate:
    """Sign a certificate with the firm's publication key.

    Two ways to provide the key:

    1. ``signing_key_bytes`` + ``key_fingerprint`` — used by tests
       and any code that already holds the 32-byte Ed25519 seed.
    2. Neither argument — defer to
       ``noosphere.ledger.publication_signing.PublicationKeyring``
       to resolve the active key from disk. This is the path the
       firm's signing CLI uses.

    The signature covers :func:`canonical_bytes` of the certificate,
    *not* the full to_dict() output. The non-canonical metadata
    (`firm_envelope`, `replicator_envelope`, `notes`) can be edited
    without invalidating the signature — by design, since wording
    fixes should not require a re-sign.
    """
    from nacl.signing import SigningKey

    if signing_key_bytes is not None:
        if key_fingerprint is None:
            # Derive from the verify key — same scheme as the keyring.
            sk = SigningKey(signing_key_bytes[:32])
            key_fingerprint = hashlib.sha256(bytes(sk.verify_key)).hexdigest()[:16]
        sk = SigningKey(signing_key_bytes[:32])
    else:
        # Resolve from the firm's keyring. Imported lazily so this
        # module does not require noosphere on the import path.
        from noosphere.ledger.publication_signing import (  # noqa: WPS433
            PublicationKeyring,
        )

        keyring = PublicationKeyring()
        keyring.ensure()
        fp = key_fingerprint or keyring.active_fingerprint()
        if fp is None:
            raise RuntimeError(
                "No active publication key in the firm's keyring. "
                "Run `noosphere ledger publication-keygen` before signing."
            )
        sk = keyring.signing_key(fp)
        key_fingerprint = fp

    # Sign the canonical hash — matches the publication signing
    # scheme so any verifier already familiar with that flow can use
    # the same code path.
    canonical_hash = cert.recompute_hash()
    signed = sk.sign(bytes.fromhex(canonical_hash))

    return dataclasses.replace(
        cert,
        signed_at=signed_at or _now_iso(),
        signature_hex=signed.signature.hex(),
        canonical_hash=canonical_hash,
        key_fingerprint=key_fingerprint,
    )


# ---------------------------------------------------------------------------
# Verify


@dataclasses.dataclass
class CertificateVerification:
    ok: bool
    reason: str = ""
    canonical_hash_expected: str = ""
    canonical_hash_recomputed: str = ""
    key_fingerprint: str = ""
    issues: list[str] = dataclasses.field(default_factory=list)


def verify_certificate(
    cert: ReplicationCertificate,
    *,
    verify_key_bytes: Optional[bytes] = None,
) -> CertificateVerification:
    """Verify a certificate's Ed25519 signature.

    If ``verify_key_bytes`` is provided, it is used directly. Otherwise
    the firm's keyring is consulted for the verify key matching
    ``cert.key_fingerprint``. A third party who has the firm's
    published verify key (32 bytes, hex-encoded on the
    `/methodology/replicators` page) can pass it here without any
    noosphere dependency.

    The function recomputes the canonical hash from the canonical
    fields and checks both (a) the recomputed hash equals
    ``cert.canonical_hash`` (no tampering with the canonical payload)
    and (b) the Ed25519 signature verifies against that hash.
    """
    from nacl.signing import VerifyKey
    from nacl.exceptions import BadSignatureError

    issues: list[str] = []
    expected_hash = cert.canonical_hash
    recomputed = cert.recompute_hash()
    if recomputed != expected_hash:
        issues.append(
            f"canonical hash mismatch: signed={expected_hash} "
            f"recomputed={recomputed} — the canonical payload was edited "
            "after signing"
        )

    vk_bytes: Optional[bytes] = verify_key_bytes
    if vk_bytes is None:
        try:
            from noosphere.ledger.publication_signing import (  # noqa: WPS433
                PublicationKeyring,
            )

            keyring = PublicationKeyring()
            vk = keyring.verify_key(cert.key_fingerprint)
            if vk is not None:
                vk_bytes = bytes(vk)
        except Exception as exc:  # pragma: no cover - import-side
            issues.append(f"could not load firm keyring: {exc}")

    if vk_bytes is None:
        issues.append(
            f"no verify key available for fingerprint {cert.key_fingerprint!r}"
        )
        return CertificateVerification(
            ok=False,
            reason="unknown_key",
            canonical_hash_expected=expected_hash,
            canonical_hash_recomputed=recomputed,
            key_fingerprint=cert.key_fingerprint,
            issues=issues,
        )

    try:
        VerifyKey(vk_bytes[:32]).verify(
            bytes.fromhex(cert.canonical_hash),
            bytes.fromhex(cert.signature_hex),
        )
    except BadSignatureError as exc:
        issues.append(f"signature failed to verify: {exc}")
    except ValueError as exc:
        issues.append(f"malformed signature hex: {exc}")

    ok = not issues
    return CertificateVerification(
        ok=ok,
        reason="" if ok else issues[0],
        canonical_hash_expected=expected_hash,
        canonical_hash_recomputed=recomputed,
        key_fingerprint=cert.key_fingerprint,
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Filesystem helpers


def write_certificate(cert: ReplicationCertificate, path: Path | str) -> Path:
    """Write the certificate to ``path`` (file or directory)."""
    p = Path(path)
    if p.is_dir() or (not p.exists() and not p.suffix):
        p.mkdir(parents=True, exist_ok=True)
        p = p / CERTIFICATE_FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(cert.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return p


def read_certificate(path: Path | str) -> ReplicationCertificate:
    """Load a certificate from a file or a directory containing one."""
    p = Path(path)
    if p.is_dir():
        p = p / CERTIFICATE_FILENAME
    if not p.exists():
        raise FileNotFoundError(f"no certificate at {p}")
    return ReplicationCertificate.from_dict(json.loads(p.read_text(encoding="utf-8")))


__all__ = [
    "CANONICAL_FIELDS",
    "CERTIFICATE_FILENAME",
    "CERTIFICATE_SCHEMA",
    "CertificateVerification",
    "ReplicationCertificate",
    "build_certificate",
    "read_certificate",
    "sign_certificate",
    "verify_certificate",
    "write_certificate",
]

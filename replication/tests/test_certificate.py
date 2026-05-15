"""Tests for the replication reproducibility certificate.

The certificate is small but load-bearing: a wrong signature or a
broken canonicalization would silently let an unverified row land on
the firm's `/methodology/replicators` page. Every claim made by
`replication/lib/certificate.py` corresponds to at least one test
here.

Tests are deterministic — no clocks, no random keys leaking into the
signature payload. The fixture key is fixed bytes so the
canonical-hash test is reproducible.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from replication.lib.certificate import (
    CANONICAL_FIELDS,
    CERTIFICATE_FILENAME,
    CERTIFICATE_SCHEMA,
    ReplicationCertificate,
    build_certificate,
    read_certificate,
    sign_certificate,
    verify_certificate,
    write_certificate,
)

# A fixed Ed25519 seed used across tests. NOT a real firm key; the
# determinism is the point.
TEST_SEED = b"\x01" * 32


def _verify_key_bytes(seed: bytes = TEST_SEED) -> bytes:
    from nacl.signing import SigningKey

    return bytes(SigningKey(seed[:32]).verify_key)


def _firm_envelope() -> dict:
    return {
        "benchmark_version": "qh-v1",
        "runner": "contradiction_geometry",
        "dataset_sha256": "sha256:" + "a" * 64,
        "models": ["hash-det"],
        "deterministic": True,
        "git_sha": "deadbeefcafe1234",
        "git_dirty": False,
        "python_version": "3.11.9",
        "platform": "Linux-6.5.0-x86_64",
    }


def _replicator_envelope(**overrides) -> dict:
    base = {
        "benchmark_version": "qh-v1",
        "runner": "contradiction_geometry",
        "dataset_sha256": "sha256:" + "a" * 64,
        "models": ["hash-det"],
        "deterministic": True,
        "git_sha": "1234abcd9876feed",
        "git_dirty": False,
        "python_version": "3.11.9",
        "platform": "Darwin-25.0.0-arm64",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# build_certificate


def test_build_requires_match_verdict() -> None:
    with pytest.raises(ValueError, match="match"):
        build_certificate(
            firm_envelope=_firm_envelope(),
            replicator_envelope=_replicator_envelope(),
            verdict="mismatch",
            abs_tol=1e-12,
            rel_tol=1e-2,
            metric_keys_compared=("accuracy",),
            replicator_name="A. Researcher",
            replicator_affiliation="MIT",
            replicator_consent_public=True,
        )


def test_build_requires_replicator_name() -> None:
    with pytest.raises(ValueError, match="replicator_name"):
        build_certificate(
            firm_envelope=_firm_envelope(),
            replicator_envelope=_replicator_envelope(),
            verdict="match",
            abs_tol=1e-12,
            rel_tol=1e-2,
            metric_keys_compared=("accuracy",),
            replicator_name="   ",
            replicator_affiliation="MIT",
            replicator_consent_public=True,
        )


def test_build_pulls_identity_from_firm_envelope() -> None:
    cert = build_certificate(
        firm_envelope=_firm_envelope(),
        replicator_envelope=_replicator_envelope(),
        verdict="match",
        abs_tol=1e-12,
        rel_tol=1e-2,
        metric_keys_compared=("accuracy",),
        replicator_name="A. Researcher",
        replicator_affiliation="MIT",
        replicator_consent_public=False,
    )
    assert cert.benchmark_version == "qh-v1"
    assert cert.dataset_sha256 == "sha256:" + "a" * 64
    assert cert.models == ("hash-det",)
    assert cert.deterministic is True
    assert cert.replicator_consent_public is False
    # Replicator-specific fields come from the replicator envelope.
    assert cert.replicator_platform.startswith("Darwin")
    # Signing fields are blank pre-sign.
    assert cert.signature_hex == ""
    assert cert.canonical_hash == ""


# ---------------------------------------------------------------------------
# canonical bytes / hash


def test_canonical_bytes_is_stable() -> None:
    cert = _make_cert()
    b1 = cert.canonical_bytes()
    b2 = cert.canonical_bytes()
    assert b1 == b2
    # The canonical payload only includes CANONICAL_FIELDS.
    parsed = json.loads(b1.decode("utf-8"))
    assert set(parsed.keys()) == set(CANONICAL_FIELDS)


def test_canonical_hash_changes_with_canonical_field() -> None:
    a = _make_cert()
    b = _make_cert(replicator_name="B. Other")
    assert a.recompute_hash() != b.recompute_hash()


def test_non_canonical_edits_do_not_change_hash() -> None:
    a = _make_cert()
    # `notes` is informational, not canonical — editing it should
    # leave the canonical hash invariant. That property is what lets
    # the firm fix wording without resigning.
    import dataclasses

    b = dataclasses.replace(a, notes="edited later")
    assert a.recompute_hash() == b.recompute_hash()


# ---------------------------------------------------------------------------
# sign / verify round-trip


def test_sign_then_verify_roundtrip() -> None:
    cert = _make_cert()
    signed = sign_certificate(
        cert, signing_key_bytes=TEST_SEED, signed_at="2026-05-14T00:00:00Z"
    )
    assert signed.signature_hex
    assert signed.canonical_hash == cert.recompute_hash()
    # Fingerprint is the same scheme as the publication keyring.
    expected_fp = hashlib.sha256(_verify_key_bytes()).hexdigest()[:16]
    assert signed.key_fingerprint == expected_fp

    result = verify_certificate(signed, verify_key_bytes=_verify_key_bytes())
    assert result.ok is True
    assert result.issues == []


def test_verify_rejects_tampered_canonical_payload() -> None:
    cert = _make_cert()
    signed = sign_certificate(cert, signing_key_bytes=TEST_SEED)
    # Edit a CANONICAL field. The signature should no longer verify
    # because the recomputed hash will not match.
    import dataclasses

    tampered = dataclasses.replace(signed, replicator_name="Mallory")
    result = verify_certificate(tampered, verify_key_bytes=_verify_key_bytes())
    assert result.ok is False
    assert any("canonical hash mismatch" in issue for issue in result.issues)


def test_verify_rejects_wrong_signing_key() -> None:
    cert = _make_cert()
    signed = sign_certificate(cert, signing_key_bytes=TEST_SEED)
    other_verify_key = _verify_key_bytes(b"\x02" * 32)
    result = verify_certificate(signed, verify_key_bytes=other_verify_key)
    assert result.ok is False
    assert any("signature failed" in issue for issue in result.issues)


def test_verify_reports_unknown_key_when_no_verify_key_resolvable(
    monkeypatch,
) -> None:
    cert = _make_cert()
    signed = sign_certificate(cert, signing_key_bytes=TEST_SEED)
    # Point the firm's keyring at an empty temp dir so it has no
    # verify key for the test fingerprint.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setenv("THESEUS_PUBLICATION_KEY_DIR", td)
        result = verify_certificate(signed)  # no explicit verify key
    assert result.ok is False
    assert "unknown_key" in result.reason or any(
        "no verify key" in issue for issue in result.issues
    )


# ---------------------------------------------------------------------------
# read/write / from_dict / to_dict


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    cert = sign_certificate(_make_cert(), signing_key_bytes=TEST_SEED)
    out = write_certificate(cert, tmp_path)
    assert out.name == CERTIFICATE_FILENAME
    loaded = read_certificate(out)
    assert loaded.schema == cert.schema
    assert loaded.canonical_hash == cert.canonical_hash
    assert loaded.signature_hex == cert.signature_hex
    assert loaded.replicator_name == cert.replicator_name
    # Verification still works after a round trip through disk.
    result = verify_certificate(loaded, verify_key_bytes=_verify_key_bytes())
    assert result.ok is True


def test_write_to_explicit_file_path(tmp_path: Path) -> None:
    cert = sign_certificate(_make_cert(), signing_key_bytes=TEST_SEED)
    target = tmp_path / "nested" / "cert.json"
    out = write_certificate(cert, target)
    assert out == target
    assert target.is_file()


def test_read_certificate_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_certificate(tmp_path / "nope.json")


def test_schema_constant_is_v1() -> None:
    # The schema string is publicly referenced; bumping it is a
    # public-facing change. This test exists to make that bump
    # visible.
    assert CERTIFICATE_SCHEMA == "theseus.replicationCertificate.v1"


# ---------------------------------------------------------------------------
# Helper


def _make_cert(**overrides) -> ReplicationCertificate:
    kwargs = {
        "firm_envelope": _firm_envelope(),
        "replicator_envelope": _replicator_envelope(),
        "verdict": "match",
        "abs_tol": 1e-12,
        "rel_tol": 1e-2,
        "metric_keys_compared": ("accuracy", "auroc_contradicting_vs_coherent"),
        "replicator_name": "A. Researcher",
        "replicator_affiliation": "MIT",
        "replicator_consent_public": True,
    }
    name = overrides.pop("replicator_name", None)
    if name is not None:
        kwargs["replicator_name"] = name
    kwargs.update(overrides)
    return build_certificate(**kwargs)

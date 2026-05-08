"""Tests for publication signing: round-trip, mutation detection, key rotation/revocation, canonical-hash stability."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from noosphere.ledger.canonicalize import (
    MqsSnapshot,
    PublicationCanonicalInput,
    canonical_input_from_dict,
    normalize_iso_timestamp,
    normalize_markdown,
)
from noosphere.ledger.publication_signing import (
    PublicationKeyring,
    PublicationSignature,
    sign_publication,
    verify_signature,
)


def _example_input(**overrides) -> PublicationCanonicalInput:
    base = dict(
        slug="example-conclusion",
        version=1,
        conclusion_text=(
            "# Theseus does not assume\n\n"
            "Calibration discounts must be **explicit**.\n"
        ),
        methodology_profile_ids=["mp_b", "mp_a"],
        citations=[
            {"format": "bibtex", "block": "@misc{x, title={X}}"},
            {"format": "apa", "block": "Theseus (2026). X."},
        ],
        discounted_confidence=0.62,
        stated_confidence=0.78,
        mqs=MqsSnapshot(
            composite=0.71,
            progressivity=0.6,
            severity=0.4,
            aim_method_fit=0.8,
            compressibility=0.5,
            domain_sensitivity=0.7,
            prompt_version="mqs-prompt-v1.0",
        ),
        published_at="2026-05-08T12:00:00+00:00",
    )
    base.update(overrides)
    return PublicationCanonicalInput(**base)


# ── canonicalization ─────────────────────────────────────────────────


def test_normalize_markdown_unifies_line_endings_and_trailing_whitespace():
    a = "Hello world  \r\nThis is a line\r\n\r\n\r\n\r\nThird"
    b = "Hello world\nThis is a line\n\nThird"
    assert normalize_markdown(a) == b


def test_normalize_markdown_idempotent_on_clean_input():
    s = "Already normalized\n\nText body"
    assert normalize_markdown(s) == s


def test_canonical_hash_stable_under_irrelevant_whitespace():
    """Whitespace changes that should NOT matter must not change the hash."""
    a = _example_input()
    b = _example_input(
        conclusion_text=(
            "# Theseus does not assume\r\n\r\n"
            "Calibration discounts must be **explicit**.   \r\n\r\n\r\n"
        ),
    )
    assert a.hash_hex() == b.hash_hex()


def test_canonical_hash_stable_under_citation_reorder():
    a = _example_input()
    b = _example_input(citations=list(reversed(a.citations)))
    assert a.hash_hex() == b.hash_hex()


def test_canonical_hash_stable_under_methodology_id_reorder():
    a = _example_input(methodology_profile_ids=["mp_a", "mp_b"])
    b = _example_input(methodology_profile_ids=["mp_b", "mp_a"])
    assert a.hash_hex() == b.hash_hex()


def test_canonical_hash_changes_when_substantive_content_changes():
    """Real content edits MUST change the hash."""
    a = _example_input()
    b = _example_input(conclusion_text=a.conclusion_text + "\n\nAdded paragraph.")
    assert a.hash_hex() != b.hash_hex()


def test_canonical_hash_changes_when_citation_is_added():
    a = _example_input()
    b = _example_input(
        citations=a.citations + [{"format": "ris", "block": "TY  - GEN\n"}],
    )
    assert a.hash_hex() != b.hash_hex()


def test_canonical_hash_changes_when_confidence_changes():
    a = _example_input()
    b = _example_input(discounted_confidence=0.61)
    assert a.hash_hex() != b.hash_hex()


def test_normalize_iso_timestamp_strips_microseconds():
    assert normalize_iso_timestamp("2026-05-08T12:00:00.123456+00:00") == "2026-05-08T12:00:00Z"
    assert normalize_iso_timestamp("2026-05-08T12:00:00Z") == "2026-05-08T12:00:00Z"


def test_canonical_input_from_dict_round_trip():
    a = _example_input()
    d = a.to_canonical_dict()
    b = canonical_input_from_dict(d)
    assert a.hash_hex() == b.hash_hex()


# ── sign / verify round trip ─────────────────────────────────────────


@pytest.fixture
def keyring(tmp_path: Path) -> PublicationKeyring:
    kr = PublicationKeyring(tmp_path / "publication-keys")
    kr.ensure()
    return kr


def test_sign_and_verify_round_trip(keyring: PublicationKeyring):
    canonical = _example_input()
    sig = sign_publication(canonical, keyring)
    assert sig.canonical_hash == canonical.hash_hex()
    assert sig.key_fingerprint == keyring.active_fingerprint()

    result = verify_signature(sig, keyring, live_input=canonical)
    assert result.ok, result.issues
    assert result.expected_hash == sig.canonical_hash
    assert result.actual_hash == sig.canonical_hash


def test_mutated_content_fails_verification(keyring: PublicationKeyring):
    canonical = _example_input()
    sig = sign_publication(canonical, keyring)

    # Database mutated after signing — conclusion text edited.
    mutated = _example_input(
        conclusion_text=canonical.conclusion_text + "\n\n[appended after signing]",
    )

    result = verify_signature(sig, keyring, live_input=mutated)
    assert not result.ok
    assert result.actual_hash != result.expected_hash
    assert any("hash mismatch" in i for i in result.issues)


def test_mutated_signature_bytes_fail_verification(keyring: PublicationKeyring):
    canonical = _example_input()
    sig = sign_publication(canonical, keyring)
    # Flip a byte in the signature; the canonical hash still matches but
    # the Ed25519 verification must reject it.
    bad_hex = bytearray(bytes.fromhex(sig.signature_hex))
    bad_hex[0] ^= 0x01
    bad_sig = PublicationSignature(
        schema=sig.schema,
        slug=sig.slug,
        version=sig.version,
        canonical_input=sig.canonical_input,
        canonical_hash=sig.canonical_hash,
        signature_hex=bad_hex.hex(),
        key_fingerprint=sig.key_fingerprint,
        signed_at=sig.signed_at,
    )
    result = verify_signature(bad_sig, keyring, live_input=canonical)
    assert not result.ok
    assert any("signature failed to verify" in i for i in result.issues)


# ── rotation & revocation ────────────────────────────────────────────


def test_key_rotation_signs_new_with_new_key_and_keeps_history(keyring: PublicationKeyring):
    canonical = _example_input()
    sig_old = sign_publication(canonical, keyring)
    old_fp = keyring.active_fingerprint()
    assert sig_old.key_fingerprint == old_fp

    new_fp = keyring.rotate()
    assert new_fp != old_fp
    assert keyring.active_fingerprint() == new_fp

    # Historical signature still verifies under the rotated keyring.
    result_old = verify_signature(sig_old, keyring, live_input=canonical)
    assert result_old.ok, result_old.issues

    # New publication is signed with the new key.
    new_pub = _example_input(version=2, conclusion_text=canonical.conclusion_text + "\n\nv2.")
    sig_new = sign_publication(new_pub, keyring)
    assert sig_new.key_fingerprint == new_fp
    assert verify_signature(sig_new, keyring, live_input=new_pub).ok


def test_revoked_key_rejects_new_signing_but_verifies_history(keyring: PublicationKeyring):
    canonical = _example_input()
    # Pin signed_at well before the (later) revocation timestamp so the
    # second-precision comparison is unambiguous.
    historical_signed_at = "2026-05-08T11:00:00Z"
    historical_sig = sign_publication(canonical, keyring, signed_at=historical_signed_at)
    old_fp = keyring.active_fingerprint()

    # Revoke before any new signing happens. Historical material must still verify.
    keyring.revoke(old_fp)

    # Active pointer cleared — must mint a fresh key to sign anything new.
    assert keyring.active_fingerprint() is None

    with pytest.raises(RuntimeError):
        sign_publication(_example_input(version=2), keyring, key_fingerprint=old_fp)

    # Historical signature: signed_at predates revocation, must still verify.
    result_hist = verify_signature(historical_sig, keyring, live_input=canonical)
    assert result_hist.ok, result_hist.issues

    # A signature dated AFTER the revocation must be rejected even if the
    # cryptographic signature is otherwise valid.
    revoked_meta = next(k for k in keyring.list_keys() if k.fingerprint == old_fp)
    after_revoke = (datetime.fromisoformat(revoked_meta.revoked_at.replace("Z", "+00:00"))
                    + timedelta(seconds=1))
    forged_future = PublicationSignature(
        schema=historical_sig.schema,
        slug=historical_sig.slug,
        version=historical_sig.version,
        canonical_input=historical_sig.canonical_input,
        canonical_hash=historical_sig.canonical_hash,
        signature_hex=historical_sig.signature_hex,
        key_fingerprint=historical_sig.key_fingerprint,
        signed_at=after_revoke.isoformat().replace("+00:00", "Z"),
    )
    bad = verify_signature(forged_future, keyring, live_input=canonical)
    assert not bad.ok
    assert any("revocation" in i for i in bad.issues)


def test_unknown_key_fingerprint_fails(keyring: PublicationKeyring, tmp_path: Path):
    canonical = _example_input()
    sig = sign_publication(canonical, keyring)

    # New, empty keyring — the fingerprint is unknown.
    other = PublicationKeyring(tmp_path / "other-keys")
    other.ensure()  # different active key
    result = verify_signature(sig, other, live_input=canonical)
    assert not result.ok
    assert result.reason == "unknown_key"


# ── PublicationSignature serialization ───────────────────────────────


def test_publication_signature_round_trip_dict(keyring: PublicationKeyring):
    canonical = _example_input()
    sig = sign_publication(canonical, keyring)
    d = sig.to_dict()
    recovered = PublicationSignature.from_dict(d)
    assert recovered.canonical_hash == sig.canonical_hash
    assert recovered.signature_hex == sig.signature_hex
    assert recovered.key_fingerprint == sig.key_fingerprint
    result = verify_signature(recovered, keyring, live_input=canonical)
    assert result.ok

"""Sign and verify CHECKSUMS files using the ledger KeyRing."""
from __future__ import annotations

import base64
import hashlib
import logging
from pathlib import Path
from typing import Optional

from noosphere.ledger.keys import KeyRing

logger = logging.getLogger(__name__)


def compute_checksums(directory: Path) -> str:
    """Compute SHA-256 checksums for every file in *directory* (sorted, recursive)."""
    lines: list[str] = []
    for p in sorted(directory.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(directory)
        if str(rel) in ("CHECKSUMS", "CHECKSUMS.sig"):
            continue
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        lines.append(f"{digest}  {rel}")
    return "\n".join(lines) + "\n"


def sign_checksums(checksums_text: str, keyring: KeyRing) -> tuple[str, str]:
    """Sign *checksums_text* and return ``(signature_b64, key_id)``."""
    sig_bytes = keyring.sign(checksums_text.encode())
    sig_b64 = base64.b64encode(sig_bytes).decode()
    return sig_b64, keyring.active_key_id


def verify_checksums(
    checksums_text: str,
    signature_b64: str,
    key_id: str,
    keyring: KeyRing,
) -> bool:
    """Verify *signature_b64* against *checksums_text* using *keyring*."""
    sig_bytes = base64.b64decode(signature_b64)
    return keyring.verify(checksums_text.encode(), sig_bytes, key_id)


def write_signed_checksums(
    directory: Path,
    keyring: KeyRing,
    checksums_path: Optional[Path] = None,
) -> Path:
    """Compute, sign, and write CHECKSUMS + CHECKSUMS.sig into *directory*.

    Returns the CHECKSUMS path.
    """
    checksums_text = compute_checksums(directory)
    sig_b64, key_id = sign_checksums(checksums_text, keyring)

    ck_path = checksums_path or (directory / "CHECKSUMS")
    ck_path.write_text(checksums_text)

    sig_path = ck_path.parent / (ck_path.name + ".sig")
    sig_path.write_text(f"{sig_b64}\n{key_id}\n")

    return ck_path


def verify_signed_checksums(directory: Path, keyring: KeyRing) -> bool:
    """Verify CHECKSUMS + CHECKSUMS.sig in *directory*."""
    ck_path = directory / "CHECKSUMS"
    sig_path = directory / "CHECKSUMS.sig"
    if not ck_path.exists() or not sig_path.exists():
        return False

    checksums_text = ck_path.read_text()
    parts = sig_path.read_text().strip().split("\n")
    if len(parts) != 2:
        return False

    sig_b64, key_id = parts
    return verify_checksums(checksums_text, sig_b64, key_id, keyring)

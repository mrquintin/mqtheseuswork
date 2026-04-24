from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

from nacl.signing import SigningKey, VerifyKey

logger = logging.getLogger(__name__)


def _key_id(verify_key: VerifyKey) -> str:
    return hashlib.sha256(bytes(verify_key)).hexdigest()[:16]


class KeyRing:
    """Manages Ed25519 signing/verification keys for the ledger."""

    def __init__(
        self,
        signing_key_path: Optional[str | Path] = None,
        verification_keys_dir: Optional[str | Path] = None,
    ) -> None:
        sk_path = signing_key_path or os.environ.get("THESEUS_LEDGER_SIGNING_KEY_PATH")
        vk_dir = verification_keys_dir or os.environ.get("THESEUS_LEDGER_VERIFICATION_KEYS_DIR")

        if sk_path is None:
            raise ValueError("Signing key path required (arg or THESEUS_LEDGER_SIGNING_KEY_PATH)")
        self._sk_path = Path(sk_path)
        self._signing_key = SigningKey(self._sk_path.read_bytes()[:32])
        self._active_key_id = _key_id(self._signing_key.verify_key)

        self._verify_keys: dict[str, VerifyKey] = {}
        self._verify_keys[self._active_key_id] = self._signing_key.verify_key

        if vk_dir is not None:
            self._vk_dir = Path(vk_dir)
            self._load_verification_keys()
        else:
            self._vk_dir = None

    def _load_verification_keys(self) -> None:
        if self._vk_dir is None or not self._vk_dir.is_dir():
            return
        for p in sorted(self._vk_dir.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                try:
                    vk = VerifyKey(p.read_bytes()[:32])
                    kid = _key_id(vk)
                    self._verify_keys[kid] = vk
                except Exception:
                    logger.warning("Skipping invalid verification key: %s", p)

    @property
    def active_key_id(self) -> str:
        return self._active_key_id

    def sign(self, data: bytes) -> bytes:
        signed = self._signing_key.sign(data)
        return signed.signature

    def verify(self, data: bytes, signature: bytes, key_id: str) -> bool:
        vk = self._verify_keys.get(key_id)
        if vk is None:
            return False
        try:
            vk.verify(data, signature)
            return True
        except Exception:
            return False

    def rotate(self, new_key_path: str | Path) -> None:
        new_path = Path(new_key_path)
        new_sk = SigningKey(new_path.read_bytes()[:32])
        new_kid = _key_id(new_sk.verify_key)
        self._verify_keys[new_kid] = new_sk.verify_key
        self._signing_key = new_sk
        self._sk_path = new_path
        self._active_key_id = new_kid

    @staticmethod
    def generate_keypair(key_dir: Path) -> Path:
        """Generate a new Ed25519 keypair, saving to key_dir. Returns signing key path."""
        key_dir.mkdir(parents=True, exist_ok=True)
        sk = SigningKey.generate()
        sk_path = key_dir / "signing.key"
        sk_path.write_bytes(bytes(sk))
        vk_path = key_dir / "verify.pub"
        vk_path.write_bytes(bytes(sk.verify_key))
        return sk_path

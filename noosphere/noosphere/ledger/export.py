from __future__ import annotations

import json
import os
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Optional

from noosphere.models import LedgerEntry
from noosphere.ledger.keys import KeyRing


def export_bundle(
    store: Any,
    keyring: KeyRing,
    *,
    from_id: str,
    to_id: str,
    out_path: str | Path,
    storage_client: Optional[Any] = None,
) -> Path:
    out_path = Path(out_path)
    entries = list(store.iter_ledger(from_id=from_id, to_id=to_id))

    with tempfile.TemporaryDirectory() as tmpdir:
        bundle_dir = Path(tmpdir) / "bundle"
        bundle_dir.mkdir()

        _write_ledger_slice(bundle_dir, entries)
        _write_blobs(bundle_dir, entries, storage_client)
        _write_method_specs(bundle_dir, entries, store)
        _write_public_keys(bundle_dir, keyring)
        _write_verify_script(bundle_dir)

        with tarfile.open(out_path, "w:gz") as tar:
            tar.add(str(bundle_dir), arcname="bundle")

    return out_path


def _write_ledger_slice(bundle_dir: Path, entries: list[LedgerEntry]) -> None:
    ledger_file = bundle_dir / "ledger.jsonl"
    with open(ledger_file, "w") as f:
        for entry in entries:
            f.write(entry.model_dump_json() + "\n")


def _write_blobs(
    bundle_dir: Path,
    entries: list[LedgerEntry],
    storage_client: Optional[Any],
) -> None:
    if storage_client is None:
        return
    blobs_dir = bundle_dir / "blobs"
    blobs_dir.mkdir()
    seen: set[str] = set()
    for entry in entries:
        for ref in (entry.inputs_ref, entry.outputs_ref):
            if not ref or ref in seen:
                continue
            seen.add(ref)
            try:
                key = _ref_to_key(ref)
                data = storage_client.open_read(key=key).read()
                safe_name = ref.replace("/", "_").replace(":", "_")
                (blobs_dir / safe_name).write_bytes(data)
            except Exception:
                pass


def _write_method_specs(
    bundle_dir: Path,
    entries: list[LedgerEntry],
    store: Any,
) -> None:
    methods_dir = bundle_dir / "methods"
    methods_dir.mkdir()
    seen: set[str] = set()
    for entry in entries:
        mid = entry.method_id
        if not mid or mid in seen:
            continue
        seen.add(mid)
        try:
            from noosphere.methods._registry import REGISTRY
            spec, _ = _find_method_by_id(REGISTRY, mid)
            (methods_dir / f"{mid}.json").write_text(spec.model_dump_json(indent=2))
        except Exception:
            pass


def _write_public_keys(bundle_dir: Path, keyring: KeyRing) -> None:
    keys_dir = bundle_dir / "keys"
    keys_dir.mkdir()
    for kid, vk in keyring._verify_keys.items():
        (keys_dir / f"{kid}.pub").write_bytes(bytes(vk))


def _write_verify_script(bundle_dir: Path) -> None:
    script = bundle_dir / "verify_bundle.py"
    script.write_text(_VERIFY_SCRIPT)
    os.chmod(script, 0o755)


def _ref_to_key(ref: str) -> str:
    if ref.startswith("file://"):
        return ref[7:].split("/blobs/", 1)[-1] if "/blobs/" in ref else ref[7:]
    return ref


def _find_method_by_id(registry: Any, method_id: str) -> tuple:
    for spec in registry.list():
        if spec.method_id == method_id:
            return registry.get(spec.name, version=spec.version)
    raise LookupError(f"Method {method_id} not found in registry")


_VERIFY_SCRIPT = '''\
#!/usr/bin/env python3
"""Standalone verification script for a ledger audit bundle."""
import hashlib
import json
import sys
from pathlib import Path

try:
    from nacl.signing import VerifyKey
except ImportError:
    sys.exit("pynacl required: pip install pynacl")


def main():
    bundle_dir = Path(__file__).parent
    ledger_file = bundle_dir / "ledger.jsonl"
    keys_dir = bundle_dir / "keys"

    if not ledger_file.exists():
        sys.exit("ledger.jsonl not found in bundle")

    verify_keys: dict[str, VerifyKey] = {}
    if keys_dir.is_dir():
        for p in sorted(keys_dir.iterdir()):
            if p.suffix == ".pub":
                kid = p.stem
                verify_keys[kid] = VerifyKey(p.read_bytes()[:32])

    entries = []
    with open(ledger_file) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    issues = []
    for i, entry in enumerate(entries):
        expected_prev = entries[i - 1]["entry_id"] if i > 0 else ""
        if entry["prev_hash"] != expected_prev:
            issues.append(f"Chain break at {entry['entry_id']}: prev_hash mismatch")

        kid = entry.get("signer_key_id", "")
        sig_hex = entry.get("signature", "")
        if kid not in verify_keys:
            issues.append(f"Unknown signer key {kid} for {entry['entry_id']}")
        else:
            try:
                verify_keys[kid].verify(
                    entry["entry_id"].encode(),
                    bytes.fromhex(sig_hex),
                )
            except Exception:
                issues.append(f"Bad signature for {entry['entry_id']}")

    if issues:
        print("VERIFICATION FAILED")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)
    else:
        print(f"OK: {len(entries)} entries verified")


if __name__ == "__main__":
    main()
'''

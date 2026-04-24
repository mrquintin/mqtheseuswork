"""Build a Methodology Interoperability Package (MIP)."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import NewType, Optional

from noosphere.docgen import compile_method_doc
from noosphere.ledger.keys import KeyRing
from noosphere.models import MethodRef
from noosphere.transfer import package as package_method

MIPPath = NewType("MIPPath", Path)

_MIP_VERSION = "1.0.0"


def build_mip(
    methods: list[MethodRef],
    include_gate_checks: bool,
    name: str,
    version: str,
    out_dir: Path,
    keyring: KeyRing,
    *,
    store: object | None = None,
    license_spdx: str = "Apache-2.0",
    sub_licenses: dict[str, str] | None = None,
    cascade_schema: dict | None = None,
    gate_checks: list[dict] | None = None,
) -> MIPPath:
    sub_licenses = sub_licenses or {}
    mip_dir = out_dir / f"{name}-{version}.mip"
    mip_dir.mkdir(parents=True, exist_ok=True)

    methods_dir = mip_dir / "methods"
    methods_dir.mkdir(exist_ok=True)
    docs_dir = mip_dir / "docs"
    docs_dir.mkdir(exist_ok=True)

    method_entries: list[dict] = []
    doc_entries: list[dict] = []

    for mref in methods:
        pkg_out = methods_dir / mref.name
        pkg_out.mkdir(exist_ok=True)
        package_method(mref, pkg_out, keyring)
        method_entries.append({
            "name": mref.name,
            "version": mref.version,
            "path": f"methods/{mref.name}",
            "checksum": _dir_checksum(pkg_out),
        })

        doc_out = docs_dir / mref.name
        doc_out.mkdir(exist_ok=True)
        compile_method_doc(mref, doc_out, keyring)
        doc_entries.append({
            "method": mref.name,
            "path": f"docs/{mref.name}",
            "checksum": _dir_checksum(doc_out),
        })

    cascade_dir = mip_dir / "cascade"
    cascade_dir.mkdir(exist_ok=True)
    schema_data = cascade_schema or _default_cascade_schema()
    (cascade_dir / "schema.json").write_text(
        json.dumps(schema_data, indent=2, sort_keys=True)
    )
    cascade_checksum = _file_checksum(cascade_dir / "schema.json")

    gate_dir = mip_dir / "gate"
    gate_dir.mkdir(exist_ok=True)
    if include_gate_checks:
        checks_data = gate_checks or _default_gate_checks()
    else:
        checks_data = []
    (gate_dir / "checks.json").write_text(
        json.dumps(checks_data, indent=2, sort_keys=True)
    )
    gate_checksum = _file_checksum(gate_dir / "checks.json")

    ledger_dir = mip_dir / "ledger"
    ledger_dir.mkdir(exist_ok=True)
    genesis = {
        "entry_id": "genesis",
        "mip_name": name,
        "mip_version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (ledger_dir / "genesis.json").write_text(
        json.dumps(genesis, indent=2, sort_keys=True)
    )

    workflows_dir = mip_dir / "workflows"
    workflows_dir.mkdir(exist_ok=True)

    _write_license(mip_dir, license_spdx)
    _write_citation(mip_dir, name, version)

    manifest = {
        "mip_version": _MIP_VERSION,
        "name": name,
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "methods": method_entries,
        "docs": doc_entries,
        "cascade_schema_checksum": cascade_checksum,
        "gate_checks_checksum": gate_checksum,
        "license": license_spdx,
        "sub_licenses": sub_licenses,
    }

    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    sig = keyring.sign(canonical)
    manifest["signature"] = sig.hex()
    manifest["signer_key_id"] = keyring.active_key_id

    (mip_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))

    from .leak_check import leak_check
    leak_check(mip_dir)

    return MIPPath(mip_dir)


def verify_manifest(mip_dir: Path, keyring: KeyRing) -> bool:
    manifest_path = mip_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    sig_hex = manifest.pop("signature")
    key_id = manifest.pop("signer_key_id")

    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return keyring.verify(canonical, bytes.fromhex(sig_hex), key_id)


def verify_checksums(mip_dir: Path) -> list[str]:
    manifest = json.loads((mip_dir / "manifest.json").read_text())
    errors: list[str] = []

    for m in manifest.get("methods", []):
        actual = _dir_checksum(mip_dir / m["path"])
        if actual != m["checksum"]:
            errors.append(f"method {m['name']}: expected {m['checksum']}, got {actual}")

    for d in manifest.get("docs", []):
        actual = _dir_checksum(mip_dir / d["path"])
        if actual != d["checksum"]:
            errors.append(f"docs {d['method']}: expected {d['checksum']}, got {actual}")

    cascade_actual = _file_checksum(mip_dir / "cascade" / "schema.json")
    if cascade_actual != manifest.get("cascade_schema_checksum"):
        errors.append(f"cascade schema: expected {manifest.get('cascade_schema_checksum')}, got {cascade_actual}")

    gate_actual = _file_checksum(mip_dir / "gate" / "checks.json")
    if gate_actual != manifest.get("gate_checks_checksum"):
        errors.append(f"gate checks: expected {manifest.get('gate_checks_checksum')}, got {gate_actual}")

    return errors


def _dir_checksum(directory: Path) -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for p in sorted(directory.rglob("*")):
            if p.is_file():
                info = tarfile.TarInfo(name=str(p.relative_to(directory)))
                info.size = p.stat().st_size
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                with open(p, "rb") as f:
                    tar.addfile(info, f)
    return hashlib.sha256(buf.getvalue()).hexdigest()


def _file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _default_cascade_schema() -> dict:
    from noosphere.models import CascadeEdgeRelation, CascadeNodeKind
    return {
        "node_kinds": [k.value for k in CascadeNodeKind],
        "edge_relations": [r.value for r in CascadeEdgeRelation],
    }


def _default_gate_checks() -> list[dict]:
    from noosphere.rigor_gate.checks import all_checks
    return [{"name": name} for name in sorted(all_checks().keys())]


def _write_license(mip_dir: Path, spdx: str) -> None:
    (mip_dir / "LICENSE").write_text(
        f"SPDX-License-Identifier: {spdx}\n\n"
        f"This MIP is distributed under the {spdx} license.\n"
        "See individual method sub-directories for method-specific licenses.\n"
    )


def _write_citation(mip_dir: Path, name: str, version: str) -> None:
    cff = (
        "cff-version: 1.2.0\n"
        f"title: \"{name}\"\n"
        f"version: \"{version}\"\n"
        f"date-released: \"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}\"\n"
        "type: software\n"
        "message: \"If you use this methodology package, please cite it as below.\"\n"
    )
    (mip_dir / "CITATION.cff").write_text(cff)

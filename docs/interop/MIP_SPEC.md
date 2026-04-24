# Methodology Interoperability Package (MIP) Specification

Version: 1.0.0

## Overview

A MIP is a self-contained, distributable bundle that packages one or more
Noosphere methods together with compiled documentation, cascade schema,
rigor-gate checks, and a minimal workflow language. Adopters can run MIPs on
their own infrastructure via Docker without access to the originating firm's
systems.

## On-Disk Layout

```
<name>-<version>.mip/
├── manifest.json          # Package metadata, content hashes, signature
├── methods/               # Packaged method artifacts
│   ├── <method-a>/        # Output of transfer.package_method
│   │   ├── method.json
│   │   ├── rationale.md
│   │   ├── implementation/
│   │   ├── adapter.py
│   │   ├── Dockerfile
│   │   ├── CHECKSUMS
│   │   ├── CHECKSUMS.sig
│   │   ├── README.md
│   │   ├── EVAL_CARD.md
│   │   └── LICENSE
│   └── <method-b>/
│       └── ...
├── cascade/               # Cascade schema export
│   └── schema.json        # Node kinds, edge relations, constraints
├── gate/                  # Rigor-gate check subset
│   └── checks.json        # Serialised check definitions for local use
├── ledger/                # Local ledger bootstrap
│   └── genesis.json       # Genesis entry for adopter's local ledger
├── docs/                  # Compiled method documentation
│   ├── <method-a>/
│   │   ├── spec.md
│   │   ├── rationale.md
│   │   ├── examples.md
│   │   ├── calibration.md
│   │   ├── transfer.md
│   │   └── operations.md
│   └── <method-b>/
│       └── ...
├── workflows/             # Optional workflow definitions
│   └── default.yaml       # Minimal YAML workflow
├── LICENSE                # Top-level license (must be compatible with sub-licenses)
└── CITATION.cff           # Citation metadata for the bundle
```

## manifest.json

```json
{
  "mip_version": "1.0.0",
  "name": "<bundle-name>",
  "version": "<semver>",
  "created_at": "<ISO-8601>",
  "methods": [
    {
      "name": "<method-name>",
      "version": "<method-version>",
      "path": "methods/<method-name>",
      "checksum": "<sha256 hex of method directory tarball>"
    }
  ],
  "docs": [
    {
      "method": "<method-name>",
      "path": "docs/<method-name>",
      "checksum": "<sha256 hex of docs directory tarball>"
    }
  ],
  "cascade_schema_checksum": "<sha256>",
  "gate_checks_checksum": "<sha256>",
  "license": "<SPDX identifier>",
  "sub_licenses": {
    "<method-name>": "<SPDX identifier>"
  },
  "signature": "<hex-encoded Ed25519 signature of canonical manifest>",
  "signer_key_id": "<key-id>"
}
```

### Content Hashing

All checksums use SHA-256 over the canonical byte content. For directories,
the content is a deterministic tar archive (sorted entries, zero timestamps,
zero uid/gid) of the directory contents.

### Signature

The signature covers the manifest JSON with the `signature` and
`signer_key_id` fields removed, serialized with sorted keys and no
whitespace. Verification uses the `ledger.keys.KeyRing`.

## Workflow Language

Workflows are defined in YAML with a deliberately minimal grammar.

### Allowed Top-Level Keys

| Key      | Type          | Required | Description                  |
|----------|---------------|----------|------------------------------|
| `name`   | string        | yes      | Workflow identifier          |
| `steps`  | list of steps | yes      | Ordered execution steps      |
| `output` | string        | yes      | Step ID whose output is final|

### Step Schema

| Key      | Type   | Required | Description                           |
|----------|--------|----------|---------------------------------------|
| `id`     | string | yes      | Unique step identifier                |
| `method` | string | yes      | Method name (must exist in bundle)    |
| `input`  | any    | yes      | Input data or reference to prior step |
| `when`   | object | no       | Equality predicate gate               |

### `when` Predicate

Only equality checks are supported:

```yaml
when:
  field: "status"
  equals: "ready"
```

No shell-out, no conditionals beyond equality, no loops.

## Security Constraints

- **No telemetry**: MIPs must not phone home. No network calls except
  explicit Docker pulls for method containers.
- **Leak check**: Before distribution, bundles are scanned against a deny-list
  of firm-private identifiers and filenames. Build fails on any hit.
- **Signature verification**: Runners must verify manifest signature and all
  content checksums before execution.
- **Container isolation**: Each method step runs in its own Docker container
  with no network access during execution.

## Adoption

Adopters receive a MIP and use `scaffold_adoption` to generate:
- A ready-to-run example directory
- A stub adapter for local data integration
- A local scoreboard setup for tracking runs
- A README with citation instructions (referencing CITATION.cff)

## Transfer Studies

Adopters can submit transfer studies back through the rigor gate using
`submit_transfer`. Studies must pass all registered checks before appearing
on the firm's public transfer-profile page.

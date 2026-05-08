#!/usr/bin/env python3
"""Materialize the method composition DAG as a static JSON snapshot.

Run at build time (Vercel deploy) so the public ``/methodology/composition``
and internal ``/methods/graph`` pages can render the DAG without needing
noosphere as a running service.

Usage::

    python noosphere/scripts/dump_method_graph.py \
        --out theseus-codex/public/method-graph.json

The snapshot shape is documented in
``noosphere.methods.composition.graph_snapshot``. Two payloads are
written when ``--public-out`` is also given: the full graph (for the
internal page) and a public-only filter that drops methods whose
``Method.status`` is not in {active, deprecated} or whose failure-mode
catalog flags every mode as private.

The script does NOT touch the noosphere store: drift state and active
failure modes default to "ok" unless the operator passes
``--leaf-severities path/to/state.json``. That separation keeps the
build deterministic and offline-runnable; production deploys may layer
in the runtime severity map via a follow-on step before serving.
"""
from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
import sys
from pathlib import Path
from typing import Optional


def _import_all_methods() -> None:
    """Import every module under ``noosphere.methods`` so the registry
    is populated. We skip private modules and the test-only legacy
    package — they don't register methods.
    """
    import noosphere.methods as methods_pkg

    for mod_info in pkgutil.iter_modules(methods_pkg.__path__):
        name = mod_info.name
        if name.startswith("_"):
            continue
        if name in {"composition", "failure_modes"}:
            continue
        try:
            importlib.import_module(f"noosphere.methods.{name}")
        except Exception as exc:  # pragma: no cover — defensive
            print(
                f"warning: failed to import noosphere.methods.{name}: {exc}",
                file=sys.stderr,
            )


def _load_severities(path: Optional[Path]) -> dict[str, str]:
    if path is None:
        return {}
    if not path.exists():
        print(f"warning: --leaf-severities {path} not found, using empty",
              file=sys.stderr)
        return {}
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise SystemExit(f"{path}: expected JSON object name->severity")
    return {str(k): str(v) for k, v in raw.items()}


def _public_set(registry) -> set[str]:  # noqa: ANN001
    """Public-side filter: include methods whose status is active or
    deprecated. Retired/experimental methods stay internal."""
    out: set[str] = set()
    for spec in registry.list():
        if spec.status in {"active", "deprecated"}:
            out.add(spec.name)
    return out


def _method_meta(registry) -> dict[str, dict]:  # noqa: ANN001
    """Latest-version metadata per method name, used for tooltips and
    detail-page links in the UI."""
    latest: dict[str, dict] = {}
    for spec in registry.list():
        cur = latest.get(spec.name)
        if cur is None or _semver_gt(spec.version, cur["version"]):
            latest[spec.name] = {
                "version": spec.version,
                "status": spec.status,
                "description": spec.description or "",
            }
    return latest


def _semver_gt(a: str, b: str) -> bool:
    def _parts(v: str):
        out = []
        for p in v.split("."):
            try:
                out.append(int(p))
            except ValueError:
                out.append(0)
        return tuple(out)
    return _parts(a) > _parts(b)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Where to write the full graph snapshot (internal /methods/graph).",
    )
    parser.add_argument(
        "--public-out",
        type=Path,
        default=None,
        help="Where to write the public-filtered snapshot. Optional.",
    )
    parser.add_argument(
        "--leaf-severities",
        type=Path,
        default=None,
        help=(
            "JSON file mapping method name -> severity label (drift state "
            "or active failure-mode severity). Defaults to all-ok."
        ),
    )
    args = parser.parse_args()

    _import_all_methods()

    from noosphere.methods import REGISTRY, build_dag, graph_snapshot

    dag = build_dag(REGISTRY)
    severities = _load_severities(args.leaf_severities)
    meta = _method_meta(REGISTRY)

    full = graph_snapshot(dag, leaf_severities=severities, method_meta=meta)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(full, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(full['nodes'])} nodes, {len(full['edges'])} edges → {args.out}")

    if args.public_out is not None:
        public = graph_snapshot(
            dag,
            leaf_severities=severities,
            public_only=_public_set(REGISTRY),
            method_meta=meta,
        )
        args.public_out.parent.mkdir(parents=True, exist_ok=True)
        args.public_out.write_text(json.dumps(public, indent=2, sort_keys=True) + "\n")
        print(
            f"wrote public {len(public['nodes'])} nodes, "
            f"{len(public['edges'])} edges → {args.public_out}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())

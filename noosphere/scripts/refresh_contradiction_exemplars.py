#!/usr/bin/env python3
"""Rebuild contradiction exemplar JSONL without requesting embedding APIs."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    REPO_ROOT / "noosphere_data" / "coherence" / "contradiction_exemplars.jsonl"
)
FIXTURE_DIR = (
    REPO_ROOT
    / "noosphere"
    / "tests"
    / "fixtures"
    / "port_parity"
    / "contradiction_geometry"
)
PAIRS_MODULE = (
    REPO_ROOT
    / "ideologicalOntology"
    / "Contradiction_Geometry"
    / "contradiction_pairs.py"
)


def _json_key(record: dict[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def _load_pairs_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "theseus_contradiction_pairs", PAIRS_MODULE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {PAIRS_MODULE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def records_from_fixtures() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "embedding_a" not in data or "embedding_b" not in data:
            continue
        records.append(
            {
                "id": f"fixture:{path.stem}",
                "source": str(path.relative_to(REPO_ROOT)),
                "relationship": "contradiction",
                "embedding_a": data["embedding_a"],
                "embedding_b": data["embedding_b"],
                "threshold": data.get("threshold"),
            }
        )
    return records


def records_from_contradiction_pairs() -> list[dict[str, Any]]:
    module = _load_pairs_module()
    records: list[dict[str, Any]] = []
    for index, pair in enumerate(module.get_pairs_by_relationship("contradiction")):
        text_a, text_b, relationship, domain, subtype = pair
        records.append(
            {
                "id": f"contradiction_pairs:{domain}:{subtype}:{index}",
                "source": str(PAIRS_MODULE.relative_to(REPO_ROOT)),
                "relationship": relationship,
                "domain": domain,
                "subtype": subtype,
                "text_a": text_a,
                "text_b": text_b,
            }
        )

    for index, row in enumerate(getattr(module, "NEGATION_TEST_PAIRS", [])):
        original = row.get("original")
        if not original:
            continue
        for style in ("simple", "antonym", "indirect", "scalar", "modal", "quantifier"):
            text_b = row.get(style)
            if not text_b:
                continue
            records.append(
                {
                    "id": f"negation_test:{index}:{style}",
                    "source": str(PAIRS_MODULE.relative_to(REPO_ROOT)),
                    "relationship": "contradiction",
                    "domain": "negation_test",
                    "subtype": style,
                    "text_a": original,
                    "text_b": text_b,
                }
            )
    return records


def build_records() -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for record in [*records_from_fixtures(), *records_from_contradiction_pairs()]:
        deduped[_json_key(record)] = record
    return [deduped[key] for key in sorted(deduped)]


def write_records(path: Path, records: list[dict[str, Any]], *, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(
            f"{path} already exists; pass --force to overwrite it intentionally"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )
    path.write_text(payload, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild noosphere_data/coherence/contradiction_exemplars.jsonl"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    records = build_records()
    write_records(args.output, records, force=args.force)
    embedded = sum(
        1 for record in records if "embedding_a" in record and "embedding_b" in record
    )
    print(
        f"wrote {len(records)} contradiction exemplar records "
        f"({embedded} embedded) to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

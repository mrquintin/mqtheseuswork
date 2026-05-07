#!/usr/bin/env python3
"""Rebuild the Noosphere domain-locality ANN index from persisted embeddings."""

from __future__ import annotations

import argparse
from pathlib import Path

from noosphere.coherence.locality import DomainLocalityIndex
from noosphere.config import get_settings
from noosphere.store import Store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override THESEUS_DATABASE_URL / settings database URL.",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Override THESEUS_DATA_DIR for locality index output.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    settings = get_settings()
    store = Store.from_database_url(args.database_url or settings.database_url)
    data_dir = Path(args.data_dir) if args.data_dir else settings.data_dir
    index = DomainLocalityIndex(data_dir=data_dir, store=store, autosave=False)
    count = index.rebuild_from_store(store)
    file_size = index.index_path.stat().st_size if index.index_path.exists() else 0
    print(f"Indexed {count} vectors")
    print(f"Index file: {index.index_path}")
    print(f"Index file size: {file_size} bytes")


if __name__ == "__main__":
    main()

"""
Backup and restore Noosphere SQLite state, data directory, and config hints.
"""

from __future__ import annotations

import io
import json
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from sqlalchemy.engine import make_url

from noosphere.config import NoosphereSettings, get_settings
from noosphere.observability import get_logger

logger = get_logger(__name__)


def _sqlite_path_from_url(database_url: str) -> Path | None:
    url = make_url(database_url)
    if url.drivername != "sqlite":
        return None
    if not url.database or url.database == ":memory:":
        return None
    return Path(unquote(str(url.database)))


def _resolve_sqlite_path(db_path: Path, *, data_dir: Path) -> Path:
    p = db_path.expanduser()
    if not p.is_absolute():
        return (data_dir / p).resolve()
    return p.resolve()


def create_backup_archive(
    settings: NoosphereSettings | None = None,
    *,
    output_dir: Path | None = None,
) -> Path:
    """
    Pack SQLite DB (if used), entire data_dir, and a manifest into a gzipped tarball.

    Returns path to the created archive.
    """
    s = settings or get_settings()
    out_dir = output_dir or (Path.home() / ".theseus" / "archives")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    archive_path = out_dir / f"theseus_backup_{stamp}.tar.gz"

    data_dir = s.data_dir.resolve()
    manifest: dict[str, Any] = {
        "version": 1,
        "created_utc": stamp,
        "database_url": s.database_url,
        "data_dir": str(data_dir),
    }

    sqlite_path = _sqlite_path_from_url(s.database_url)
    if sqlite_path is not None:
        manifest["sqlite_path_in_archive"] = "store.sqlite"
        sqlite_resolved = _resolve_sqlite_path(sqlite_path, data_dir=data_dir)

    with tarfile.open(archive_path, "w:gz") as tf:
        info = tarfile.TarInfo(name="manifest.json")
        raw = json.dumps(manifest, indent=2).encode("utf-8")
        info.size = len(raw)
        tf.addfile(info, fileobj=io.BytesIO(raw))

        if data_dir.is_dir():
            for path in data_dir.rglob("*"):
                if path.is_dir():
                    continue
                arc = Path("data_dir") / path.relative_to(data_dir)
                tf.add(path, arcname=str(arc), recursive=False)

        if sqlite_path is not None and sqlite_resolved.is_file():
            tf.add(sqlite_resolved, arcname="store.sqlite")

    logger.info("backup_created", path=str(archive_path))
    return archive_path


def restore_backup_archive(
    archive_path: Path,
    *,
    settings: NoosphereSettings | None = None,
    force: bool = False,
) -> None:
    """
    Extract tarball and merge ``data_dir/`` into configured data_dir; replace SQLite file.
    """
    if not archive_path.is_file():
        raise FileNotFoundError(str(archive_path))
    s = settings or get_settings()
    data_dir = s.data_dir.resolve()
    if data_dir.exists() and any(data_dir.iterdir()) and not force:
        raise FileExistsError(
            f"Refusing to restore into non-empty data_dir {data_dir} without force=True"
        )

    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        with tarfile.open(archive_path, "r:gz") as tf:
            # filter= suppresses unsafe path warnings on Python 3.12+
            if hasattr(tarfile, "data_filter"):
                tf.extractall(tdir, filter=tarfile.data_filter)
            else:
                tf.extractall(tdir)

        man_path = tdir / "manifest.json"
        if not man_path.is_file():
            raise ValueError("Backup missing manifest.json")
        manifest = json.loads(man_path.read_text(encoding="utf-8"))

        extracted_data = tdir / "data_dir"
        if extracted_data.is_dir():
            data_dir.mkdir(parents=True, exist_ok=True)
            for path in extracted_data.rglob("*"):
                if path.is_dir():
                    continue
                rel = path.relative_to(extracted_data)
                dest = data_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)

        db_blob = tdir / "store.sqlite"
        if db_blob.is_file():
            sqlite_path = _sqlite_path_from_url(s.database_url)
            if sqlite_path is None:
                raise ValueError(
                    "Backup contains store.sqlite but current THESEUS_DATABASE_URL is not sqlite"
                )
            dest_db = _resolve_sqlite_path(sqlite_path, data_dir=data_dir)
            dest_db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_blob, dest_db)

        logger.info(
            "restore_complete",
            archive=str(archive_path),
            manifest_database_url=manifest.get("database_url"),
        )

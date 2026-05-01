"""Nightly backfill for missing conclusion embeddings."""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from noosphere.config import get_settings
from noosphere.embedding_pipeline import _coerce_vector, _embedding_id, _text_sha256
from noosphere.embeddings import EmbeddingClient, sentence_transformers_client_from_settings
from noosphere.models import Conclusion
from noosphere.store import Store


LOGGER = logging.getLogger(__name__)
DEFAULT_BATCH_SIZE = 32
DEFAULT_MAX_PER_RUN = 1000
OPERATOR_STATE_KEY = "embedding_backfill"


@dataclass(frozen=True)
class EmbedBackfillReport:
    count: int
    elapsed_ms: int
    remaining: int
    model_name: str
    errors: list[str]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def database_url_from_env() -> str:
    explicit = os.environ.get("DATABASE_URL") or os.environ.get("THESEUS_DATABASE_URL")
    if explicit:
        return explicit
    data_dir = os.environ.get("NOOSPHERE_DATA_DIR", "").strip()
    if data_dir:
        return f"sqlite:///{Path(data_dir) / 'noosphere.db'}"
    return get_settings().database_url


def _ensure_sqlite_parent(database_url: str) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        return
    database = url.database
    if not database or database == ":memory:":
        return
    Path(database).parent.mkdir(parents=True, exist_ok=True)


def _organization_ids(store: Store) -> list[str]:
    inspector = inspect(store.engine)
    if not inspector.has_table("Organization"):
        return []
    columns = {column["name"] for column in inspector.get_columns("Organization")}
    if "id" not in columns:
        return []
    with store.engine.connect() as conn:
        rows = conn.execute(text('SELECT id FROM "Organization"')).fetchall()
    return [str(row[0]) for row in rows]


def _write_operator_status(store: Store, report: EmbedBackfillReport) -> None:
    payload = {
        "status": "failed" if report.errors else "ok",
        "count": report.count,
        "remaining": report.remaining,
        "modelName": report.model_name,
        "errors": report.errors[:5],
        "finishedAt": datetime.now(timezone.utc).isoformat(),
    }
    for organization_id in _organization_ids(store):
        try:
            store.set_operator_state(organization_id, OPERATOR_STATE_KEY, payload)
        except Exception:
            LOGGER.exception(
                "embed_backfill.operator_state_failed organization_id=%s",
                organization_id,
            )


def _chunks(items: list[Conclusion], size: int) -> list[list[Conclusion]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _embed_batch_with_backoff(
    client: EmbeddingClient,
    texts: list[str],
    *,
    max_attempts: int = 4,
) -> list[list[float]]:
    delay = 1.0
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return [_coerce_vector(vec) for vec in client.encode(texts)]
        except Exception as exc:
            last_error = exc
            if attempt == max_attempts - 1:
                break
            time.sleep(delay)
            delay = min(delay * 2.0, 30.0)
    assert last_error is not None
    raise last_error


def run_backfill(
    *,
    store: Store | None = None,
    max_per_run: int | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    client: EmbeddingClient | None = None,
) -> EmbedBackfillReport:
    started = time.monotonic()
    if store is None:
        database_url = database_url_from_env()
        _ensure_sqlite_parent(database_url)
        store = Store.from_database_url(database_url)

    max_count = (
        max_per_run
        if max_per_run is not None
        else _env_int("EMBED_BACKFILL_MAX_PER_RUN", DEFAULT_MAX_PER_RUN)
    )
    if max_count <= 0:
        max_count = DEFAULT_MAX_PER_RUN
    batch_size = max(1, batch_size)

    model_name = store.active_embedding_model_name()
    missing = store.list_conclusions_missing_embeddings(
        model_name=model_name,
        limit=max_count,
    )
    if not missing:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        report = EmbedBackfillReport(
            count=0,
            elapsed_ms=elapsed_ms,
            remaining=0,
            model_name=model_name,
            errors=[],
        )
        LOGGER.info(
            "embed_backfill.complete count=%d elapsed=%d remaining=%d",
            report.count,
            report.elapsed_ms,
            report.remaining,
        )
        _write_operator_status(store, report)
        return report

    try:
        embedder = client or sentence_transformers_client_from_settings()
    except Exception as exc:
        remaining = store.count_conclusions_missing_embeddings(model_name=model_name)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        report = EmbedBackfillReport(
            count=0,
            elapsed_ms=elapsed_ms,
            remaining=remaining,
            model_name=model_name,
            errors=[f"client:{type(exc).__name__}: {exc}"],
        )
        LOGGER.info(
            "embed_backfill.complete count=%d elapsed=%d remaining=%d",
            report.count,
            report.elapsed_ms,
            report.remaining,
        )
        _write_operator_status(store, report)
        return report

    embedded = 0
    errors: list[str] = []
    for batch in _chunks(missing, batch_size):
        texts = [item.text for item in batch]
        try:
            vectors = _embed_batch_with_backoff(embedder, texts)
        except Exception as exc:
            errors.append(f"batch:{type(exc).__name__}: {exc}")
            for item in batch:
                store.queue_embedding_retry(
                    source_kind="conclusion",
                    source_id=item.id,
                    model_name=model_name,
                    text_sha256=_text_sha256(item.text),
                    error=f"{type(exc).__name__}: {exc}",
                )
            continue

        for conclusion, vector in zip(batch, vectors):
            text_sha256 = _text_sha256(conclusion.text)
            store.put_embedding(
                embedding_id=_embedding_id("conclusion", conclusion.id, model_name),
                model_name=model_name,
                text_sha256=text_sha256,
                vector=vector,
                ref_claim_id=conclusion.id,
            )
            store.update_prisma_conclusion_embedding_json(conclusion.id, vector)
            store.clear_embedding_retry(
                source_kind="conclusion",
                source_id=conclusion.id,
                model_name=model_name,
            )
            embedded += 1

    remaining = store.count_conclusions_missing_embeddings(model_name=model_name)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    report = EmbedBackfillReport(
        count=embedded,
        elapsed_ms=elapsed_ms,
        remaining=remaining,
        model_name=model_name,
        errors=errors,
    )
    LOGGER.info(
        "embed_backfill.complete count=%d elapsed=%d remaining=%d",
        report.count,
        report.elapsed_ms,
        report.remaining,
    )
    _write_operator_status(store, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m noosphere.cli_commands.embed_backfill")
    parser.add_argument(
        "--max-per-run",
        type=int,
        default=None,
        help="Max embeddings to write this run. Defaults to EMBED_BACKFILL_MAX_PER_RUN or 1000.",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    report = run_backfill(max_per_run=args.max_per_run, batch_size=args.batch_size)
    if args.json:
        print(json.dumps(asdict(report), sort_keys=True))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Batch embedding pass: fill missing claim embeddings and persist to Store.
"""

from __future__ import annotations

import hashlib

import click
import numpy as np
from sentence_transformers import SentenceTransformer

from noosphere.config import get_settings
from noosphere.store import Store


def run_embedding_pass(
    *,
    rebuild: bool = False,
    database_url: str | None = None,
    model=None,
) -> int:
    """
    Embed all claims missing vectors (or all if ``rebuild``). Returns number embedded.
    If ``model`` is provided (SentenceTransformer), it is used; otherwise one is loaded.
    """
    settings = get_settings()
    url = database_url or settings.database_url
    store = Store.from_database_url(url)
    model_name = settings.embedding_model_name
    device = settings.embedding_device or None
    kwargs: dict = {}
    if device:
        kwargs["device"] = device
    if model is None:
        model = SentenceTransformer(model_name, **kwargs)

    if rebuild:
        store.delete_embeddings_for_model(model_name)

    ids = store.list_claim_ids()
    batch: list[str] = []
    batch_ids: list[str] = []
    total = 0

    def flush() -> None:
        nonlocal total
        if not batch:
            return
        vecs = model.encode(batch, convert_to_numpy=True, show_progress_bar=False)
        arr = np.asarray(vecs, dtype=float)
        for i, cid in enumerate(batch_ids):
            vec = arr[i].tolist()
            h = hashlib.sha256(batch[i].encode()).hexdigest()
            eid = f"emb_{model_name}_{cid}_{h[:16]}"
            store.put_embedding(
                embedding_id=eid,
                model_name=model_name,
                text_sha256=h,
                vector=vec,
                ref_claim_id=cid,
            )
            cl = store.get_claim(cid)
            if cl is not None:
                cl.embedding = vec
                store.put_claim(cl)
        total += len(batch_ids)
        batch.clear()
        batch_ids.clear()

    for cid in ids:
        cl = store.get_claim(cid)
        if cl is None:
            continue
        if cl.embedding and not rebuild:
            continue
        batch.append(cl.text)
        batch_ids.append(cid)
        if len(batch) >= 64:
            flush()
    flush()
    return total


def rebuild_embeddings_main(orch: object | None = None) -> int:
    """CLI / Typer entry: use orchestrator embedding model when provided."""
    settings = get_settings()
    model = None
    if orch is not None:
        model = orch.model
    n = run_embedding_pass(rebuild=True, database_url=settings.database_url, model=model)
    return n


@click.command("embed-pass")
@click.option("--rebuild", is_flag=True, help="Drop embeddings for current model then recompute.")
@click.option("--database-url", default=None, help="Override THESEUS_DATABASE_URL.")
def main(rebuild: bool, database_url: str | None) -> None:
    settings = get_settings()
    n = run_embedding_pass(rebuild=rebuild, database_url=database_url or settings.database_url)
    click.echo(f"Embedded {n} claims")


if __name__ == "__main__":
    main()

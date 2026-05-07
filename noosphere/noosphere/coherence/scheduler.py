"""
Coherence scheduling.

The legacy pair scheduler is retained for explicit pair-evaluation jobs. The
scaled path is the ingest-time entry point: one new proposition is embedded,
upserted into the domain-locality index, checked against its local scope plus
contradiction-probe candidates, and memoized by the exact methodology/config
that produced the report.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from noosphere.coherence.aggregator import CoherenceModelVersions
from noosphere.coherence.engine import Proposition, coherence_check_local
from noosphere.coherence.locality import DomainLocalityIndex
from noosphere.config import get_settings
from noosphere.models import Claim, CoherenceReport, Conclusion, Speaker
from noosphere.observability import get_logger
from noosphere.store import Store

logger = get_logger(__name__)

SCALED_COHERENCE_METHODOLOGY_VERSION = "scaled-coherence:v1"

DEFAULT_SCALED_LOCALITY_CFG: dict[str, Any] = {
    "k": 64,
    "radius": None,
    "include_outside_sample": 8,
    "contradiction_probe_k": 64,
    "contradiction_probe_radius": None,
}


class _NoExternalLLMClient:
    """Neutral local stand-in; prevents ambient API-key use in ingest checks."""

    def complete(self, **_kwargs: Any) -> str:
        return "0.5"


def _cosine_sim(a: list[float], b: list[float]) -> float:
    va = np.asarray(a, dtype=float)
    vb = np.asarray(b, dtype=float)
    if va.shape != vb.shape or va.size == 0:
        return -1.0
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na < 1e-12 or nb < 1e-12:
        return -1.0
    return float(np.dot(va, vb) / (na * nb))


def conclusion_to_claim(c: Conclusion) -> Claim:
    """Represent a firm conclusion as a Claim-shaped node for pairwise checks."""
    return Claim(
        id=c.id,
        text=c.text,
        speaker=Speaker(id="firm", name="firm"),
        episode_id="",
        episode_date=date.today(),
    )


def schedule_pairs_for_new_claim(
    store: Store,
    claim: Claim,
    *,
    k_neighbors: int = 20,
) -> list[tuple[str, str]]:
    """
    Return canonical (id_a, id_b) pairs to evaluate for ``claim`` (id always first = claim.id).

    Strategy:
    (a) ``k_neighbors`` nearest claims by embedding on in-memory claim payloads.
    (b) Prior claims by same speaker name on the same topic cluster.
    (c) All firm-level conclusions from the conclusion store.
    """
    if not claim.embedding:
        logger.warning("schedule_pairs_no_embedding", claim_id=claim.id)

    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_pair(other_id: str) -> None:
        if other_id == claim.id:
            return
        a, b = (claim.id, other_id) if claim.id < other_id else (other_id, claim.id)
        key = (a, b)
        if key in seen:
            return
        seen.add(key)
        pairs.append((a, b))

    # (a) Nearest neighbors by embedding
    scored: list[tuple[float, str]] = []
    for cid in store.list_claim_ids():
        if cid == claim.id:
            continue
        oc = store.get_claim(cid)
        if oc is None or not oc.embedding or not claim.embedding:
            continue
        sim = _cosine_sim(claim.embedding, oc.embedding)
        scored.append((sim, cid))
    scored.sort(key=lambda x: -x[0])
    for _, oid in scored[:k_neighbors]:
        add_pair(oid)

    # (b) Same author + same topic
    topic = store.get_topic_id_for_claim(claim.id)
    author = claim.speaker.name.strip().lower()
    if topic and author:
        for cid in store.list_claim_ids():
            if cid == claim.id:
                continue
            oc = store.get_claim(cid)
            if oc is None:
                continue
            if oc.speaker.name.strip().lower() != author:
                continue
            if store.get_topic_id_for_claim(cid) != topic:
                continue
            add_pair(cid)

    # (c) Firm conclusions
    for conc in store.list_conclusions():
        add_pair(conc.id)

    return pairs


def pair_key_sorted(id_a: str, id_b: str) -> tuple[str, str]:
    return (id_a, id_b) if id_a < id_b else (id_b, id_a)


def run_scaled_coherence_check(
    proposition: Any,
    store: Store,
    *,
    locality_cfg: dict[str, Any] | None = None,
) -> CoherenceReport:
    """Run the ingest-time scaled coherence pipeline for one proposition.

    Pipeline:
      embed/load embedding -> upsert DomainLocalityIndex -> local check
      (neighbors + outside sample + contradiction probe) -> cache report.

    ``locality_cfg`` accepts the public locality parameters plus optional
    test/operator injection points: ``index``, ``nli_engine``, ``llm_client``,
    ``enable_layers``, ``weights``, ``data_dir``, and
    ``contradiction_exemplar_pairs``.
    """
    _ensure_scaled_components_present()
    cfg = {**DEFAULT_SCALED_LOCALITY_CFG, **(locality_cfg or {})}
    log_cfg = _loggable_locality_cfg(cfg)
    started = time.perf_counter()

    index = _resolve_index(store, cfg)
    prop = _materialize_proposition(proposition, store=store, index=index)
    logger.info(
        "coherence.scaled.start",
        proposition_id=prop.id,
        locality_cfg=log_cfg,
    )

    embedding_hash = _embedding_hash(prop.embedding)
    versions = _methodology_versions()
    corpus_fingerprint = _corpus_fingerprint(index)
    cache_key = _scaled_cache_key(
        proposition_id=prop.id,
        embedding_hash=embedding_hash,
        locality_cfg=log_cfg,
        methodology_versions=versions,
        corpus_fingerprint=corpus_fingerprint,
    )
    cache_dir = _cache_dir(index=index, cfg=cfg)
    cached = _load_cached_report(cache_dir, cache_key)
    if cached is not None:
        cached.methodology = {
            **cached.methodology,
            "cache_hit": True,
            "cache_key": cache_key,
            "embedding_hash": embedding_hash,
            "scaled_methodology_version": SCALED_COHERENCE_METHODOLOGY_VERSION,
            "methodology_versions": versions,
            "locality_cfg": log_cfg,
            "corpus_fingerprint": corpus_fingerprint,
        }
        _emit_scaled_stage_logs(
            cached,
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
        return cached

    report = coherence_check_local(
        prop,
        store=store,
        k=int(cfg["k"]),
        radius=cfg.get("radius"),
        include_outside_sample=int(cfg["include_outside_sample"]),
        index=index,
        weights=cfg.get("weights"),
        nli_engine=cfg.get("nli_engine"),
        enable_layers=cfg.get("enable_layers"),
        llm_client=cfg.get("llm_client", _NoExternalLLMClient()),
        contradiction_probe_k=int(cfg["contradiction_probe_k"]),
        contradiction_probe_radius=cfg.get("contradiction_probe_radius"),
        contradiction_exemplar_pairs=cfg.get("contradiction_exemplar_pairs"),
    )
    report.methodology = {
        **report.methodology,
        "cache_hit": False,
        "cache_key": cache_key,
        "embedding_hash": embedding_hash,
        "scaled_methodology_version": SCALED_COHERENCE_METHODOLOGY_VERSION,
        "methodology_versions": versions,
        "locality_cfg": log_cfg,
        "corpus_fingerprint": corpus_fingerprint,
    }
    _store_cached_report(cache_dir, cache_key, report)
    _emit_scaled_stage_logs(
        report,
        duration_ms=(time.perf_counter() - started) * 1000.0,
    )
    return report


def _ensure_scaled_components_present() -> None:
    coherence_dir = Path(__file__).resolve().parent
    required = [
        coherence_dir / "locality.py",
        coherence_dir.parent / "methods" / "contradiction_probe.py",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Scaled coherence requires prompt 05/06 artifacts; missing: "
            + ", ".join(missing)
        )


def _resolve_index(store: Store, cfg: dict[str, Any]) -> Any:
    supplied = cfg.get("index")
    if supplied is not None:
        return supplied

    index_kwargs: dict[str, Any] = {"store": store}
    for key in (
        "data_dir",
        "space",
        "dim",
        "m",
        "ef_construction",
        "ef_search",
        "random_seed",
        "autosave",
    ):
        if key in cfg:
            index_kwargs[key] = cfg[key]
    return DomainLocalityIndex(**index_kwargs)


def _materialize_proposition(
    proposition: Any,
    *,
    store: Store,
    index: Any,
) -> Proposition:
    pid = str(getattr(proposition, "id", "") or "")
    text = str(getattr(proposition, "text", "") or "")
    if not pid or not text:
        raise ValueError("run_scaled_coherence_check requires proposition.id and text")

    vector = getattr(proposition, "embedding", None)
    if vector is None and hasattr(index, "vector_for"):
        vector = index.vector_for(pid)
    if vector is None:
        _embed_missing_proposition(proposition, store=store)
        if hasattr(index, "rebuild_from_store"):
            try:
                index.rebuild_from_store(store)
            except Exception:
                pass
        if hasattr(index, "vector_for"):
            vector = index.vector_for(pid)
    if vector is None:
        raise ValueError(
            f"Scaled coherence requires an embedding for proposition {pid!r}"
        )

    arr = np.asarray(vector, dtype=float).reshape(-1)
    if arr.size == 0 or not np.all(np.isfinite(arr)):
        raise ValueError(f"Invalid embedding for proposition {pid!r}")
    if hasattr(index, "upsert"):
        index.upsert(pid, arr)

    conviction = float(getattr(proposition, "confidence", 0.5) or 0.5)
    return Proposition(id=pid, text=text, embedding=arr, conviction_score=conviction)


def _embed_missing_proposition(proposition: Any, *, store: Store) -> None:
    text = str(getattr(proposition, "text", "") or "").strip()
    pid = str(getattr(proposition, "id", "") or "")
    if not text or not pid:
        return
    if isinstance(proposition, Claim):
        source_kind = "claim"
    elif isinstance(proposition, Conclusion):
        source_kind = "conclusion"
    else:
        source_kind = "claim"
    try:
        from noosphere.embedding_pipeline import embed_text_and_store_with_store

        embed_text_and_store_with_store(
            store,
            source_kind=source_kind,
            source_id=pid,
            text=text,
        )
    except Exception as exc:
        logger.warning(
            "coherence.scaled.embedding_failed",
            proposition_id=pid,
            error=str(exc),
        )


def _embedding_hash(embedding: Any) -> str:
    arr = np.asarray(embedding, dtype=np.float32).reshape(-1)
    blob = hashlib.sha256()
    blob.update(str(arr.shape).encode("utf-8"))
    blob.update(arr.tobytes())
    return blob.hexdigest()


def _methodology_versions() -> dict[str, Any]:
    return {
        "scaled_scheduler": SCALED_COHERENCE_METHODOLOGY_VERSION,
        "domain_locality_index": "metadata-v1",
        "contradiction_probe": "1.0.0",
        "six_layer_engine": CoherenceModelVersions.from_settings().to_json(),
    }


def _loggable_locality_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    omitted = {
        "index",
        "nli_engine",
        "llm_client",
        "weights",
        "contradiction_exemplar_pairs",
    }
    out: dict[str, Any] = {}
    for key, value in cfg.items():
        if key in omitted:
            if value is not None:
                out[key] = _object_marker(value)
            continue
        out[key] = _jsonable(value)
    return out


def _object_marker(value: Any) -> str:
    return f"{type(value).__module__}.{type(value).__qualname__}"


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(_jsonable(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(val) for key, val in sorted(value.items())}
    if isinstance(value, np.ndarray):
        return {
            "shape": list(value.shape),
            "sha256": _embedding_hash(value),
        }
    return _object_marker(value)


def _stable_json(data: Any) -> str:
    return json.dumps(_jsonable(data), sort_keys=True, separators=(",", ":"))


def _corpus_fingerprint(index: Any) -> str:
    parts = {
        "backend": getattr(index, "backend", None),
        "ids": [],
    }
    try:
        parts["ids"] = list(getattr(index, "ids", []))
    except Exception:
        parts["ids"] = []
    for attr in ("metadata_path", "index_path", "vectors_path"):
        path = getattr(index, attr, None)
        if path is None:
            continue
        try:
            stat = Path(path).stat()
        except OSError:
            parts[attr] = {"exists": False}
        else:
            parts[attr] = {
                "exists": True,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
    return hashlib.sha256(_stable_json(parts).encode("utf-8")).hexdigest()


def _scaled_cache_key(
    *,
    proposition_id: str,
    embedding_hash: str,
    locality_cfg: dict[str, Any],
    methodology_versions: dict[str, Any],
    corpus_fingerprint: str,
) -> str:
    payload = {
        "proposition_id": proposition_id,
        "embedding_hash": embedding_hash,
        "locality_cfg": locality_cfg,
        "methodology_versions": methodology_versions,
        "corpus_fingerprint": corpus_fingerprint,
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _cache_dir(*, index: Any, cfg: dict[str, Any]) -> Path:
    root = getattr(index, "root", None)
    if root is not None:
        return Path(root) / "scaled_reports"
    if cfg.get("data_dir") is not None:
        return Path(cfg["data_dir"]) / "coherence" / "scaled_reports"
    return get_settings().data_dir / "coherence" / "scaled_reports"


def _load_cached_report(cache_dir: Path, cache_key: str) -> CoherenceReport | None:
    path = cache_dir / f"{cache_key}.json"
    if not path.is_file():
        return None
    try:
        return CoherenceReport.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(
            "coherence.scaled.cache_read_failed",
            cache_key=cache_key,
            error=str(exc),
        )
        return None


def _store_cached_report(
    cache_dir: Path,
    cache_key: str,
    report: CoherenceReport,
) -> None:
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{cache_key}.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning(
            "coherence.scaled.cache_write_failed",
            cache_key=cache_key,
            error=str(exc),
        )


def _emit_scaled_stage_logs(report: CoherenceReport, *, duration_ms: float) -> None:
    methodology = report.methodology or {}
    local_ids = list(methodology.get("local_ids") or [])
    outside_ids = list(methodology.get("outside_sample_ids") or [])
    logger.info(
        "coherence.locality.neighbors",
        k_local=len(local_ids),
        k_outside=len(outside_ids),
    )

    probe = methodology.get("contradiction_probe") or {}
    probe_candidates = list(probe.get("candidates") or [])
    mean_predicted_distance = probe.get("mean_predicted_distance")
    if mean_predicted_distance is None and probe_candidates:
        distances = [
            float(row["predicted_distance"])
            for row in probe_candidates
            if isinstance(row, dict) and row.get("predicted_distance") is not None
        ]
        mean_predicted_distance = (
            float(sum(distances) / len(distances)) if distances else None
        )
    logger.info(
        "coherence.probe.candidates",
        count=len(probe.get("candidate_ids") or []),
        mean_predicted_distance=mean_predicted_distance,
    )

    logger.info(
        "coherence.verify.layers",
        per_layer=_layer_pass_fail_counts(report),
    )
    logger.info(
        "coherence.scaled.complete",
        duration_ms=duration_ms,
        contradictions_found=len(report.contradictions_found),
        tentative_contradictions_found=len(report.tentative_contradictions),
    )


def _layer_pass_fail_counts(report: CoherenceReport) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for layer_name, raw_score in (report.layer_scores or {}).items():
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 0.0
        counts[str(layer_name)] = {
            "pass": 1 if score >= 0.5 else 0,
            "fail": 0 if score >= 0.5 else 1,
        }
    return counts

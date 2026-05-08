"""Live argument-map builder.

Consumes finalized utterances from the transcriber, extracts atomic
claims, links them to existing nodes via NLI (supports / contradicts /
refines / asks_about), and exposes a thread-safe snapshot for the UI
and exporter.

Design constraints
------------------
* The builder runs on its own worker thread driven by a bounded queue,
  so a slow LLM/NLI call cannot stall the transcribe loop. When the
  queue saturates, the *oldest pending* utterance is dropped (a
  back-pressure signal that's preferable to blocking the caller —
  the live transcript is the ground truth, the map is best-effort).
* Node deduplication uses embedding similarity, not string compare.
  Threshold and other tunables come from a config object loadable from
  ``DIALECTIC_ARGUMENT_MAP_CONFIG`` (TOML).
* All heavy collaborators (claim extractor, embedder, NLI) are
  injectable so tests can run without LLMs / network / Qt.

The builder is pure-Python (no Qt imports) so it can be unit-tested
headlessly. The UI widget subscribes via the ``on_event`` callback.
"""

from __future__ import annotations

import json
import logging
import math
import os
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

log = logging.getLogger(__name__)


# ── relation vocabulary ────────────────────────────────────────────────
RELATION_SUPPORTS = "supports"
RELATION_CONTRADICTS = "contradicts"
RELATION_REFINES = "refines"
RELATION_ASKS_ABOUT = "asks_about"
RELATIONS = (
    RELATION_SUPPORTS,
    RELATION_CONTRADICTS,
    RELATION_REFINES,
    RELATION_ASKS_ABOUT,
)


# ── data classes ───────────────────────────────────────────────────────


@dataclass
class Utterance:
    """One finalized turn of speech."""

    text: str
    speaker: str = "unknown"
    t_start: float = 0.0
    t_end: float = 0.0
    turn_index: int = 0


@dataclass
class ArgumentNode:
    node_id: str
    text: str
    speaker: str
    claim_type: str  # empirical | normative | methodological | predictive | definitional | question
    turn_index: int
    embedding: list[float] = field(default_factory=list)
    is_question: bool = False
    state: str = "active"  # active | amber | red | answered
    seen_count: int = 1
    pulse_until: float = 0.0  # epoch seconds; UI uses to draw the highlight
    last_seen_turn: int = 0


@dataclass
class ArgumentEdge:
    edge_id: str
    src: str  # the new claim
    dst: str  # the existing claim it relates to
    relation: str
    confidence: float
    turn_index: int


@dataclass
class DriftReading:
    turn_index: int
    drift: float
    flagged: bool


@dataclass
class BuilderConfig:
    """Tunables loaded from TOML so threshold sweeps don't need a redeploy."""

    dedup_similarity: float = 0.86
    nli_supports_threshold: float = 0.55
    nli_contradicts_threshold: float = 0.55
    nli_refines_overlap: float = 0.40
    drift_window: int = 8
    drift_threshold: float = 0.55
    unresolved_K_turns: int = 5
    queue_maxsize: int = 128
    pulse_seconds: float = 1.5
    max_links_per_claim: int = 3

    @classmethod
    def load(cls, path: str | Path | None = None) -> "BuilderConfig":
        """Load from a TOML file. Missing keys fall back to dataclass defaults."""

        p = Path(path) if path else None
        if p is None:
            env = os.environ.get("DIALECTIC_ARGUMENT_MAP_CONFIG")
            if env:
                p = Path(env)
        if p is None or not p.exists():
            return cls()
        try:
            try:
                import tomllib  # py311+
            except ImportError:  # pragma: no cover
                import tomli as tomllib  # type: ignore
            data = tomllib.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # pragma: no cover - defensive
            log.warning("argument_map config %s unreadable: %s", p, e)
            return cls()
        # Accept either flat or [argument_map] section.
        if "argument_map" in data and isinstance(data["argument_map"], dict):
            data = data["argument_map"]
        kwargs = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**kwargs)


# ── default extractor / embedder / NLI (heuristic, dependency-free) ────


_QUESTION_RE = re.compile(r"\?\s*$|^(who|what|when|where|why|how|is|are|do|does|did|should|could|would|can|will)\b", re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOPWORDS = frozenset(
    "a an and are as at be but by for from has have if in is it its of on or so that the to was were will with you your i we they he she them do does did this these those not no yes about into over under again very just".split()
)


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text) if t.lower() not in _STOPWORDS]


def heuristic_extract_claims(utterance: Utterance) -> list[dict]:
    """Sentence-level fallback extractor. Used when no LLM is wired in.

    Splits on sentence boundaries; each non-trivial sentence becomes one
    claim. Question sentences are tagged for the asks_about relation.
    """

    out: list[dict] = []
    raw = (utterance.text or "").strip()
    if not raw:
        return out
    for sent in _SENTENCE_SPLIT.split(raw):
        s = sent.strip()
        if len(s) < 4:
            continue
        is_q = bool(_QUESTION_RE.search(s)) or s.endswith("?")
        out.append(
            {
                "text": s,
                "claim_type": "question" if is_q else "empirical",
                "is_question": is_q,
            }
        )
    return out


def heuristic_embed(text: str, *, dim: int = 64) -> list[float]:
    """Hashed-bag-of-words embedding. Deterministic, no deps.

    Sufficient for dedup of paraphrases that share most content words.
    Replace via injection when sentence-transformers is available.
    """

    vec = [0.0] * dim
    toks = _tokens(text)
    if not toks:
        return vec
    for tok in toks:
        h = hash(tok) % dim
        vec[h] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


_NEGATION_RE = re.compile(r"\b(not|no|never|n't|cannot|isn't|aren't|wasn't|weren't|don't|doesn't|didn't)\b", re.IGNORECASE)


def heuristic_nli(claim_a: str, claim_b: str) -> dict:
    """Cheap NLI proxy: token overlap + negation polarity.

    Returns probabilities for {entailment, contradiction, neutral}.
    Replace via injection when the noosphere nli_scorer or a transformer
    is available.
    """

    ta = set(_tokens(claim_a))
    tb = set(_tokens(claim_b))
    if not ta or not tb:
        return {"entailment": 0.0, "contradiction": 0.0, "neutral": 1.0}
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    neg_a = bool(_NEGATION_RE.search(claim_a))
    neg_b = bool(_NEGATION_RE.search(claim_b))
    polarity_clash = neg_a ^ neg_b
    if overlap >= 0.4 and polarity_clash:
        return {"entailment": 0.0, "contradiction": 0.6 + 0.3 * overlap, "neutral": max(0.0, 0.4 - 0.3 * overlap)}
    if overlap >= 0.4:
        return {"entailment": 0.4 + 0.4 * overlap, "contradiction": 0.0, "neutral": max(0.0, 0.6 - 0.4 * overlap)}
    return {"entailment": 0.1 * overlap, "contradiction": 0.0, "neutral": 1.0 - 0.1 * overlap}


# ── builder ────────────────────────────────────────────────────────────


_SENTINEL: Any = object()


@dataclass
class BuilderEvent:
    """One change in the live map. Streamed to UI subscribers."""

    kind: str  # node_added | node_updated | edge_added | drift | unresolved
    payload: dict


class ArgumentMapBuilder:
    """Thread-safe live builder.

    Usage:
        builder = ArgumentMapBuilder(config=BuilderConfig.load(),
                                     on_event=widget.on_event)
        builder.start()
        for utterance in stream:
            builder.submit(utterance)
        builder.stop()
        markdown = builder.export_markdown()
    """

    def __init__(
        self,
        *,
        config: Optional[BuilderConfig] = None,
        extractor: Optional[Callable[[Utterance], list[dict]]] = None,
        embedder: Optional[Callable[[str], list[float]]] = None,
        nli: Optional[Callable[[str, str], dict]] = None,
        on_event: Optional[Callable[[BuilderEvent], None]] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.config = config or BuilderConfig()
        self._extract = extractor or heuristic_extract_claims
        self._embed = embedder or heuristic_embed
        self._nli = nli or heuristic_nli
        self._on_event = on_event
        self._clock = clock or time.time

        self._nodes: dict[str, ArgumentNode] = {}
        self._edges: list[ArgumentEdge] = []
        self._drift: list[DriftReading] = []
        self._utterances: list[Utterance] = []  # kept for transcript fallback
        self._turn_count = 0

        self._lock = threading.RLock()
        self._queue: "queue.Queue[Any]" = queue.Queue(maxsize=self.config.queue_maxsize)
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # ── lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker, name="argmap-builder", daemon=True
        )
        self._thread.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        if not self._running:
            return
        self._running = False
        try:
            self._queue.put_nowait(_SENTINEL)
        except queue.Full:
            # drop one to make room for the sentinel
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(_SENTINEL)
            except queue.Full:
                pass
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    # ── ingress ───────────────────────────────────────────────────────

    def submit(self, utterance: Utterance) -> bool:
        """Enqueue an utterance for processing. Non-blocking.

        Returns True if accepted, False if dropped due to back-pressure.
        Drops the OLDEST pending item rather than the new one — newer
        context is more useful for a live map.
        """

        try:
            self._queue.put_nowait(utterance)
            return True
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(utterance)
                return True
            except queue.Full:
                return False

    def process_now(self, utterance: Utterance) -> None:
        """Synchronous processing path — used by tests and the ingester
        replay codepath where we don't want a thread."""

        self._handle_utterance(utterance)

    # ── snapshot / export ─────────────────────────────────────────────

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "nodes": [asdict(n) for n in self._nodes.values()],
                "edges": [asdict(e) for e in self._edges],
                "drift": [asdict(d) for d in self._drift],
                "turn_count": self._turn_count,
            }

    def nodes(self) -> list[ArgumentNode]:
        with self._lock:
            return list(self._nodes.values())

    def edges(self) -> list[ArgumentEdge]:
        with self._lock:
            return list(self._edges)

    def drift_readings(self) -> list[DriftReading]:
        with self._lock:
            return list(self._drift)

    def utterances(self) -> list[Utterance]:
        with self._lock:
            return list(self._utterances)

    # ── worker loop ───────────────────────────────────────────────────

    def _worker(self) -> None:
        while self._running:
            try:
                item = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if item is _SENTINEL:
                break
            try:
                self._handle_utterance(item)
            except Exception as e:  # pragma: no cover - defensive
                log.exception("argument_map worker error: %s", e)

    # ── core processing ──────────────────────────────────────────────

    def _handle_utterance(self, utterance: Utterance) -> None:
        with self._lock:
            self._turn_count += 1
            turn = self._turn_count
            ut = Utterance(
                text=utterance.text,
                speaker=utterance.speaker,
                t_start=utterance.t_start,
                t_end=utterance.t_end,
                turn_index=turn,
            )
            self._utterances.append(ut)

        try:
            extracted = list(self._extract(ut))
        except Exception as e:
            log.warning("extractor failed: %s", e)
            extracted = heuristic_extract_claims(ut)

        for item in extracted:
            self._ingest_claim(item, ut)

        # Update unresolved-question states whenever the turn count moves.
        self._refresh_unresolved(turn)

    def _ingest_claim(self, item: dict, ut: Utterance) -> None:
        text = (item.get("text") or "").strip()
        if not text:
            return
        is_q = bool(item.get("is_question")) or text.endswith("?")
        claim_type = item.get("claim_type") or ("question" if is_q else "empirical")
        try:
            embedding = list(self._embed(text))
        except Exception:
            embedding = heuristic_embed(text)

        with self._lock:
            existing_id = self._find_dup(text, embedding)
            if existing_id is not None:
                node = self._nodes[existing_id]
                node.seen_count += 1
                node.last_seen_turn = ut.turn_index
                node.pulse_until = self._clock() + self.config.pulse_seconds
                # If the question is being re-asked, leave its state.
                # If it was unresolved (amber/red) and someone repeats it,
                # we don't auto-answer — that's still asking.
                self._emit(BuilderEvent("node_updated", asdict(node)))
                self._update_drift_locked(embedding, ut.turn_index)
                return

            nid = uuid.uuid4().hex[:12]
            node = ArgumentNode(
                node_id=nid,
                text=text,
                speaker=ut.speaker,
                claim_type=claim_type,
                turn_index=ut.turn_index,
                embedding=embedding,
                is_question=is_q,
                state="active",
                pulse_until=self._clock() + self.config.pulse_seconds,
                last_seen_turn=ut.turn_index,
            )
            self._nodes[nid] = node
            self._emit(BuilderEvent("node_added", asdict(node)))

            self._link_locked(node)

            # Answering: a non-question claim with high entailment/overlap
            # to a prior unresolved question marks that question answered.
            if not is_q:
                self._mark_answered_locked(node)

            self._update_drift_locked(embedding, ut.turn_index)

    # ── deduplication ────────────────────────────────────────────────

    def _find_dup(self, text: str, embedding: list[float]) -> Optional[str]:
        # Exact text match short-circuit (also catches the "no embedder" case).
        norm = text.strip().lower()
        for nid, node in self._nodes.items():
            if node.text.strip().lower() == norm:
                return nid
        if not embedding:
            return None
        best_id = None
        best_sim = 0.0
        for nid, node in self._nodes.items():
            if not node.embedding:
                continue
            sim = cosine(embedding, node.embedding)
            if sim > best_sim:
                best_sim = sim
                best_id = nid
        if best_id is not None and best_sim >= self.config.dedup_similarity:
            return best_id
        return None

    # ── linking ──────────────────────────────────────────────────────

    def _link_locked(self, node: ArgumentNode) -> None:
        """Attach the new node to existing claims. Uses NLI for
        supports/contradicts; uses asks_about when the node is a
        question; falls back to refines for high-overlap, non-polar
        statements."""

        if not self._nodes:
            return

        candidates: list[tuple[str, ArgumentNode, float]] = []
        for nid, other in self._nodes.items():
            if nid == node.node_id:
                continue
            sim = cosine(node.embedding, other.embedding) if node.embedding and other.embedding else 0.0
            candidates.append((nid, other, sim))
        candidates.sort(key=lambda t: t[2], reverse=True)
        # Look at the few most-similar prior claims; full pairwise NLI is
        # too costly when the map gets large.
        top = candidates[: max(1, self.config.max_links_per_claim * 2)]

        added = 0
        for nid, other, sim in top:
            if added >= self.config.max_links_per_claim:
                break
            relation: Optional[str] = None
            confidence = 0.0
            if node.is_question:
                # Questions only attach via asks_about, and only when there
                # is at least topical overlap.
                if sim >= self.config.nli_refines_overlap:
                    relation = RELATION_ASKS_ABOUT
                    confidence = sim
            else:
                try:
                    scores = self._nli(node.text, other.text)
                except Exception:
                    scores = heuristic_nli(node.text, other.text)
                ent = float(scores.get("entailment", 0.0))
                con = float(scores.get("contradiction", 0.0))
                if con >= self.config.nli_contradicts_threshold and con > ent:
                    relation = RELATION_CONTRADICTS
                    confidence = con
                elif ent >= self.config.nli_supports_threshold:
                    relation = RELATION_SUPPORTS
                    confidence = ent
                elif sim >= self.config.nli_refines_overlap and other.claim_type == node.claim_type:
                    relation = RELATION_REFINES
                    confidence = sim
            if relation is None:
                continue
            edge = ArgumentEdge(
                edge_id=uuid.uuid4().hex[:12],
                src=node.node_id,
                dst=nid,
                relation=relation,
                confidence=float(confidence),
                turn_index=node.turn_index,
            )
            self._edges.append(edge)
            self._emit(BuilderEvent("edge_added", asdict(edge)))
            added += 1

    # ── unresolved-question tracking ─────────────────────────────────

    def _mark_answered_locked(self, node: ArgumentNode) -> None:
        """If this new claim addresses an open question, flip the
        question to ``answered``. We treat any incoming edge from a
        non-question to a question as an answer."""

        for edge in self._edges:
            if edge.src != node.node_id:
                continue
            tgt = self._nodes.get(edge.dst)
            if tgt is None or not tgt.is_question:
                continue
            if edge.relation in (RELATION_SUPPORTS, RELATION_REFINES):
                if tgt.state in ("active", "amber", "red"):
                    tgt.state = "answered"
                    self._emit(BuilderEvent("node_updated", asdict(tgt)))

    def _refresh_unresolved(self, turn: int) -> None:
        K = self.config.unresolved_K_turns
        with self._lock:
            for node in self._nodes.values():
                if not node.is_question:
                    continue
                if node.state == "answered":
                    continue
                age = turn - node.turn_index
                new_state = node.state
                if age >= 2 * K:
                    new_state = "red"
                elif age >= K:
                    new_state = "amber"
                else:
                    new_state = "active"
                if new_state != node.state:
                    node.state = new_state
                    self._emit(BuilderEvent("unresolved", asdict(node)))

    # ── drift ────────────────────────────────────────────────────────

    def _update_drift_locked(self, embedding: list[float], turn: int) -> None:
        if not embedding:
            return
        # Recent center = mean of the last W claim embeddings (excluding
        # the new one — drift is its distance to the prior center).
        recent = [n.embedding for n in list(self._nodes.values())[-self.config.drift_window - 1 : -1] if n.embedding]
        if not recent:
            return
        dim = len(embedding)
        center = [0.0] * dim
        for vec in recent:
            for i in range(min(dim, len(vec))):
                center[i] += vec[i]
        center = [c / len(recent) for c in center]
        sim = cosine(embedding, center)
        drift = max(0.0, 1.0 - sim)
        flagged = drift >= self.config.drift_threshold
        reading = DriftReading(turn_index=turn, drift=drift, flagged=flagged)
        self._drift.append(reading)
        self._emit(BuilderEvent("drift", asdict(reading)))

    # ── event fan-out ────────────────────────────────────────────────

    def _emit(self, event: BuilderEvent) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event)
        except Exception as e:  # pragma: no cover - defensive
            log.warning("argument_map subscriber raised: %s", e)


# ── exports facade (thin convenience wrappers) ────────────────────────


def builder_from_settings(
    *,
    extractor: Optional[Callable[[Utterance], list[dict]]] = None,
    embedder: Optional[Callable[[str], list[float]]] = None,
    nli: Optional[Callable[[str, str], dict]] = None,
    on_event: Optional[Callable[[BuilderEvent], None]] = None,
) -> ArgumentMapBuilder:
    """Construct a builder using the configured TOML (if any).

    Production callers should pass real LLM-backed callables; if they
    pass nothing, the heuristic fallbacks keep the map functional but
    coarser.
    """

    return ArgumentMapBuilder(
        config=BuilderConfig.load(),
        extractor=extractor,
        embedder=embedder,
        nli=nli,
        on_event=on_event,
    )


__all__ = [
    "ArgumentEdge",
    "ArgumentMapBuilder",
    "ArgumentNode",
    "BuilderConfig",
    "BuilderEvent",
    "DriftReading",
    "RELATIONS",
    "RELATION_ASKS_ABOUT",
    "RELATION_CONTRADICTS",
    "RELATION_REFINES",
    "RELATION_SUPPORTS",
    "Utterance",
    "builder_from_settings",
    "cosine",
    "heuristic_embed",
    "heuristic_extract_claims",
    "heuristic_nli",
]

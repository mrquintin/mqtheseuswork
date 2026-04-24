"""Real-time analysis engine — contradictions, topics, open loops, questions."""

from __future__ import annotations

import asyncio
import logging
import queue
import re
import time
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import numpy as np

from .config import AnalysisConfig
from .transcriber import TranscriptSegment, TranscriptionEvent

log = logging.getLogger(__name__)


# ======================================================================
# Data types for analysis results
# ======================================================================

@dataclass
class Contradiction:
    statement_a: str
    statement_b: str
    score: float               # 0–1 confidence
    timestamp: float           # when detected
    speaker_a: str = ""
    speaker_b: str = ""


@dataclass
class TopicState:
    current_topic: str         # short label for the current cluster
    keywords: list[str]        # representative keywords
    on_topic: bool             # whether recent utterances are aligned
    drift_direction: str = ""  # description of where conversation is drifting
    timestamp: float = 0.0


@dataclass
class OpenLoop:
    """A topic or question that was raised but left unresolved."""
    description: str
    opened_at: float           # timestamp
    last_referenced: float
    status: str = "open"       # "open" | "closing" | "abandoned"
    related_text: str = ""


@dataclass
class SuggestedQuestion:
    text: str
    rationale: str             # why this question is relevant now
    category: str = ""         # "deepening" | "contradiction" | "open_loop" | "pivot"
    timestamp: float = 0.0


# ======================================================================
# Main Analyzer
# ======================================================================

class LiveAnalyzer:
    """
    Receives transcript segments and produces real-time analysis.

    All heavy computation runs in background threads so the UI stays
    responsive.  Results are delivered via callbacks.
    """

    def __init__(
        self,
        config: AnalysisConfig,
        on_contradiction: Callable[[Contradiction], None] | None = None,
        on_topic_update: Callable[[TopicState], None] | None = None,
        on_open_loop: Callable[[OpenLoop], None] | None = None,
        on_question: Callable[[SuggestedQuestion], None] | None = None,
    ):
        self.cfg = config

        # Callbacks
        self._on_contradiction = on_contradiction
        self._on_topic_update = on_topic_update
        self._on_open_loop = on_open_loop
        self._on_question = on_question

        # State. ``_segments`` and ``_embeddings`` are append-only parallel
        # lists — index i in one corresponds to index i in the other. They
        # are only mutated by the single ``_worker_thread`` below, so readers
        # take ``_lock`` for atomic snapshots and writes happen without
        # contention from other analysis tasks.
        self._segments: list[TranscriptSegment] = []
        self._embeddings: list[np.ndarray | None] = []
        self._open_loops: list[OpenLoop] = []
        self._topic_history: list[TopicState] = []
        self._last_question_time: float = 0.0
        self._lock = threading.Lock()
        self._running = False

        # Single-consumer work queue. Previously ``feed_segment`` spawned a
        # fresh thread per segment, which in turn appended to
        # ``_embeddings`` in whatever order those threads happened to
        # finish — misaligning the segment/embedding indices so DBSCAN /
        # topic windows could silently operate on the wrong utterances.
        # Serializing on one worker eliminates that race and keeps per-
        # segment CPU bounded even under bursts.
        self._work_q: queue.Queue[TranscriptSegment | None] = queue.Queue()
        self._worker_thread: threading.Thread | None = None

        self._nli_model = None
        self._embedder = None
        self._anthropic = None

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._load_models, daemon=True).start()
        self._worker_thread = threading.Thread(
            target=self._worker_loop, name="LiveAnalyzer-worker", daemon=True
        )
        self._worker_thread.start()

    def stop(self) -> None:
        self._running = False
        # Poison pill so the worker unblocks from ``queue.get`` and exits.
        try:
            self._work_q.put_nowait(None)
        except queue.Full:
            pass

    def feed_segment(self, segment: TranscriptSegment) -> None:
        """Enqueue a segment for analysis on the worker thread."""
        if not self._running:
            return
        try:
            self._work_q.put_nowait(segment)
        except queue.Full:
            log.warning("LiveAnalyzer: work queue full, dropping segment")

    def _worker_loop(self) -> None:
        while self._running:
            try:
                item = self._work_q.get(timeout=0.25)
            except queue.Empty:
                continue
            if item is None:
                return
            try:
                self._analyze_segment(item)
            except Exception as e:
                log.warning("LiveAnalyzer: analysis failed for a segment: %s", e)

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_models(self) -> None:
        """Load NLI + embedding models.  Called once at start."""
        try:
            from sentence_transformers import CrossEncoder, SentenceTransformer

            self._nli_model = CrossEncoder(self.cfg.nli_model)
            self._embedder = SentenceTransformer(self.cfg.embedding_model)
        except Exception:
            pass  # models unavailable — analyses degrade gracefully

        if self.cfg.anthropic_key:
            try:
                import anthropic
                self._anthropic = anthropic.Anthropic(api_key=self.cfg.anthropic_key)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Per-segment analysis
    # ------------------------------------------------------------------

    def _analyze_segment(self, segment: TranscriptSegment) -> None:
        """Run all analysis pipelines on a new segment.

        Invariant: segments and embeddings are appended together under the
        lock so that ``_segments[i]`` always pairs with ``_embeddings[i]``.
        This is what the DBSCAN / topic-window math assumes.
        """
        if not self._running:
            return

        embedding = self._embed(segment.text)
        with self._lock:
            self._segments.append(segment)
            self._embeddings.append(embedding)

        self._check_contradictions(segment)
        self._update_topics(segment, embedding)
        self._check_open_loops(segment, embedding)

        now = time.time()
        if now - self._last_question_time >= self.cfg.question_interval_seconds:
            self._generate_questions(segment)
            self._last_question_time = now

    # ------------------------------------------------------------------
    # 1. Contradiction detection
    # ------------------------------------------------------------------

    def _check_contradictions(self, segment: TranscriptSegment) -> None:
        if self._nli_model is None:
            return

        with self._lock:
            history = list(self._segments[:-1])  # everything before this segment

        window = history[-8:]
        if not window:
            return

        # Build `pairs` and a *parallel* list of the source segments so
        # filtered-out empties can't desynchronize the two. Previously we
        # used `window[i]` keyed by the score index, but `window` still
        # contained the empty-text entries that `pairs` had dropped — so
        # an empty slot anywhere in the window shifted every subsequent
        # attribution by one, pairing contradiction scores with the wrong
        # utterance.
        pair_segments: list[TranscriptSegment] = []
        pairs: list[tuple[str, str]] = []
        for prev in window:
            if not prev.text.strip():
                continue
            pair_segments.append(prev)
            pairs.append((prev.text, segment.text))
        if not pairs:
            return

        try:
            scores = self._nli_model.predict(pairs)
        except Exception as e:
            log.warning("LiveAnalyzer: NLI predict failed: %s", e)
            return

        for i, score_row in enumerate(scores):
            if hasattr(score_row, "__len__"):
                contradiction_score = float(score_row[0])
            else:
                contradiction_score = float(score_row)

            if contradiction_score > self.cfg.contradiction_threshold:
                prev_seg = pair_segments[i]
                c = Contradiction(
                    statement_a=prev_seg.text,
                    statement_b=segment.text,
                    score=contradiction_score,
                    timestamp=segment.start_time,
                    speaker_a=prev_seg.speaker,
                    speaker_b=segment.speaker,
                )
                if self._on_contradiction:
                    try:
                        self._on_contradiction(c)
                    except Exception as e:
                        log.warning(
                            "LiveAnalyzer: on_contradiction callback raised: %s", e
                        )

    # ------------------------------------------------------------------
    # 2. Topic tracking
    # ------------------------------------------------------------------

    def _update_topics(
        self, segment: TranscriptSegment, embedding: np.ndarray | None
    ) -> None:
        if embedding is None or self._embedder is None:
            return

        with self._lock:
            n_segments = len(self._segments)
            all_embeddings = list(self._embeddings)
            all_segs = list(self._segments)

        if n_segments % self.cfg.topic_recluster_every != 0:
            return

        # Window from the tail, then drop any slots where embedding failed.
        # Previously any ``None`` in the window would crash ``np.array``.
        tail_embs = all_embeddings[-self.cfg.topic_window_size:]
        tail_segs = all_segs[-self.cfg.topic_window_size:]
        window_embs = [e for e in tail_embs if e is not None]
        window_segs = [s for s, e in zip(tail_segs, tail_embs) if e is not None]
        if len(window_embs) < 4:
            return

        try:
            from sklearn.cluster import DBSCAN
            from collections import Counter
            import re

            emb_matrix = np.array(window_embs)
            # Normalise for cosine-like DBSCAN
            norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1
            emb_normed = emb_matrix / norms

            clustering = DBSCAN(
                eps=self.cfg.topic_eps,
                min_samples=self.cfg.topic_min_samples,
                metric="cosine",
            ).fit(emb_normed)

            labels = clustering.labels_

            # Find the cluster the latest segment belongs to
            latest_label = labels[-1]

            # Determine if on-topic: is the latest in the same cluster as the majority?
            recent_labels = labels[-6:]
            from collections import Counter

            label_counts = Counter(l for l in recent_labels if l != -1)
            if not label_counts:
                dominant = -1
            else:
                dominant = label_counts.most_common(1)[0][0]

            on_topic = latest_label == dominant and latest_label != -1

            # Extract keywords for the dominant cluster
            cluster_texts = [
                window_segs[i].text
                for i in range(len(labels))
                if labels[i] == dominant and dominant != -1
            ]
            keywords = self._extract_keywords(cluster_texts)

            topic_label = ", ".join(keywords[:3]) if keywords else "undetermined"

            # Detect drift
            drift = ""
            if not on_topic and latest_label != -1:
                drift_texts = [
                    window_segs[i].text
                    for i in range(len(labels))
                    if labels[i] == latest_label
                ]
                drift_kw = self._extract_keywords(drift_texts)
                drift = f"drifting toward: {', '.join(drift_kw[:3])}"

            state = TopicState(
                current_topic=topic_label,
                keywords=keywords,
                on_topic=on_topic,
                drift_direction=drift,
                timestamp=segment.start_time,
            )
            with self._lock:
                self._topic_history.append(state)

            if self._on_topic_update:
                self._on_topic_update(state)

        except Exception:
            pass

    def _extract_keywords(self, texts: list[str], top_n: int = 5) -> list[str]:
        """Simple TF-based keyword extraction."""
        import re
        from collections import Counter

        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "shall", "can", "to", "of", "in", "for",
            "on", "with", "at", "by", "from", "as", "into", "through", "during",
            "before", "after", "above", "below", "between", "out", "off", "over",
            "under", "again", "further", "then", "once", "here", "there", "when",
            "where", "why", "how", "all", "each", "every", "both", "few", "more",
            "most", "other", "some", "such", "no", "nor", "not", "only", "own",
            "same", "so", "than", "too", "very", "just", "because", "but", "and",
            "or", "if", "while", "about", "up", "it", "its", "this", "that",
            "these", "those", "i", "you", "he", "she", "we", "they", "me", "him",
            "her", "us", "them", "my", "your", "his", "our", "their", "what",
            "which", "who", "whom", "think", "know", "like", "really", "thing",
            "things", "going", "actually", "right", "well", "yeah", "okay", "mean",
            "something", "kind", "lot", "way", "much", "get", "got", "also", "one",
        }
        words: list[str] = []
        for t in texts:
            tokens = re.findall(r"\b[a-z]{3,}\b", t.lower())
            words.extend(w for w in tokens if w not in stopwords)
        counts = Counter(words)
        return [w for w, _ in counts.most_common(top_n)]

    # ------------------------------------------------------------------
    # 3. Open-loop detection
    # ------------------------------------------------------------------

    def _check_open_loops(
        self, segment: TranscriptSegment, embedding: np.ndarray | None
    ) -> None:
        """
        Detect open loops: topics/questions that were raised but never resolved.

        Heuristics:
        - A question mark in a segment opens a potential loop.
        - A topic cluster that appears and then disappears without convergence.
        - Segments containing hedging language ("we should come back to",
          "let's table that", "I want to return to") signal deferred topics.
        """
        text_lower = segment.text.lower()

        # Detect new loops from questions and deferral language
        deferral_phrases = [
            "come back to", "table that", "return to", "park that",
            "revisit", "another time", "later", "set aside", "move on from",
            "skip that for now", "bracket that",
        ]

        is_question = "?" in segment.text
        is_deferral = any(p in text_lower for p in deferral_phrases)

        if is_question or is_deferral:
            loop = OpenLoop(
                description=segment.text.strip(),
                opened_at=segment.start_time,
                last_referenced=segment.start_time,
                status="open",
                related_text=segment.text,
            )
            with self._lock:
                self._open_loops.append(loop)
            if self._on_open_loop:
                self._on_open_loop(loop)

        # Check for stale loops (abandoned)
        now = segment.start_time
        with self._lock:
            for loop in self._open_loops:
                if loop.status != "open":
                    continue

                # Check if recent segments reference this loop
                if embedding is not None and self._embedder is not None:
                    loop_emb = self._embed(loop.description)
                    if loop_emb is not None:
                        sim = float(
                            np.dot(embedding, loop_emb)
                            / (np.linalg.norm(embedding) * np.linalg.norm(loop_emb) + 1e-9)
                        )
                        if sim > self.cfg.loop_similarity_threshold:
                            loop.last_referenced = now
                            continue

                # Mark as abandoned if stale
                if now - loop.last_referenced > self.cfg.loop_staleness_seconds:
                    loop.status = "abandoned"
                    if self._on_open_loop:
                        self._on_open_loop(loop)

    # ------------------------------------------------------------------
    # 4. Question generation
    # ------------------------------------------------------------------

    def _generate_questions(self, segment: TranscriptSegment) -> None:
        """Generate follow-up questions using Claude or local LLM."""
        with self._lock:
            recent = self._segments[-12:]
            loops = [l for l in self._open_loops if l.status == "open"]
            topics = list(self._topic_history[-3:])

        transcript_block = "\n".join(
            f"[{s.speaker}] {s.text}" for s in recent
        )

        open_loops_block = ""
        if loops:
            open_loops_block = "\n\nOpen loops (raised but not yet resolved):\n" + "\n".join(
                f"- {l.description}" for l in loops[-5:]
            )

        topic_block = ""
        if topics:
            t = topics[-1]
            topic_block = f"\n\nCurrent topic: {t.current_topic}"
            if t.drift_direction:
                topic_block += f" ({t.drift_direction})"

        prompt = f"""You are an intellectual dialogue facilitator for Theseus, a firm dedicated to rigorous inquiry. You are observing a live discussion and must suggest 2-3 questions that would deepen or sharpen the conversation.

Recent discussion:
{transcript_block}
{open_loops_block}
{topic_block}

Generate 2-3 questions. For each, give a one-line rationale. Prioritise:
1. Questions that probe unexamined assumptions in what was just said
2. Questions that address open loops the speakers seem to be abandoning
3. Questions that sharpen contradictions rather than smoothing them over
4. Questions that push toward falsifiable claims rather than vague assertions

Format:
Q: [question]
Rationale: [why this question matters now]
Category: [deepening | contradiction | open_loop | pivot]
"""

        if self._anthropic and self.cfg.anthropic_key:
            self._generate_via_claude(prompt)
        else:
            self._generate_via_heuristic(segment)

    def _generate_via_claude(self, prompt: str) -> None:
        try:
            response = self._anthropic.messages.create(
                model=self.cfg.question_model_claude,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            self._parse_and_emit_questions(text)
        except Exception:
            pass

    def _generate_via_heuristic(self, segment: TranscriptSegment) -> None:
        """Fallback: generate simple probing questions without an LLM."""
        templates = [
            SuggestedQuestion(
                text=f"What would falsify the claim that '{segment.text[:60]}...'?",
                rationale="Pushing toward falsifiability",
                category="deepening",
                timestamp=segment.start_time,
            ),
            SuggestedQuestion(
                text="What are we assuming here that we haven't examined?",
                rationale="Probing hidden assumptions",
                category="deepening",
                timestamp=segment.start_time,
            ),
        ]
        for q in templates:
            if self._on_question:
                self._on_question(q)

    def _parse_and_emit_questions(self, text: str) -> None:
        """Parse Claude's response into SuggestedQuestion objects."""
        import re

        blocks = re.split(r"\nQ:", text)
        for block in blocks:
            block = block.strip()
            if not block:
                continue

            q_match = re.match(r"(.+?)(?:\nRationale:\s*(.+?))?(?:\nCategory:\s*(.+?))?$", block, re.DOTALL)
            if q_match:
                sq = SuggestedQuestion(
                    text=q_match.group(1).strip().lstrip("Q:").strip(),
                    rationale=q_match.group(2).strip() if q_match.group(2) else "",
                    category=q_match.group(3).strip() if q_match.group(3) else "deepening",
                    timestamp=time.time(),
                )
                if self._on_question:
                    self._on_question(sq)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> np.ndarray | None:
        if self._embedder is None:
            return None
        try:
            return self._embedder.encode(text, convert_to_numpy=True)
        except Exception:
            return None

    def get_open_loops(self) -> list[OpenLoop]:
        with self._lock:
            return [l for l in self._open_loops if l.status == "open"]

    def get_abandoned_loops(self) -> list[OpenLoop]:
        with self._lock:
            return [l for l in self._open_loops if l.status == "abandoned"]

    def get_current_topic(self) -> TopicState | None:
        with self._lock:
            return self._topic_history[-1] if self._topic_history else None


# ======================================================================
# Live session analyzer (MiniLM + DeBERTa NLI + online k-means)
# ======================================================================

POOL_CAP = 200
K_TOPICS = 8
KMEANS_LR = 0.08


class SessionEventKind(str, Enum):
    PARTIAL_TRANSCRIPT = "partial_transcript"
    CLAIM = "claim"
    CONTRADICTION_ALERT = "contradiction_alert"
    TOPIC_SHIFT = "topic_shift"


@dataclass
class SessionEvent:
    kind: SessionEventKind
    data: dict[str, Any]


@dataclass
class ContradictionAlert:
    pair_id: str
    score: float
    claim_a_id: str
    claim_b_id: str
    text_a: str
    text_b: str


@dataclass
class ClaimRecord:
    id: str
    text: str
    speaker: str
    embedding: np.ndarray
    topic_cluster_id: str


_CLAIM_HINT = re.compile(
    r"(?i)\b(we (must|should|need to|have to)|it follows|therefore|thus|"
    r"always|never|impossible|necessarily|proves that|implies that|"
    r"the (key|main) (point|issue|problem)|in fact|clearly)\b"
)


def _extract_claims_local(text: str, llm_fn: Callable[[str], str] | None) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    found: list[str] = []
    for m in _CLAIM_HINT.finditer(t):
        span = t[m.start() : min(len(t), m.start() + 280)].strip()
        if len(span) >= 14:
            found.append(span)
    if found:
        return list(dict.fromkeys(found))
    parts = re.split(r"(?<=[.!?])\s+", t)
    rough = [p.strip() for p in parts if len(p.strip()) >= 22]
    if rough:
        return rough[:4]
    if len(t) >= 30:
        if llm_fn is not None:
            distilled = llm_fn(t).strip()
            if distilled:
                return [distilled[:500]]
        return [t[:500]]
    return []


class DialecticSessionAnalyzer:
    """
    Consumes :class:`~dialectic.transcriber.TranscriptionEvent` objects (async),
    extracts claims, embeds with MiniLM-L6, maintains a rolling pool (``POOL_CAP``),
    runs DeBERTa cross-encoder NLI vs the pool, online k-means topics, and emits
    :class:`SessionEvent` instances (including :class:`ContradictionAlert` payloads).
    """

    def __init__(
        self,
        cfg: AnalysisConfig,
        out_queue: asyncio.Queue,
        *,
        session_writer: Any = None,
    ):
        self.cfg = cfg
        self._out = out_queue
        self._writer = session_writer
        self._pool: list[ClaimRecord] = []
        self._centroids: np.ndarray | None = None  # (K, dim)
        self._last_topic_id: str | None = None
        self._lock = threading.Lock()
        self._embedder = None
        self._nli = None
        self._llm_fn: Callable[[str], str] | None = None
        if cfg.anthropic_key:
            try:
                import anthropic

                client = anthropic.Anthropic(api_key=cfg.anthropic_key)

                def _llm(chunk: str) -> str:
                    msg = client.messages.create(
                        model=cfg.question_model_claude,
                        max_tokens=120,
                        messages=[
                            {
                                "role": "user",
                                "content": (
                                    "Extract ONE short declarative claim (max 25 words) "
                                    "from this utterance. Reply with only the claim, no quotes.\n\n"
                                    f"{chunk}"
                                ),
                            }
                        ],
                    )
                    return str(msg.content[0].text)

                self._llm_fn = _llm
            except Exception:
                self._llm_fn = None

    def set_session_writer(self, writer: Any) -> None:
        self._writer = writer

    def _ensure_models(self) -> None:
        if self._embedder is not None:
            return
        try:
            from sentence_transformers import CrossEncoder, SentenceTransformer

            self._embedder = SentenceTransformer(self.cfg.embedding_model)
            self._nli = CrossEncoder(self.cfg.nli_model)
        except Exception:
            self._embedder = None
            self._nli = None

    def _embed(self, text: str) -> np.ndarray | None:
        self._ensure_models()
        if self._embedder is None:
            return None
        try:
            v = self._embedder.encode(text, convert_to_numpy=True)
            n = float(np.linalg.norm(v) + 1e-9)
            return (v / n).astype(np.float32)
        except Exception:
            return None

    def _nli_contradiction_scores(self, premise: str, hypotheses: list[str]) -> list[float]:
        if self._nli is None or not hypotheses:
            return [0.0] * len(hypotheses)
        pairs = [(premise, h) for h in hypotheses]
        try:
            logits = self._nli.predict(pairs, show_progress_bar=False)
            out: list[float] = []
            for row in logits:
                arr = np.asarray(row, dtype=np.float32).ravel()
                if arr.size >= 3:
                    e = np.exp(arr - arr.max())
                    p = e / e.sum()
                    out.append(float(p[0]))
                else:
                    out.append(float(arr.ravel()[0]))
            return out
        except Exception:
            return [0.0] * len(hypotheses)

    def _assign_topic(self, emb: np.ndarray) -> tuple[str, bool]:
        """Return (topic_cluster_id, shifted) and update online centroids."""
        if self._centroids is None:
            dim = emb.shape[0]
            self._centroids = np.random.randn(K_TOPICS, dim).astype(np.float32)
            self._centroids /= (
                np.linalg.norm(self._centroids, axis=1, keepdims=True) + 1e-9
            )
        sims = self._centroids @ emb
        k = int(np.argmax(sims))
        topic_id = f"topic_{k}"
        prev = self._last_topic_id
        shifted = prev is not None and prev != topic_id
        self._centroids[k] = (1.0 - KMEANS_LR) * self._centroids[k] + KMEANS_LR * emb
        n = float(np.linalg.norm(self._centroids[k]) + 1e-9)
        self._centroids[k] = (self._centroids[k] / n).astype(np.float32)
        self._last_topic_id = topic_id
        return topic_id, shifted

    def process_final_sync(self, ev: TranscriptionEvent) -> list[SessionEvent]:
        """CPU-heavy path: extract claims, NLI, pool, topics. Call via executor."""
        events: list[SessionEvent] = []
        text = ev.text.strip()
        if not text or text.startswith("["):
            return events
        claims_text = _extract_claims_local(text, self._llm_fn)
        if not claims_text:
            return events
        speaker = ev.speaker
        for ctext in claims_text:
            cid = str(uuid.uuid4())
            emb = self._embed(ctext)
            if emb is None:
                emb = np.zeros(384, dtype=np.float32)
            topic_id, shifted = self._assign_topic(emb)
            pair_ids: list[str] = []
            alerts: list[ContradictionAlert] = []
            with self._lock:
                pool_snap = list(self._pool)
            if pool_snap:
                others = [p.text for p in pool_snap]
                scores_fwd = self._nli_contradiction_scores(ctext, others)
                for i, p in enumerate(pool_snap):
                    sc = max(
                        scores_fwd[i],
                        self._nli_contradiction_scores(p.text, [ctext])[0],
                    )
                    if sc >= self.cfg.contradiction_threshold:
                        pid = f"{min(cid, p.id)}:{max(cid, p.id)}"
                        alerts.append(
                            ContradictionAlert(
                                pair_id=pid,
                                score=sc,
                                claim_a_id=p.id,
                                claim_b_id=cid,
                                text_a=p.text,
                                text_b=ctext,
                            )
                        )
                        pair_ids.append(pid)
            rec = ClaimRecord(
                id=cid,
                text=ctext,
                speaker=speaker,
                embedding=emb,
                topic_cluster_id=topic_id,
            )
            with self._lock:
                self._pool.append(rec)
                if len(self._pool) > POOL_CAP:
                    self._pool = self._pool[-POOL_CAP:]
            events.append(
                SessionEvent(
                    kind=SessionEventKind.CLAIM,
                    data={
                        "claim_id": cid,
                        "text": ctext,
                        "speaker": speaker,
                        "topic_cluster_id": topic_id,
                        "embedding": emb.astype(float).tolist(),
                    },
                )
            )
            for a in alerts:
                events.append(
                    SessionEvent(
                        kind=SessionEventKind.CONTRADICTION_ALERT,
                        data={"alert": a},
                    )
                )
            if shifted:
                events.append(
                    SessionEvent(
                        kind=SessionEventKind.TOPIC_SHIFT,
                        data={
                            "topic_cluster_id": topic_id,
                            "claim_id": cid,
                        },
                    )
                )
            if self._writer is not None:
                self._writer.append_claim(
                    speaker=speaker,
                    text=ctext,
                    embedding=emb.astype(float).tolist(),
                    contradiction_pair_ids=pair_ids,
                    topic_cluster_id=topic_id,
                )
        return events

    async def handle_transcription(self, ev: TranscriptionEvent) -> None:
        if ev.kind == "partial":
            await self._out.put(
                SessionEvent(
                    kind=SessionEventKind.PARTIAL_TRANSCRIPT,
                    data={
                        "text": ev.text,
                        "t_start": ev.t_start,
                        "t_end": ev.t_end,
                        "segment_id": ev.segment_id,
                    },
                )
            )
            return
        loop = asyncio.get_event_loop()
        events = await loop.run_in_executor(None, self.process_final_sync, ev)
        for e in events:
            await self._out.put(e)

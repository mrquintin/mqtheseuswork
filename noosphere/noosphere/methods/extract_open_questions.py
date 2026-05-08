"""Registered method: extract unanswered open questions from a transcript.

The firm's transcripts contain dozens of questions that fall out of view —
someone raises one, the conversation moves on, and no one ever circles
back. This method surfaces them as first-class artifacts so they can be
prioritized and tracked.

Heuristic, not LLM-bound. The detection rules are:

  1. Interrogative form (ends in `?`) OR an "I-don't-know" hedge
     ("I don't know whether", "I'm not sure if", "we don't know whether",
     "the question is whether", ...).
  2. Not answered within K turns of the same speaker. If the same speaker
     supplies a non-interrogative answer-shaped utterance within K of
     their own turns, the question is treated as rhetorical/answered and
     dropped.
  3. Not redundant with an existing OpenQuestion in the registry. A cheap
     paraphrase match (token Jaccard above a threshold, after light
     normalization) is sufficient — the registry is not a vector store.

The method emits `ExtractedOpenQuestion` rows. Resolution is *not* this
method's job: a question that already has a resolution event must be
filtered out by the caller before it is shown anywhere user-facing. The
extractor is deliberately stateless about resolution.
"""

from __future__ import annotations

import re
from typing import Sequence

from pydantic import BaseModel, Field

from noosphere.models import MethodType
from noosphere.methods._decorator import register_method


_DEFAULT_K_TURNS = 2
_PARAPHRASE_JACCARD_THRESHOLD = 0.55
_MIN_QUESTION_TOKENS = 4

_DONT_KNOW_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bi (?:do not|don'?t|dont) know (?:whether|if|how|why|what|which|when|where)\b",
        r"\b(?:we|i|they|nobody|no one) (?:do not|don'?t|dont|aren'?t|isn'?t) (?:know|sure|certain) (?:whether|if|how|why|what|which|when|where)\b",
        r"\bi(?:'m| am) not (?:sure|certain) (?:whether|if|how|why|what|which|when|where)\b",
        r"\bthe (?:real |open )?question (?:is|remains) (?:whether|if|how|why|what|which|when|where)\b",
        r"\bit(?:'s| is) (?:unclear|an open question) (?:whether|if|how|why|what|which|when|where)\b",
        r"\bopen question(?:s)?\b",
    )
)

_RHETORICAL_SELF_ANSWER_MARKERS: tuple[str, ...] = (
    "the answer is",
    "the answer's",
    "answer:",
    "obviously",
    "of course",
    "clearly,",
    "and the answer",
    "and i think the answer",
    "well, yes",
    "well, no",
)

_STOPWORDS: frozenset[str] = frozenset(
    """
    a an the and or but if then so that this these those of in on at to for from
    is are was were be been being do does did have has had not no nor as by it its
    we you they i he she them us our your their my mine ours yours theirs about
    with which who whom whose what when where why how whether
    """.split()
)


class TranscriptTurn(BaseModel):
    """One turn in a transcript-shaped input."""

    speaker: str = ""
    text: str = ""
    turn_index: int = 0


class ExistingQuestion(BaseModel):
    """A question already in the open-question registry."""

    id: str
    summary: str


class ExtractOpenQuestionsInput(BaseModel):
    turns: list[TranscriptTurn] = Field(default_factory=list)
    existing_questions: list[ExistingQuestion] = Field(default_factory=list)
    k_turns: int = _DEFAULT_K_TURNS
    paraphrase_threshold: float = _PARAPHRASE_JACCARD_THRESHOLD


class ExtractedOpenQuestion(BaseModel):
    text: str
    speaker: str = ""
    turn_index: int = 0
    detection_rule: str = "interrogative"  # interrogative | dont_know
    rationale: str = ""


class ExtractOpenQuestionsOutput(BaseModel):
    questions: list[ExtractedOpenQuestion] = Field(default_factory=list)
    rejected_rhetorical: int = 0
    rejected_redundant: int = 0
    rejected_too_short: int = 0


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalize_tokens(text: str) -> set[str]:
    raw = re.findall(r"[a-zA-Z][a-zA-Z'-]+", text.lower())
    return {tok for tok in raw if tok not in _STOPWORDS and len(tok) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _is_interrogative(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.endswith("?"):
        return True
    return False


def _has_dont_know_marker(text: str) -> bool:
    for pat in _DONT_KNOW_PATTERNS:
        if pat.search(text):
            return True
    return False


def _split_sentences(text: str) -> list[str]:
    """Split on sentence boundaries while keeping the trailing punctuation.

    Cheap regex split; good enough for transcript prose.
    """
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _looks_self_answered(turn: TranscriptTurn, question: str) -> bool:
    """Did the speaker answer their own question inside the same turn?

    Counts as rhetorical if (a) a sentence after the question contains a
    self-answer marker, OR (b) any sentence after the question is
    declarative (not interrogative) and shares >=2 content tokens with
    the question itself.
    """
    sentences = _split_sentences(turn.text)
    try:
        idx = next(i for i, s in enumerate(sentences) if question in s)
    except StopIteration:
        return False
    tail = sentences[idx + 1 :]
    if not tail:
        return False
    q_tokens = _normalize_tokens(question)
    for s in tail:
        low = s.lower()
        if any(marker in low for marker in _RHETORICAL_SELF_ANSWER_MARKERS):
            return True
        if s.endswith("?"):
            continue
        # Declarative tail that thematically echoes the question.
        s_tokens = _normalize_tokens(s)
        if len(q_tokens & s_tokens) >= 2:
            return True
    return False


def _answered_by_same_speaker_within_k(
    turns: Sequence[TranscriptTurn],
    asking_turn_idx: int,
    speaker: str,
    question: str,
    k: int,
) -> bool:
    """Did `speaker` answer this question within K of their own subsequent turns?

    "Answer" here = a non-interrogative utterance from the same speaker
    that shares ≥2 content tokens with the question, OR contains an
    explicit answer marker.
    """
    if k <= 0:
        return False
    q_tokens = _normalize_tokens(question)
    seen_own_turns = 0
    for t in turns[asking_turn_idx + 1 :]:
        if t.speaker != speaker:
            continue
        seen_own_turns += 1
        if seen_own_turns > k:
            break
        text = t.text.strip()
        if not text:
            continue
        # If this turn IS another question, skip — it's not an answer.
        sentences = _split_sentences(text)
        non_q_sentences = [s for s in sentences if not s.endswith("?")]
        if not non_q_sentences:
            continue
        joined = " ".join(non_q_sentences).lower()
        if any(marker in joined for marker in _RHETORICAL_SELF_ANSWER_MARKERS):
            return True
        s_tokens = _normalize_tokens(joined)
        if len(q_tokens & s_tokens) >= 2:
            return True
    return False


def _is_redundant_with_registry(
    question: str,
    registry: Sequence[ExistingQuestion],
    threshold: float,
) -> bool:
    if not registry:
        return False
    q_tokens = _normalize_tokens(question)
    if not q_tokens:
        return False
    for existing in registry:
        e_tokens = _normalize_tokens(existing.summary)
        if _jaccard(q_tokens, e_tokens) >= threshold:
            return True
    return False


def _candidate_sentences(text: str) -> list[tuple[str, str]]:
    """Return (sentence, rule) pairs that could be questions."""
    out: list[tuple[str, str]] = []
    for sentence in _split_sentences(text):
        if _is_interrogative(sentence):
            out.append((sentence, "interrogative"))
            continue
        if _has_dont_know_marker(sentence):
            out.append((sentence, "dont_know"))
    return out


# ── Method ───────────────────────────────────────────────────────────────────


@register_method(
    name="extract_open_questions",
    version="1.0.0",
    method_type=MethodType.EXTRACTION,
    input_schema=ExtractOpenQuestionsInput,
    output_schema=ExtractOpenQuestionsOutput,
    description=(
        "Surfaces unanswered questions from a transcript — interrogatives "
        "or 'I don't know whether' hedges that the speaker did not answer "
        "within K of their own turns and that are not paraphrases of an "
        "existing OpenQuestion."
    ),
    rationale=(
        "Transcripts contain dozens of unresolved questions that fall out "
        "of view. Heuristic detection (interrogative form OR don't-know "
        "marker), bounded by a same-speaker self-answer window and a "
        "paraphrase check against the live registry, surfaces them "
        "without needing an LLM in the hot path."
    ),
    owner="founder",
    status="active",
    nondeterministic=False,
    emits_edges=[],
    dependencies=[],
)
def extract_open_questions(
    input_data: ExtractOpenQuestionsInput,
) -> ExtractOpenQuestionsOutput:
    turns = input_data.turns
    k = max(0, int(input_data.k_turns))
    threshold = max(0.0, min(1.0, float(input_data.paraphrase_threshold)))

    out: list[ExtractedOpenQuestion] = []
    rejected_rhetorical = 0
    rejected_redundant = 0
    rejected_too_short = 0

    # Local registry that accumulates as we accept questions, so two
    # near-paraphrases inside the same transcript don't both surface.
    accumulated: list[ExistingQuestion] = list(input_data.existing_questions)

    for i, turn in enumerate(turns):
        if not turn.text.strip():
            continue
        for sentence, rule in _candidate_sentences(turn.text):
            if len(_normalize_tokens(sentence)) < _MIN_QUESTION_TOKENS:
                rejected_too_short += 1
                continue
            if _looks_self_answered(turn, sentence):
                rejected_rhetorical += 1
                continue
            if _answered_by_same_speaker_within_k(
                turns, i, turn.speaker, sentence, k
            ):
                rejected_rhetorical += 1
                continue
            if _is_redundant_with_registry(sentence, accumulated, threshold):
                rejected_redundant += 1
                continue
            extracted = ExtractedOpenQuestion(
                text=sentence,
                speaker=turn.speaker,
                turn_index=turn.turn_index or i,
                detection_rule=rule,
                rationale=(
                    "interrogative form, no same-speaker answer in "
                    f"K={k} turns"
                    if rule == "interrogative"
                    else "don't-know hedge, no same-speaker answer in "
                    f"K={k} turns"
                ),
            )
            out.append(extracted)
            accumulated.append(
                ExistingQuestion(id=f"_local_{len(out)}", summary=sentence)
            )

    return ExtractOpenQuestionsOutput(
        questions=out,
        rejected_rhetorical=rejected_rhetorical,
        rejected_redundant=rejected_redundant,
        rejected_too_short=rejected_too_short,
    )

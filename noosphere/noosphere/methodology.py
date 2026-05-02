"""Methodological analysis for transcripts and conclusions.

The existing claim pipeline answers "what did we conclude?" This module answers
"how did we get there?" The output is intentionally portable: a methodology
profile should be reusable on a different domain without pretending that the
original object-level conclusion transfers with it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]+|[^.!?\n]+(?=\n|$)", re.MULTILINE)
_WORD_RE = re.compile(r"\b[a-z][a-z'-]{2,}\b", re.IGNORECASE)


@dataclass(frozen=True)
class MethodPattern:
    pattern_type: str
    title: str
    summary_template: str
    move: str
    transfer: str
    assumption: str
    failure_mode: str
    default_transfer_targets: tuple[str, ...]
    keywords: tuple[str, ...]
    evidence_terms: tuple[str, ...]


@dataclass(frozen=True)
class MethodologyProfileDraft:
    pattern_type: str
    title: str
    summary: str
    reasoning_moves: list[str] = field(default_factory=list)
    transfer_targets: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    evidence_anchors: list[dict[str, object]] = field(default_factory=list)
    confidence: float = 0.5


PATTERNS: tuple[MethodPattern, ...] = (
    MethodPattern(
        pattern_type="first_principles_decomposition",
        title="First-principles decomposition",
        summary_template=(
            "The material tends to reduce a surface dispute to purposes, "
            "constraints, and primitive obligations before accepting the "
            "object-level category as decisive."
        ),
        move=(
            "Break the topic into purpose, constraint, mechanism, and "
            "consequence before endorsing a conclusion."
        ),
        transfer=(
            "Use this when a new domain is over-described by inherited "
            "institutional categories."
        ),
        assumption=(
            "The most revealing unit is the reason a system exists, not its "
            "familiar label."
        ),
        failure_mode=(
            "It can over-abstract away local history or tacit practice if the "
            "primitive terms are chosen too quickly."
        ),
        default_transfer_targets=(
            "institutional design",
            "governance",
            "product strategy",
        ),
        keywords=(
            "first principle",
            "fundamental",
            "primitive",
            "root",
            "purpose",
            "constraint",
            "mechanism",
        ),
        evidence_terms=(
            "first",
            "fundamental",
            "root",
            "purpose",
            "constraint",
            "mechanism",
        ),
    ),
    MethodPattern(
        pattern_type="adversarial_revision",
        title="Adversarial revision",
        summary_template=(
            "The material treats objections, contradictions, and failure cases "
            "as productive inputs rather than social interruptions."
        ),
        move=(
            "Name the objection, test the strongest rival formulation, and "
            "keep the answer conditional on surviving pressure."
        ),
        transfer=(
            "Use this for claims that sound plausible but have not yet met a "
            "serious counter-case."
        ),
        assumption=(
            "A belief's usable strength is revealed by the best objection it "
            "can answer."
        ),
        failure_mode=(
            "It can become performative skepticism if objections are collected "
            "without deciding what would settle them."
        ),
        default_transfer_targets=(
            "research review",
            "risk assessment",
            "strategic decision-making",
        ),
        keywords=(
            "objection",
            "contradiction",
            "challenge",
            "dissent",
            "counter",
            "pressure",
            "wrong",
            "failure",
        ),
        evidence_terms=(
            "objection",
            "contradiction",
            "challenge",
            "dissent",
            "counter",
            "failure",
            "wrong",
        ),
    ),
    MethodPattern(
        pattern_type="analogical_transfer",
        title="Analogical transfer",
        summary_template=(
            "The material separates a conclusion's portable reasoning pattern "
            "from the original topic, then asks where the same structure may apply."
        ),
        move=(
            "Abstract the structure of the reasoning, then test whether "
            "another domain has the same causal or normative shape."
        ),
        transfer=(
            "Use this to apply an education, market, technology, or "
            "institutional insight to a seemingly unrelated case."
        ),
        assumption=(
            "Some conclusions matter because of their method shape, not only "
            "their topic."
        ),
        failure_mode=(
            "It can smuggle conclusions across domains when the structural "
            "similarity is superficial."
        ),
        default_transfer_targets=(
            "institutional design",
            "technology strategy",
            "capital allocation",
        ),
        keywords=(
            "analog",
            "analogy",
            "transfer",
            "apply",
            "frame",
            "unrelated",
            "similar",
            "structure",
            "elsewhere",
        ),
        evidence_terms=(
            "analog",
            "transfer",
            "apply",
            "frame",
            "unrelated",
            "similar",
            "structure",
            "elsewhere",
        ),
    ),
    MethodPattern(
        pattern_type="dialogic_unfolding",
        title="Dialogic unfolding",
        summary_template=(
            "The material lets thought develop through questions, reformulations, "
            "agreement, disagreement, and participant handoffs rather than through "
            "a single monologic assertion."
        ),
        move=(
            "Track which question or response changed the direction of "
            "reasoning, then preserve the turn-level context."
        ),
        transfer=(
            "Use this when the value is in the sequence of inquiry rather "
            "than in one isolated sentence."
        ),
        assumption=(
            "Conversation can be an epistemic instrument, not just a delivery "
            "channel for already-formed views."
        ),
        failure_mode=(
            "It can mistake conversational energy for evidential progress "
            "unless catalyst turns are tied to claims."
        ),
        default_transfer_targets=(
            "research dialogue",
            "founder interviews",
            "deliberative governance",
        ),
        keywords=(
            "question",
            "conversation",
            "dialogue",
            "dialogic",
            "because",
            "wait",
            "maybe",
            "i think",
            "you mean",
        ),
        evidence_terms=(
            "question",
            "conversation",
            "dialogue",
            "because",
            "maybe",
            "think",
            "mean",
        ),
    ),
    MethodPattern(
        pattern_type="normative_to_institutional_design",
        title="Normative-to-institutional design",
        summary_template=(
            "The material derives practical system design from explicit values "
            "instead of treating values as decorative justification after the fact."
        ),
        move=(
            "Move from what should matter to what structures, incentives, or "
            "practices would make it real."
        ),
        transfer=(
            "Use this when a principle must become an institution, product "
            "workflow, investment rule, or governance norm."
        ),
        assumption="Values are incomplete until they imply design constraints.",
        failure_mode=(
            "It can hard-code a value before enough plural objections have "
            "been heard."
        ),
        default_transfer_targets=(
            "institutional design",
            "product governance",
            "capital allocation",
        ),
        keywords=(
            "should",
            "ought",
            "better",
            "institution",
            "system",
            "design",
            "school",
            "education",
            "incentive",
        ),
        evidence_terms=(
            "should",
            "ought",
            "better",
            "institution",
            "system",
            "design",
            "school",
            "education",
        ),
    ),
    MethodPattern(
        pattern_type="empirical_calibration",
        title="Empirical calibration",
        summary_template=(
            "The material asks what evidence, probability, market signal, or "
            "future observation would discipline the belief."
        ),
        move=(
            "Convert posture into evidence thresholds, confidence, "
            "predictions, or exit conditions."
        ),
        transfer=(
            "Use this when an idea must face time, markets, measurement, or "
            "outcome feedback."
        ),
        assumption="A serious belief should expose what would move or defeat it.",
        failure_mode=(
            "It can quantify false precision when the evidence channel is "
            "thin or badly specified."
        ),
        default_transfer_targets=(
            "forecasting",
            "market validation",
            "impact evaluation",
        ),
        keywords=(
            "evidence",
            "data",
            "probability",
            "confidence",
            "predict",
            "market",
            "falsif",
            "measure",
            "outcome",
        ),
        evidence_terms=(
            "evidence",
            "data",
            "probability",
            "confidence",
            "predict",
            "market",
            "measure",
            "outcome",
        ),
    ),
)


def _normalize_source_text(text: str) -> str:
    """Collapse visual line wraps while keeping paragraph boundaries."""
    value = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    paragraphs = [
        re.sub(r"\s*\n\s*", " ", para).strip()
        for para in re.split(r"\n\s*\n+", value)
    ]
    return "\n".join(para for para in paragraphs if para)


def split_sentences(text: str) -> list[str]:
    out: list[str] = []
    cleaned = _normalize_source_text(text)
    for match in _SENTENCE_RE.finditer(cleaned):
        sentence = match.group(0).strip()
        if 30 <= len(sentence) <= 600:
            out.append(sentence)
    return out


def _contains_term(sentence: str, term: str) -> bool:
    if " " in term:
        return term in sentence.lower()
    return bool(re.search(rf"\b{re.escape(term)}[a-z'-]*\b", sentence, re.IGNORECASE))


def _sentence_score(sentence: str, pattern: MethodPattern) -> int:
    return sum(1 for term in pattern.evidence_terms if _contains_term(sentence, term))


def _content_words(sentences: Iterable[str]) -> set[str]:
    stop = {
        "about", "after", "again", "also", "because", "being", "from", "have",
        "into", "just", "like", "more", "only", "should", "that", "their",
        "there", "these", "this", "what", "when", "where", "which", "with",
        "would", "think", "right", "really", "thing", "things",
    }
    words: set[str] = set()
    for sentence in sentences:
        for word in _WORD_RE.findall(sentence.lower()):
            if len(word) >= 5 and word not in stop:
                words.add(word)
    return words


def infer_transfer_targets(
    evidence: list[str],
    fallback_targets: tuple[str, ...],
) -> list[str]:
    words = _content_words(evidence)
    targets: list[str] = []
    domain_map = (
        (
            "institutional design",
            {
                "school",
                "education",
                "student",
                "teacher",
                "credential",
                "institution",
                "governance",
                "system",
                "incentive",
                "organization",
            },
        ),
        (
            "capital allocation",
            {"market", "capital", "investment", "price", "portfolio"},
        ),
        (
            "technology strategy",
            {"technology", "product", "platform", "software", "interface"},
        ),
        (
            "truth-seeking dialogue",
            {"conversation", "dialogue", "question", "transcript", "voice"},
        ),
    )
    for label, terms in domain_map:
        if words & terms:
            targets.append(label)
    for label in fallback_targets:
        if label not in targets:
            targets.append(label)
    return targets[:4]


def derive_methodology_profiles(
    text: str,
    *,
    source_title: str = "",
    max_profiles: int = 6,
) -> list[MethodologyProfileDraft]:
    """Return deterministic methodology profiles from raw source text.

    This is not meant to be the final human judgment. It is the durable first
    pass that lets the Codex carry methods forward, makes publication review
    ask about method, and gives a later LLM pass structured fields to improve.
    """
    sentences = split_sentences(text)
    if not sentences:
        return []

    scored: list[tuple[int, MethodPattern, list[tuple[int, str, int]]]] = []
    for pattern in PATTERNS:
        anchors: list[tuple[int, str, int]] = []
        keyword_hits = 0
        for idx, sentence in enumerate(sentences):
            score = _sentence_score(sentence, pattern)
            if score:
                anchors.append((idx, sentence, score))
                keyword_hits += score
        if anchors:
            scored.append((keyword_hits, pattern, anchors))

    scored.sort(key=lambda item: (-item[0], item[1].pattern_type))
    profiles: list[MethodologyProfileDraft] = []
    for keyword_hits, pattern, anchors in scored[:max_profiles]:
        ordered = sorted(anchors, key=lambda item: (-item[2], item[0]))[:4]
        evidence_sentences = [sentence for _, sentence, _ in ordered]
        confidence = min(
            0.92,
            0.42
            + min(keyword_hits, 12) * 0.04
            + min(len(anchors), 6) * 0.025,
        )
        transfer_targets = infer_transfer_targets(
            evidence_sentences,
            pattern.default_transfer_targets,
        )
        profiles.append(
            MethodologyProfileDraft(
                pattern_type=pattern.pattern_type,
                title=pattern.title,
                summary=pattern.summary_template,
                reasoning_moves=[pattern.move],
                transfer_targets=transfer_targets,
                assumptions=[pattern.assumption],
                failure_modes=[pattern.failure_mode],
                evidence_anchors=[
                    {
                        "sentenceIndex": idx,
                        "quote": sentence[:500],
                        "sourceTitle": source_title,
                    }
                    for idx, sentence, _ in ordered
                ],
                confidence=round(confidence, 3),
            )
        )

    return profiles

"""
Research Advisor — Post-Discussion Topic and Reading Generator.

After a discussion is processed, this module analyses the principles and
arguments presented, researches their ramifications and historical/empirical
parallels, and produces a structured brief for the next discussion:

  1. TOPIC PROPOSALS — 3–5 topics for the next conversation, each grounded
     in what was discussed but extending it into new territory.  Each topic
     pairs a philosophical question with a concrete historical case or
     empirical finding, so that the next discussion is anchored in the real
     world rather than drifting into abstraction.

  2. READING LIST — For each proposed topic, a curated set of readings
     (books, papers, historical primary sources, empirical studies) selected
     because they either:
       (a) illuminate a ramification of a principle the founders have adopted,
       (b) present a historical case that tests or challenges that principle,
       (c) provide empirical evidence bearing on the principle's validity, or
       (d) represent a thinker who arrived at a similar (or contradictory)
           conclusion through a different route.

  3. EMPIRICAL ANCHORS — For each topic, a concrete historical event,
     experiment, policy outcome, or case study that makes the philosophical
     question tangible.  The purpose is to prevent discussions from remaining
     at the level of pure abstraction; every idea should be tested against
     something that actually happened.

Design principle: the advisor does *not* tell the founders what to think.
It identifies what is most worth thinking about next, given what they have
already said, and provides the raw material for that thinking.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
from sqlalchemy import text

from pydantic import BaseModel, Field

from noosphere.models import Claim, Principle, Episode

from noosphere.observability import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class EmpiricalAnchor:
    """A concrete historical/empirical case connected to a philosophical idea."""
    title: str                    # e.g. "The Semmelweis Reflex"
    period: str                   # e.g. "Vienna, 1847–1861"
    summary: str                  # 2–3 sentence description
    relevance: str                # how it connects to the principle
    source_suggestion: str = ""   # where to read more


@dataclass
class Reading:
    """A recommended reading with reasons tied to the discussion."""
    title: str
    author: str
    year: int | str
    type: str = "book"            # book | paper | primary_source | empirical_study
    reason: str = ""              # why this reading matters for this topic
    key_argument: str = ""        # the core claim the reading makes
    chapter_focus: str = ""       # specific chapter/section if not the whole work


@dataclass
class TopicProposal:
    """A proposed topic for the next discussion."""
    title: str                    # short, evocative title
    philosophical_question: str   # the core question to investigate
    connection_to_discussion: str # how it arises from what was said
    ramifications: str            # what follows if the principle is true/false
    empirical_anchors: list[EmpiricalAnchor] = field(default_factory=list)
    readings: list[Reading] = field(default_factory=list)
    priority: str = "medium"      # "high" | "medium" | "exploratory"
    tags: list[str] = field(default_factory=list)


@dataclass
class ResearchBrief:
    """Complete output of the research advisor for one discussion."""
    episode_number: int
    episode_title: str
    generated_at: str
    preamble: str                           # contextual framing
    topics: list[TopicProposal]
    cross_cutting_themes: list[str] = field(default_factory=list)
    methodology_note: str = ""              # note on *how* the topics were selected


# ═══════════════════════════════════════════════════════════════════════════════
# LLM dispatch (shared with synthesis.py pattern)
# ═══════════════════════════════════════════════════════════════════════════════

def _call_llm(prompt: str, system: str = "", max_tokens: int = 4000) -> str:
    """Call Claude (preferred) or OpenAI, with graceful fallback."""

    # Try Anthropic first
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=system or "You are a rigorous philosophical research advisor.",
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            logger.warning(f"Anthropic API call failed: {e}")

    # Fall back to OpenAI
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.4,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.warning(f"OpenAI API call failed: {e}")

    return f"[LLM unavailable — raw prompt below]\n\n{prompt[:3000]}"


# ═══════════════════════════════════════════════════════════════════════════════
# ResearchAdvisor
# ═══════════════════════════════════════════════════════════════════════════════

class ResearchAdvisor:
    """
    Analyses the output of a discussion and generates structured research
    briefs for the next conversation.

    Requires:
      - The ontology graph (for principles and their relationships)
      - The embedding model (for similarity computations)
      - Optionally, the conclusions registry (for empirical claims)
    """

    def __init__(
        self,
        data_dir: Path,
        graph,                # OntologyGraph
        model,                # SentenceTransformer
        conclusions_registry=None,
    ):
        self.data_dir = data_dir
        self.briefs_dir = data_dir / "synthesis" / "research_briefs"
        self.briefs_dir.mkdir(parents=True, exist_ok=True)

        self.graph = graph
        self.model = model
        self.conclusions = conclusions_registry

    # ──────────────────────────────────────────────────────────────────────────
    # Main entry point
    # ──────────────────────────────────────────────────────────────────────────

    def generate_research_brief(
        self,
        episode: Episode,
        claims: list[Claim],
        new_principles: list[Principle],
        contradictions: list[tuple[Principle, Principle, float]],
        all_principles: list[Principle],
    ) -> ResearchBrief:
        """
        Generate a complete research brief for the next discussion.

        This is the master method that orchestrates the three stages:
          1. Identify the most productive lines of inquiry from the discussion
          2. Research ramifications, historical parallels, and empirical cases
          3. Curate readings and structure the brief

        Returns a ResearchBrief and saves it to disk as Markdown.
        """
        logger.info(f"Generating research brief after episode {episode.number}...")

        # ── Stage 1: Identify productive lines of inquiry ──────────────────
        inquiry_lines = self._identify_inquiry_lines(
            episode, claims, new_principles, contradictions, all_principles
        )

        # ── Stage 2: Research each line — ramifications + empirical cases ──
        topics = self._research_topics(
            inquiry_lines, episode, claims, new_principles, contradictions
        )

        # ── Stage 3: Cross-cutting themes ──────────────────────────────────
        cross_themes = self._identify_cross_cutting_themes(topics)

        # ── Assemble the brief ─────────────────────────────────────────────
        preamble = self._generate_preamble(episode, topics, claims)

        brief = ResearchBrief(
            episode_number=episode.number,
            episode_title=episode.title,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            preamble=preamble,
            topics=topics,
            cross_cutting_themes=cross_themes,
            methodology_note=(
                "Topics selected by: (1) identifying principles with the highest "
                "embedding-space novelty relative to prior discussions, (2) detecting "
                "unresolved contradictions via Hoyer sparsity, (3) tracing ramifications "
                "of newly adopted positions, (4) matching against historical and empirical "
                "case databases via LLM research."
            ),
        )

        # Save
        self._save_brief(brief)
        logger.info(f"Research brief generated: {len(topics)} topics")
        return brief

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 1: Identify lines of inquiry
    # ──────────────────────────────────────────────────────────────────────────

    def _identify_inquiry_lines(
        self,
        episode: Episode,
        claims: list[Claim],
        new_principles: list[Principle],
        contradictions: list[tuple[Principle, Principle, float]],
        all_principles: list[Principle],
    ) -> list[dict]:
        """
        Identify the 4–6 most productive lines of inquiry by combining:

        1. Novel principles — ideas articulated for the first time
        2. Unresolved contradictions — tensions that demand confrontation
        3. High-conviction principles with unexplored consequences
        4. Points where the discussion petered out or changed topic abruptly
        """

        # Embed recent claims for novelty detection
        recent_texts = [c.text for c in claims[:60]]
        prior_principles = [
            p for p in all_principles
            if p not in new_principles and p.text.strip()
        ]

        # ── Build the prompt ───────────────────────────────────────────────
        new_princ_block = "\n".join(
            f"- {p.text} (conviction: {p.conviction_score:.2f})"
            for p in new_principles[:15]
        )

        contradiction_block = "\n".join(
            f"- TENSION: \"{a.text}\" vs \"{b.text}\" (geometric sparsity: {s:.3f})"
            for a, b, s in contradictions[:8]
        )

        prior_block = "\n".join(
            f"- {p.text} (conviction: {p.conviction_score:.2f}, mentions: {p.mention_count})"
            for p in sorted(prior_principles, key=lambda x: x.conviction_score, reverse=True)[:15]
        )

        claim_sample = "\n".join(f"- {t}" for t in recent_texts[:25])

        cal_block = ""
        try:
            from noosphere.config import get_settings
            from noosphere.scoring import weak_calibration_domains
            from noosphere.store import Store

            st = Store.from_database_url(get_settings().database_url)
            wd = weak_calibration_domains(st, max_items=6, min_n=4)
            if wd:
                lines = "\n".join(
                    f"- author `{a}` domain `{d}`: mean Brier {b:.3f} over {n} scored predictions"
                    for a, d, b, n in wd
                )
                cal_block = (
                    "\n\nCALIBRATION SIGNAL (resolved falsifiable predictions; prefer empirical "
                    "depth or disconfirming evidence in these pockets):\n"
                    f"{lines}\n"
                )
        except Exception as e:
            logger.debug("research_advisor_calibration_context_skip", error=str(e))

        prompt = f"""You are the research director of Theseus, an intellectual capital firm. After each discussion, you identify the most productive lines of inquiry for the NEXT discussion.

EPISODE JUST COMPLETED: {episode.title} (Episode {episode.number})

NEW PRINCIPLES DISTILLED FROM THIS DISCUSSION:
{new_princ_block if new_princ_block else "None — discussion refined existing principles only"}

UNRESOLVED CONTRADICTIONS (detected via embedding geometry):
{contradiction_block if contradiction_block else "None currently detected"}

EXISTING HIGH-CONVICTION PRINCIPLES (from prior discussions):
{prior_block if prior_block else "None — this is the first discussion"}

SAMPLE CLAIMS FROM THIS DISCUSSION:
{claim_sample}
{cal_block}
TASK: Identify 4–6 lines of inquiry for the next discussion. For each, provide:
1. TITLE — A short, evocative name for the topic
2. PHILOSOPHICAL_QUESTION — The core question to investigate (should be genuinely philosophical, not administrative)
3. CONNECTION — How this arises from what was discussed
4. TYPE — One of: "ramification" (what follows from an adopted principle), "contradiction" (an unresolved tension), "unexplored" (an important area the founders haven't addressed), "deepening" (pushing a principle further)
5. PRIORITY — "high" (urgent, blocks other progress), "medium" (important, natural next step), or "exploratory" (interesting but optional)

CRITICAL REQUIREMENTS:
- Each topic must be philosophical in character but connectable to real-world history or empirical evidence
- Do NOT suggest purely abstract topics — every topic should have a "so what" in terms of actual events, policies, experiments, or historical episodes
- Prioritise topics that would FORCE the founders to confront something uncomfortable or unexamined in their own framework
- At least one topic should arise from a contradiction
- At least one topic should extend a principle into a domain where its implications are non-obvious

Format your response as a JSON array of objects with keys: title, philosophical_question, connection, type, priority, tags (array of 2-3 keyword tags).
"""

        system = (
            "You are a philosophical research director. You identify the most "
            "intellectually productive directions for inquiry. You always ground "
            "philosophical questions in historical and empirical reality."
        )

        response = _call_llm(prompt, system=system, max_tokens=3000)

        # Parse JSON from the response
        return self._parse_inquiry_lines(response)

    def _parse_inquiry_lines(self, response: str) -> list[dict]:
        """Extract structured inquiry lines from LLM response."""
        # Try to find JSON array in the response
        try:
            # Look for JSON array
            match = re.search(r'\[.*\]', response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except (json.JSONDecodeError, AttributeError):
            pass

        # Fallback: parse numbered items
        lines = []
        blocks = re.split(r'\n\d+\.\s+', response)
        for block in blocks:
            if not block.strip():
                continue
            title_match = re.search(r'TITLE[:\s]*(.+?)(?:\n|$)', block, re.IGNORECASE)
            q_match = re.search(r'PHILOSOPHICAL[_ ]QUESTION[:\s]*(.+?)(?:\n|$)', block, re.IGNORECASE)
            conn_match = re.search(r'CONNECTION[:\s]*(.+?)(?:\n|$)', block, re.IGNORECASE)
            type_match = re.search(r'TYPE[:\s]*(.+?)(?:\n|$)', block, re.IGNORECASE)
            prio_match = re.search(r'PRIORITY[:\s]*(.+?)(?:\n|$)', block, re.IGNORECASE)

            if title_match or q_match:
                lines.append({
                    "title": title_match.group(1).strip() if title_match else "Untitled",
                    "philosophical_question": q_match.group(1).strip() if q_match else block[:200],
                    "connection": conn_match.group(1).strip() if conn_match else "",
                    "type": type_match.group(1).strip().lower() if type_match else "deepening",
                    "priority": prio_match.group(1).strip().lower() if prio_match else "medium",
                    "tags": [],
                })

        return lines[:6]

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 2: Research each topic
    # ──────────────────────────────────────────────────────────────────────────

    def _research_topics(
        self,
        inquiry_lines: list[dict],
        episode: Episode,
        claims: list[Claim],
        new_principles: list[Principle],
        contradictions: list[tuple[Principle, Principle, float]],
    ) -> list[TopicProposal]:
        """
        For each identified line of inquiry, research:
        - Historical parallels and case studies
        - Empirical findings bearing on the question
        - Relevant readings across philosophy, history, and science
        - The ramifications if the founders' position is correct / incorrect
        """
        topics: list[TopicProposal] = []

        for line in inquiry_lines[:5]:  # cap at 5 to manage LLM calls
            topic = self._research_single_topic(line, claims, new_principles)
            topics.append(topic)

        return topics

    def _research_single_topic(
        self,
        inquiry: dict,
        claims: list[Claim],
        new_principles: list[Principle],
    ) -> TopicProposal:
        """Deep-research a single topic: empirical anchors, readings, ramifications."""

        title = inquiry.get("title", "Untitled")
        question = inquiry.get("philosophical_question", "")
        connection = inquiry.get("connection", "")
        topic_type = inquiry.get("type", "deepening")
        priority = inquiry.get("priority", "medium")
        tags = inquiry.get("tags", [])

        # Build context from the principles most related to this topic
        relevant_principles = "\n".join(
            f"- {p.text}" for p in new_principles[:10]
        )

        prompt = f"""You are a philosophical research advisor preparing materials for the next discussion at Theseus, an intellectual capital firm. The founders need both philosophical depth and empirical grounding for every topic.

TOPIC: {title}
CORE QUESTION: {question}
HOW IT CONNECTS TO THE LAST DISCUSSION: {connection}
TOPIC TYPE: {topic_type}

RELEVANT PRINCIPLES FROM THE DISCUSSION:
{relevant_principles}

For this topic, produce the following (be specific and scholarly — no vague gestures):

1. RAMIFICATIONS (2–3 paragraphs):
   What follows if the founders' position (as expressed in the principles above) is correct? What follows if it is wrong? What domains of thought or action are affected? What would change in practice?

2. EMPIRICAL ANCHORS (2–3 specific cases):
   For each, provide:
   - TITLE: A short name (e.g., "The Replication Crisis", "Semmelweis and Handwashing")
   - PERIOD: When and where (e.g., "Psychology, 2011–present")
   - SUMMARY: 2–3 sentences describing the case
   - RELEVANCE: How this case bears on the philosophical question
   - SOURCE: One specific book or paper where the founders can read about it

3. READINGS (4–6 specific works):
   For each, provide:
   - TITLE, AUTHOR, YEAR
   - TYPE: book | paper | primary_source | empirical_study
   - REASON: Why this reading matters for this specific topic (not generic relevance)
   - KEY_ARGUMENT: The core claim of the work in one sentence
   - CHAPTER_FOCUS: If the whole book isn't relevant, which chapter/section is

   Mix of types: at least one philosophical work, one historical/empirical study, and one that presents a position the founders would likely disagree with (the "adversarial" reading).

CRITICAL REQUIREMENTS:
- All works must be REAL — cite actual books, papers, and historical events. Do not fabricate sources.
- Historical cases must be specific: names, dates, places. Not "various instances in history."
- Readings must be chosen for their specific relevance to THIS question, not general relevance to the firm.
- Include at least one "adversarial" reading — a work that challenges the founders' likely position.

Format your response with clear section headers: RAMIFICATIONS, EMPIRICAL ANCHORS (numbered), READINGS (numbered).
"""

        system = (
            "You are a philosophical research advisor with deep knowledge of intellectual "
            "history, philosophy of science, political philosophy, epistemology, and empirical "
            "social science. You never fabricate sources. You always connect abstract ideas "
            "to concrete historical and empirical cases."
        )

        response = _call_llm(prompt, system=system, max_tokens=3500)

        # Parse the response into structured data
        ramifications = self._extract_section(response, "RAMIFICATIONS")
        anchors = self._parse_empirical_anchors(response)
        readings = self._parse_readings(response)

        return TopicProposal(
            title=title,
            philosophical_question=question,
            connection_to_discussion=connection,
            ramifications=ramifications,
            empirical_anchors=anchors,
            readings=readings,
            priority=priority,
            tags=tags if isinstance(tags, list) else [],
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 3: Cross-cutting themes
    # ──────────────────────────────────────────────────────────────────────────

    def _identify_cross_cutting_themes(self, topics: list[TopicProposal]) -> list[str]:
        """Identify themes that appear across multiple proposed topics."""
        if len(topics) < 2:
            return []

        topic_descriptions = "\n".join(
            f"- {t.title}: {t.philosophical_question}"
            for t in topics
        )

        prompt = f"""Given these proposed discussion topics, identify 2–3 cross-cutting themes — patterns or tensions that appear in multiple topics and could serve as a unifying thread for the next discussion.

TOPICS:
{topic_descriptions}

For each theme, provide one sentence. Be specific — not "epistemology" but "the tension between method-dependence and objectivity in evaluating novel claims."
"""
        response = _call_llm(prompt, max_tokens=500)

        # Parse into list
        themes = []
        for line in response.strip().split("\n"):
            line = line.strip().lstrip("0123456789.-) ")
            if line and len(line) > 15:
                themes.append(line)

        return themes[:4]

    # ──────────────────────────────────────────────────────────────────────────
    # Preamble
    # ──────────────────────────────────────────────────────────────────────────

    def _generate_preamble(
        self, episode: Episode, topics: list[TopicProposal], claims: list[Claim]
    ) -> str:
        """Generate a contextual framing paragraph for the brief."""
        topic_titles = ", ".join(t.title for t in topics)
        high_priority = [t for t in topics if t.priority == "high"]

        preamble = (
            f"This research brief follows Episode {episode.number} "
            f"(\"{episode.title}\"), from which {len(claims)} claims were extracted. "
            f"The analysis identified {len(topics)} productive lines of inquiry: "
            f"{topic_titles}."
        )

        if high_priority:
            preamble += (
                f" Of these, {len(high_priority)} {'is' if len(high_priority) == 1 else 'are'} "
                f"marked high-priority: {', '.join(t.title for t in high_priority)}."
            )

        return preamble

    # ──────────────────────────────────────────────────────────────────────────
    # Parsing helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _extract_section(self, text: str, header: str) -> str:
        """Extract content under a section header."""
        pattern = rf'{header}\s*[:\n](.+?)(?=\n[A-Z][A-Z ]+[:\n]|\Z)'
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""

    def _parse_empirical_anchors(self, text: str) -> list[EmpiricalAnchor]:
        """Parse empirical anchor entries from LLM response."""
        anchors = []
        section = self._extract_section(text, "EMPIRICAL ANCHORS")
        if not section:
            return anchors

        # Split by numbered items or "TITLE:" markers
        blocks = re.split(r'\n\s*\d+[\.\)]\s+|(?=TITLE\s*:)', section)

        for block in blocks:
            if not block.strip():
                continue

            title = self._field(block, "TITLE") or block.split("\n")[0].strip()[:80]
            period = self._field(block, "PERIOD") or ""
            summary = self._field(block, "SUMMARY") or ""
            relevance = self._field(block, "RELEVANCE") or ""
            source = self._field(block, "SOURCE") or ""

            if title and (summary or relevance):
                anchors.append(EmpiricalAnchor(
                    title=title.strip(" -:"),
                    period=period,
                    summary=summary,
                    relevance=relevance,
                    source_suggestion=source,
                ))

        return anchors[:4]

    def _parse_readings(self, text: str) -> list[Reading]:
        """Parse reading entries from LLM response."""
        readings = []
        section = self._extract_section(text, "READINGS")
        if not section:
            return readings

        blocks = re.split(r'\n\s*\d+[\.\)]\s+', section)

        for block in blocks:
            if not block.strip():
                continue

            title = self._field(block, "TITLE") or ""
            author = self._field(block, "AUTHOR") or ""
            year = self._field(block, "YEAR") or ""
            rtype = self._field(block, "TYPE") or "book"
            reason = self._field(block, "REASON") or ""
            key_arg = self._field(block, "KEY_ARGUMENT") or self._field(block, "KEY ARGUMENT") or ""
            chapter = self._field(block, "CHAPTER_FOCUS") or self._field(block, "CHAPTER FOCUS") or ""

            # If no structured fields found, try to parse "Author — Title (Year)"
            if not title and not author:
                dash_match = re.match(r'(.+?)\s*[—–-]\s*(.+?)(?:\((\d{4})\))?', block.split("\n")[0])
                if dash_match:
                    author = dash_match.group(1).strip()
                    title = dash_match.group(2).strip()
                    year = dash_match.group(3) or year

            if title or author:
                readings.append(Reading(
                    title=title.strip(" *_"),
                    author=author.strip(),
                    year=year,
                    type=rtype.strip().lower(),
                    reason=reason,
                    key_argument=key_arg,
                    chapter_focus=chapter,
                ))

        return readings[:8]

    @staticmethod
    def _field(text: str, name: str) -> str:
        """Extract a field value from a block of text."""
        pattern = rf'{name}\s*[:\-]\s*(.+?)(?=\n[A-Z_]+\s*[:\-]|\n\n|\Z)'
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    # ──────────────────────────────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────────────────────────────

    def _save_brief(self, brief: ResearchBrief) -> Path:
        """Save the research brief as a Markdown file."""
        filename = f"research_brief_ep{brief.episode_number}.md"
        filepath = self.briefs_dir / filename

        lines = [
            f"# Research Brief: Next Discussion Topics",
            f"",
            f"**After Episode {brief.episode_number}:** {brief.episode_title}",
            f"**Generated:** {brief.generated_at}",
            f"",
            f"---",
            f"",
            f"## Overview",
            f"",
            brief.preamble,
            f"",
        ]

        if brief.methodology_note:
            lines += [
                f"*Methodology: {brief.methodology_note}*",
                f"",
            ]

        if brief.cross_cutting_themes:
            lines += [
                f"### Cross-Cutting Themes",
                f"",
            ]
            for theme in brief.cross_cutting_themes:
                lines.append(f"- {theme}")
            lines.append("")

        lines += [f"---", f""]

        for i, topic in enumerate(brief.topics, 1):
            priority_badge = {
                "high": "🔴 HIGH PRIORITY",
                "medium": "🟡 MEDIUM",
                "exploratory": "🟢 EXPLORATORY",
            }.get(topic.priority, topic.priority.upper())

            lines += [
                f"## Topic {i}: {topic.title}",
                f"",
                f"**Priority:** {priority_badge}",
                f"**Tags:** {', '.join(topic.tags) if topic.tags else 'general'}",
                f"",
                f"### Core Question",
                f"",
                f"> {topic.philosophical_question}",
                f"",
                f"**Connection to the discussion:** {topic.connection_to_discussion}",
                f"",
            ]

            if topic.ramifications:
                lines += [
                    f"### Ramifications",
                    f"",
                    topic.ramifications,
                    f"",
                ]

            if topic.empirical_anchors:
                lines += [f"### Empirical Anchors", f""]
                for anchor in topic.empirical_anchors:
                    lines += [
                        f"**{anchor.title}** ({anchor.period})",
                        f"",
                        anchor.summary,
                        f"",
                        f"*Relevance:* {anchor.relevance}",
                        f"",
                    ]
                    if anchor.source_suggestion:
                        lines.append(f"*Read more:* {anchor.source_suggestion}")
                        lines.append("")

            if topic.readings:
                lines += [f"### Recommended Readings", f""]
                for r in topic.readings:
                    year_str = f" ({r.year})" if r.year else ""
                    lines.append(f"**{r.author} — *{r.title}*{year_str}** [{r.type}]")
                    if r.reason:
                        lines.append(f"*Why:* {r.reason}")
                    if r.key_argument:
                        lines.append(f"*Core argument:* {r.key_argument}")
                    if r.chapter_focus:
                        lines.append(f"*Focus on:* {r.chapter_focus}")
                    lines.append("")

            lines += [f"---", f""]

        with open(filepath, "w") as f:
            f.write("\n".join(lines))

        logger.info(f"Research brief saved to {filepath}")
        return filepath

    # ──────────────────────────────────────────────────────────────────────────
    # JSON export (for programmatic consumption)
    # ──────────────────────────────────────────────────────────────────────────

    def brief_to_dict(self, brief: ResearchBrief) -> dict:
        """Convert a ResearchBrief to a JSON-serialisable dict."""
        return {
            "episode_number": brief.episode_number,
            "episode_title": brief.episode_title,
            "generated_at": brief.generated_at,
            "preamble": brief.preamble,
            "cross_cutting_themes": brief.cross_cutting_themes,
            "methodology_note": brief.methodology_note,
            "topics": [
                {
                    "title": t.title,
                    "philosophical_question": t.philosophical_question,
                    "connection_to_discussion": t.connection_to_discussion,
                    "ramifications": t.ramifications,
                    "priority": t.priority,
                    "tags": t.tags,
                    "empirical_anchors": [
                        {
                            "title": a.title,
                            "period": a.period,
                            "summary": a.summary,
                            "relevance": a.relevance,
                            "source_suggestion": a.source_suggestion,
                        }
                        for a in t.empirical_anchors
                    ],
                    "readings": [
                        {
                            "title": r.title,
                            "author": r.author,
                            "year": r.year,
                            "type": r.type,
                            "reason": r.reason,
                            "key_argument": r.key_argument,
                            "chapter_focus": r.chapter_focus,
                        }
                        for r in t.readings
                    ],
                }
                for t in brief.topics
            ],
        }


# ═══════════════════════════════════════════════════════════════════════════
# Session-scoped research (Phase 4) — grounded topic + reading suggestions
# ═══════════════════════════════════════════════════════════════════════════


class GroundedTopicSuggestion(BaseModel):
    title: str
    rationale: str
    citing_claim_id: str
    citing_open_question_or_conclusion_id: str
    #: Optional retrieved external claim grounding this topic line.
    grounding_claim_id: str = ""


class GroundedReadingSuggestion(BaseModel):
    title: str
    author: str
    rationale: str
    citing_claim_id: str
    citing_open_question_or_conclusion_id: str
    #: Must be one of the ``retrieved_evidence[].claim_id`` values supplied to the LLM.
    grounding_claim_id: str
    artifact_id: str = ""


class SessionResearchBundle(BaseModel):
    topics: list[GroundedTopicSuggestion] = Field(default_factory=list)
    readings: list[GroundedReadingSuggestion] = Field(default_factory=list)


def _session_cache_path(orch: Any, session_id: str) -> Path:
    d = orch.data_dir / "synthesis" / "research_sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{session_id}.json"


def session_research(
    orch: Any,
    *,
    session_id: str,
    generate: bool = False,
    list_only: bool = False,
) -> str:
    """
    Build or load grounded research suggestions for a session (episode id label).

    When ``generate``, calls the configured LLM with session claims, firm positions,
    drift notes, and open questions; validates citation fields.
    """
    path = _session_cache_path(orch, session_id)
    if list_only and path.is_file():
        return path.read_text(encoding="utf-8")

    claims = [c for c in orch.graph.claims.values() if c.episode_id == session_id]
    firm = [c.text for c in orch.graph.principles.values()][:12]
    drift_txt = ""
    try:
        st = orch.store
        drift_txt = "\n".join(
            f"- {d.natural_language_summary or d.notes}"
            for d in st.list_drift_events(limit=40)
            if session_id in (d.episode_id or "") or session_id in (d.notes or "")
        )
    except Exception:
        pass
    oq_lines = []
    for oq in getattr(orch.conclusions, "open_questions", {}).values():
        oq_lines.append(f"- {oq.summary} ({oq.id})")
    voice_gaps: list[dict[str, str]] = []
    try:
        from noosphere.voices import voice_reading_gaps

        voice_gaps = voice_reading_gaps(orch.store)
    except Exception:
        voice_gaps = []
    ctx = {
        "session": session_id,
        "claims": [{"id": c.id, "text": c.text} for c in claims[:80]],
        "firm_positions": firm,
        "drift": drift_txt,
        "open_questions": oq_lines[:25],
        "voice_reading_gaps": voice_gaps[:25],
    }
    if not generate:
        return json.dumps({"cached": path.is_file(), "context": ctx}, indent=2)

    from noosphere.llm import llm_client_from_settings
    from noosphere.models import ReadingQueueEntry
    from noosphere.retrieval import HybridRetriever

    st = orch.store
    retriever = HybridRetriever()
    try:
        with st.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='retrieval_claim_fts' LIMIT 1"
                )
            ).fetchone()
        if row is None:
            retriever.rebuild(st)
    except Exception:
        retriever.rebuild(st)

    query_bits: list[str] = []
    for c in claims[:5]:
        query_bits.append(c.text)
    if oq_lines:
        query_bits.append(oq_lines[0])
    query_text = "\n".join(query_bits)[:8000]

    q_emb = None
    try:
        q_emb = np.asarray(orch.model.encode(query_text[:2000]), dtype=float)
    except Exception as e:
        logger.warning("session_research_embed_skip", error=str(e))

    hits = retriever.search(st, query_text=query_text, query_embedding=q_emb, top_k=18)
    hit_map = {h.claim_id: h for h in hits}
    ctx["retrieved_evidence"] = [
        {
            "claim_id": h.claim_id,
            "artifact_id": h.artifact_id,
            "chunk_id": h.chunk_id,
            "score": h.score,
            "origin": h.claim_origin,
            "text": h.text[:900],
        }
        for h in hits
    ]
    allowed_grounding = set(hit_map.keys())
    if not allowed_grounding:
        return json.dumps(
            {
                "error": "no_retrieval_hits",
                "message": "Indexer returned no candidates; broaden corpus or rebuild FTS.",
                "context": ctx,
            },
            indent=2,
        )

    llm = llm_client_from_settings()
    system = (
        "Return JSON only: {\"topics\":[...],\"readings\":[...]} with 3–6 topics and 2–5 readings. "
        "Each topic MUST include citing_claim_id and citing_open_question_or_conclusion_id from the session block. "
        "Each reading MUST include citing_claim_id, citing_open_question_or_conclusion_id, AND grounding_claim_id "
        "where grounding_claim_id is copied EXACTLY from one of retrieved_evidence[].claim_id. "
        "Also set artifact_id on each reading to the matching retrieved_evidence[].artifact_id for that grounding_claim_id. "
        "Do not invent titles for papers that are not evidenced by retrieved_evidence text; paraphrase only what you see there."
    )
    user = json.dumps(ctx, indent=2)
    raw = llm.complete(system=system, user=user, max_tokens=2500, temperature=0.25)
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return json.dumps({"error": "no_json", "raw": raw[:500]})
    data = json.loads(m.group(0))
    try:
        bundle = SessionResearchBundle.model_validate(
            {
                "topics": data.get("topics", [])[:7],
                "readings": data.get("readings", [])[:5],
            }
        )
        for t in bundle.topics:
            if not t.citing_claim_id or not t.citing_open_question_or_conclusion_id:
                raise ValueError("topic missing citations")
        fixed_readings: list[GroundedReadingSuggestion] = []
        for r in bundle.readings:
            if not r.citing_claim_id or not r.citing_open_question_or_conclusion_id:
                raise ValueError("reading missing session citations")
            if not r.grounding_claim_id or r.grounding_claim_id not in allowed_grounding:
                raise ValueError("reading missing or invalid grounding_claim_id")
            hit = hit_map.get(r.grounding_claim_id)
            if hit and not r.artifact_id:
                fixed_readings.append(r.model_copy(update={"artifact_id": hit.artifact_id}))
            else:
                fixed_readings.append(r)
        bundle = SessionResearchBundle(topics=bundle.topics, readings=fixed_readings)
        out = bundle.model_dump_json(indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "raw": raw[:1200]})
    path.write_text(out, encoding="utf-8")
    logger.info("session_research_saved", session=session_id, path=str(path))
    try:
        bundle_saved = SessionResearchBundle.model_validate_json(path.read_text(encoding="utf-8"))
        for r in bundle_saved.readings:
            hit = hit_map.get(r.grounding_claim_id)
            aid = r.artifact_id or (hit.artifact_id if hit else "")
            entry = ReadingQueueEntry(
                session_id=session_id,
                grounding_claim_id=r.grounding_claim_id,
                artifact_id=aid,
                title=r.title,
                author=r.author,
                rationale=r.rationale,
            )
            st.put_reading_queue_entry(entry)
    except Exception as e:
        logger.warning("reading_queue_append_failed", error=str(e))
    return out

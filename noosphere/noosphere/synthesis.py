"""
Post-Discussion Synthesis Module for the Noosphere System.

After every podcast episode or written input is ingested, this module
produces five outputs:

  1. DISCUSSION SUMMARY — A structured summary of the episode's intellectual
     content: claims made, positions taken, contradictions surfaced, principles
     distilled.

  2. MANUSCRIPT UPDATE — Appends a new chapter/section to a running book
     manuscript that accumulates across all discussions. Each discussion refines
     and extends the manuscript rather than simply appending raw material.

  3. NEXT QUESTIONS — Generates the next set of questions for future episodes
     based on what was discussed, what contradictions remain unresolved, and
     what regions of the embedding space remain unexplored.

  4. SOURCE RECOMMENDATIONS — Maps discussed ideas to relevant readings using
     embedding-space proximity to a curated source catalogue, and specifically
     targets sources that address geometrically-detected contradictions.

  5. CONTRADICTION REPORT — Identifies principle pairs whose embedding
     difference vectors exhibit high Hoyer sparsity (the Embedding Geometry
     Conjecture's signature of logical contradiction) and recommends
     intellectual strategies for resolution.

All outputs are persisted as Markdown files in the Noosphere data directory
under a `synthesis/` subfolder, with the manuscript maintained as a single
growing document.
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np

from noosphere.models import (
    Claim,
    Conclusion,
    Principle,
    Episode,
    CoherenceReport,
    FounderProfile,
    InputSourceType,
)

from noosphere.observability import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SynthesisPipelineRun:
    """Outcome of ``run_synthesis_pipeline`` (persisted rows and optional dry-run previews)."""

    persisted_count: int
    preview_conclusions: list[Conclusion]


# ── Source Catalogue ─────────────────────────────────────────────────────────

# Curated sources with topic descriptors for embedding-based matching.
# Each entry will be embedded and compared against discussed content.
# This list is extensible — founders can add sources via the catalogue file.

DEFAULT_SOURCE_CATALOGUE = [
    {
        "title": "Discourse on the Method",
        "author": "René Descartes",
        "year": 1637,
        "topic": "Rules for directing inquiry. Foundational meta-methodology. Four rules: accept nothing without evidence, divide problems, build simple to complex, enumerate completely.",
    },
    {
        "title": "How to Solve It",
        "author": "George Pólya",
        "year": 1945,
        "topic": "Heuristic method for problem-solving. Analogy, generalisation, specialisation, variation, decomposition as meta-methodological tools.",
    },
    {
        "title": "The Logic of Scientific Discovery",
        "author": "Karl Popper",
        "year": 1934,
        "topic": "Falsifiability as demarcation criterion. Methods evaluated by their capacity to be proven wrong. Corroboration without verification.",
    },
    {
        "title": "The Structure of Scientific Revolutions",
        "author": "Thomas Kuhn",
        "year": 1962,
        "topic": "Paradigm shifts, normal science, anomalies. Methods are not paradigm-independent. Incommensurability of competing frameworks.",
    },
    {
        "title": "The Methodology of Scientific Research Programmes",
        "author": "Imre Lakatos",
        "year": 1978,
        "topic": "Progressive vs degenerating research programmes. Hard core and protective belt. Novel predictions as criterion of progress.",
    },
    {
        "title": "Progress and Its Problems",
        "author": "Larry Laudan",
        "year": 1977,
        "topic": "Problem-solving effectiveness as progress criterion. Reticulated model of aims, methods, theories. Rationality is coherence across the triad.",
    },
    {
        "title": "Statistical Inference as Severe Testing",
        "author": "Deborah Mayo",
        "year": 2018,
        "topic": "Severity principle. Evidence supports a claim only if the test would probably have detected falsity. Error-statistical philosophy.",
    },
    {
        "title": "Against Method",
        "author": "Paul Feyerabend",
        "year": 1975,
        "topic": "Methodological anarchism. Every rule has been productively violated. Anything goes as description of actual scientific practice.",
    },
    {
        "title": "Probability Theory: The Logic of Science",
        "author": "E.T. Jaynes",
        "year": 2003,
        "topic": "Bayesian reasoning as extension of logic. Probability as degree of belief. Maximum entropy. Prior selection. Cox's theorem.",
    },
    {
        "title": "Causality",
        "author": "Judea Pearl",
        "year": 2009,
        "topic": "Do-calculus for causal inference. Seeing vs doing. Structural causal models. Counterfactual reasoning. Confounding.",
    },
    {
        "title": "The Beginning of Infinity",
        "author": "David Deutsch",
        "year": 2011,
        "topic": "Good explanations are hard to vary. Progress is growth of explanatory knowledge. Constructor theory. Optimism about inquiry.",
    },
    {
        "title": "An Introduction to Kolmogorov Complexity and Its Applications",
        "author": "Ming Li & Paul Vitányi",
        "year": 2008,
        "topic": "Algorithmic information theory. Kolmogorov complexity. Solomonoff induction. Minimum description length. Compressibility as simplicity.",
    },
    {
        "title": "Gödel, Escher, Bach",
        "author": "Douglas Hofstadter",
        "year": 1979,
        "topic": "Self-reference, strange loops, limits of formal systems. Gödel's incompleteness. Recursive structures. Meta-level reasoning.",
    },
    {
        "title": "The Black Swan",
        "author": "Nassim Taleb",
        "year": 2007,
        "topic": "Tail risks, fat-tailed distributions, fragility of models. Narrative fallacy. Domain dependence. Mediocristan vs Extremistan.",
    },
    {
        "title": "Antifragile",
        "author": "Nassim Taleb",
        "year": 2012,
        "topic": "Systems that gain from disorder. Optionality. Via negativa. Skin in the game. Robustness beyond fragility.",
    },
    {
        "title": "Personal Knowledge",
        "author": "Michael Polanyi",
        "year": 1958,
        "topic": "Tacit knowledge. We know more than we can tell. Limits of formalisation. Indwelling. The personal coefficient in all knowing.",
    },
]


# ── Helper: LLM Prompt Dispatch ──────────────────────────────────────────────

def _call_llm(prompt: str, system: str = "", max_tokens: int = 4000) -> str:
    """
    Call an LLM to generate text.

    Tries OpenAI API first (GPT-4o), falls back to a local summary.
    In production, this should be configurable to use Claude, local models, etc.
    """
    import os

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
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
            logger.warning(f"LLM call failed: {e}; using fallback")

    # Fallback: return the prompt context as-is for manual processing
    return f"[LLM unavailable — raw context below]\n\n{prompt[:3000]}"


# ═══════════════════════════════════════════════════════════════════════════════
# SynthesisEngine
# ═══════════════════════════════════════════════════════════════════════════════


class SynthesisEngine:
    """
    Produces post-discussion synthesis outputs.

    Initialised with references to the orchestrator's sub-modules so it can
    read the current state of the graph, principles, contradictions, and
    embedding space without duplicating any data.
    """

    def __init__(
        self,
        data_dir: Path,
        graph,                # OntologyGraph
        geometry,             # EmbeddingAnalyzer
        model,                # SentenceTransformer
        founder_registry,     # FounderRegistry
        conclusions_registry, # ConclusionsRegistry
    ):
        self.data_dir = data_dir
        self.synthesis_dir = data_dir / "synthesis"
        self.synthesis_dir.mkdir(parents=True, exist_ok=True)

        self.graph = graph
        self.geometry = geometry
        self.model = model
        self.founder_registry = founder_registry
        self.conclusions = conclusions_registry

        # Load or initialise source catalogue
        self.catalogue_path = data_dir / "source_catalogue.json"
        self.source_catalogue = self._load_catalogue()
        self._source_embeddings: Optional[np.ndarray] = None

        # Manuscript path — single growing document
        self.manuscript_path = self.synthesis_dir / "manuscript.md"

    # ── Source Catalogue ─────────────────────────────────────────────────────

    def _load_catalogue(self) -> list[dict]:
        """Load source catalogue from disk, or initialise with defaults."""
        if self.catalogue_path.exists():
            with open(self.catalogue_path, "r") as f:
                return json.load(f)
        # Initialise
        with open(self.catalogue_path, "w") as f:
            json.dump(DEFAULT_SOURCE_CATALOGUE, f, indent=2)
        return DEFAULT_SOURCE_CATALOGUE.copy()

    def _get_source_embeddings(self) -> np.ndarray:
        """Embed all source topics. Cached after first call."""
        if self._source_embeddings is None:
            topics = [s["topic"] for s in self.source_catalogue]
            self._source_embeddings = self.model.encode(topics)
        return self._source_embeddings

    def add_source(self, title: str, author: str, year: int, topic: str) -> None:
        """Add a source to the catalogue and clear the embedding cache."""
        self.source_catalogue.append({
            "title": title, "author": author, "year": year, "topic": topic,
        })
        self._source_embeddings = None  # invalidate cache
        with open(self.catalogue_path, "w") as f:
            json.dump(self.source_catalogue, f, indent=2)

    # ── 1. Discussion Summary ────────────────────────────────────────────────

    def generate_summary(
        self,
        episode: Episode,
        claims: list[Claim],
        new_principles: list[Principle],
        contradictions: list[tuple[Principle, Principle, float]],
        method_count: int,
        substance_count: int,
    ) -> str:
        """
        Generate a structured summary of a single discussion.

        Returns the summary as Markdown text and saves it to disk.
        """
        # Build context for the LLM
        claim_texts = [c.text for c in claims[:50]]  # cap for prompt size
        principle_texts = [p.text for p in new_principles[:20]]
        contradiction_texts = [
            f"TENSION: '{a.text}' vs '{b.text}' (sparsity: {s:.3f})"
            for a, b, s in contradictions[:10]
        ]

        # Identify speakers / founders
        speakers = set()
        for c in claims:
            if c.speaker:
                speakers.add(c.speaker.name)

        prompt = f"""You are the intellectual secretary of Theseus, a firm dedicated to meta-methodological epistemology. Produce a structured summary of the following discussion.

EPISODE: {episode.title} (#{episode.number}, {episode.date})
SPEAKERS: {', '.join(speakers) if speakers else 'Unknown'}
TOTAL CLAIMS: {len(claims)} ({method_count} methodological, {substance_count} substantive)

KEY CLAIMS (sample):
{chr(10).join('- ' + t for t in claim_texts[:30])}

PRINCIPLES DISTILLED:
{chr(10).join('- ' + t for t in principle_texts)}

CONTRADICTIONS DETECTED:
{chr(10).join('- ' + t for t in contradiction_texts) if contradiction_texts else '- None detected'}

Write the summary in the following structure:
1. ONE-PARAGRAPH OVERVIEW — What was this conversation about, at the highest level?
2. KEY POSITIONS — The settled positions that emerged, attributed to specific speakers where possible.
3. METHODOLOGICAL INSIGHTS — Any second- or third-order observations about HOW the speakers reasoned, not just WHAT they concluded.
4. UNRESOLVED TENSIONS — Contradictions or open questions that remain after the discussion.
5. CONNECTIONS TO PRIOR DISCUSSIONS — How this discussion relates to or extends the firm's existing principles.

Be precise. Attribute ideas to specific speakers. Do not pad with generic praise."""

        summary = _call_llm(prompt, system="You produce rigorous intellectual summaries. No filler.")

        # Save
        filename = f"summary_ep{episode.number}_{episode.date.isoformat()}.md"
        filepath = self.synthesis_dir / filename
        header = f"# Discussion Summary: {episode.title}\n\n"
        header += f"**Episode {episode.number}** | {episode.date} | "
        header += f"{len(claims)} claims | {len(new_principles)} principles\n\n---\n\n"
        full_text = header + summary

        with open(filepath, "w") as f:
            f.write(full_text)

        logger.info(f"Summary saved to {filepath}")
        return full_text

    # ── 2. Manuscript Update ─────────────────────────────────────────────────

    def update_manuscript(
        self,
        episode: Episode,
        summary: str,
        new_principles: list[Principle],
        all_principles: list[Principle],
    ) -> str:
        """
        Update the running book manuscript with material from this discussion.

        The manuscript is NOT a concatenation of summaries. Each update:
        - Identifies where the new material fits thematically
        - Adds a new section for genuinely new territory
        - Refines existing sections where the discussion deepened prior themes
        - Maintains a coherent narrative arc across all discussions

        Returns the updated manuscript text.
        """
        # Load existing manuscript
        existing = ""
        if self.manuscript_path.exists():
            with open(self.manuscript_path, "r") as f:
                existing = f.read()

        # Build the principle landscape for thematic context
        principle_landscape = "\n".join(
            f"- [{p.id[:8]}] {p.text} (conviction: {p.conviction_score:.2f})"
            for p in sorted(all_principles, key=lambda x: x.conviction_score, reverse=True)[:40]
        )

        new_principle_texts = "\n".join(
            f"- {p.text}" for p in new_principles[:20]
        )

        prompt = f"""You are the editor of an evolving intellectual manuscript for Theseus, a firm building a meta-methodological theory of inquiry. The manuscript grows with each discussion, becoming more refined and comprehensive over time.

EXISTING MANUSCRIPT:
---
{existing[:6000] if existing else '[This is the first entry. Create the manuscript structure.]'}
---

NEW DISCUSSION: {episode.title} (Episode {episode.number}, {episode.date})

NEW SUMMARY:
{summary[:3000]}

NEW PRINCIPLES DISTILLED:
{new_principle_texts}

FULL PRINCIPLE LANDSCAPE (top 40 by conviction):
{principle_landscape}

INSTRUCTIONS:
1. If this is the first entry, create the manuscript with a title, introduction, and the first chapter based on this discussion.
2. If the manuscript exists, integrate the new material:
   a. Add a new SECTION (not chapter) for genuinely new intellectual territory.
   b. REFINE existing sections where this discussion deepened or clarified prior themes.
   c. Add new footnotes or asides where the discussion contradicted or complicated prior material.
   d. Update the introduction if the manuscript's scope has expanded.
3. The manuscript should read as a coherent book-in-progress, NOT as a log of discussions.
4. Maintain an academic but accessible tone. Cite specific speakers where appropriate.
5. Every chapter/section should have a clear thesis, not just a topic.
6. Output the COMPLETE updated manuscript (not just the new additions).

The manuscript should grow in depth and quality with each discussion, not just in length."""

        updated = _call_llm(prompt, system="You are an expert academic editor producing a book manuscript.", max_tokens=8000)

        # Save
        with open(self.manuscript_path, "w") as f:
            f.write(updated)

        logger.info(f"Manuscript updated ({len(updated)} chars)")
        return updated

    # ── 3. Next Questions ────────────────────────────────────────────────────

    def generate_next_questions(
        self,
        episode: Episode,
        claims: list[Claim],
        contradictions: list[tuple[Principle, Principle, float]],
        all_principles: list[Principle],
    ) -> str:
        """
        Generate the next set of discussion questions based on:
        - What was discussed (to deepen, not repeat)
        - What contradictions remain unresolved
        - What regions of the embedding space are underexplored

        Returns Markdown text with the questions.
        """
        # Find underexplored regions: principles with low conviction or few mentions
        underexplored = [
            p for p in all_principles
            if p.conviction_score < 0.4 or p.mention_count <= 1
        ]
        underexplored_texts = [p.text for p in underexplored[:10]]

        # Find high-conviction principles that were NOT discussed this episode
        episode_claim_texts = set(c.text[:80] for c in claims)
        undiscussed_strong = [
            p for p in all_principles
            if p.conviction_score > 0.7
            and not any(ct in p.text[:80] for ct in episode_claim_texts)
        ]

        contradiction_texts = [
            f"'{a.text}' CONTRADICTS '{b.text}' (geometric sparsity: {s:.3f})"
            for a, b, s in contradictions[:8]
        ]

        prompt = f"""You are the intellectual director of Theseus's podcast. Based on the latest discussion and the current state of the firm's knowledge, generate 5-8 questions for the NEXT discussion.

LAST DISCUSSION: {episode.title} (Episode {episode.number})
CLAIMS MADE: {len(claims)}

UNRESOLVED CONTRADICTIONS (detected via embedding geometry):
{chr(10).join('- ' + t for t in contradiction_texts) if contradiction_texts else '- None currently detected'}

UNDEREXPLORED PRINCIPLES (low conviction or few mentions):
{chr(10).join('- ' + t for t in underexplored_texts) if underexplored_texts else '- None — all principles well-explored'}

HIGH-CONVICTION PRINCIPLES NOT DISCUSSED THIS EPISODE:
{chr(10).join('- ' + p.text for p in undiscussed_strong[:8]) if undiscussed_strong else '- None'}

INSTRUCTIONS:
1. At least 2 questions should target UNRESOLVED CONTRADICTIONS — force the speakers to confront tensions in their own framework.
2. At least 1 question should probe UNDEREXPLORED territory — regions of the intellectual space the firm has mentioned but not developed.
3. At least 1 question should DEEPEN a theme from the latest discussion — push beyond where the conversation stopped.
4. At least 1 question should be a STRESS TEST — a question that would be uncomfortable to answer honestly.
5. Each question should include a brief note (in parentheses) explaining WHY this question matters now.
6. Questions should be philosophical and open-ended, suitable for a podcast. They should provoke, not quiz.
7. Label each question with a category: e.g., "On contradiction resolution", "On unexplored territory", "On deepening", "On stress-testing"."""

        questions = _call_llm(prompt, system="You generate profound, discussion-sparking philosophical questions.")

        # Save
        filename = f"next_questions_after_ep{episode.number}.md"
        filepath = self.synthesis_dir / filename
        header = f"# Next Questions (after Episode {episode.number}: {episode.title})\n\n"
        header += f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n---\n\n"
        full_text = header + questions

        with open(filepath, "w") as f:
            f.write(full_text)

        logger.info(f"Next questions saved to {filepath}")
        return full_text

    # ── 4. Source Recommendations ────────────────────────────────────────────

    def recommend_sources(
        self,
        claims: list[Claim],
        contradictions: list[tuple[Principle, Principle, float]],
        top_k: int = 8,
    ) -> str:
        """
        Recommend sources by embedding proximity to discussed content,
        with special attention to sources that address detected contradictions.

        Uses the curated source catalogue, embedded and compared against:
        1. The centroid of this episode's claim embeddings (general relevance)
        2. The difference vectors of contradiction pairs (targeted resolution)
        """
        source_embs = self._get_source_embeddings()
        recommendations: list[dict] = []
        seen_titles: set[str] = set()

        # ── General relevance: match against episode centroid ────────────
        claim_embs = []
        for c in claims:
            if c.embedding:
                claim_embs.append(np.array(c.embedding))
            else:
                try:
                    emb = self.model.encode(c.text)
                    claim_embs.append(emb)
                except Exception:
                    pass

        if claim_embs:
            centroid = np.mean(claim_embs, axis=0)
            # Cosine similarities
            norms = np.linalg.norm(source_embs, axis=1) * np.linalg.norm(centroid)
            norms = np.where(norms == 0, 1e-8, norms)
            sims = source_embs @ centroid / norms
            top_indices = np.argsort(sims)[::-1][:top_k]

            for idx in top_indices:
                src = self.source_catalogue[idx]
                if src["title"] not in seen_titles:
                    recommendations.append({
                        **src,
                        "reason": "general_relevance",
                        "similarity": float(sims[idx]),
                    })
                    seen_titles.add(src["title"])

        # ── Contradiction-targeted: match against difference vectors ─────
        for princ_a, princ_b, sparsity in contradictions[:5]:
            if not (princ_a.embedding and princ_b.embedding):
                continue
            emb_a = np.array(princ_a.embedding)
            emb_b = np.array(princ_b.embedding)

            # The midpoint of the contradiction pair represents the
            # *topic* of the tension; sources near this point are relevant
            midpoint = (emb_a + emb_b) / 2
            norms = np.linalg.norm(source_embs, axis=1) * np.linalg.norm(midpoint)
            norms = np.where(norms == 0, 1e-8, norms)
            sims = source_embs @ midpoint / norms
            best_idx = int(np.argmax(sims))

            src = self.source_catalogue[best_idx]
            if src["title"] not in seen_titles:
                recommendations.append({
                    **src,
                    "reason": "contradiction_resolution",
                    "similarity": float(sims[best_idx]),
                    "addresses_tension": f"'{princ_a.text[:60]}...' vs '{princ_b.text[:60]}...'",
                })
                seen_titles.add(src["title"])

        # Sort: contradiction-resolution sources first, then by similarity
        recommendations.sort(
            key=lambda r: (0 if r["reason"] == "contradiction_resolution" else 1, -r["similarity"])
        )

        # Format as Markdown
        lines = []
        for r in recommendations:
            entry = f"### {r['author']} — *{r['title']}* ({r['year']})\n\n"
            entry += f"**Relevance:** {r['topic'][:200]}\n\n"
            if r["reason"] == "contradiction_resolution":
                entry += f"**Addresses tension:** {r.get('addresses_tension', 'N/A')}\n\n"
            entry += f"*Match score: {r['similarity']:.3f}*\n"
            lines.append(entry)

        return "\n---\n\n".join(lines)

    # ── 5. Contradiction Report ──────────────────────────────────────────────

    def generate_contradiction_report(
        self,
        contradictions: list[tuple[Principle, Principle, float]],
    ) -> str:
        """
        Produce a detailed report on geometrically-detected contradictions
        with strategies for resolution.
        """
        if not contradictions:
            return "No contradictions currently detected in the principle graph."

        entries = []
        for i, (a, b, sparsity) in enumerate(contradictions, 1):
            # Identify contributing founders
            founders_a = ", ".join(a.endorsing_founders) if a.endorsing_founders else "unattributed"
            founders_b = ", ".join(b.endorsing_founders) if b.endorsing_founders else "unattributed"

            entry = f"""### Contradiction {i} (Hoyer sparsity: {sparsity:.4f})

**Principle A** (endorsed by {founders_a}):
> {a.text}

**Principle B** (endorsed by {founders_b}):
> {b.text}

**Conviction levels:** A = {a.conviction_score:.2f}, B = {b.conviction_score:.2f}

**Geometric signature:** The difference vector between these principles' embeddings exhibits sparsity {sparsity:.4f}, concentrated in a small number of dimensions. This is the hallmark of logical contradiction as opposed to mere topical divergence (which produces dense, distributed differences)."""

            entries.append(entry)

        # Ask LLM for resolution strategies if available
        contradiction_block = "\n\n".join(entries)
        prompt = f"""The following contradictions have been detected in a philosophical knowledge system via embedding geometry analysis. For each, suggest a resolution strategy: is this a genuine logical contradiction, a terminological ambiguity, a domain-boundary issue (the principles are both correct but in different domains), or something else? Suggest what questions or readings might resolve each tension.

{contradiction_block}

For each contradiction:
1. Classify the type of tension (logical, terminological, domain-boundary, level-of-abstraction, empirical)
2. Suggest a specific question the founders should discuss to resolve it
3. Suggest a reading that addresses this specific type of tension
4. Assess which principle, if either, should be revised"""

        analysis = _call_llm(prompt, system="You are a philosophical analyst specialising in contradiction resolution.")

        full_report = f"# Contradiction Report\n\n"
        full_report += f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
        full_report += f"{len(contradictions)} contradictions detected\n\n---\n\n"
        full_report += contradiction_block
        full_report += f"\n\n---\n\n## Resolution Analysis\n\n{analysis}"

        return full_report

    # ── Master: Run Full Synthesis ───────────────────────────────────────────

    def run_post_discussion_synthesis(
        self,
        episode: Episode,
        claims: list[Claim],
        new_principles: list[Principle],
        method_count: int,
        substance_count: int,
    ) -> dict[str, str]:
        """
        Run the complete post-discussion synthesis pipeline.

        Called by the orchestrator after episode ingestion completes.

        Returns a dict with keys: summary, manuscript, questions, sources,
        contradictions — each containing the output text.
        """
        logger.info(f"=== Running post-discussion synthesis for episode {episode.number} ===")

        # Gather current state
        all_principles = list(self.graph.principles.values())
        contradictions = self.graph.get_contradictions()

        # 1. Summary
        logger.info("Synthesis 1/5: Generating discussion summary...")
        summary = self.generate_summary(
            episode=episode,
            claims=claims,
            new_principles=new_principles,
            contradictions=contradictions,
            method_count=method_count,
            substance_count=substance_count,
        )

        # 2. Manuscript
        logger.info("Synthesis 2/5: Updating manuscript...")
        manuscript = self.update_manuscript(
            episode=episode,
            summary=summary,
            new_principles=new_principles,
            all_principles=all_principles,
        )

        # 3. Next questions
        logger.info("Synthesis 3/5: Generating next questions...")
        questions = self.generate_next_questions(
            episode=episode,
            claims=claims,
            contradictions=contradictions,
            all_principles=all_principles,
        )

        # 4. Source recommendations
        logger.info("Synthesis 4/5: Recommending sources...")
        sources_md = self.recommend_sources(
            claims=claims,
            contradictions=contradictions,
        )
        sources_filename = f"sources_ep{episode.number}.md"
        sources_path = self.synthesis_dir / sources_filename
        sources_header = f"# Recommended Sources (Episode {episode.number}: {episode.title})\n\n"
        sources_header += f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n---\n\n"
        sources_full = sources_header + sources_md
        with open(sources_path, "w") as f:
            f.write(sources_full)

        # 5. Contradiction report
        logger.info("Synthesis 5/5: Generating contradiction report...")
        contra_report = self.generate_contradiction_report(contradictions)
        contra_filename = f"contradictions_ep{episode.number}.md"
        contra_path = self.synthesis_dir / contra_filename
        with open(contra_path, "w") as f:
            f.write(contra_report)

        # 6. Research brief — topics and readings for the next discussion
        logger.info("Synthesis 6/6: Generating research brief...")
        research_brief_text = ""
        try:
            from noosphere.research_advisor import ResearchAdvisor
            advisor = ResearchAdvisor(
                data_dir=self.data_dir,
                graph=self.graph,
                model=self.model,
                conclusions_registry=self.conclusions,
            )
            brief = advisor.generate_research_brief(
                episode=episode,
                claims=claims,
                new_principles=new_principles,
                contradictions=contradictions,
                all_principles=all_principles,
            )
            research_brief_text = brief.preamble
            logger.info(f"  Research brief: {len(brief.topics)} topics proposed")
        except Exception as e:
            logger.error(f"Research brief generation failed (non-fatal): {e}")

        logger.info(f"=== Post-discussion synthesis complete for episode {episode.number} ===")

        return {
            "summary": summary,
            "manuscript": manuscript,
            "questions": questions,
            "sources": sources_full,
            "contradictions": contra_report,
            "research_brief": research_brief_text,
        }


# ── Firm / founder conclusion assembly (meta gates + evidence chain) ────────


def _synthesis_assemble_one(
    pid: str,
    pr: Any,
    claims_by_id: dict[str, Any],
    store: Any | None = None,
) -> tuple[str, Any | None, Any | None]:
    """
    Pure CPU path for one principle. Returns
    (\"skip\", None, None) | (\"oq\", OpenQuestionCandidate, None) | (\"ok\", None, Conclusion).
    """
    import numpy as np

    from noosphere.conclusions import OpenQuestionCandidate
    from noosphere.adversarial import cluster_fingerprint
    from noosphere.config import get_settings
    from noosphere.meta_analysis import ClaimClusterMeta, evaluate_five_meta_criteria
    from noosphere.models import ConfidenceTier, Conclusion

    texts: list[str] = []
    cids: list[str] = []
    for cid in pr.supporting_claims[:40]:
        c = claims_by_id.get(cid)
        if c is None:
            continue
        texts.append(c.text)
        cids.append(cid)
    if len(texts) < 2:
        return ("skip", None, None)
    centroid = pr.embedding
    s = get_settings()
    fp = cluster_fingerprint(pid, sorted(cids))
    adv_fp = fp if s.adversarial_enforce else ""
    adv_store = store if (s.adversarial_enforce and store is not None) else None
    cluster = ClaimClusterMeta(
        claim_ids=cids,
        texts=texts,
        centroid_embedding=list(centroid) if centroid else None,
        claimed_confidence=float(pr.conviction_score),
        domain="methodological_rule",
        adversarial_fingerprint=adv_fp,
        adversarial_store=adv_store,
    )
    meta = evaluate_five_meta_criteria(cluster)
    dissent: list[str] = []
    for c in claims_by_id.values():
        if c.id in cids:
            continue
        if not c.embedding or not centroid:
            continue
        a = np.asarray(c.embedding, dtype=float)
        b = np.asarray(centroid, dtype=float)
        if a.shape != b.shape:
            continue
        sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
        if sim < 0.25:
            dissent.append(c.id)
    if meta.route_open_question:
        oq = OpenQuestionCandidate(
            summary=f"Cluster around principle {pid} failed meta gates.",
            claim_a_id=cids[0],
            claim_b_id=cids[-1] if len(cids) > 1 else cids[0],
            unresolved_reason="; ".join(meta.failed_criteria) or "meta_gate",
            layer_disagreement_summary=str(meta.scores),
        )
        return ("oq", oq, None)
    if not meta.passed_all:
        return ("skip", None, None)
    con = Conclusion(
        text=pr.text,
        confidence_tier=ConfidenceTier.FIRM,
        rationale="; ".join(f"{k}={v:.2f}" for k, v in meta.scores.items()),
        supporting_principle_ids=[pid],
        evidence_chain_claim_ids=cids,
        dissent_claim_ids=dissent[:20],
        confidence=min(0.95, float(pr.conviction_score)),
    )
    if s.calibration_confidence_enabled and store is not None:
        from noosphere.predictive_extractor import author_key_for_claim
        from noosphere.scoring import discount_conclusion_confidence

        domain = "unspecified"
        if pr.disciplines:
            d0 = pr.disciplines[0]
            domain = d0.value if hasattr(d0, "value") else str(d0)
        author = "firm"
        if pr.endorsing_founders:
            author = str(pr.endorsing_founders[0])
        else:
            c0 = claims_by_id.get(cids[0]) if cids else None
            if c0 is not None:
                author = author_key_for_claim(c0)
        adj, note = discount_conclusion_confidence(
            store,
            author_key=author,
            domain=domain,
            stated_confidence=float(con.confidence),
        )
        con = con.model_copy(
            update={"calibration_adjusted_confidence": adj, "calibration_note": note}
        )
    return ("ok", None, con)


def run_synthesis_pipeline(
    orch: Any,
    *,
    store: Any | None = None,
    claims_by_id: dict[str, Claim] | None = None,
    dry_run: bool = False,
) -> SynthesisPipelineRun:
    """
    Assemble firm-level ``Conclusion`` rows from principle clusters + graph claims,
    respecting five-criterion meta gates. Writes to SQL ``Store`` when ``dry_run`` is false.

    When ``claims_by_id`` is set (e.g. temporal replay), assembly uses that dict instead of
    the full in-memory graph claims.
    """
    from noosphere.adversarial import cluster_fingerprint
    from noosphere.config import get_settings
    from noosphere.store import Store

    st = store or Store.from_database_url(get_settings().database_url)
    written = 0
    preview: list[Conclusion] = []
    claims_by_id = claims_by_id if claims_by_id is not None else dict(orch.graph.claims)
    items = list(orch.graph.principles.items())
    max_workers = int(os.environ.get("THESEUS_SYNTHESIS_MAX_WORKERS", "1"))
    if max_workers < 1:
        max_workers = 1

    results: list[tuple[str, Any | None, Any | None]] = []
    if max_workers == 1 or len(items) < 4:
        for pid, pr in items:
            results.append(_synthesis_assemble_one(pid, pr, claims_by_id, st))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {
                ex.submit(_synthesis_assemble_one, pid, pr, claims_by_id, st): pid
                for pid, pr in items
            }
            for fut in as_completed(futs):
                results.append(fut.result())

    for kind, oq, con in results:
        if kind == "oq" and oq is not None:
            if not dry_run:
                orch.conclusions.register_open_question(oq)
        elif kind == "ok" and con is not None:
            if dry_run:
                preview.append(con)
            else:
                st.put_conclusion(con)
                pid0 = con.supporting_principle_ids[0] if con.supporting_principle_ids else "none"
                fp0 = cluster_fingerprint(pid0, sorted(con.evidence_chain_claim_ids))
                st.link_adversarial_fingerprint_to_conclusion(fp0, con.id)
                written += 1
    out_dir = orch.data_dir / "synthesis" / "assembly"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "last_run.json").write_text(
        json.dumps(
            {
                "written": written,
                "principles_scanned": len(orch.graph.principles),
                "dry_run": dry_run,
            }
        ),
        encoding="utf-8",
    )
    logger.info("synthesis_assembly_complete", written=written, dry_run=dry_run)
    return SynthesisPipelineRun(persisted_count=written, preview_conclusions=preview)

"""
Orchestrator for the Noosphere system — The Brain of the Firm.

This module ties all sub-modules together into a coherent pipeline.
The critical architectural principle: the brain stores ONLY methodological
knowledge (how to think). Substantive conclusions (what the founders think
is true) are routed to a separate Conclusions Registry for calibration.

Pipeline:
  Transcript → Parse → Extract Claims → Classify (method/substance) →
  Route methodological claims to Ontology Graph →
  Route substantive claims to Conclusions Registry →
  Run meta-analysis on substantive discourse →
  Promote methodological observations to the Graph →
  Track temporal evolution → Run coherence checks → Persist

All sub-module constructors and method names match their actual
implementations as of 2026-04-11.
"""

from __future__ import annotations

import json
import os
import uuid
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Any

import numpy as np
import structlog.contextvars

from noosphere.models import (
    Claim, Discipline, Episode, InferenceQuery, InferenceResult,
    Principle, CoherenceReport, TemporalSnapshot, ConvictionLevel,
    Speaker, Relationship, RelationType, FounderProfile,
    InputSource, InputSourceType,
)

from noosphere.config import get_settings
from noosphere.observability import configure_logging, get_logger

logger = get_logger(__name__)


# ── Default Configuration ────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "model_name": "",  # filled from settings when empty
    "model_device": "cpu",
    "coherence_weights": {
        "s1_consistency": 0.25,
        "s2_argumentation": 0.10,
        "s3_probabilistic": 0.15,
        "s4_geometric": 0.15,
        "s5_compression": 0.10,
        "s6_llm_judge": 0.25,
    },
    "clustering_distance_threshold": 0.3,
    "min_observation_confidence_for_promotion": 0.75,
}


class NoosphereOrchestrator:
    """
    Central orchestrator for the Noosphere knowledge system.

    The orchestrator owns two stores:
      1. The Ontology Graph (methodological principles only)
      2. The Conclusions Registry (substantive claims for calibration)

    The Discourse Classifier determines which store receives each claim.
    The Meta-Analytical Layer generates methodological observations from
    substantive discourse and promotes the best ones to the Graph.
    """

    def __init__(self, data_dir: str | None = None):
        settings = get_settings()
        configure_logging(level=settings.log_level, json_format=True)
        base = Path(data_dir) if data_dir else settings.data_dir
        self.data_dir = base
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Config
        self.config_path = self.data_dir / "noosphere_config.json"
        self.config = self._load_config()
        if not self.config.get("model_name"):
            self.config["model_name"] = settings.embedding_model_name
        if not self.config.get("model_device"):
            self.config["model_device"] = settings.embedding_device

        # Shared SBERT model (loaded once, used everywhere)
        self._model = None  # lazy

        # Sub-modules (all lazy-loaded)
        self._graph = None
        self._persistence = None
        self._distiller = None
        self._ingester = None
        self._classifier = None
        self._conclusions = None
        self._meta_analyzer = None
        self._monitor = None
        self._geometry = None
        self._founder_registry = None
        self._source_registry = None
        self._written_processor = None
        self._founder_analyser = None
        self._synthesis_engine = None
        self._research_advisor = None

        # Temporal state
        self.snapshots: list[TemporalSnapshot] = []
        self.episodes: dict[str, Episode] = {}
        self._store = None

        # Load existing graph if available
        self._load_existing_graph()

        logger.info("noosphere_orchestrator_initialized", data_dir=str(self.data_dir))

    # ── Config ───────────────────────────────────────────────────────────────

    def _load_config(self) -> dict[str, Any]:
        if self.config_path.exists():
            with open(self.config_path, "r") as f:
                return json.load(f)
        self._save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    def _save_config(self, config: dict[str, Any]) -> None:
        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=2)

    # ── Lazy-loaded sub-modules ──────────────────────────────────────────────

    @property
    def model(self):
        """Shared SBERT model, loaded once."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            name = self.config.get("model_name") or get_settings().embedding_model_name
            device = self.config.get("model_device", "cpu")
            logger.info("loading_sbert", model=name)
            self._model = SentenceTransformer(name, device=device)
        return self._model

    @property
    def graph(self):
        """The Ontology Graph — stores methodological principles only."""
        if self._graph is None:
            from noosphere.ontology import OntologyGraph
            self._graph = OntologyGraph()
        return self._graph

    @property
    def persistence(self):
        """Graph persistence layer."""
        if self._persistence is None:
            from noosphere.ontology import GraphPersistence
            self._persistence = GraphPersistence(self.graph)
        return self._persistence

    @property
    def distiller(self):
        """Principle distiller — clusters claims into principles."""
        if self._distiller is None:
            from noosphere.ontology import PrincipleDistiller
            self._distiller = PrincipleDistiller(graph=self.graph)
        return self._distiller

    @property
    def ingester(self):
        """Transcript ingester — parses and extracts claims."""
        if self._ingester is None:
            from noosphere.ingester import TranscriptIngester
            self._ingester = TranscriptIngester()
        return self._ingester

    @property
    def classifier(self):
        """Discourse classifier — separates methodology from substance."""
        if self._classifier is None:
            from noosphere.classifier import DiscourseClassifier
            self._classifier = DiscourseClassifier()
        return self._classifier

    @property
    def conclusions(self):
        """Conclusions registry — tracks substantive claims for calibration."""
        if self._conclusions is None:
            from noosphere.conclusions import ConclusionsRegistry
            path = str(self.data_dir / "conclusions_registry.json")
            self._conclusions = ConclusionsRegistry(data_path=path)
        return self._conclusions

    @property
    def store(self):
        """SQLite store (claims, conclusions, drift, coherence cache)."""
        if self._store is None:
            from noosphere.store import Store

            self._store = Store.from_database_url(get_settings().database_url)
        return self._store

    @property
    def meta_analyzer(self):
        """Meta-analytical layer — extracts methodology from substance."""
        if self._meta_analyzer is None:
            from noosphere.meta_analysis import MetaAnalyzer
            self._meta_analyzer = MetaAnalyzer(
                conclusions_registry=self.conclusions
            )
        return self._meta_analyzer

    @property
    def geometry(self):
        """Embedding geometry analyzer."""
        if self._geometry is None:
            from noosphere.geometry import EmbeddingAnalyzer
            self._geometry = EmbeddingAnalyzer()
        return self._geometry

    @property
    def founder_registry(self):
        """Founder registry — maps speakers to stable profiles."""
        if self._founder_registry is None:
            from noosphere.founders import FounderRegistry
            path = str(self.data_dir / "founders_registry.json")
            self._founder_registry = FounderRegistry(data_path=path)
        return self._founder_registry

    @property
    def source_registry(self):
        """Input source registry — provenance for all ingested material."""
        if self._source_registry is None:
            from noosphere.founders import InputSourceRegistry
            path = str(self.data_dir / "input_sources.json")
            self._source_registry = InputSourceRegistry(data_path=path)
        return self._source_registry

    @property
    def written_processor(self):
        """Processor for written inputs (essays, memos, notes)."""
        if self._written_processor is None:
            from noosphere.founders import WrittenInputProcessor
            self._written_processor = WrittenInputProcessor(
                founder_registry=self.founder_registry,
                source_registry=self.source_registry,
            )
        return self._written_processor

    @property
    def founder_analyser(self):
        """Analytical engine for inter-founder dynamics."""
        if self._founder_analyser is None:
            from noosphere.founders import FounderAnalyser
            self._founder_analyser = FounderAnalyser(
                registry=self.founder_registry,
            )
        return self._founder_analyser

    @property
    def synthesis(self):
        """Post-discussion synthesis engine."""
        if self._synthesis_engine is None:
            from noosphere.synthesis import SynthesisEngine
            self._synthesis_engine = SynthesisEngine(
                data_dir=self.data_dir,
                graph=self.graph,
                geometry=self.geometry,
                model=self.model,
                founder_registry=self.founder_registry,
                conclusions_registry=self.conclusions,
            )
        return self._synthesis_engine

    @property
    def research_advisor(self):
        """Post-discussion research advisor — topic and reading suggestions."""
        if self._research_advisor is None:
            from noosphere.research_advisor import ResearchAdvisor
            self._research_advisor = ResearchAdvisor(
                data_dir=self.data_dir,
                graph=self.graph,
                model=self.model,
                conclusions_registry=self.conclusions,
            )
        return self._research_advisor

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load_existing_graph(self) -> None:
        graph_path = self.data_dir / "graph.json"
        if graph_path.exists():
            try:
                from noosphere.ontology import GraphPersistence
                # Must init graph first, then persistence loads into it
                _ = self.graph
                self._persistence = GraphPersistence(self.graph)
                self._persistence.load_from_json(str(graph_path))
                logger.info(
                    f"Loaded graph: {len(self.graph.principles)} principles, "
                    f"{len(self.graph.claims)} claims"
                )
            except Exception as e:
                logger.error(f"Failed to load graph: {e}")

    def _save_all(self) -> None:
        """Persist graph, conclusions, and snapshots."""
        # Graph
        graph_path = self.data_dir / "graph.json"
        try:
            self.persistence.save_to_json(str(graph_path))
            logger.info(f"Saved graph to {graph_path}")
        except Exception as e:
            logger.error(f"Failed to save graph: {e}")

        # Conclusions
        try:
            self.conclusions.save()
            logger.info("Saved conclusions registry")
        except Exception as e:
            logger.error(f"Failed to save conclusions: {e}")

        # Founders
        try:
            self.founder_registry.save()
            self.source_registry.save()
            logger.info("Saved founder and source registries")
        except Exception as e:
            logger.error(f"Failed to save founder data: {e}")

        # Snapshots
        snapshots_path = self.data_dir / "snapshots.jsonl"
        try:
            with open(snapshots_path, "w") as f:
                for s in self.snapshots:
                    f.write(s.model_dump_json() + "\n")
        except Exception as e:
            logger.error(f"Failed to save snapshots: {e}")

    # ── Main Pipeline: Ingest Episode ────────────────────────────────────────

    def ingest_episode(
        self,
        transcript_path: str,
        episode_number: int,
        episode_date: date,
        title: str = "",
        speakers: Optional[list[str]] = None,
    ) -> Episode:
        """
        Full pipeline with methodology/substance separation.

        Steps:
          1. Parse transcript and extract raw claims
          2. Classify each claim (METHODOLOGICAL / SUBSTANTIVE / MIXED / etc.)
          3. Route methodological claims to the Ontology Graph
          4. Route substantive claims to the Conclusions Registry
          5. Decompose MIXED claims and route each component
          6. Run meta-analysis on substantive discourse
          7. Promote high-confidence methodological observations to Graph
          8. Record temporal snapshots
          9. Persist everything

        Returns:
            Episode metadata.
        """
        with structlog.contextvars.bound_contextvars(
            correlation_id=str(uuid.uuid4())
        ):
            return self._ingest_episode_impl(
                transcript_path,
                episode_number,
                episode_date,
                title,
                speakers,
            )

    def _ingest_episode_impl(
        self,
        transcript_path: str,
        episode_number: int,
        episode_date: date,
        title: str = "",
        speakers: Optional[list[str]] = None,
    ) -> Episode:
        path = Path(transcript_path)
        if not path.exists():
            raise FileNotFoundError(f"Transcript not found: {path}")

        episode_id = f"ep_{episode_number}"
        logger.info(
            "ingest_episode_start", episode_number=episode_number, title=title
        )

        # ── Step 1: Extract raw claims ───────────────────────────────────
        logger.info("Step 1: Parsing transcript and extracting claims...")
        speaker_objects = (
            [Speaker(name=s) for s in speakers] if speakers else None
        )
        claims, episode_meta = self.ingester.ingest(
            transcript_path=str(path),
            episode_number=episode_number,
            episode_date=episode_date,
            episode_title=title,
            speaker_list=speaker_objects,
        )
        logger.info(f"  Extracted {len(claims)} raw claims")

        # ── Step 1b: Register input source and attribute to founders ─────
        logger.info("Step 1b: Attributing claims to founders...")
        source = self.source_registry.register_transcript(
            episode_id=episode_id,
            title=title,
            episode_date=episode_date,
            file_path=str(path),
        )

        # Resolve each claim's speaker to a FounderProfile
        founder_claim_counts: dict[str, int] = defaultdict(int)
        for claim in claims:
            founder = self.founder_registry.resolve_speaker(claim.speaker)
            if founder:
                claim.founder_id = founder.id
                claim.source_type = InputSourceType.TRANSCRIPT
                claim.source_id = source.id
                founder_claim_counts[founder.id] += 1
                self.founder_registry.record_claims(
                    founder_id=founder.id,
                    claims=[claim],
                    source_type=InputSourceType.TRANSCRIPT,
                    episode_date=episode_date,
                )

        logger.info(
            f"  Founders resolved: {len(founder_claim_counts)} active "
            f"({', '.join(self.founder_registry.get_founder(fid).name for fid in founder_claim_counts)})"
        )

        # ── Step 2: Classify each claim ──────────────────────────────────
        logger.info("Step 2: Classifying claims (methodology vs substance)...")
        from noosphere.classifier import DiscourseType

        classified = self.classifier.classify_batch(claims)

        counts = defaultdict(int)
        for cc in classified:
            counts[cc.discourse_type.value] += 1
        logger.info(f"  Classification: {dict(counts)}")

        # ── Step 3-5: Route claims differentially ────────────────────────
        logger.info("Step 3-5: Routing claims...")

        methodological_claims = []
        substantive_claims = []

        for cc in classified:
            original_claim = next(
                (c for c in claims if c.id == cc.claim_id), None
            )
            if original_claim is None:
                continue

            if cc.discourse_type == DiscourseType.METHODOLOGICAL:
                methodological_claims.append(original_claim)

            elif cc.discourse_type == DiscourseType.META_METHODOLOGICAL:
                # Meta-methodological claims are the highest-value methodology
                methodological_claims.append(original_claim)

            elif cc.discourse_type == DiscourseType.SUBSTANTIVE:
                substantive_claims.append(original_claim)
                # Register in conclusions with method attribution
                self._register_conclusion(
                    original_claim, cc, episode_id, episode_date
                )

            elif cc.discourse_type == DiscourseType.MIXED:
                # Decompose: methodological component → graph,
                # substantive component → conclusions
                if cc.methodological_content:
                    method_claim = Claim(
                        text=cc.methodological_content,
                        speaker=original_claim.speaker,
                        episode_id=episode_id,
                        episode_date=episode_date,
                        segment_context=original_claim.segment_context,
                        disciplines=original_claim.disciplines,
                        embedding=original_claim.embedding,
                        confidence=cc.confidence * 0.8,
                        founder_id=original_claim.founder_id,
                        source_type=original_claim.source_type,
                        source_id=original_claim.source_id,
                    )
                    methodological_claims.append(method_claim)

                if cc.substantive_content:
                    substantive_claims.append(original_claim)
                    self._register_conclusion(
                        original_claim, cc, episode_id, episode_date
                    )

            # NON_PROPOSITIONAL → discard

        logger.info(
            f"  Routed: {len(methodological_claims)} methodological, "
            f"{len(substantive_claims)} substantive"
        )

        # ── Step 2b: Track per-founder methodology/substance counts ─────
        founder_method_counts: dict[str, int] = defaultdict(int)
        founder_subst_counts: dict[str, int] = defaultdict(int)
        for c in methodological_claims:
            if c.founder_id:
                founder_method_counts[c.founder_id] += 1
        for c in substantive_claims:
            if c.founder_id:
                founder_subst_counts[c.founder_id] += 1

        all_fids = set(founder_method_counts) | set(founder_subst_counts)
        for fid in all_fids:
            self.founder_registry.record_methodology_counts(
                founder_id=fid,
                methodological=founder_method_counts.get(fid, 0),
                substantive=founder_subst_counts.get(fid, 0),
            )

        # ── Step 3 continued: Distill methodological principles ──────────
        logger.info("Step 3 continued: Distilling methodological principles...")
        new_principles = []
        if methodological_claims:
            new_principles, new_relationships = self.distiller.distill_principles(
                claims=methodological_claims
            )
            # Add to graph with founder contribution tracking
            for p in new_principles:
                # Compute founder contributions for this principle
                contrib_counts: dict[str, int] = defaultdict(int)
                for cid in p.supporting_claims:
                    claim = next((c for c in methodological_claims if c.id == cid), None)
                    if claim and claim.founder_id:
                        contrib_counts[claim.founder_id] += 1

                # Normalise to weights summing to 1.0
                total = sum(contrib_counts.values())
                if total > 0:
                    p.founder_contributions = {
                        fid: count / total
                        for fid, count in contrib_counts.items()
                    }
                    p.endorsing_founders = list(contrib_counts.keys())
                    p.source_types = list({
                        c.source_type
                        for c in methodological_claims
                        if c.id in p.supporting_claims
                    })

                    # Record in founder profiles
                    for fid in contrib_counts:
                        self.founder_registry.record_principle_contribution(fid, p.id)

                if self.graph.get_principle(p.id):
                    self.graph.update_principle(p)
                else:
                    self.graph.add_principle(p)
            for r in new_relationships:
                self.graph.add_relationship(r)
            logger.info(f"  Distilled {len(new_principles)} principles")

        # ── Step 6: Meta-analysis of substantive discourse ───────────────
        logger.info("Step 6: Running meta-analysis on substantive discourse...")
        observations = []
        if substantive_claims and classified:
            substantive_classified = [
                cc for cc in classified
                if cc.discourse_type in (
                    DiscourseType.SUBSTANTIVE, DiscourseType.MIXED
                )
            ]
            observations = self.meta_analyzer.analyze_discourse_segment(
                claims=substantive_classified,
                context=f"Episode {episode_number}: {title}",
            )
            logger.info(f"  Generated {len(observations)} methodological observations")

        # ── Step 7: Promote high-confidence observations ─────────────────
        min_conf = self.config.get(
            "min_observation_confidence_for_promotion", 0.75
        )
        promoted = [o for o in observations if o.confidence >= min_conf]
        if promoted:
            brain_entries = self.meta_analyzer.bridge_to_brain(promoted)
            for entry in brain_entries:
                p = Principle(
                    text=entry["text"],
                    disciplines=[
                        Discipline(d) for d in entry.get("disciplines", [])
                        if d in [e.value for e in Discipline]
                    ],
                    conviction=ConvictionLevel(
                        entry.get("conviction_level", "exploratory")
                    ),
                    conviction_score=0.4,
                    first_appeared=episode_date,
                    last_reinforced=episode_date,
                    mention_count=1,
                    tags=["meta-observation", "auto-promoted"],
                )
                # Embed
                try:
                    emb = self.model.encode(p.text).tolist()
                    p.embedding = emb
                except Exception:
                    pass
                self.graph.add_principle(p)
            logger.info(f"  Promoted {len(promoted)} observations to principles")

        # ── Step 8: Temporal snapshots ───────────────────────────────────
        for p in new_principles:
            self.snapshots.append(
                TemporalSnapshot(
                    principle_id=p.id,
                    episode_id=episode_id,
                    date=episode_date,
                    conviction_score=p.conviction_score,
                    mention_count_cumulative=p.mention_count,
                    embedding=p.embedding,
                )
            )

        # ── Build episode metadata ───────────────────────────────────────
        episode = Episode(
            id=episode_id,
            number=episode_number,
            date=episode_date,
            title=title,
            transcript_path=str(path),
            claim_count=len(claims),
            new_principles=[p.id for p in new_principles],
        )
        self.episodes[episode_id] = episode

        # ── Step 9: Persist ──────────────────────────────────────────────
        self._save_all()
        logger.info(f"=== Episode {episode_number} ingestion complete ===")
        logger.info(
            f"  Claims: {len(claims)} total → "
            f"{len(methodological_claims)} method, "
            f"{len(substantive_claims)} substance"
        )
        logger.info(
            f"  Principles: {len(new_principles)} new/updated, "
            f"{len(promoted)} promoted from meta-analysis"
        )
        logger.info(
            f"  Observations: {len(observations)} generated"
        )

        # ── Step 10: Post-discussion synthesis ──────────────────────────
        logger.info("Step 10: Running post-discussion synthesis...")
        try:
            synthesis_outputs = self.synthesis.run_post_discussion_synthesis(
                episode=episode,
                claims=claims,
                new_principles=new_principles,
                method_count=len(methodological_claims),
                substance_count=len(substantive_claims),
            )
            logger.info(
                f"  Synthesis complete: summary, manuscript, "
                f"{len(synthesis_outputs.get('questions', ''))} chars of questions, "
                f"sources, contradiction report"
            )
        except Exception as e:
            logger.error(f"Synthesis failed (non-fatal): {e}")

        return episode

    def _register_conclusion(self, claim, classified_claim, episode_id, episode_date):
        """Register a substantive claim in the Conclusions Registry."""
        from noosphere.conclusions import SubstantiveConclusion

        conclusion = SubstantiveConclusion(
            text=claim.text,
            speaker_id=claim.speaker.id if claim.speaker else "",
            speaker_name=claim.speaker.name if claim.speaker else "Unknown",
            episode_id=episode_id,
            episode_date=episode_date,
            domain=claim.disciplines[0].value if claim.disciplines else "general",
            method_used=classified_claim.method_attribution or "unknown",
            confidence_expressed=claim.confidence,
            is_prediction=False,  # Could be refined with further analysis
            methodological_context=classified_claim.decomposition_notes,
        )
        self.conclusions.register(conclusion)

    # ── Written Input Ingestion ─────────────────────────────────────────────

    def ingest_written_input(
        self,
        file_path: str,
        author_name: str,
        title: str = "",
        input_date: Optional[date] = None,
        description: str = "",
        source_type: str = "written",
    ) -> dict:
        """
        Ingest a written document from a specific founder.

        Uses the same classification and routing pipeline as transcripts,
        but every claim is attributed to the named author. Supports
        .txt, .md, .pdf, and .docx files.

        Args:
            file_path: Path to the document
            author_name: Name of the founding author
            title: Document title
            input_date: When it was written
            description: Brief description
            source_type: "written", "annotation", or "external"

        Returns:
            Summary dict with counts and founder profile update.
        """
        logger.info(f"=== Ingesting written input: {title or file_path} by {author_name} ===")

        source_type_enum = InputSourceType(source_type)

        # Extract claims via WrittenInputProcessor
        claims, source = self.written_processor.ingest_written_input(
            file_path=file_path,
            author_name=author_name,
            title=title,
            input_date=input_date,
            description=description,
            source_type=source_type_enum,
        )

        if not claims:
            logger.warning("No claims extracted from written input")
            return {"claims": 0, "methodological": 0, "substantive": 0}

        # Classify claims (same pipeline as transcript)
        from noosphere.classifier import DiscourseType
        classified = self.classifier.classify_batch(claims)

        methodological_claims = []
        substantive_claims = []

        for cc in classified:
            original = next((c for c in claims if c.id == cc.claim_id), None)
            if original is None:
                continue

            if cc.discourse_type in (DiscourseType.METHODOLOGICAL, DiscourseType.META_METHODOLOGICAL):
                methodological_claims.append(original)
            elif cc.discourse_type == DiscourseType.SUBSTANTIVE:
                substantive_claims.append(original)
                self._register_conclusion(
                    original, cc, source.id, input_date or date.today()
                )
            elif cc.discourse_type == DiscourseType.MIXED:
                if cc.methodological_content:
                    method_claim = Claim(
                        text=cc.methodological_content,
                        speaker=original.speaker,
                        episode_id=original.episode_id,
                        episode_date=original.episode_date,
                        disciplines=original.disciplines,
                        embedding=original.embedding,
                        confidence=cc.confidence * 0.8,
                        founder_id=original.founder_id,
                        source_type=original.source_type,
                        source_id=original.source_id,
                    )
                    methodological_claims.append(method_claim)
                if cc.substantive_content:
                    substantive_claims.append(original)
                    self._register_conclusion(
                        original, cc, source.id, input_date or date.today()
                    )

        # Track per-founder methodology counts
        founder = self.founder_registry.get_by_name(author_name)
        if founder:
            self.founder_registry.record_methodology_counts(
                founder_id=founder.id,
                methodological=len(methodological_claims),
                substantive=len(substantive_claims),
            )

        # Distill principles from methodological claims
        new_principles = []
        if methodological_claims:
            new_principles, new_rels = self.distiller.distill_principles(
                claims=methodological_claims
            )
            for p in new_principles:
                # Single author — 100% contribution
                if founder:
                    p.founder_contributions = {founder.id: 1.0}
                    p.endorsing_founders = [founder.id]
                    p.source_types = [source_type_enum]
                    self.founder_registry.record_principle_contribution(founder.id, p.id)

                if self.graph.get_principle(p.id):
                    self.graph.update_principle(p)
                else:
                    self.graph.add_principle(p)
            for r in new_rels:
                self.graph.add_relationship(r)

        # Persist
        self._save_all()

        # Post-ingestion synthesis (uses Episode-like wrapper for the written input)
        try:
            synth_episode = Episode(
                id=source.id,
                number=0,  # written inputs don't have episode numbers
                date=input_date or date.today(),
                title=title or f"Written input by {author_name}",
                transcript_path=file_path,
                claim_count=len(claims),
                new_principles=[p.id for p in new_principles],
            )
            self.synthesis.run_post_discussion_synthesis(
                episode=synth_episode,
                claims=claims,
                new_principles=new_principles,
                method_count=len(methodological_claims),
                substance_count=len(substantive_claims),
            )
            logger.info("Post-ingestion synthesis complete for written input")
        except Exception as e:
            logger.error(f"Synthesis failed for written input (non-fatal): {e}")

        summary = {
            "claims": len(claims),
            "methodological": len(methodological_claims),
            "substantive": len(substantive_claims),
            "principles_distilled": len(new_principles),
            "author": author_name,
            "source_id": source.id,
        }
        logger.info(f"=== Written input ingestion complete: {summary} ===")
        return summary

    # ── Founder Analysis ────────────────────────────────────────────────────

    def founder_report(self, founder_name: Optional[str] = None) -> dict:
        """
        Get founder profile summary or inter-founder dynamics report.

        If founder_name is given, returns that founder's profile.
        Otherwise returns the convergence/divergence report.
        """
        if founder_name:
            fp = self.founder_registry.get_by_name(founder_name)
            if not fp:
                return {"error": f"Founder '{founder_name}' not found"}
            return self.founder_analyser.founder_profile_summary(fp.id)
        else:
            return self.founder_analyser.convergence_report()

    def principle_authorship(self) -> dict:
        """Analyse how principles are distributed across founders."""
        return self.founder_analyser.principle_authorship_report(
            self.graph.principles
        )

    # ── Coherence Analysis ───────────────────────────────────────────────────

    def coherence_report(self) -> CoherenceReport:
        """Run full 6-layer coherence analysis on all methodological principles."""
        if not self.graph.principles:
            raise ValueError("No principles in graph")

        from noosphere.coherence import score_principles
        principles = list(self.graph.principles.values())
        report = score_principles(
            principles,
            weights=self.config.get("coherence_weights"),
        )
        logger.info(f"Coherence score: {report.composite_score:.3f}")
        return report

    # ── Inference ────────────────────────────────────────────────────────────

    def ask(
        self,
        question: str,
        context: str = "",
        disciplines: Optional[list[Discipline]] = None,
    ) -> InferenceResult:
        """Query the inference engine. Reasons from methodological principles."""
        if not self.graph.principles:
            raise ValueError("No principles to query")

        query = InferenceQuery(
            question=question,
            context=context,
            disciplines=disciplines or [],
        )

        # Find relevant principles
        relevant = self.search_principles(question, k=10)
        if not relevant:
            return InferenceResult(
                query=query,
                answer="No relevant methodological principles found.",
                confidence=0.0,
            )

        # Try full inference engine
        try:
            from noosphere.inference import InferenceEngine
            engine = InferenceEngine(
                graph=self.graph.graph,  # the nx.DiGraph inside OntologyGraph
                principles_dict=self.graph.principles,
                claims_dict=self.graph.claims,
                model_name=self.config.get("model_name", "all-mpnet-base-v2"),
            )
            return engine.ask(question, context=context, disciplines=disciplines)
        except Exception as e:
            logger.warning(f"Full inference engine failed: {e}; using simple mode")

        # Fallback: simple principle-grounded answer
        principle_texts = [f"- {p.text}" for p, _ in relevant[:5]]
        avg_conviction = np.mean([p.conviction_score for p, _ in relevant[:5]])

        return InferenceResult(
            query=query,
            answer=(
                f"Based on {len(relevant)} relevant methodological principles:\n"
                + "\n".join(principle_texts)
            ),
            principles_used=[p.id for p, _ in relevant[:5]],
            confidence=float(avg_conviction * 0.7),
        )

    # ── Search ───────────────────────────────────────────────────────────────

    def search_principles(
        self, query: str, k: int = 5
    ) -> list[tuple[Principle, float]]:
        """Semantic search over methodological principles."""
        if not self.graph.principles:
            return []

        query_emb = self.model.encode(query)
        return self.graph.find_nearest_principles(query_emb.tolist(), k=k)

    # ── Calibration Feedback ─────────────────────────────────────────────────

    def calibration_feedback(self) -> list[dict]:
        """
        Get methodological feedback from the Conclusions Registry.

        This is the KEY integration: it transforms accuracy data about
        substantive conclusions into methodological observations that
        the brain can store.
        """
        from noosphere.conclusions import CalibrationAnalyzer
        analyzer = CalibrationAnalyzer(self.conclusions)
        return analyzer.feedback_for_methodology()

    # ── Evolution ────────────────────────────────────────────────────────────

    def evolution_report(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict[str, Any]:
        """Generate temporal evolution report."""
        filtered = self.snapshots
        if start_date:
            filtered = [s for s in filtered if s.date >= start_date]
        if end_date:
            filtered = [s for s in filtered if s.date <= end_date]

        by_principle = defaultdict(list)
        for s in filtered:
            by_principle[s.principle_id].append(s)

        evolution = {}
        for pid, snaps in by_principle.items():
            snaps.sort(key=lambda s: s.date)
            drift = None
            if snaps[0].embedding and snaps[-1].embedding:
                from scipy.spatial.distance import cosine as cos_dist
                drift = cos_dist(snaps[0].embedding, snaps[-1].embedding)

            evolution[pid] = {
                "first_appearance": snaps[0].date.isoformat(),
                "last_update": snaps[-1].date.isoformat(),
                "conviction_start": snaps[0].conviction_score,
                "conviction_end": snaps[-1].conviction_score,
                "conviction_change": snaps[-1].conviction_score - snaps[0].conviction_score,
                "mention_count": snaps[-1].mention_count_cumulative,
                "embedding_drift": drift,
                "num_episodes": len(snaps),
            }

        return evolution

    # ── Export ────────────────────────────────────────────────────────────────

    def export_graph(self, format: str = "json", path: Optional[str] = None) -> str:
        if format == "json":
            data = {
                "principles": {
                    pid: p.model_dump(mode="json")
                    for pid, p in self.graph.principles.items()
                },
                "claims": {
                    cid: c.model_dump(mode="json")
                    for cid, c in self.graph.claims.items()
                },
                "metadata": {
                    "exported_at": datetime.now().isoformat(),
                    "principle_count": len(self.graph.principles),
                    "claim_count": len(self.graph.claims),
                },
            }
            result = json.dumps(data, indent=2, default=str)
        elif format == "graphml":
            self.persistence.export_to_graphml(path or str(self.data_dir / "graph.graphml"))
            return path or str(self.data_dir / "graph.graphml")
        else:
            raise ValueError(f"Unsupported format: {format}")

        if path:
            with open(path, "w") as f:
                f.write(result)
            return path
        return result

    # ── Stats ────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        principles = list(self.graph.principles.values())
        conclusion_count = len(self.conclusions.conclusions)

        founders = self.founder_registry.all_founders()

        return {
            "methodological_principles": len(principles),
            "substantive_conclusions": conclusion_count,
            "claims_in_graph": len(self.graph.claims),
            "relationships": len(self.graph.relationships),
            "episodes": len(self.episodes),
            "temporal_snapshots": len(self.snapshots),
            "founders": len(founders),
            "input_sources": len(self.source_registry.sources),
            "avg_coherence": round(
                np.mean([p.coherence_score or 0.5 for p in principles]), 3
            ) if principles else 0.0,
            "avg_conviction": round(
                np.mean([p.conviction_score for p in principles]), 3
            ) if principles else 0.0,
        }

    # ── Direct accessors ─────────────────────────────────────────────────────

    def get_principle(self, principle_id: str) -> Optional[Principle]:
        return self.graph.get_principle(principle_id)

    def get_contradictions(self) -> list[tuple[Principle, Principle, float]]:
        return self.graph.get_contradictions()

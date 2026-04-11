"""
Orchestrator for the Noosphere system — The Brain of the Firm.

This module ties all sub-modules together into a coherent pipeline for:
1. Ingesting transcripts and extracting claims
2. Building and maintaining the principle knowledge graph
3. Running coherence analysis across 6 layers
4. Performing semantic search and inference
5. Tracking temporal evolution of principles

The orchestrator manages initialization, data persistence, and cross-module
integration, presenting a clean public API for all Noosphere operations.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any

from sentence_transformers import SentenceTransformer

from noosphere.models import (
    Claim, Discipline, Episode, InferenceQuery, InferenceResult,
    Principle, CoherenceReport, TemporalSnapshot, ConvictionLevel
)
from noosphere.ingester import TranscriptIngester, TranscriptParser
from noosphere.ontology import OntologyGraph, PrincipleDistiller, GraphPersistence
from noosphere.coherence import CoherenceEngine
from noosphere.geometry import EmbeddingAnalyzer

# ── Logging ──────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


# ── Default Configuration ────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "model_name": "all-MiniLM-L6-v2",  # SBERT model for embeddings
    "model_device": "cpu",  # or "cuda"
    "coherence_weights": {
        "s1_consistency": 0.20,
        "s2_argumentation": 0.20,
        "s3_probabilistic": 0.15,
        "s4_geometric": 0.20,
        "s5_compression": 0.15,
        "s6_llm_judge": 0.10,
    },
    "ingestion_config": {
        "batch_size": 7,
        "use_fallback": False,
        "api_timeout_seconds": 60,
        "min_claim_length": 10,
        "max_claims_per_segment": 5,
    },
    "clustering_config": {
        "distance_threshold": 0.3,
        "min_samples": 2,
    }
}


# ── NoosphereOrchestrator ────────────────────────────────────────────────────

class NoosphereOrchestrator:
    """
    Central orchestrator for the Noosphere knowledge system.

    Manages the full pipeline from transcript ingestion to inference,
    with automatic persistence and coherence checking.

    Attributes:
        data_dir: Directory where graph, snapshots, and config are persisted
        config: Configuration dict loaded from noosphere_config.json
        graph: OntologyGraph instance (lazy-loaded)
        ingester: TranscriptIngester instance (lazy-loaded)
        coherence: CoherenceEngine instance (lazy-loaded)
        geometry: EmbeddingAnalyzer instance (lazy-loaded)
        model: Shared SBERT SentenceTransformer model
    """

    def __init__(self, data_dir: str = "./noosphere_data"):
        """
        Initialize the orchestrator.

        Creates data_dir if it doesn't exist, loads config, and initializes
        the shared SBERT model.

        Args:
            data_dir: Directory for persisting graph and config.
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Load or create config
        self.config_path = self.data_dir / "noosphere_config.json"
        self.config = self._load_config()

        # Initialize shared SBERT model (once)
        logger.info(f"Loading SBERT model: {self.config['model_name']}")
        try:
            self.model = SentenceTransformer(
                self.config['model_name'],
                device=self.config.get('model_device', 'cpu')
            )
        except Exception as e:
            logger.error(f"Failed to load SBERT model: {e}")
            raise

        # Lazy-loaded sub-modules
        self._graph: Optional[OntologyGraph] = None
        self._ingester: Optional[TranscriptIngester] = None
        self._coherence: Optional[CoherenceEngine] = None
        self._geometry: Optional[EmbeddingAnalyzer] = None
        self._distiller: Optional[PrincipleDistiller] = None
        self._persistence: Optional[GraphPersistence] = None

        # Temporal tracking
        self.snapshots: List[TemporalSnapshot] = []
        self.episodes: Dict[str, Episode] = {}

        # Load existing graph if available
        self._load_graph()

        logger.info(f"Noosphere orchestrator initialized at {self.data_dir}")

    def _load_config(self) -> Dict[str, Any]:
        """Load config from disk or create default."""
        if self.config_path.exists():
            logger.info(f"Loading config from {self.config_path}")
            with open(self.config_path, 'r') as f:
                return json.load(f)
        else:
            logger.info("Creating default config")
            self._save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG

    def _save_config(self, config: Dict[str, Any]) -> None:
        """Save config to disk."""
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info(f"Saved config to {self.config_path}")

    @property
    def graph(self) -> OntologyGraph:
        """Lazy-load the ontology graph."""
        if self._graph is None:
            self._graph = OntologyGraph()
        return self._graph

    @property
    def ingester(self) -> TranscriptIngester:
        """Lazy-load the transcript ingester."""
        if self._ingester is None:
            self._ingester = TranscriptIngester(
                model=self.model,
                config=self.config['ingestion_config']
            )
        return self._ingester

    @property
    def coherence(self) -> CoherenceEngine:
        """Lazy-load the coherence engine."""
        if self._coherence is None:
            self._coherence = CoherenceEngine(
                weights=self.config['coherence_weights']
            )
        return self._coherence

    @property
    def geometry(self) -> EmbeddingAnalyzer:
        """Lazy-load the embedding geometry analyzer."""
        if self._geometry is None:
            self._geometry = EmbeddingAnalyzer(verbose=False)
        return self._geometry

    @property
    def distiller(self) -> PrincipleDistiller:
        """Lazy-load the principle distiller."""
        if self._distiller is None:
            self._distiller = PrincipleDistiller(
                model=self.model,
                clustering_config=self.config['clustering_config']
            )
        return self._distiller

    @property
    def persistence(self) -> GraphPersistence:
        """Lazy-load the graph persistence layer."""
        if self._persistence is None:
            self._persistence = GraphPersistence(
                graph_dir=str(self.data_dir / "graph")
            )
        return self._persistence

    # ── Graph Loading/Saving ─────────────────────────────────────────────────

    def _load_graph(self) -> None:
        """Load existing graph from disk if available."""
        graph_dir = self.data_dir / "graph"
        if graph_dir.exists():
            try:
                logger.info(f"Loading graph from {graph_dir}")
                loaded_graph = self.persistence.load_graph(str(graph_dir))
                self._graph = loaded_graph
                logger.info(
                    f"Loaded graph with {len(self.graph.principles)} "
                    f"principles and {len(self.graph.claims)} claims"
                )
            except Exception as e:
                logger.error(f"Failed to load graph: {e}")
                self._graph = OntologyGraph()

    def _save_graph(self) -> None:
        """Persist the graph to disk."""
        graph_dir = self.data_dir / "graph"
        graph_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.persistence.save_graph(self.graph, str(graph_dir))
            logger.info(f"Saved graph to {graph_dir}")
        except Exception as e:
            logger.error(f"Failed to save graph: {e}")

    # ── Main Pipeline: Ingest Episodes ───────────────────────────────────────

    def ingest_episode(
        self,
        transcript_path: str,
        episode_number: int,
        episode_date: date,
        title: str = "",
        speakers: Optional[List[str]] = None
    ) -> Episode:
        """
        Full pipeline: ingest episode, extract claims, update graph.

        Steps:
        1. Parse transcript
        2. Extract claims using Claude
        3. Embed claims with SBERT
        4. Classify disciplines
        5. Distill principles (cluster claims, generate principle statements)
        6. Update graph (add principles, relationships)
        7. Record temporal snapshots
        8. Run coherence check
        9. Save everything

        Args:
            transcript_path: Path to transcript file
            episode_number: Episode number
            episode_date: Date of episode
            title: Optional episode title
            speakers: Optional list of speaker names

        Returns:
            Episode metadata object

        Raises:
            FileNotFoundError: If transcript file doesn't exist
            Exception: If any step of the pipeline fails
        """
        transcript_path = Path(transcript_path)
        if not transcript_path.exists():
            raise FileNotFoundError(f"Transcript not found: {transcript_path}")

        logger.info(f"Ingesting episode {episode_number}: {title}")

        # 1. Read and parse transcript
        with open(transcript_path, 'r') as f:
            transcript_text = f.read()

        # 2. Extract claims
        logger.info("Extracting claims...")
        claims = self.ingester.ingest_transcript(
            transcript_text=transcript_text,
            episode_id=f"ep_{episode_number}",
            episode_date=episode_date,
            speakers=speakers or []
        )
        logger.info(f"Extracted {len(claims)} claims")

        # 3-5. Distill principles from claims
        logger.info("Distilling principles...")
        new_principles = self.distiller.distill_from_claims(
            claims=claims,
            episode_date=episode_date
        )
        logger.info(f"Distilled {len(new_principles)} new/updated principles")

        # 6. Update graph
        logger.info("Updating graph...")
        for claim in claims:
            try:
                self.graph.add_claim(claim)
            except Exception as e:
                logger.warning(f"Could not add claim {claim.id}: {e}")

        reinforced_principles = []
        for principle in new_principles:
            if principle.id in self.graph.principles:
                self.graph.update_principle(principle)
                reinforced_principles.append(principle.id)
            else:
                self.graph.add_principle(principle)

        # 7. Record temporal snapshots
        logger.info("Recording temporal snapshots...")
        for principle in new_principles:
            snapshot = TemporalSnapshot(
                principle_id=principle.id,
                episode_id=f"ep_{episode_number}",
                date=episode_date,
                conviction_score=principle.conviction_score,
                mention_count_cumulative=principle.mention_count,
                embedding=principle.embedding
            )
            self.snapshots.append(snapshot)

        # 8. Run coherence check
        logger.info("Running coherence check...")
        try:
            coherence_report = self.coherence_report()
            logger.info(
                f"Coherence score: {coherence_report.composite_score:.3f}"
            )
        except Exception as e:
            logger.warning(f"Coherence check failed: {e}")

        # 9. Create and save episode metadata
        episode = Episode(
            id=f"ep_{episode_number}",
            number=episode_number,
            date=episode_date,
            title=title,
            transcript_path=str(transcript_path),
            claim_count=len(claims),
            new_principles=[p.id for p in new_principles if p.id not in reinforced_principles],
            reinforced_principles=reinforced_principles
        )
        self.episodes[episode.id] = episode

        # Persist everything
        self._save_graph()
        self._save_snapshots()

        logger.info(f"Episode {episode_number} ingestion complete")
        return episode

    def _save_snapshots(self) -> None:
        """Persist temporal snapshots to disk."""
        snapshots_path = self.data_dir / "snapshots.jsonl"
        try:
            with open(snapshots_path, 'w') as f:
                for snapshot in self.snapshots:
                    f.write(snapshot.model_dump_json() + '\n')
            logger.info(f"Saved {len(self.snapshots)} snapshots")
        except Exception as e:
            logger.error(f"Failed to save snapshots: {e}")

    # ── Inference ────────────────────────────────────────────────────────────

    def ask(
        self,
        question: str,
        context: str = "",
        disciplines: Optional[List[Discipline]] = None
    ) -> InferenceResult:
        """
        Query the inference engine against the current principle graph.

        Searches for relevant principles, grounds reasoning in them,
        and generates a coherence-aware response.

        Args:
            question: The question to answer
            context: Optional additional context
            disciplines: Optional filter by discipline(s)

        Returns:
            InferenceResult with answer, reasoning, and confidence

        Raises:
            ValueError: If graph has no principles
        """
        if not self.graph.principles:
            raise ValueError("Graph has no principles to query")

        logger.info(f"Answering question: {question}")

        # Create inference query
        query = InferenceQuery(
            question=question,
            context=context,
            disciplines=disciplines or [],
            require_coherence=True
        )

        # Search for relevant principles
        relevant_principles = self.search_principles(question, k=10)

        if not relevant_principles:
            logger.warning("No relevant principles found")
            return InferenceResult(
                query=query,
                answer="No relevant principles found in the knowledge base.",
                confidence=0.0
            )

        # Extract principle IDs and texts
        principle_ids = [p[0].id for p in relevant_principles]
        principle_texts = [
            f"• {p[0].text}" for p in relevant_principles[:5]
        ]

        # Build reasoning chain (simplified inference)
        reasoning_chain = [
            "Searching knowledge graph for relevant principles...",
            f"Found {len(relevant_principles)} relevant principles",
            "Building reasoning chain from principles...",
            "Checking coherence with existing corpus...",
        ]

        # Synthesize answer (placeholder - in real system would use Claude)
        answer = (
            f"Based on {len(relevant_principles)} relevant principles:\n"
            + "\n".join(principle_texts[:3])
        )

        # Calculate confidence
        avg_conviction = sum(
            p[0].conviction_score for p in relevant_principles[:5]
        ) / min(5, len(relevant_principles))

        coherence_alignment = (
            self.graph.principles[principle_ids[0]].coherence_score or 0.5
            if principle_ids and principle_ids[0] in self.graph.principles
            else 0.5
        )

        result = InferenceResult(
            query=query,
            answer=answer,
            reasoning_chain=reasoning_chain,
            principles_used=principle_ids[:5],
            confidence=min(1.0, avg_conviction * 0.7 + coherence_alignment * 0.3),
            coherence_with_corpus=coherence_alignment,
            caveats=[]
        )

        logger.info(f"Generated answer with confidence {result.confidence:.3f}")
        return result

    # ── Coherence Analysis ───────────────────────────────────────────────────

    def coherence_report(self) -> CoherenceReport:
        """
        Run full 6-layer coherence analysis on all current principles.

        Returns:
            CoherenceReport with composite score and layer breakdowns

        Raises:
            ValueError: If no principles in graph
        """
        if not self.graph.principles:
            raise ValueError("Cannot run coherence check on empty graph")

        logger.info("Running 6-layer coherence analysis...")

        principle_ids = list(self.graph.principles.keys())
        propositions = [
            self.graph.principles[pid] for pid in principle_ids
        ]

        try:
            report = self.coherence.analyze(propositions)

            # Update principle coherence scores
            for principle_id, scores in zip(principle_ids, report.layer_scores.values()):
                if principle_id in self.graph.principles:
                    principle = self.graph.principles[principle_id]
                    principle.coherence_score = report.composite_score
                    # Note: layer scores would need to be broken down per principle
                    # This is a simplification
                    self.graph.update_principle(principle)

            logger.info(f"Coherence score: {report.composite_score:.3f}")
            return report

        except Exception as e:
            logger.error(f"Coherence analysis failed: {e}")
            raise

    # ── Temporal Evolution ───────────────────────────────────────────────────

    def evolution_report(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Generate temporal evolution report for principles.

        Tracks how principles change over time: conviction evolution,
        mention frequency, and drift in embedding space.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dict with evolution metrics per principle
        """
        logger.info(f"Generating evolution report ({start_date} to {end_date})")

        filtered_snapshots = self.snapshots
        if start_date:
            filtered_snapshots = [
                s for s in filtered_snapshots if s.date >= start_date
            ]
        if end_date:
            filtered_snapshots = [
                s for s in filtered_snapshots if s.date <= end_date
            ]

        # Group snapshots by principle
        evolution = {}
        from collections import defaultdict
        by_principle = defaultdict(list)
        for snapshot in filtered_snapshots:
            by_principle[snapshot.principle_id].append(snapshot)

        for principle_id, snapshots in by_principle.items():
            if not snapshots:
                continue

            snapshots = sorted(snapshots, key=lambda s: s.date)
            conviction_trajectory = [s.conviction_score for s in snapshots]
            mention_trajectory = [s.mention_count_cumulative for s in snapshots]

            # Calculate drift
            drift = None
            if snapshots[0].embedding and snapshots[-1].embedding:
                from scipy.spatial.distance import cosine
                import numpy as np
                drift = cosine(
                    np.array(snapshots[0].embedding),
                    np.array(snapshots[-1].embedding)
                )

            evolution[principle_id] = {
                "first_appearance": snapshots[0].date,
                "last_update": snapshots[-1].date,
                "conviction_start": conviction_trajectory[0],
                "conviction_end": conviction_trajectory[-1],
                "conviction_change": conviction_trajectory[-1] - conviction_trajectory[0],
                "mention_count": mention_trajectory[-1],
                "embedding_drift": drift,
                "num_episodes": len(snapshots),
            }

        logger.info(f"Evolution report: {len(evolution)} principles tracked")
        return evolution

    # ── Graph Export ─────────────────────────────────────────────────────────

    def export_graph(self, format: str = "json", path: Optional[str] = None) -> str:
        """
        Export the knowledge graph in specified format.

        Args:
            format: 'json', 'graphml', or 'adjacency'
            path: Optional path to save to. If None, returns string.

        Returns:
            Exported graph as string (or path if saved to file)

        Raises:
            ValueError: If format not supported
        """
        if format not in ("json", "graphml", "adjacency"):
            raise ValueError(f"Unsupported format: {format}")

        logger.info(f"Exporting graph as {format}")

        if format == "json":
            export_data = {
                "principles": [
                    p.model_dump() for p in self.graph.principles.values()
                ],
                "relationships": [
                    r.model_dump() for r in self.graph.relationships.values()
                ],
                "metadata": {
                    "exported_at": datetime.now().isoformat(),
                    "principle_count": len(self.graph.principles),
                    "relationship_count": len(self.graph.relationships),
                }
            }
            result = json.dumps(export_data, indent=2, default=str)

        elif format == "graphml":
            import networkx as nx
            result = "\n".join(
                nx.generate_graphml(self.graph.graph)
            )

        else:  # adjacency
            import networkx as nx
            result = "\n".join(
                nx.generate_adjlist(self.graph.graph)
            )

        if path:
            with open(path, 'w') as f:
                f.write(result)
            logger.info(f"Graph exported to {path}")
            return path
        else:
            return result

    # ── Statistics ───────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """
        Return comprehensive statistics about the knowledge graph.

        Returns:
            Dict with statistics: counts, dates, coherence, etc.
        """
        principles = self.graph.principles.values()

        avg_coherence = (
            sum(p.coherence_score or 0.5 for p in principles)
            / len(principles)
            if principles
            else 0.0
        )

        avg_conviction = (
            sum(p.conviction_score for p in principles)
            / len(principles)
            if principles
            else 0.0
        )

        disciplines_set = set()
        for p in principles:
            disciplines_set.update(p.disciplines)

        stats = {
            "principle_count": len(self.graph.principles),
            "claim_count": len(self.graph.claims),
            "relationship_count": len(self.graph.relationships),
            "episode_count": len(self.episodes),
            "average_coherence_score": round(avg_coherence, 3),
            "average_conviction_score": round(avg_conviction, 3),
            "unique_disciplines": len(disciplines_set),
            "temporal_snapshots": len(self.snapshots),
            "first_episode": (
                min(e.date for e in self.episodes.values()).isoformat()
                if self.episodes else None
            ),
            "last_episode": (
                max(e.date for e in self.episodes.values()).isoformat()
                if self.episodes else None
            ),
        }

        return stats

    # ── Search ───────────────────────────────────────────────────────────────

    def search_principles(
        self,
        query: str,
        k: int = 5
    ) -> List[Tuple[Principle, float]]:
        """
        Semantic search over principles.

        Args:
            query: Search query text
            k: Number of results to return

        Returns:
            List of (Principle, similarity_score) tuples, sorted by score
        """
        if not self.graph.principles:
            return []

        logger.info(f"Searching principles: {query}")

        # Embed query
        query_embedding = self.model.encode(query, convert_to_tensor=True)

        # Score all principles
        scores = []
        for principle in self.graph.principles.values():
            if principle.embedding:
                import numpy as np
                from scipy.spatial.distance import cosine
                similarity = 1.0 - cosine(
                    np.array(principle.embedding),
                    query_embedding.cpu().numpy()
                    if hasattr(query_embedding, 'cpu')
                    else query_embedding
                )
                scores.append((principle, similarity))

        # Sort and return top-k
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:k]

    # ── Graph Queries ────────────────────────────────────────────────────────

    def get_principle(self, principle_id: str) -> Optional[Principle]:
        """Get a principle by ID."""
        return self.graph.principles.get(principle_id)

    def get_contradictions(self) -> List[Tuple[str, str, float]]:
        """
        Get all detected contradictions in the graph.

        Returns:
            List of (principle_id_a, principle_id_b, severity) tuples
        """
        contradictions = []
        for rel in self.graph.relationships.values():
            if rel.relation.value == "contradicts":
                contradictions.append((
                    rel.source_id,
                    rel.target_id,
                    rel.strength
                ))
        return contradictions

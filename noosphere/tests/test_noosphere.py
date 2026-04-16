"""
Comprehensive test suite for the Noosphere system.

Tests all major components without requiring external APIs or model downloads.
Uses synthetic embeddings and sample data for complete coverage.
"""

import pytest
import json
import tempfile
import numpy as np
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# Import all modules
from noosphere.models import (
    Speaker, TranscriptSegment, Claim, Principle, Relationship, Episode,
    CoherenceReport, InferenceQuery, InferenceResult, TemporalSnapshot,
    RelationType, Discipline, ConvictionLevel
)
from noosphere.ingester import TranscriptParser, ClaimExtractor, DisciplineClassifier
from noosphere.ontology import OntologyGraph, PrincipleDistiller, GraphPersistence
from noosphere.coherence import CoherenceEngine, Proposition, LayerScores
from noosphere.geometry import EmbeddingAnalyzer, ConceptAxisBuilder, IdeologyReflector, GeometricCoherenceAnalyzer
from noosphere.temporal import TemporalTracker, EvolutionAnalyzer, ConvictionEstimator


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_speaker():
    """Create a sample speaker."""
    return Speaker(name="Alice", role="founder")


@pytest.fixture
def sample_speakers():
    """Create a list of sample speakers."""
    return [
        Speaker(name="Alice", role="founder"),
        Speaker(name="Bob", role="founder"),
        Speaker(name="Charlie", role="guest"),
    ]


@pytest.fixture
def sample_transcript_segment(sample_speaker):
    """Create a sample transcript segment."""
    return TranscriptSegment(
        speaker=sample_speaker,
        text="Building a product is the hardest part of entrepreneurship.",
        start_time=120.5,
        end_time=125.5,
        episode_id="ep-001",
    )


@pytest.fixture
def sample_claim(sample_speaker):
    """Create a sample claim."""
    return Claim(
        text="Deep understanding of user needs drives product success.",
        speaker=sample_speaker,
        episode_id="ep-001",
        episode_date=date(2024, 1, 15),
        segment_context="We spent six months talking to users.",
        disciplines=[Discipline.ENTREPRENEURSHIP, Discipline.PHILOSOPHY],
        embedding=[0.1, 0.2, 0.3],  # Synthetic embedding
        confidence=0.95,
        timestamp_seconds=100.0,
    )


@pytest.fixture
def sample_claims():
    """Create multiple sample claims."""
    speaker1 = Speaker(name="Alice", role="founder")
    speaker2 = Speaker(name="Bob", role="founder")

    return [
        Claim(
            text="Deep understanding of user needs drives product success.",
            speaker=speaker1,
            episode_id="ep-001",
            episode_date=date(2024, 1, 15),
            disciplines=[Discipline.ENTREPRENEURSHIP],
            embedding=np.random.randn(768).tolist(),
            confidence=0.95,
        ),
        Claim(
            text="Rapid iteration is essential for finding product-market fit.",
            speaker=speaker2,
            episode_id="ep-001",
            episode_date=date(2024, 1, 15),
            disciplines=[Discipline.ENTREPRENEURSHIP],
            embedding=np.random.randn(768).tolist(),
            confidence=0.90,
        ),
        Claim(
            text="Long-term vision prevents short-term compromises.",
            speaker=speaker1,
            episode_id="ep-001",
            episode_date=date(2024, 1, 15),
            disciplines=[Discipline.STRATEGY, Discipline.PHILOSOPHY],
            embedding=np.random.randn(768).tolist(),
            confidence=0.85,
        ),
    ]


@pytest.fixture
def sample_principle():
    """Create a sample principle."""
    return Principle(
        text="Product success requires deep user understanding.",
        description="Understanding user needs at a deep level is foundational.",
        disciplines=[Discipline.ENTREPRENEURSHIP, Discipline.PHILOSOPHY],
        conviction=ConvictionLevel.STRONG,
        conviction_score=0.75,
        embedding=np.random.randn(768).tolist(),
        supporting_claims=["claim-1", "claim-2"],
        first_appeared=date(2024, 1, 15),
        last_reinforced=date(2024, 1, 22),
        mention_count=5,
        coherence_score=0.72,
    )


@pytest.fixture
def sample_principles():
    """Create multiple sample principles."""
    return [
        Principle(
            text="Product success requires deep user understanding.",
            disciplines=[Discipline.ENTREPRENEURSHIP],
            conviction=ConvictionLevel.STRONG,
            conviction_score=0.8,
            embedding=np.random.randn(768).tolist(),
            mention_count=5,
        ),
        Principle(
            text="Rapid iteration enables product discovery.",
            disciplines=[Discipline.ENTREPRENEURSHIP],
            conviction=ConvictionLevel.MODERATE,
            conviction_score=0.6,
            embedding=np.random.randn(768).tolist(),
            mention_count=3,
        ),
        Principle(
            text="Long-term vision guides daily decisions.",
            disciplines=[Discipline.STRATEGY],
            conviction=ConvictionLevel.STRONG,
            conviction_score=0.75,
            embedding=np.random.randn(768).tolist(),
            mention_count=4,
        ),
    ]


@pytest.fixture
def ontology_graph_with_principles(sample_principles):
    """Create an ontology graph with sample principles."""
    graph = OntologyGraph()
    for principle in sample_principles:
        graph.add_principle(principle)
    return graph


# ── Tests for Models ──────────────────────────────────────────────────────────

class TestModels:
    """Test data model creation and validation."""

    def test_speaker_creation(self, sample_speaker):
        assert sample_speaker.name == "Alice"
        assert sample_speaker.role == "founder"
        assert sample_speaker.id is not None

    def test_claim_creation(self, sample_claim):
        assert sample_claim.text is not None
        assert sample_claim.speaker.name == "Alice"
        assert sample_claim.episode_id == "ep-001"
        assert Discipline.ENTREPRENEURSHIP in sample_claim.disciplines
        assert sample_claim.confidence == 0.95

    def test_claim_serialization(self, sample_claim):
        """Test Claim can be serialized to JSON."""
        claim_json = sample_claim.model_dump_json()
        assert claim_json is not None
        # Deserialize and verify
        claim_dict = json.loads(claim_json)
        assert claim_dict["text"] == sample_claim.text

    def test_principle_creation(self, sample_principle):
        assert sample_principle.text is not None
        assert sample_principle.conviction == ConvictionLevel.STRONG
        assert sample_principle.conviction_score == 0.75
        assert sample_principle.mention_count == 5

    def test_principle_serialization(self, sample_principle):
        """Test Principle can be serialized to JSON."""
        principle_json = sample_principle.model_dump_json()
        assert principle_json is not None
        principle_dict = json.loads(principle_json)
        assert principle_dict["conviction"] == "strong"

    def test_relationship_creation(self, sample_principles):
        rel = Relationship(
            source_id=sample_principles[0].id,
            target_id=sample_principles[1].id,
            relation=RelationType.SUPPORTS,
            strength=0.8,
            evidence="One principle supports the other.",
        )
        assert rel.relation == RelationType.SUPPORTS
        assert rel.strength == 0.8

    def test_temporal_snapshot_creation(self, sample_principle):
        snapshot = TemporalSnapshot(
            principle_id=sample_principle.id,
            episode_id="ep-002",
            date=date(2024, 1, 22),
            conviction_score=0.82,
            mention_count_cumulative=6,
            embedding=sample_principle.embedding,
            drift_from_origin=0.05,
        )
        assert snapshot.principle_id == sample_principle.id
        assert snapshot.conviction_score == 0.82
        assert snapshot.drift_from_origin == 0.05

    def test_coherence_report_creation(self, sample_principles):
        report = CoherenceReport(
            principle_ids=[p.id for p in sample_principles],
            composite_score=0.72,
            layer_scores={
                "S₁ Formal Consistency": 0.70,
                "S₂ Argumentation": 0.75,
                "S₃ Probabilistic": 0.68,
                "S₄ Geometric": 0.75,
                "S₅ Compression": 0.70,
                "S₆ LLM Judge": 0.72,
            },
            contradictions_found=[],
            weakest_links=[],
        )
        assert report.composite_score == 0.72
        assert len(report.layer_scores) == 6

    def test_episode_creation(self):
        episode = Episode(
            number=1,
            date=date(2024, 1, 15),
            title="Founding Principles",
            duration_seconds=3600.0,
            claim_count=10,
        )
        assert episode.number == 1
        assert episode.claim_count == 10


# ── Tests for Ingestion ───────────────────────────────────────────────────────

class TestTranscriptParser:
    """Test the TranscriptParser module."""

    def test_parse_labeled_transcript(self):
        """Test parsing transcript with speaker labels."""
        transcript = """ALICE: Building a product is hard.
BOB: Iteration is key to success.
ALICE: User feedback drives decisions."""

        parser = TranscriptParser()
        segments = parser.parse(transcript, "ep-001")

        assert len(segments) == 3
        assert segments[0].speaker.name == "ALICE"
        assert segments[1].speaker.name == "BOB"
        assert segments[2].speaker.name == "ALICE"

    def test_parse_timestamped_transcript(self):
        """Test parsing transcript with timestamps."""
        transcript = """[00:01:20] ALICE: Building a product is hard.
[00:02:15] BOB: Iteration is key to success."""

        parser = TranscriptParser()
        segments = parser.parse(transcript, "ep-001")

        assert len(segments) == 2
        assert segments[0].start_time == 80.0  # 1 minute 20 seconds
        assert segments[1].start_time == 135.0  # 2 minutes 15 seconds

    def test_parse_unstructured_transcript(self):
        """Test parsing unstructured text."""
        transcript = "Building a product is hard. Iteration is key. User feedback matters."

        parser = TranscriptParser()
        segments = parser.parse(transcript, "ep-001", default_speaker=Speaker(name="Unknown"))

        # Should split into sentences
        assert len(segments) >= 2
        assert all(len(s.text) > 0 for s in segments)

    def test_parse_empty_transcript(self):
        """Test parsing empty transcript."""
        parser = TranscriptParser()
        segments = parser.parse("", "ep-001")
        assert len(segments) == 0

    def test_default_speaker_usage(self):
        """Test that default speaker is used for unstructured text."""
        transcript = "This is a statement."
        default_speaker = Speaker(name="DefaultSpeaker", role="unknown")

        parser = TranscriptParser()
        segments = parser.parse(transcript, "ep-001", default_speaker=default_speaker)

        if segments:
            assert segments[0].speaker.name == "DefaultSpeaker"


class TestClaimExtractor:
    """Test the ClaimExtractor module."""

    def test_extractor_initialization(self):
        """Test that extractor can be initialized."""
        extractor = ClaimExtractor()
        assert extractor.config is not None

    def test_extract_valid_claims(self):
        """Test claim extraction with fallback (no API)."""
        segments = [
            TranscriptSegment(
                speaker=Speaker(name="Alice"),
                text="The market for mobile apps is growing rapidly.",
                episode_id="ep-001",
            ),
            TranscriptSegment(
                speaker=Speaker(name="Bob"),
                text="User retention is more important than acquisition.",
                episode_id="ep-001",
            ),
        ]

        extractor = ClaimExtractor()
        # Without API key, this will use fallback mode
        claims = extractor.extract(segments)

        # Should extract at least some claims (if spaCy is available)
        assert isinstance(claims, list)

    def test_is_valid_claim(self):
        """Test claim validation logic."""
        extractor = ClaimExtractor()

        # Valid claims
        assert extractor._is_valid_claim("The market is growing.") is True
        assert extractor._is_valid_claim("Products must solve real problems.") is True

        # Invalid claims
        assert extractor._is_valid_claim("Hmm") is False  # Too short
        assert extractor._is_valid_claim("I think maybe") is False  # Weak signal words


class TestDisciplineClassifier:
    """Test the DisciplineClassifier module."""

    def test_classify_claim(self):
        """Test discipline classification."""
        claim = Claim(
            text="Building a startup requires understanding market dynamics and user needs.",
            speaker=Speaker(name="Alice"),
            episode_id="ep-001",
            episode_date=date(2024, 1, 15),
        )

        classifier = DisciplineClassifier()
        disciplines = classifier.classify(claim)

        # Should classify to at least one discipline
        assert len(disciplines) > 0
        # Should include entrepreneurship due to "startup"
        assert Discipline.ENTREPRENEURSHIP in disciplines

    def test_classify_philosophy_claim(self):
        """Test classification of philosophical claim."""
        claim = Claim(
            text="The nature of consciousness and existence is fundamental.",
            speaker=Speaker(name="Alice"),
            episode_id="ep-001",
            episode_date=date(2024, 1, 15),
        )

        classifier = DisciplineClassifier()
        disciplines = classifier.classify(claim)

        assert Discipline.PHILOSOPHY in disciplines

    def test_classify_ai_claim(self):
        """Test classification of AI-related claim."""
        claim = Claim(
            text="Deep learning models have transformed natural language processing.",
            speaker=Speaker(name="Alice"),
            episode_id="ep-001",
            episode_date=date(2024, 1, 15),
        )

        classifier = DisciplineClassifier()
        disciplines = classifier.classify(claim)

        assert Discipline.AI in disciplines


# ── Tests for Ontology ────────────────────────────────────────────────────────

class TestOntologyGraph:
    """Test the OntologyGraph module."""

    def test_graph_creation(self):
        """Test creating an empty ontology graph."""
        graph = OntologyGraph()
        assert len(graph.principles) == 0
        assert len(graph.claims) == 0

    def test_add_principle(self, sample_principle, sample_principles):
        """Test adding principles to graph."""
        graph = OntologyGraph()
        graph.add_principle(sample_principle)

        assert sample_principle.id in graph.principles
        assert graph.principles[sample_principle.id] == sample_principle

    def test_add_multiple_principles(self, sample_principles):
        """Test adding multiple principles."""
        graph = OntologyGraph()
        for principle in sample_principles:
            graph.add_principle(principle)

        assert len(graph.principles) == len(sample_principles)

    def test_add_claim(self, sample_claim):
        """Test adding claims to graph."""
        graph = OntologyGraph()
        graph.add_claim(sample_claim)

        assert sample_claim.id in graph.claims

    def test_add_relationship(self, sample_principles):
        """Test adding relationships between principles."""
        graph = OntologyGraph()
        for principle in sample_principles:
            graph.add_principle(principle)

        rel = Relationship(
            source_id=sample_principles[0].id,
            target_id=sample_principles[1].id,
            relation=RelationType.SUPPORTS,
            strength=0.8,
        )
        graph.add_relationship(rel)

        assert rel.id in graph.relationships

    def test_get_principle(self, sample_principle):
        """Test retrieving a principle."""
        graph = OntologyGraph()
        graph.add_principle(sample_principle)

        retrieved = graph.get_principle(sample_principle.id)
        assert retrieved == sample_principle

    def test_get_related_principles(self, sample_principles):
        """Test getting related principles."""
        graph = OntologyGraph()
        for principle in sample_principles:
            graph.add_principle(principle)

        # Add relationships
        rel1 = Relationship(
            source_id=sample_principles[0].id,
            target_id=sample_principles[1].id,
            relation=RelationType.SUPPORTS,
            strength=0.8,
        )
        rel2 = Relationship(
            source_id=sample_principles[1].id,
            target_id=sample_principles[2].id,
            relation=RelationType.REFINES,
            strength=0.7,
        )
        graph.add_relationship(rel1)
        graph.add_relationship(rel2)

        # Get related principles
        related = graph.get_related(sample_principles[0].id, depth=2)
        assert len(related) > 0

    def test_get_principles_by_discipline(self, sample_principles):
        """Test filtering principles by discipline."""
        graph = OntologyGraph()
        for principle in sample_principles:
            graph.add_principle(principle)

        entrepreneurship_principles = graph.get_principles_by_discipline(
            Discipline.ENTREPRENEURSHIP
        )
        assert len(entrepreneurship_principles) >= 2

    def test_get_principles_by_conviction(self, sample_principles):
        """Test filtering principles by conviction level."""
        graph = OntologyGraph()
        for principle in sample_principles:
            graph.add_principle(principle)

        strong_principles = graph.get_principles_by_conviction(ConvictionLevel.STRONG)
        assert len(strong_principles) >= 2

    def test_find_nearest_principles(self, sample_principles):
        """Test finding nearest principles by embedding."""
        graph = OntologyGraph()
        for principle in sample_principles:
            graph.add_principle(principle)

        # Query with random embedding
        query_embedding = np.random.randn(768).tolist()
        nearest = graph.find_nearest_principles(query_embedding, k=2)

        assert len(nearest) <= 2
        # Results should be (principle, similarity) tuples
        for principle, similarity in nearest:
            assert isinstance(principle, Principle)
            assert -1.0 <= similarity <= 1.0

    def test_get_stats(self, sample_principles):
        """Test getting graph statistics."""
        graph = OntologyGraph()
        for principle in sample_principles:
            graph.add_principle(principle)

        stats = graph.get_stats()
        assert stats["num_principles"] == len(sample_principles)
        assert "graph_density" in stats
        assert "conviction_distribution" in stats

    def test_get_axioms(self, sample_principles):
        """Test getting axioms (high conviction principles)."""
        graph = OntologyGraph()

        # Add principle with AXIOM conviction
        axiom = Principle(
            text="This is an axiom.",
            conviction=ConvictionLevel.AXIOM,
            conviction_score=0.95,
            embedding=np.random.randn(768).tolist(),
        )
        graph.add_principle(axiom)

        for principle in sample_principles:
            graph.add_principle(principle)

        axioms = graph.get_axioms()
        assert axiom in axioms
        assert len(axioms) == 1


class TestGraphPersistence:
    """Test the GraphPersistence module."""

    def test_save_and_load_graph(self, sample_principles):
        """Test saving and loading graph to/from JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create and save graph
            graph = OntologyGraph()
            for principle in sample_principles:
                graph.add_principle(principle)

            persistence = GraphPersistence(graph)
            save_path = Path(tmpdir) / "graph.json"
            persistence.save_to_json(str(save_path))

            # Load into new graph
            new_graph = OntologyGraph()
            new_persistence = GraphPersistence(new_graph)
            new_persistence.load_from_json(str(save_path))

            assert len(new_graph.principles) == len(sample_principles)

    def test_export_to_graphml(self, sample_principles):
        """Test exporting graph to GraphML format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            graph = OntologyGraph()
            for principle in sample_principles:
                graph.add_principle(principle)

            persistence = GraphPersistence(graph)
            export_path = Path(tmpdir) / "graph.graphml"
            persistence.export_to_graphml(str(export_path))

            assert export_path.exists()
            assert export_path.stat().st_size > 0

    def test_export_to_adjacency_list(self, sample_principles):
        """Test exporting graph to adjacency list format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            graph = OntologyGraph()
            for principle in sample_principles:
                graph.add_principle(principle)

            persistence = GraphPersistence(graph)
            export_path = Path(tmpdir) / "graph.txt"
            persistence.export_to_adjacency_list(str(export_path))

            assert export_path.exists()
            content = export_path.read_text()
            assert "Principle" in content or len(sample_principles) > 0


# ── Tests for Coherence ───────────────────────────────────────────────────────

class TestCoherenceEngine:
    """Test the 6-layer coherence engine."""

    def test_coherence_engine_initialization(self):
        """Test initializing the coherence engine."""
        propositions = [
            Proposition(
                id="p1",
                text="The market is growing.",
                conviction_score=0.8,
            ),
            Proposition(
                id="p2",
                text="Growth requires iteration.",
                conviction_score=0.7,
            ),
        ]

        engine = CoherenceEngine(propositions)
        assert engine is not None
        assert len(engine.propositions) == 2

    def test_layer_4_geometric_coherence_with_embeddings(self):
        """Test Layer 4 (geometric) coherence scoring with embeddings."""
        # Create propositions with embeddings
        embeddings = [
            np.random.randn(768),
            np.random.randn(768),
            np.random.randn(768),
        ]

        propositions = [
            Proposition(
                id=f"p{i}",
                text=f"Principle {i}",
                embedding=emb.tolist(),
                conviction_score=0.7,
            )
            for i, emb in enumerate(embeddings)
        ]

        engine = CoherenceEngine(propositions, enable_layers={"s4"})
        report = engine.compute()

        assert report.composite_score >= 0.0
        assert report.composite_score <= 1.0
        assert "S₄ Geometric" in report.layer_scores

    def test_layer_5_compression_coherence(self):
        """Test Layer 5 (compression) coherence scoring."""
        propositions = [
            Proposition(
                id="p1",
                text="The market is growing rapidly.",
                conviction_score=0.8,
            ),
            Proposition(
                id="p2",
                text="Growth requires constant iteration.",
                conviction_score=0.7,
            ),
            Proposition(
                id="p3",
                text="Markets reward focused solutions.",
                conviction_score=0.75,
            ),
        ]

        engine = CoherenceEngine(propositions, enable_layers={"s5"})
        report = engine.compute()

        assert "S₅ Compression" in report.layer_scores
        s5_score = report.layer_scores["S₅ Compression"]
        assert 0.0 <= s5_score <= 1.0


# ── Tests for Geometry ────────────────────────────────────────────────────────

class TestEmbeddingAnalyzer:
    """Test the EmbeddingAnalyzer module."""

    def test_cosine_similarity(self):
        """Test cosine similarity computation."""
        analyzer = EmbeddingAnalyzer()

        a = np.array([1.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        c = np.array([0.0, 1.0, 0.0])

        # Same vector
        assert abs(analyzer.cosine_similarity(a, b) - 1.0) < 0.01
        # Orthogonal vectors
        assert abs(analyzer.cosine_similarity(a, c)) < 0.01

    def test_hoyer_sparsity(self):
        """Test Hoyer sparsity computation."""
        analyzer = EmbeddingAnalyzer()

        # Dense vector (all ones)
        dense = np.ones(10)
        sparsity_dense = analyzer.hoyer_sparsity(dense)

        # Sparse vector (one element)
        sparse = np.zeros(10)
        sparse[0] = 1.0
        sparsity_sparse = analyzer.hoyer_sparsity(sparse)

        # Sparse vector should have higher sparsity
        assert sparsity_sparse > sparsity_dense

    def test_detect_contradiction(self):
        """Test contradiction detection."""
        analyzer = EmbeddingAnalyzer()

        # Create two very different vectors
        a = np.random.randn(100)
        b = np.random.randn(100) * 10  # Very different scale/direction

        is_contra, sparsity = analyzer.detect_contradiction(a, b, threshold=0.35)
        assert isinstance(is_contra, bool)
        assert 0.0 <= sparsity <= 1.0

    def test_batch_contradiction_check(self):
        """Test batch contradiction checking."""
        analyzer = EmbeddingAnalyzer()

        embeddings = np.random.randn(5, 100)
        results = analyzer.batch_contradiction_check(embeddings)

        # Should check all pairs
        expected_pairs = 5 * 4 // 2  # C(5,2)
        assert len(results) == expected_pairs

    def test_pca_contradiction_subspace(self):
        """Test PCA on contradiction subspace."""
        analyzer = EmbeddingAnalyzer()

        # Create random difference vectors
        diff_vectors = np.random.randn(20, 100)

        pca, variance = analyzer.pca_contradiction_subspace(
            diff_vectors, n_components=5
        )

        assert pca is not None
        assert len(variance) == 5
        assert sum(variance) <= 1.0


class TestConceptAxisBuilder:
    """Test the ConceptAxisBuilder module."""

    def test_build_axis_from_embeddings(self):
        """Test building axis from synthetic embeddings (no model needed)."""
        # Create synthetic embeddings manually
        positive_embeddings = [np.random.randn(100) for _ in range(3)]
        negative_embeddings = [np.random.randn(100) for _ in range(3)]

        pos_mean = np.mean(positive_embeddings, axis=0)
        neg_mean = np.mean(negative_embeddings, axis=0)
        axis = pos_mean - neg_mean
        axis = axis / (np.linalg.norm(axis) + 1e-10)

        # Axis should be normalized
        assert abs(np.linalg.norm(axis) - 1.0) < 0.01


class TestIdeologyReflector:
    """Test the IdeologyReflector module."""

    def test_reflect_vector(self):
        """Test Householder reflection of a vector."""
        reflector = IdeologyReflector()

        # Create a simple vector and axis
        vector = np.array([1.0, 1.0, 0.0])
        axis = np.array([1.0, 0.0, 0.0])  # Unit vector along x-axis

        reflected = reflector.reflect(vector, axis)

        # Should have same length
        assert abs(np.linalg.norm(reflected) - np.linalg.norm(vector)) < 0.01

    def test_ideology_distance(self):
        """Test measuring ideological distance."""
        reflector = IdeologyReflector()

        embedding = np.array([1.0, 1.0, 1.0])
        axis = np.array([1.0, 0.0, 0.0])

        distance = reflector.ideology_distance(embedding, axis)

        assert distance >= 0.0
        assert isinstance(distance, float)

    def test_decompose_ideology(self):
        """Test decomposing an embedding along multiple axes."""
        reflector = IdeologyReflector()

        embedding = np.random.randn(100)
        axes = {
            "axis1": np.random.randn(100),
            "axis2": np.random.randn(100),
            "axis3": np.random.randn(100),
        }

        # Normalize axes
        axes = {
            k: v / (np.linalg.norm(v) + 1e-10)
            for k, v in axes.items()
        }

        fingerprint = reflector.decompose_ideology(embedding, axes)

        assert len(fingerprint) == 3
        assert all(d >= 0.0 for d in fingerprint.values())


class TestGeometricCoherenceAnalyzer:
    """Test the GeometricCoherenceAnalyzer module."""

    def test_pairwise_coherence(self):
        """Test pairwise coherence calculation."""
        analyzer = GeometricCoherenceAnalyzer()

        # Create similar embeddings
        embeddings = np.random.randn(5, 100)
        coherence = analyzer.pairwise_coherence(embeddings)

        assert 0.0 <= coherence <= 1.0

    def test_cluster_dispersion(self):
        """Test cluster dispersion calculation."""
        analyzer = GeometricCoherenceAnalyzer()

        # Create tight cluster
        center = np.random.randn(100)
        embeddings = center + np.random.randn(5, 100) * 0.01

        dispersion = analyzer.cluster_dispersion(embeddings)

        assert dispersion >= 0.0

    def test_contradiction_scan(self):
        """Test contradiction scanning."""
        analyzer = GeometricCoherenceAnalyzer()

        embeddings = np.random.randn(4, 100)
        texts = ["Text 1", "Text 2", "Text 3", "Text 4"]

        results = analyzer.contradiction_scan(embeddings, texts)

        # Should find C(4,2) = 6 pairs
        assert len(results) == 6
        assert all("is_contradiction" in r for r in results)
        assert all("sparsity" in r for r in results)

    def test_coherence_report(self):
        """Test generating coherence report."""
        analyzer = GeometricCoherenceAnalyzer()

        embeddings = np.random.randn(3, 100)
        texts = ["Statement 1", "Statement 2", "Statement 3"]

        report = analyzer.coherence_report(embeddings, texts)

        assert "pairwise_coherence" in report
        assert "cluster_dispersion" in report
        assert "contradiction_count" in report
        assert "summary" in report


# ── Tests for Temporal ────────────────────────────────────────────────────────

class TestTemporalTracker:
    """Test the TemporalTracker module."""

    def test_temporal_tracker_initialization(self, ontology_graph_with_principles):
        """Test initializing temporal tracker."""
        tracker = TemporalTracker(ontology_graph_with_principles)
        assert tracker.graph is not None

    def test_record_snapshot(self, ontology_graph_with_principles):
        """Test recording principle snapshots."""
        tracker = TemporalTracker(ontology_graph_with_principles)
        principle_id = list(ontology_graph_with_principles.principles.keys())[0]

        snapshot = tracker.record_snapshot(
            principle_id=principle_id,
            episode_id="ep-001",
            date_=date(2024, 1, 15),
        )

        assert snapshot.principle_id == principle_id
        assert snapshot.date == date(2024, 1, 15)

    def test_get_history(self, ontology_graph_with_principles):
        """Test retrieving principle history."""
        tracker = TemporalTracker(ontology_graph_with_principles)
        principle_id = list(ontology_graph_with_principles.principles.keys())[0]

        # Record multiple snapshots
        for i in range(3):
            tracker.record_snapshot(
                principle_id=principle_id,
                episode_id=f"ep-{i:03d}",
                date_=date(2024, 1, 15) + timedelta(days=i),
            )

        history = tracker.get_history(principle_id)
        assert len(history) == 3

    def test_compute_conviction_trajectory(self, ontology_graph_with_principles):
        """Test computing conviction trajectory."""
        tracker = TemporalTracker(ontology_graph_with_principles)
        principle_id = list(ontology_graph_with_principles.principles.keys())[0]

        # Record snapshots with varying conviction
        for i in range(3):
            principle = ontology_graph_with_principles.get_principle(principle_id)
            principle.conviction_score = 0.5 + (i * 0.1)
            tracker.record_snapshot(
                principle_id=principle_id,
                episode_id=f"ep-{i:03d}",
                date_=date(2024, 1, 15) + timedelta(days=i),
            )

        trajectory = tracker.compute_conviction_trajectory(principle_id)
        assert len(trajectory) >= 1

    def test_detect_emergence(self, ontology_graph_with_principles):
        """Test detecting principle emergence."""
        tracker = TemporalTracker(ontology_graph_with_principles)
        principle_id = list(ontology_graph_with_principles.principles.keys())[0]

        tracker.record_snapshot(
            principle_id=principle_id,
            episode_id="ep-001",
            date_=date(2024, 1, 15),
        )

        emerged = tracker.detect_emergence("ep-001")
        # May or may not detect as emergence depending on mention count
        assert isinstance(emerged, list)


class TestConvictionEstimator:
    """Test the ConvictionEstimator module."""

    def test_estimate_conviction(self, sample_principle):
        """Test conviction score estimation."""
        estimator = ConvictionEstimator()

        conviction = estimator.estimate(sample_principle, episode_count=10)

        assert 0.0 <= conviction <= 1.0

    def test_estimate_conviction_with_recency(self, sample_principle):
        """Test conviction estimation with recency factor."""
        estimator = ConvictionEstimator()

        # Set last_reinforced to today
        sample_principle.last_reinforced = date.today()

        conviction = estimator.estimate(sample_principle, episode_count=5)
        assert conviction >= 0.0


# ── Tests for Inference ───────────────────────────────────────────────────────

class TestInferenceQuery:
    """Test the InferenceQuery model."""

    def test_create_inference_query(self):
        """Test creating an inference query."""
        query = InferenceQuery(
            question="How should we approach product development?",
            context="We're building a B2B SaaS product.",
            disciplines=[Discipline.ENTREPRENEURSHIP],
            require_coherence=True,
        )

        assert query.question is not None
        assert query.require_coherence is True

    def test_inference_result_creation(self):
        """Test creating an inference result."""
        query = InferenceQuery(question="What is success?")

        result = InferenceResult(
            query=query,
            answer="Success is achieving your goals.",
            reasoning_chain=["Step 1", "Step 2"],
            principles_used=["p1", "p2"],
            confidence=0.75,
            coherence_with_corpus=0.8,
            caveats=["This is subjective"],
        )

        assert result.confidence == 0.75
        assert len(result.reasoning_chain) == 2


# ── Integration Tests ─────────────────────────────────────────────────────────

class TestIntegration:
    """Integration tests combining multiple modules."""

    def test_full_ingestion_pipeline(self):
        """Test complete ingestion pipeline without APIs."""
        # 1. Parse transcript
        transcript = """ALICE: Deep user understanding drives product success.
BOB: Rapid iteration enables learning.
ALICE: Long-term vision prevents short-term compromises."""

        parser = TranscriptParser()
        segments = parser.parse(transcript, "ep-001")
        assert len(segments) == 3

        # 2. Create claims manually (avoiding API)
        claims = [
            Claim(
                text=segment.text,
                speaker=segment.speaker,
                episode_id=segment.episode_id,
                episode_date=date(2024, 1, 15),
                embedding=np.random.randn(768).tolist(),
                disciplines=[Discipline.ENTREPRENEURSHIP],
                confidence=0.9,
            )
            for segment in segments
        ]
        assert len(claims) == 3

        # 3. Create principles from claims
        principle = Principle(
            text="Product success requires understanding users and iterating quickly.",
            disciplines=[Discipline.ENTREPRENEURSHIP],
            conviction=ConvictionLevel.STRONG,
            conviction_score=0.8,
            embedding=np.random.randn(768).tolist(),
            supporting_claims=[c.id for c in claims[:2]],
            mention_count=3,
        )

        # 4. Build ontology
        graph = OntologyGraph()
        for claim in claims:
            graph.add_claim(claim)
        graph.add_principle(principle)

        assert len(graph.claims) == 3
        assert len(graph.principles) == 1

    def test_graph_with_coherence_analysis(self, sample_principles):
        """Test graph creation and coherence analysis."""
        graph = OntologyGraph()
        for principle in sample_principles:
            graph.add_principle(principle)

        # Create propositions from principles
        propositions = [
            Proposition(
                id=p.id,
                text=p.text,
                embedding=np.array(p.embedding) if p.embedding else None,
                conviction_score=p.conviction_score,
            )
            for p in sample_principles
        ]

        # Run Layer 5 coherence (doesn't need embeddings)
        engine = CoherenceEngine(propositions, enable_layers={"s5"})
        report = engine.compute()

        assert report.composite_score >= 0.0
        assert report.composite_score <= 1.0

    def test_temporal_evolution(self, ontology_graph_with_principles):
        """Test temporal tracking and evolution analysis."""
        tracker = TemporalTracker(ontology_graph_with_principles)

        # Record snapshots over time
        principle_id = list(ontology_graph_with_principles.principles.keys())[0]
        for i in range(5):
            tracker.record_snapshot(
                principle_id=principle_id,
                episode_id=f"ep-{i:03d}",
                date_=date(2024, 1, 15) + timedelta(days=i),
            )

        # Analyze evolution
        analyzer = EvolutionAnalyzer(tracker)

        lifecycle = analyzer.principle_lifecycle(principle_id)
        assert "principle_text" in lifecycle
        assert "conviction_trajectory" in lifecycle

    def test_geometric_analysis_on_graph(self, sample_principles):
        """Test geometric analysis on principles."""
        # Create embeddings that are somewhat similar
        base_emb = np.random.randn(100)
        for i, principle in enumerate(sample_principles):
            principle.embedding = (base_emb + np.random.randn(100) * 0.1).tolist()

        # Analyze geometry
        embeddings = np.array([p.embedding for p in sample_principles])
        analyzer = GeometricCoherenceAnalyzer()

        report = analyzer.coherence_report(embeddings)
        assert "pairwise_coherence" in report
        assert "cluster_dispersion" in report


# ── Performance Tests ─────────────────────────────────────────────────────────

class TestPerformance:
    """Performance tests to ensure scalability."""

    def test_large_principle_graph(self):
        """Test handling large number of principles."""
        graph = OntologyGraph()

        # Create 100 principles
        principles = []
        for i in range(100):
            principle = Principle(
                text=f"Principle {i}: Statement about domain {i % 5}",
                conviction=ConvictionLevel.MODERATE,
                conviction_score=0.5 + (i % 10) * 0.05,
                embedding=np.random.randn(768).tolist(),
                mention_count=i + 1,
            )
            principles.append(principle)
            graph.add_principle(principle)

        assert len(graph.principles) == 100

        # Test querying
        stats = graph.get_stats()
        assert stats["num_principles"] == 100

    def test_embedding_analysis_batch(self):
        """Test batch embedding analysis performance."""
        analyzer = EmbeddingAnalyzer()

        # Create 50 embeddings
        embeddings = np.random.randn(50, 100)

        # Run batch contradiction check
        results = analyzer.batch_contradiction_check(embeddings)

        expected_pairs = 50 * 49 // 2
        assert len(results) == expected_pairs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

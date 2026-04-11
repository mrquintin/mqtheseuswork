"""
Knowledge graph ontology for Noosphere — the Brain of the Firm.

This module manages the firm's principles and their relationships as a directed
knowledge graph, built on NetworkX. It supports:

1. OntologyGraph: Core graph structure storing Principles (nodes), Relationships
   (edges), and Claims (leaf nodes). Provides semantic queries and graph analytics.

2. PrincipleDistiller: Ingests raw Claims and generates/updates Principles via
   clustering, LLM analysis, and relationship detection.

3. GraphPersistence: Serializes to/from JSON and other formats, supporting
   incremental updates.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from collections import defaultdict

import networkx as nx
from numpy.typing import NDArray
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity
from anthropic import Anthropic

from noosphere.models import (
    Principle,
    Claim,
    Relationship,
    RelationType,
    Discipline,
    ConvictionLevel,
    Episode,
    TemporalSnapshot,
)


logger = logging.getLogger(__name__)


# ── OntologyGraph ────────────────────────────────────────────────────────────


class OntologyGraph:
    """
    Directed knowledge graph of principles and their relationships.

    Nodes represent Principles (and optionally Claims as leaf nodes).
    Directed edges represent Relationships (supports, contradicts, refines, etc.).

    All Principle objects are stored as node attributes, enabling rich queries
    across disciplines, conviction levels, and semantic embeddings.
    """

    def __init__(self):
        """Initialize an empty knowledge graph."""
        self.graph: nx.DiGraph = nx.DiGraph()
        self.principles: Dict[str, Principle] = {}
        self.claims: Dict[str, Claim] = {}
        self.relationships: Dict[str, Relationship] = {}
        logger.info("Initialized OntologyGraph")

    # ── Basic Operations ─────────────────────────────────────────────────────

    def add_principle(self, principle: Principle) -> None:
        """
        Add a principle to the graph as a node.

        Args:
            principle: The Principle to add.
        """
        self.principles[principle.id] = principle
        self.graph.add_node(
            principle.id,
            data=principle,
            node_type="principle",
        )
        logger.debug(f"Added principle {principle.id}: {principle.text[:50]}")

    def add_claim(self, claim: Claim) -> None:
        """
        Add a claim as a leaf node in the graph.

        Args:
            claim: The Claim to add.
        """
        self.claims[claim.id] = claim
        self.graph.add_node(
            claim.id,
            data=claim,
            node_type="claim",
        )
        logger.debug(f"Added claim {claim.id}: {claim.text[:50]}")

    def add_relationship(self, relationship: Relationship) -> None:
        """
        Add a directed relationship (edge) between two nodes.

        Args:
            relationship: The Relationship to add.

        Raises:
            ValueError: If source or target node does not exist.
        """
        if relationship.source_id not in self.graph:
            raise ValueError(
                f"Source node {relationship.source_id} not in graph"
            )
        if relationship.target_id not in self.graph:
            raise ValueError(
                f"Target node {relationship.target_id} not in graph"
            )

        self.relationships[relationship.id] = relationship
        self.graph.add_edge(
            relationship.source_id,
            relationship.target_id,
            data=relationship,
            relation=relationship.relation,
            strength=relationship.strength,
        )
        logger.debug(
            f"Added relationship {relationship.source_id} "
            f"--{relationship.relation.value}--> {relationship.target_id}"
        )

    def update_principle(self, principle: Principle) -> None:
        """
        Update an existing principle's attributes.

        Args:
            principle: The updated Principle.

        Raises:
            ValueError: If principle ID not in graph.
        """
        if principle.id not in self.principles:
            raise ValueError(f"Principle {principle.id} not in graph")

        self.principles[principle.id] = principle
        self.graph.nodes[principle.id]["data"] = principle
        logger.debug(f"Updated principle {principle.id}")

    # ── Query Methods ────────────────────────────────────────────────────────

    def get_principle(self, principle_id: str) -> Optional[Principle]:
        """
        Retrieve a principle by ID.

        Args:
            principle_id: The principle's ID.

        Returns:
            The Principle object, or None if not found.
        """
        return self.principles.get(principle_id)

    def get_related(
        self,
        principle_id: str,
        relation_type: Optional[RelationType] = None,
        depth: int = 1,
    ) -> List[Principle]:
        """
        Get principles related to a given principle within a certain depth.

        Args:
            principle_id: The seed principle ID.
            relation_type: If provided, filter to this relationship type.
            depth: Maximum distance to traverse (default 1 = direct neighbors).

        Returns:
            List of related Principle objects.

        Raises:
            ValueError: If principle_id not in graph.
        """
        if principle_id not in self.graph:
            raise ValueError(f"Principle {principle_id} not in graph")

        related = set()
        visited = set()
        queue = [(principle_id, 0)]

        while queue:
            node_id, dist = queue.pop(0)
            if node_id in visited or dist > depth:
                continue
            visited.add(node_id)

            # Look at successor and predecessor nodes
            for neighbor in list(self.graph.successors(node_id)) + list(
                self.graph.predecessors(node_id)
            ):
                edge_data = self.graph.get_edge_data(node_id, neighbor) or self.graph.get_edge_data(neighbor, node_id)
                if edge_data is None:
                    continue

                relation = edge_data.get("relation")
                if relation_type and relation != relation_type:
                    continue

                if neighbor != principle_id and neighbor in self.principles:
                    related.add(neighbor)

                if dist + 1 <= depth:
                    queue.append((neighbor, dist + 1))

        return [self.principles[pid] for pid in related if pid in self.principles]

    def get_supporting_claims(self, principle_id: str) -> List[Claim]:
        """
        Get all claims that support a principle.

        Args:
            principle_id: The principle ID.

        Returns:
            List of Claim objects connected to this principle.
        """
        supporting = []
        if principle_id in self.graph:
            for neighbor in self.graph.predecessors(principle_id):
                if neighbor in self.claims:
                    supporting.append(self.claims[neighbor])
        return supporting

    def get_contradictions(self) -> List[Tuple[Principle, Principle, float]]:
        """
        Find all contradictory relationships in the graph.

        Returns:
            List of (Principle_A, Principle_B, strength) tuples where A contradicts B.
        """
        contradictions = []
        for src, tgt, edge_data in self.graph.edges(data=True):
            if edge_data.get("relation") == RelationType.CONTRADICTS:
                if src in self.principles and tgt in self.principles:
                    strength = edge_data.get("strength", 1.0)
                    contradictions.append(
                        (self.principles[src], self.principles[tgt], strength)
                    )
        return contradictions

    def get_principles_by_discipline(self, discipline: Discipline) -> List[Principle]:
        """
        Get all principles tagged with a specific discipline.

        Args:
            discipline: The Discipline to filter by.

        Returns:
            List of Principles in that discipline.
        """
        return [
            p for p in self.principles.values() if discipline in p.disciplines
        ]

    def get_principles_by_conviction(self, min_conviction: ConvictionLevel) -> List[Principle]:
        """
        Get principles with conviction level >= min_conviction.

        Conviction levels ordered: AXIOM > STRONG > MODERATE > EXPLORATORY > CONTESTED

        Args:
            min_conviction: Minimum ConvictionLevel.

        Returns:
            List of Principles meeting the threshold.
        """
        conviction_rank = {
            ConvictionLevel.AXIOM: 5,
            ConvictionLevel.STRONG: 4,
            ConvictionLevel.MODERATE: 3,
            ConvictionLevel.EXPLORATORY: 2,
            ConvictionLevel.CONTESTED: 1,
        }
        min_rank = conviction_rank[min_conviction]
        return [
            p for p in self.principles.values()
            if conviction_rank.get(p.conviction, 0) >= min_rank
        ]

    def find_nearest_principles(
        self, embedding: List[float], k: int = 5
    ) -> List[Tuple[Principle, float]]:
        """
        Find k nearest principles by cosine similarity of embeddings.

        Args:
            embedding: Query embedding (list of floats).
            k: Number of results to return.

        Returns:
            List of (Principle, similarity_score) tuples, sorted descending by similarity.

        Raises:
            ValueError: If no principles have embeddings.
        """
        principles_with_embeddings = [
            p for p in self.principles.values()
            if p.embedding is not None
        ]
        if not principles_with_embeddings:
            logger.warning("No principles with embeddings found")
            return []

        embeddings_matrix = np.array([p.embedding for p in principles_with_embeddings])
        query_embedding = np.array(embedding).reshape(1, -1)

        similarities = cosine_similarity(query_embedding, embeddings_matrix)[0]
        top_indices = np.argsort(similarities)[::-1][:k]

        results = [
            (principles_with_embeddings[i], float(similarities[i]))
            for i in top_indices
        ]
        return results

    def get_axioms(self) -> List[Principle]:
        """
        Get all principles with conviction level == AXIOM (foundational beliefs).

        Returns:
            List of axiomatic Principles.
        """
        return [
            p for p in self.principles.values()
            if p.conviction == ConvictionLevel.AXIOM
        ]

    def get_principle_neighborhood(
        self, principle_id: str, radius: int = 2
    ) -> nx.DiGraph:
        """
        Extract a subgraph around a principle (ego network).

        Args:
            principle_id: The seed principle ID.
            radius: Maximum distance from the seed.

        Returns:
            A new DiGraph containing the neighborhood.

        Raises:
            ValueError: If principle_id not in graph.
        """
        if principle_id not in self.graph:
            raise ValueError(f"Principle {principle_id} not in graph")

        # Use ego_graph from NetworkX
        neighborhood = nx.ego_graph(
            self.graph, principle_id, radius=radius, undirected=False
        )
        return neighborhood

    # ── Analytics ────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """
        Get summary statistics about the graph.

        Returns:
            Dictionary with node/edge counts, density, etc.
        """
        num_principles = len(self.principles)
        num_claims = len(self.claims)
        num_edges = self.graph.number_of_edges()

        density = (
            nx.density(self.graph)
            if num_principles > 1
            else 0.0
        )

        conviction_dist = defaultdict(int)
        for p in self.principles.values():
            conviction_dist[p.conviction.value] += 1

        return {
            "num_principles": num_principles,
            "num_claims": num_claims,
            "num_relationships": num_edges,
            "graph_density": density,
            "conviction_distribution": dict(conviction_dist),
            "num_contradictions": len(self.get_contradictions()),
        }

    def get_principle_centrality(self) -> Dict[str, float]:
        """
        Compute betweenness centrality for all principles.

        Identifies principles that bridge different parts of the graph.

        Returns:
            Dictionary mapping principle IDs to centrality scores (0-1).
        """
        return nx.betweenness_centrality(self.graph)


# ── PrincipleDistiller ───────────────────────────────────────────────────────


class PrincipleDistiller:
    """
    Converts raw claims into distilled principles via clustering and LLM analysis.

    Process:
    1. Embed and cluster claims by semantic similarity
    2. For each cluster, use Claude to distill a canonical principle
    3. Check for duplicates in existing graph (via embedding similarity)
    4. Update existing principles or create new ones
    5. Detect relationships between new and existing principles
    """

    def __init__(self, graph: OntologyGraph, client: Optional[Anthropic] = None):
        """
        Initialize the distiller.

        Args:
            graph: The OntologyGraph to update.
            client: Anthropic API client (creates new if None).
        """
        self.graph = graph
        self.client = client or Anthropic()
        logger.info("Initialized PrincipleDistiller")

    def distill_principles(
        self,
        claims: List[Claim],
        clustering_threshold: float = 0.3,
        min_cluster_size: int = 2,
    ) -> Tuple[List[Principle], List[Relationship]]:
        """
        Distill a set of claims into principles.

        Args:
            claims: List of Claim objects to cluster and distill.
            clustering_threshold: Distance threshold for agglomerative clustering.
            min_cluster_size: Minimum claims per cluster to form a principle.

        Returns:
            Tuple of (new/updated Principles, new Relationships)
        """
        if not claims:
            logger.info("No claims to distill")
            return [], []

        # Embed claims if not already done
        for claim in claims:
            if claim.embedding is None:
                claim.embedding = self._get_embedding(claim.text)

        # Cluster claims
        clusters = self._cluster_claims(claims, clustering_threshold, min_cluster_size)
        logger.info(f"Clustered {len(claims)} claims into {len(clusters)} clusters")

        new_principles = []
        new_relationships = []

        for cluster in clusters:
            principle = self._distill_cluster(cluster)
            if principle is None:
                continue

            # Check for duplicate in graph
            existing_id = self._find_duplicate_principle(principle)
            if existing_id:
                # Update existing principle
                existing = self.graph.get_principle(existing_id)
                if existing:
                    existing.mention_count += len(cluster)
                    existing.last_reinforced = date.today()
                    # Merge supporting claims
                    claim_ids = [c.id for c in cluster]
                    for cid in claim_ids:
                        if cid not in existing.supporting_claims:
                            existing.supporting_claims.append(cid)
                    self.graph.update_principle(existing)
                    logger.info(
                        f"Updated principle {existing_id} "
                        f"(now {existing.mention_count} mentions)"
                    )
                    principle = existing
            else:
                # New principle
                principle.mention_count = len(cluster)
                principle.first_appeared = date.today()
                principle.last_reinforced = date.today()
                principle.supporting_claims = [c.id for c in cluster]

                # Add claims to graph
                for claim in cluster:
                    if claim.id not in self.graph.claims:
                        self.graph.add_claim(claim)
                    # Connect claim to principle
                    rel = Relationship(
                        source_id=claim.id,
                        target_id=principle.id,
                        relation=RelationType.SUPPORTS,
                        strength=0.95,
                        detected_by="distillation",
                    )
                    self.graph.add_relationship(rel)
                    new_relationships.append(rel)

                self.graph.add_principle(principle)
                new_principles.append(principle)
                logger.info(f"Created principle {principle.id}")

        # Detect relationships between principles
        inter_principle_rels = self._detect_principle_relationships(
            new_principles
        )
        for rel in inter_principle_rels:
            self.graph.add_relationship(rel)
        new_relationships.extend(inter_principle_rels)

        logger.info(
            f"Distilled {len(new_principles)} new principles, "
            f"{len(new_relationships)} relationships"
        )
        return new_principles, new_relationships

    def _cluster_claims(
        self,
        claims: List[Claim],
        threshold: float,
        min_size: int,
    ) -> List[List[Claim]]:
        """
        Cluster claims by semantic similarity using agglomerative clustering.

        Args:
            claims: Claims with embeddings.
            threshold: Distance cutoff for clustering.
            min_size: Minimum cluster size.

        Returns:
            List of claim clusters.
        """
        if len(claims) == 1:
            return [[claims[0]]]

        embeddings = np.array([c.embedding for c in claims])
        distances = 1 - cosine_similarity(embeddings)

        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=threshold,
            linkage="average",
        )
        labels = clustering.fit_predict(embeddings)

        clusters_dict = defaultdict(list)
        for i, label in enumerate(labels):
            clusters_dict[label].append(claims[i])

        # Filter by minimum size
        clusters = [
            c for c in clusters_dict.values()
            if len(c) >= min_size
        ]
        logger.debug(
            f"After filtering by min_size={min_size}, "
            f"kept {len(clusters)} clusters"
        )
        return clusters

    def _distill_cluster(self, cluster: List[Claim]) -> Optional[Principle]:
        """
        Use Claude to distill a cluster of claims into a single principle.

        Args:
            cluster: List of related claims.

        Returns:
            A new Principle object, or None if distillation fails.
        """
        claim_texts = [f"- {c.text}" for c in cluster]
        claims_str = "\n".join(claim_texts)

        prompt = f"""You are an expert knowledge distiller. Given these related claims,
extract a single canonical principle that captures their essence.

Claims:
{claims_str}

Respond with ONLY a JSON object (no markdown, no explanation):
{{
  "principle_text": "A concise, general statement capturing the core belief",
  "description": "A more detailed explanation of the principle",
  "conviction_level": "axiom" | "strong" | "moderate" | "exploratory" | "contested",
  "disciplines": ["Philosophy", "AI", ...]
}}

Be precise. The principle text should be a single assertoric statement, 2-3 sentences maximum.
"""

        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text
            data = json.loads(content)

            conviction_str = data.get("conviction_level", "moderate").lower()
            conviction = ConvictionLevel(conviction_str)

            disciplines = [
                Discipline(d) for d in data.get("disciplines", [])
                if d in [disc.value for disc in Discipline]
            ]

            principle = Principle(
                text=data.get("principle_text", ""),
                description=data.get("description", ""),
                conviction=conviction,
                conviction_score=self._conviction_to_score(conviction),
                disciplines=disciplines,
                embedding=self._get_embedding(data.get("principle_text", "")),
            )
            logger.debug(f"Distilled principle: {principle.text[:50]}")
            return principle

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to distill cluster: {e}")
            return None

    def _find_duplicate_principle(self, principle: Principle) -> Optional[str]:
        """
        Check if principle already exists in graph via embedding similarity.

        Args:
            principle: The candidate principle.

        Returns:
            The existing principle ID if found (similarity > 0.85), else None.
        """
        if principle.embedding is None:
            return None

        similar = self.graph.find_nearest_principles(principle.embedding, k=1)
        if similar and similar[0][1] > 0.85:
            return similar[0][0].id
        return None

    def _detect_principle_relationships(
        self, principles: List[Principle]
    ) -> List[Relationship]:
        """
        Detect relationships between newly created principles.

        Checks textual and embedding similarity to find supports, refines, etc.

        Args:
            principles: New principles to relate.

        Returns:
            List of Relationship objects.
        """
        relationships = []

        for i, p1 in enumerate(principles):
            for p2 in principles[i + 1:]:
                if p1.embedding is None or p2.embedding is None:
                    continue

                sim = cosine_similarity(
                    np.array([p1.embedding]),
                    np.array([p2.embedding]),
                )[0, 0]

                # If high similarity, they might be versions of each other
                if sim > 0.8:
                    rel = Relationship(
                        source_id=p1.id,
                        target_id=p2.id,
                        relation=RelationType.REFINES,
                        strength=sim,
                        detected_by="geometric",
                    )
                    relationships.append(rel)

        return relationships

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Get embedding for text from Claude (using API-based embedding).

        For production, integrate with dedicated embedding service (e.g., SBERT).
        This is a placeholder that generates a random embedding.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding.
        """
        # Placeholder: return a dummy embedding
        # In production, use: SentenceTransformer("all-MiniLM-L6-v2").encode(text)
        import hashlib

        hash_obj = hashlib.sha256(text.encode())
        seed = int(hash_obj.hexdigest(), 16) % (2 ** 32)
        np.random.seed(seed)
        embedding = np.random.randn(384).tolist()
        return embedding

    @staticmethod
    def _conviction_to_score(conviction: ConvictionLevel) -> float:
        """Convert conviction level to continuous score."""
        scores = {
            ConvictionLevel.AXIOM: 0.95,
            ConvictionLevel.STRONG: 0.75,
            ConvictionLevel.MODERATE: 0.5,
            ConvictionLevel.EXPLORATORY: 0.3,
            ConvictionLevel.CONTESTED: 0.1,
        }
        return scores.get(conviction, 0.5)


# ── GraphPersistence ─────────────────────────────────────────────────────────


class GraphPersistence:
    """
    Serialize/deserialize OntologyGraph to/from JSON and other formats.

    Supports incremental updates and multiple export formats.
    """

    def __init__(self, graph: OntologyGraph):
        """
        Initialize persistence handler.

        Args:
            graph: The OntologyGraph to persist.
        """
        self.graph = graph
        logger.info("Initialized GraphPersistence")

    def save_to_json(self, path: str) -> None:
        """
        Serialize entire graph to JSON.

        Args:
            path: File path to save to.
        """
        data = {
            "principles": [
                p.model_dump() for p in self.graph.principles.values()
            ],
            "claims": [
                c.model_dump() for c in self.graph.claims.values()
            ],
            "relationships": [
                r.model_dump() for r in self.graph.relationships.values()
            ],
            "metadata": {
                "saved_at": datetime.now().isoformat(),
                "num_principles": len(self.graph.principles),
                "num_claims": len(self.graph.claims),
                "num_relationships": len(self.graph.relationships),
            },
        }

        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)

        with open(path_obj, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Saved graph to {path}")

    def load_from_json(self, path: str) -> None:
        """
        Deserialize graph from JSON.

        Clears existing graph and rebuilds from file.

        Args:
            path: File path to load from.

        Raises:
            FileNotFoundError: If path doesn't exist.
        """
        path_obj = Path(path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Graph file not found: {path}")

        with open(path_obj, "r") as f:
            data = json.load(f)

        # Clear existing
        self.graph.graph.clear()
        self.graph.principles.clear()
        self.graph.claims.clear()
        self.graph.relationships.clear()

        # Load principles
        for p_data in data.get("principles", []):
            principle = Principle(**p_data)
            self.graph.add_principle(principle)

        # Load claims
        for c_data in data.get("claims", []):
            claim = Claim(**c_data)
            self.graph.add_claim(claim)

        # Load relationships
        for r_data in data.get("relationships", []):
            relationship = Relationship(**r_data)
            self.graph.add_relationship(relationship)

        logger.info(
            f"Loaded graph from {path}: "
            f"{len(self.graph.principles)} principles, "
            f"{len(self.graph.claims)} claims"
        )

    def export_to_graphml(self, path: str) -> None:
        """
        Export graph to GraphML format for visualization.

        Args:
            path: Output file path.
        """
        # Create a simpler graph for export (store principle text as labels)
        export_graph = nx.DiGraph()

        for pid, principle in self.graph.principles.items():
            export_graph.add_node(
                pid,
                label=principle.text,
                conviction=principle.conviction.value,
            )

        for rid, rel in self.graph.relationships.items():
            if rel.source_id in self.graph.principles and \
               rel.target_id in self.graph.principles:
                export_graph.add_edge(
                    rel.source_id,
                    rel.target_id,
                    label=rel.relation.value,
                    strength=rel.strength,
                )

        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        nx.write_graphml(export_graph, path_obj)
        logger.info(f"Exported graph to GraphML: {path}")

    def export_to_adjacency_list(self, path: str) -> None:
        """
        Export graph as adjacency list (text format).

        Args:
            path: Output file path.
        """
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)

        with open(path_obj, "w") as f:
            f.write("# Principle Knowledge Graph - Adjacency List\n\n")

            for pid, principle in sorted(self.graph.principles.items()):
                f.write(f"[{pid}] {principle.text}\n")
                f.write(f"  Conviction: {principle.conviction.value}\n")
                f.write(f"  Mentions: {principle.mention_count}\n")

                successors = list(self.graph.graph.successors(pid))
                if successors:
                    f.write("  -> ")
                    relations_str = []
                    for succ in successors:
                        edge_data = self.graph.graph.get_edge_data(pid, succ)
                        if edge_data and succ in self.graph.principles:
                            rel_type = edge_data.get("relation", "unknown")
                            relations_str.append(
                                f"{rel_type.value}({succ[:8]})"
                            )
                    f.write(", ".join(relations_str))
                    f.write("\n")

                f.write("\n")

        logger.info(f"Exported graph to adjacency list: {path}")

    def incremental_update(
        self,
        new_principles: List[Principle],
        new_relationships: List[Relationship],
        new_claims: List[Claim],
    ) -> None:
        """
        Add new principles, claims, and relationships to existing graph.

        Skips duplicates based on ID.

        Args:
            new_principles: Principles to add/update.
            new_relationships: Relationships to add.
            new_claims: Claims to add.
        """
        # Add claims first (they may be referenced by relationships)
        for claim in new_claims:
            if claim.id not in self.graph.claims:
                self.graph.add_claim(claim)

        # Add/update principles
        for principle in new_principles:
            if principle.id in self.graph.principles:
                self.graph.update_principle(principle)
            else:
                self.graph.add_principle(principle)

        # Add relationships (edges)
        for rel in new_relationships:
            if rel.id not in self.graph.relationships:
                self.graph.add_relationship(rel)

        logger.info(
            f"Incremental update: +{len(new_principles)} principles, "
            f"+{len(new_claims)} claims, +{len(new_relationships)} relationships"
        )

    def export_to_json_ld(self, path: str) -> None:
        """
        Export graph as JSON-LD for semantic web compatibility.

        Args:
            path: Output file path.
        """
        context = {
            "@context": {
                "@vocab": "http://noosphere.theseus/ontology/",
                "text": "rdfs:label",
                "conviction": "noosphere:conviction",
                "mentions": "noosphere:mentionCount",
                "supports": {"@type": "@id"},
                "contradicts": {"@type": "@id"},
            },
            "@graph": [],
        }

        for principle in self.graph.principles.values():
            context["@graph"].append(
                {
                    "@id": principle.id,
                    "@type": "Principle",
                    "text": principle.text,
                    "description": principle.description,
                    "conviction": principle.conviction.value,
                    "mentions": principle.mention_count,
                }
            )

        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)

        with open(path_obj, "w") as f:
            json.dump(context, f, indent=2)
        logger.info(f"Exported graph to JSON-LD: {path}")

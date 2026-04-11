"""
ONTOLOGICAL CONTRADICTION MAPPER
=================================

Integrates formal ontology with embedding-space geometry to map
concepts, claims, and their contradictions as a structured graph
embedded in vector space.

THE PROBLEM:
  The contradiction detector (contradiction_detector.py) works on
  isolated sentence pairs. But ideological contradiction is not just
  pairwise — it's *structural*. A claim can be locally coherent but
  globally contradictory when its downstream consequences collide
  with consequences of other claims in the same system.

  Example from the book: "Capitalism tends toward perfect coherence"
  is locally coherent. "Industries inevitably drift toward purposeless
  efficiency" is also locally coherent. But together they create a
  *tension* that requires resolution — which the book resolves via
  the "capitalist society, not capitalism" distinction. Without the
  ontological structure, pairwise detection misses this.

THE SOLUTION:
  1. Parse claims into a directed graph (claim → therefore → consequence)
  2. Embed every node (claim) in vector space
  3. Use the graph structure to propagate contradiction signals:
     - Direct contradiction: two claims that flatly oppose each other
     - Inherited contradiction: A entails B, C contradicts B ∴ C
       undermines A
     - Tension: two claims that are not directly contradictory but
       whose downstream consequences collide
  4. Compute a COHERENCE SCORE for any subset of the ontology —
     measuring how internally consistent a set of claims is
  5. Use Householder reflection to generate the "anti-ontology" —
     the maximally contradictory mirror of the system

This bridges the three experiments:
  - Contradiction Geometry → pairwise detection at each edge
  - Reverse Marxism → reflection of entire conceptual structures
  - Embedding Geometry Conjecture → the geometric theory underpinning
    why this works (difference vectors, not cosine)

REQUIRES:
    pip install sentence-transformers numpy scipy scikit-learn networkx
"""

import numpy as np
import json
import re
import os
from typing import List, Tuple, Dict, Optional, Set
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict

try:
    import networkx as nx
except ImportError:
    raise ImportError("networkx required: pip install networkx")

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    raise ImportError("sentence-transformers required: pip install sentence-transformers")

from scipy.spatial.distance import cosine as cosine_dist


# ═════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class Claim:
    """A single claim in the ontology."""
    id: str                          # e.g. "ch01.claim.03"
    text: str                        # The claim text
    claim_type: str                  # "CLAIM", "THEREFORE", "CONSEQUENCE", etc.
    chapter: str                     # e.g. "Chapter 01"
    section: str = ""                # e.g. "Foundation: Coherence and Reality"
    embedding: Optional[np.ndarray] = field(default=None, repr=False)
    metadata: Dict = field(default_factory=dict)

    def __hash__(self):
        return hash(self.id)


@dataclass
class Edge:
    """A relationship between two claims."""
    source: str         # claim id
    target: str         # claim id
    relation: str       # "entails", "contradicts", "supports", "tensions"
    weight: float = 1.0
    metadata: Dict = field(default_factory=dict)


# ═════════════════════════════════════════════════════════════════════════════
# ONTOLOGY PARSER
# ═════════════════════════════════════════════════════════════════════════════

def parse_ontology_markdown(filepath: str) -> Tuple[List[Claim], List[Edge]]:
    """
    Parse the Argumentative_Ontology.md into structured claims and edges.

    The markdown uses a consistent format:
      **CLAIM:** text
      **THEREFORE:** text
      **CONSEQUENCE:** text
      **CHALLENGE:** text
      **DISTINCT CLAIM:** text
      **RESERVED:** text
      **PURPOSE:** text

    Logical flow: CLAIM → THEREFORE → CONSEQUENCE
    Each THEREFORE is entailed by the preceding CLAIM(s).
    Each CONSEQUENCE follows from a THEREFORE.
    """
    with open(filepath, 'r') as f:
        content = f.read()

    claims = []
    edges = []

    current_chapter = ""
    current_section = ""
    claim_counter = defaultdict(int)
    prev_claims = []  # stack of recent claims for building edges

    for line in content.split('\n'):
        line = line.strip()

        # Track chapter
        chapter_match = re.match(r'^## (Chapter \d+.*)', line)
        if chapter_match:
            current_chapter = chapter_match.group(1)
            prev_claims = []
            continue

        # Track section
        section_match = re.match(r'^### (.+)', line)
        if section_match:
            current_section = section_match.group(1)
            prev_claims = []
            continue

        # Parse claim types
        claim_patterns = [
            (r'\*\*CLAIM:\*\*\s*(.*)', "CLAIM"),
            (r'\*\*THEREFORE:\*\*\s*(.*)', "THEREFORE"),
            (r'\*\*CONSEQUENCE:\*\*\s*(.*)', "CONSEQUENCE"),
            (r'\*\*CHALLENGE:\*\*\s*(.*)', "CHALLENGE"),
            (r'\*\*DISTINCT CLAIM:\*\*\s*(.*)', "DISTINCT_CLAIM"),
            (r'\*\*RESERVED:\*\*\s*(.*)', "RESERVED"),
            (r'\*\*PURPOSE:\*\*\s*(.*)', "PURPOSE"),
        ]

        for pattern, claim_type in claim_patterns:
            match = re.match(pattern, line)
            if match:
                text = match.group(1).strip()
                if not text:
                    continue

                # Generate ID
                ch_num = re.search(r'Chapter (\d+)', current_chapter)
                ch_id = f"ch{ch_num.group(1)}" if ch_num else "ch00"
                claim_counter[ch_id] += 1
                claim_id = f"{ch_id}.{claim_type.lower()}.{claim_counter[ch_id]:02d}"

                claim = Claim(
                    id=claim_id,
                    text=text,
                    claim_type=claim_type,
                    chapter=current_chapter,
                    section=current_section,
                )
                claims.append(claim)

                # Build edges based on logical flow
                if claim_type == "THEREFORE" and prev_claims:
                    # THEREFORE is entailed by preceding CLAIMs
                    for prev in prev_claims:
                        if prev.claim_type in ("CLAIM", "DISTINCT_CLAIM"):
                            edges.append(Edge(
                                source=prev.id,
                                target=claim_id,
                                relation="entails",
                            ))
                elif claim_type == "CONSEQUENCE" and prev_claims:
                    # CONSEQUENCE follows from preceding THEREFORE
                    for prev in prev_claims:
                        if prev.claim_type == "THEREFORE":
                            edges.append(Edge(
                                source=prev.id,
                                target=claim_id,
                                relation="entails",
                            ))
                            break
                elif claim_type == "CHALLENGE" and prev_claims:
                    # CHALLENGE contradicts or tensions the preceding
                    for prev in prev_claims:
                        edges.append(Edge(
                            source=prev.id,
                            target=claim_id,
                            relation="tensions",
                        ))

                # Update stack
                if claim_type in ("THEREFORE", "CONSEQUENCE"):
                    prev_claims = [claim]
                elif claim_type == "CHALLENGE":
                    prev_claims = [claim]
                else:
                    prev_claims.append(claim)

                break

    return claims, edges


# ═════════════════════════════════════════════════════════════════════════════
# THE ONTOLOGICAL GRAPH
# ═════════════════════════════════════════════════════════════════════════════

class OntologicalGraph:
    """
    A directed graph of claims embedded in vector space.

    Nodes are claims (with embeddings).
    Edges are logical relationships (entails, contradicts, tensions).

    The graph supports:
      1. Contradiction detection between any two nodes
      2. Contradiction propagation through the graph
      3. Coherence scoring for subsets of nodes
      4. Ontological reflection (generating the anti-ontology)
      5. Tension detection (claims that don't directly contradict
         but whose consequences do)
    """

    def __init__(self, model_name: str = "all-mpnet-base-v2",
                 device: Optional[str] = None):
        self.model = SentenceTransformer(model_name, device=device)
        self.graph = nx.DiGraph()
        self.claims = {}          # id → Claim
        self.embeddings = {}      # id → np.ndarray
        self._contradiction_direction = None

    # ─── Building the Graph ──────────────────────────────────────────────

    def load_from_ontology(self, filepath: str):
        """Load claims and edges from the Argumentative_Ontology.md file."""
        claims, edges = parse_ontology_markdown(filepath)

        print(f"Parsed {len(claims)} claims and {len(edges)} edges")

        # Embed all claims
        texts = [c.text for c in claims]
        embeddings = self.model.encode(texts, show_progress_bar=True,
                                        convert_to_numpy=True)

        for claim, emb in zip(claims, embeddings):
            claim.embedding = emb
            self.claims[claim.id] = claim
            self.embeddings[claim.id] = emb
            self.graph.add_node(claim.id, claim=claim)

        for edge in edges:
            if edge.source in self.claims and edge.target in self.claims:
                self.graph.add_edge(
                    edge.source, edge.target,
                    relation=edge.relation,
                    weight=edge.weight,
                )

        print(f"Graph built: {self.graph.number_of_nodes()} nodes, "
              f"{self.graph.number_of_edges()} edges")

    def add_claim(self, claim: Claim):
        """Add a single claim to the graph."""
        if claim.embedding is None:
            claim.embedding = self.model.encode([claim.text],
                                                 show_progress_bar=False)[0]
        self.claims[claim.id] = claim
        self.embeddings[claim.id] = claim.embedding
        self.graph.add_node(claim.id, claim=claim)

    def add_edge(self, edge: Edge):
        """Add a relationship between two claims."""
        self.graph.add_edge(
            edge.source, edge.target,
            relation=edge.relation,
            weight=edge.weight,
        )

    # ─── Pairwise Analysis ──────────────────────────────────────────────

    def cosine_similarity(self, id_a: str, id_b: str) -> float:
        """Cosine similarity between two claim embeddings."""
        return float(1.0 - cosine_dist(self.embeddings[id_a],
                                        self.embeddings[id_b]))

    def difference_vector(self, id_a: str, id_b: str) -> np.ndarray:
        """Difference vector from claim A to claim B."""
        return self.embeddings[id_b] - self.embeddings[id_a]

    def hoyer_sparsity(self, vec: np.ndarray) -> float:
        """Hoyer sparsity of a vector."""
        n = len(vec)
        l1 = np.sum(np.abs(vec))
        l2 = np.sqrt(np.sum(vec ** 2))
        if l2 == 0:
            return 0.0
        return (np.sqrt(n) - l1 / l2) / (np.sqrt(n) - 1)

    def analyze_pair(self, id_a: str, id_b: str) -> Dict:
        """Full analysis of the relationship between two claims."""
        d = self.difference_vector(id_a, id_b)
        cos = self.cosine_similarity(id_a, id_b)
        hoy = self.hoyer_sparsity(d)
        l2 = float(np.linalg.norm(d))

        result = {
            "claim_a": self.claims[id_a].text,
            "claim_b": self.claims[id_b].text,
            "cosine_similarity": cos,
            "hoyer_sparsity": hoy,
            "l2_distance": l2,
            "graph_relationship": self._get_graph_relationship(id_a, id_b),
        }

        if self._contradiction_direction is not None:
            proj = float(np.dot(d, self._contradiction_direction))
            result["contradiction_projection"] = proj

        return result

    def _get_graph_relationship(self, id_a: str, id_b: str) -> str:
        """Get the relationship between two claims from the graph."""
        if self.graph.has_edge(id_a, id_b):
            return self.graph[id_a][id_b].get("relation", "connected")
        if self.graph.has_edge(id_b, id_a):
            return f"reverse_{self.graph[id_b][id_a].get('relation', 'connected')}"
        # Check for path
        try:
            path = nx.shortest_path(self.graph, id_a, id_b)
            return f"path_length_{len(path) - 1}"
        except nx.NetworkXNoPath:
            pass
        try:
            path = nx.shortest_path(self.graph, id_b, id_a)
            return f"reverse_path_length_{len(path) - 1}"
        except nx.NetworkXNoPath:
            return "disconnected"

    # ─── Contradiction Detection (Graph-Propagated) ──────────────────────

    def detect_contradictions(self,
                              cosine_threshold: float = 0.3,
                              top_k: int = 20) -> List[Dict]:
        """
        Detect contradictions across the entire ontology.

        Unlike pairwise detection, this uses the graph structure:
        1. Find claim pairs with high cosine similarity (topically related)
           but geometric signatures of contradiction
        2. Propagate: if A→B and C contradicts B, then C undermines A
        3. Detect tensions: claims whose downstream consequences collide

        Returns the top-k most likely contradictions/tensions.
        """
        claim_ids = list(self.claims.keys())
        n = len(claim_ids)
        all_embs = np.array([self.embeddings[cid] for cid in claim_ids])

        # Compute pairwise cosine similarity matrix
        # (only upper triangle needed)
        cos_matrix = all_embs @ all_embs.T
        norms = np.linalg.norm(all_embs, axis=1)
        cos_matrix = cos_matrix / (norms[:, None] * norms[None, :] + 1e-10)

        # Find pairs with high topical similarity
        candidates = []
        for i in range(n):
            for j in range(i + 1, n):
                cos = cos_matrix[i, j]
                if cos < cosine_threshold:
                    continue  # Too dissimilar — probably just unrelated

                # Same chapter pairs that are already in an entailment
                # chain are not contradictions
                if self.graph.has_edge(claim_ids[i], claim_ids[j]) or \
                   self.graph.has_edge(claim_ids[j], claim_ids[i]):
                    edge_rel = self._get_graph_relationship(
                        claim_ids[i], claim_ids[j])
                    if "entails" in edge_rel:
                        continue

                # Compute difference-space features
                d = all_embs[j] - all_embs[i]
                hoy = self.hoyer_sparsity(d)
                l2 = float(np.linalg.norm(d))

                # Contradiction score: combine signals
                # Higher L2 + higher sparsity + high cosine = contradiction
                # (topically related but semantically divergent)
                contra_score = hoy * l2 * cos

                if self._contradiction_direction is not None:
                    proj = abs(float(np.dot(d, self._contradiction_direction)))
                    contra_score *= (1 + proj)

                candidates.append({
                    "claim_a_id": claim_ids[i],
                    "claim_b_id": claim_ids[j],
                    "claim_a": self.claims[claim_ids[i]].text,
                    "claim_b": self.claims[claim_ids[j]].text,
                    "chapter_a": self.claims[claim_ids[i]].chapter,
                    "chapter_b": self.claims[claim_ids[j]].chapter,
                    "cosine_similarity": float(cos),
                    "hoyer_sparsity": float(hoy),
                    "l2_distance": l2,
                    "contradiction_score": float(contra_score),
                    "graph_relationship": self._get_graph_relationship(
                        claim_ids[i], claim_ids[j]),
                })

        # Sort by contradiction score
        candidates.sort(key=lambda x: -x["contradiction_score"])
        return candidates[:top_k]

    def detect_tensions(self, depth: int = 3) -> List[Dict]:
        """
        Detect *structural* tensions: claims that are not directly
        contradictory but whose downstream consequences conflict.

        This is the key advantage of the ontological approach over
        pairwise detection. A tension exists when:
          - Claim A entails consequence X
          - Claim B entails consequence Y
          - X and Y are contradictory (or highly divergent)
          - But A and B are not directly contradictory

        These are the most interesting findings because they reveal
        hidden incoherence in an ideological system.
        """
        tensions = []
        claim_ids = list(self.claims.keys())

        # For each pair of claims, trace their downstream consequences
        # and check for collisions
        for i, id_a in enumerate(claim_ids):
            # Get all claims reachable from A within `depth` edges
            downstream_a = self._get_downstream(id_a, depth)
            if not downstream_a:
                continue

            for j, id_b in enumerate(claim_ids):
                if j <= i:
                    continue
                # Skip if A and B are in the same chain
                if id_b in downstream_a or id_a in self._get_downstream(id_b, 1):
                    continue

                downstream_b = self._get_downstream(id_b, depth)
                if not downstream_b:
                    continue

                # Check if any downstream consequence of A conflicts
                # with any downstream consequence of B
                for da_id in downstream_a:
                    for db_id in downstream_b:
                        if da_id == db_id:
                            continue

                        d = self.embeddings[db_id] - self.embeddings[da_id]
                        cos = self.cosine_similarity(da_id, db_id)
                        l2 = float(np.linalg.norm(d))
                        hoy = self.hoyer_sparsity(d)

                        # Tension: high topical similarity + high divergence
                        if cos > 0.4 and l2 > 0.6:
                            tension_score = hoy * l2 * cos
                            tensions.append({
                                "root_a": self.claims[id_a].text,
                                "root_b": self.claims[id_b].text,
                                "consequence_a": self.claims[da_id].text,
                                "consequence_b": self.claims[db_id].text,
                                "root_a_id": id_a,
                                "root_b_id": id_b,
                                "consequence_a_id": da_id,
                                "consequence_b_id": db_id,
                                "cosine_similarity": float(cos),
                                "l2_distance": l2,
                                "tension_score": float(tension_score),
                            })

        tensions.sort(key=lambda x: -x["tension_score"])
        return tensions[:20]

    def _get_downstream(self, claim_id: str, depth: int) -> Set[str]:
        """Get all claim IDs reachable from a claim within `depth` edges."""
        visited = set()
        frontier = {claim_id}
        for _ in range(depth):
            next_frontier = set()
            for node in frontier:
                for successor in self.graph.successors(node):
                    if successor not in visited:
                        visited.add(successor)
                        next_frontier.add(successor)
            frontier = next_frontier
        return visited

    # ─── Coherence Scoring ───────────────────────────────────────────────

    def coherence_score(self,
                        claim_ids: Optional[List[str]] = None) -> Dict:
        """
        Compute a coherence score for a set of claims.

        Coherence is measured as the ratio of structurally consistent
        relationships to total relationships. A perfectly coherent
        ontology has:
          - All entailment edges connecting claims that are geometrically
            close (high cosine in difference direction)
          - No contradiction signals between claims in the same chain
          - Low tension between downstream consequences

        The score ranges from 0 (maximally incoherent) to 1 (perfectly
        coherent).

        If claim_ids is None, scores the entire ontology.
        """
        if claim_ids is None:
            claim_ids = list(self.claims.keys())

        if len(claim_ids) < 2:
            return {"coherence": 1.0, "n_claims": len(claim_ids)}

        # Get subgraph
        subgraph = self.graph.subgraph(claim_ids)
        embs = np.array([self.embeddings[cid] for cid in claim_ids])

        # 1. Entailment consistency: entailment edges should have
        #    high cosine similarity
        entailment_scores = []
        for u, v, data in subgraph.edges(data=True):
            if data.get("relation") == "entails":
                cos = self.cosine_similarity(u, v)
                entailment_scores.append(cos)

        mean_entailment_cos = np.mean(entailment_scores) if entailment_scores else 1.0

        # 2. Internal contradiction density: how many high-tension
        #    pairs exist within the claim set?
        n_pairs = 0
        tension_sum = 0
        for i, id_a in enumerate(claim_ids):
            for j in range(i + 1, len(claim_ids)):
                id_b = claim_ids[j]
                d = self.embeddings[id_b] - self.embeddings[id_a]
                cos = self.cosine_similarity(id_a, id_b)
                if cos > 0.3:  # Only count topically related pairs
                    hoy = self.hoyer_sparsity(d)
                    l2 = float(np.linalg.norm(d))
                    tension_sum += hoy * l2
                    n_pairs += 1

        mean_tension = tension_sum / max(n_pairs, 1)

        # 3. Chain integrity: are there broken chains (claims that
        #    should connect but don't)?
        n_components = nx.number_weakly_connected_components(subgraph)
        fragmentation = 1.0 - (1.0 / max(n_components, 1))

        # Composite score
        coherence = (
            0.5 * mean_entailment_cos +
            0.3 * (1.0 - min(mean_tension / 0.3, 1.0)) +
            0.2 * (1.0 - fragmentation)
        )

        return {
            "coherence": float(coherence),
            "mean_entailment_cosine": float(mean_entailment_cos),
            "mean_tension": float(mean_tension),
            "fragmentation": float(fragmentation),
            "n_claims": len(claim_ids),
            "n_edges": subgraph.number_of_edges(),
            "n_components": n_components,
        }

    def chapter_coherence(self) -> Dict[str, Dict]:
        """Compute coherence scores per chapter."""
        chapters = defaultdict(list)
        for cid, claim in self.claims.items():
            chapters[claim.chapter].append(cid)

        results = {}
        for chapter, ids in sorted(chapters.items()):
            results[chapter] = self.coherence_score(ids)
            results[chapter]["n_claims_in_chapter"] = len(ids)

        return results

    # ─── Ontological Reflection (Anti-Ontology) ─────────────────────────

    def reflect_ontology(self,
                         axis: np.ndarray,
                         alpha: float = 2.0) -> 'OntologicalGraph':
        """
        Generate the anti-ontology by Householder-reflecting every
        claim across a conceptual axis.

        This produces the maximally contradictory mirror of the system:
        if the original ontology argues for X, the anti-ontology argues
        for not-X, preserving the logical structure but inverting the
        ideological content.

        Returns a new OntologicalGraph with reflected embeddings.
        (The new graph has the same structure but inverted semantics.)
        """
        reflected = OntologicalGraph.__new__(OntologicalGraph)
        reflected.model = self.model
        reflected.graph = self.graph.copy()
        reflected.claims = {}
        reflected.embeddings = {}
        reflected._contradiction_direction = self._contradiction_direction

        for cid, claim in self.claims.items():
            emb = claim.embedding
            proj = np.dot(emb, axis)
            reflected_emb = emb - alpha * 2 * proj * axis
            reflected_emb = reflected_emb / (np.linalg.norm(reflected_emb) + 1e-10)

            new_claim = Claim(
                id=f"anti_{cid}",
                text=f"[REFLECTED] {claim.text}",
                claim_type=claim.claim_type,
                chapter=f"Anti-{claim.chapter}",
                section=claim.section,
                embedding=reflected_emb,
            )
            reflected.claims[f"anti_{cid}"] = new_claim
            reflected.embeddings[f"anti_{cid}"] = reflected_emb

        return reflected

    def measure_ideological_distance(self,
                                      other: 'OntologicalGraph') -> Dict:
        """
        Measure the ideological distance between this ontology and another.

        Computes:
          - Mean cosine distance between aligned claims
          - Structural alignment (do the entailment patterns match?)
          - Flip rate (how many claims are on the opposite side of the
            conceptual axis?)
        """
        # Find matching claims by ID pattern
        our_ids = set(self.claims.keys())
        their_ids = set(other.claims.keys())

        # Match anti_X to X
        pairs = []
        for tid in their_ids:
            base_id = tid.replace("anti_", "")
            if base_id in our_ids:
                pairs.append((base_id, tid))

        if not pairs:
            # Try direct matching
            common = our_ids & their_ids
            pairs = [(cid, cid) for cid in common]

        if not pairs:
            return {"error": "No matching claims found between ontologies"}

        cosines = []
        l2s = []
        for our_id, their_id in pairs:
            cos = float(1.0 - cosine_dist(
                self.embeddings[our_id], other.embeddings[their_id]))
            l2 = float(np.linalg.norm(
                other.embeddings[their_id] - self.embeddings[our_id]))
            cosines.append(cos)
            l2s.append(l2)

        return {
            "n_matched_pairs": len(pairs),
            "mean_cosine": float(np.mean(cosines)),
            "mean_l2_distance": float(np.mean(l2s)),
            "std_cosine": float(np.std(cosines)),
            "min_cosine": float(np.min(cosines)),
            "max_cosine": float(np.max(cosines)),
        }

    # ─── Visualization Data ──────────────────────────────────────────────

    def to_json(self) -> Dict:
        """Export the graph as JSON for visualization."""
        nodes = []
        for cid, claim in self.claims.items():
            nodes.append({
                "id": cid,
                "text": claim.text[:100],
                "type": claim.claim_type,
                "chapter": claim.chapter,
                "section": claim.section,
            })

        edges = []
        for u, v, data in self.graph.edges(data=True):
            edges.append({
                "source": u,
                "target": v,
                "relation": data.get("relation", ""),
            })

        return {"nodes": nodes, "edges": edges}

    # ─── Persistence ─────────────────────────────────────────────────────

    def save_results(self, filepath: str, results: Dict):
        """Save analysis results to JSON."""
        def convert(obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, (np.bool_,)):
                return bool(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            raise TypeError(f"Type {type(obj)} not serializable")

        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2, default=convert)
        print(f"Saved to {filepath}")


# ═════════════════════════════════════════════════════════════════════════════
# FULL ANALYSIS PIPELINE
# ═════════════════════════════════════════════════════════════════════════════

def run_ontological_analysis(ontology_path: str = None,
                              results_dir: str = None) -> Dict:
    """
    Run the complete ontological analysis pipeline.

    1. Parse the argumentative ontology
    2. Embed all claims
    3. Build the graph
    4. Detect contradictions and tensions
    5. Score coherence per chapter and overall
    6. Generate the anti-ontology
    7. Measure ideological distance
    """
    if ontology_path is None:
        base = Path(__file__).parent.parent.parent / "Book"
        ontology_path = str(base / "Argumentative_Ontology.md")

    if results_dir is None:
        results_dir = str(Path(__file__).parent / "results")
    os.makedirs(results_dir, exist_ok=True)

    print("=" * 70)
    print("  ONTOLOGICAL CONTRADICTION ANALYSIS")
    print("=" * 70)

    # 1. Build the graph
    print("\n  Step 1: Parsing and embedding ontology...")
    graph = OntologicalGraph()
    graph.load_from_ontology(ontology_path)

    results = {
        "graph_stats": {
            "n_claims": len(graph.claims),
            "n_edges": graph.graph.number_of_edges(),
            "n_chapters": len(set(c.chapter for c in graph.claims.values())),
        }
    }

    # 2. Chapter-level coherence
    print("\n  Step 2: Computing chapter coherence scores...")
    chapter_coherence = graph.chapter_coherence()
    results["chapter_coherence"] = {}
    for chapter, scores in chapter_coherence.items():
        print(f"    {chapter[:30]:30s}  coherence={scores['coherence']:.3f}  "
              f"claims={scores['n_claims']}")
        results["chapter_coherence"][chapter] = scores

    # 3. Overall coherence
    print("\n  Step 3: Computing overall coherence...")
    overall = graph.coherence_score()
    results["overall_coherence"] = overall
    print(f"    Overall coherence: {overall['coherence']:.3f}")
    print(f"    Mean entailment cosine: {overall['mean_entailment_cosine']:.3f}")
    print(f"    Mean tension: {overall['mean_tension']:.4f}")
    print(f"    Fragmentation: {overall['fragmentation']:.3f}")

    # 4. Detect contradictions
    print("\n  Step 4: Detecting contradictions...")
    contradictions = graph.detect_contradictions(cosine_threshold=0.3, top_k=15)
    results["top_contradictions"] = contradictions
    print(f"    Found {len(contradictions)} candidate contradictions/tensions")
    for i, c in enumerate(contradictions[:5]):
        print(f"\n    #{i+1} (score={c['contradiction_score']:.3f}):")
        print(f"      A [{c['chapter_a'][:15]}]: {c['claim_a'][:80]}")
        print(f"      B [{c['chapter_b'][:15]}]: {c['claim_b'][:80]}")
        print(f"      cos={c['cosine_similarity']:.3f} l2={c['l2_distance']:.3f}")

    # 5. Detect structural tensions
    print("\n  Step 5: Detecting structural tensions...")
    tensions = graph.detect_tensions(depth=2)
    results["top_tensions"] = tensions[:10]
    print(f"    Found {len(tensions)} structural tensions")
    for i, t in enumerate(tensions[:3]):
        print(f"\n    #{i+1} (tension={t['tension_score']:.3f}):")
        print(f"      Root A: {t['root_a'][:70]}")
        print(f"      Root B: {t['root_b'][:70]}")
        print(f"      Consequence A: {t['consequence_a'][:70]}")
        print(f"      Consequence B: {t['consequence_b'][:70]}")

    # 6. Build concept axis from the book's own vocabulary and reflect
    print("\n  Step 6: Generating anti-ontology...")
    # Build a "coherence vs incoherence" axis from the book's own terms
    coherence_terms = [
        "coherent logical structure", "truth under scrutiny",
        "purpose driven organization", "genuine value creation",
        "rational progress", "voluntary exchange"
    ]
    incoherence_terms = [
        "purposeless efficiency", "institutional drift",
        "mimetic competition", "gamification as collectivism",
        "deceptive products", "information asymmetry"
    ]
    pos_emb = graph.model.encode(coherence_terms, show_progress_bar=False)
    neg_emb = graph.model.encode(incoherence_terms, show_progress_bar=False)
    axis = np.mean(pos_emb, axis=0) - np.mean(neg_emb, axis=0)
    axis = axis / (np.linalg.norm(axis) + 1e-10)

    anti = graph.reflect_ontology(axis, alpha=2.0)
    distance = graph.measure_ideological_distance(anti)
    results["anti_ontology_distance"] = distance
    print(f"    Mean cosine to anti-ontology: {distance['mean_cosine']:.3f}")
    print(f"    Mean L2 distance: {distance['mean_l2_distance']:.3f}")

    # 7. Graph export
    results["graph"] = graph.to_json()

    # Save
    out_path = os.path.join(results_dir, "ontological_analysis.json")
    graph.save_results(out_path, results)

    print(f"\n{'=' * 70}")
    print(f"  ANALYSIS COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Claims analyzed: {len(graph.claims)}")
    print(f"  Overall coherence: {overall['coherence']:.3f}")
    print(f"  Contradictions found: {len(contradictions)}")
    print(f"  Tensions found: {len(tensions)}")

    return results


if __name__ == "__main__":
    results = run_ontological_analysis()

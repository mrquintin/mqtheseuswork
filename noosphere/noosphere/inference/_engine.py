"""
Inference Engine for the Noosphere System — the Brain of the Firm

This module implements the core reasoning capability of the Noosphere. It takes a
question or scenario and reasons from the firm's stored principles to produce an
analysis that is rigorously grounded in those principles.

Key Components:
1. PrincipleRetriever: Semantic retrieval of relevant principles from the graph
2. ReasoningChain: Step-by-step reasoning path from principles to conclusion
3. InferenceEngine: Main orchestrator that asks questions and produces grounded answers
4. AdversarialGenerator: Generates counter-positions via embedding geometry reflection
5. ConsistencyChecker: Validates that answers don't contradict firm principles
"""

from __future__ import annotations

import json
import re
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import networkx as nx
from sentence_transformers import SentenceTransformer
from anthropic import Anthropic

from noosphere.models import (
    InferenceQuery,
    InferenceResult,
    Principle,
    Claim,
    Discipline,
)
from noosphere.coherence import CoherenceEngine, Proposition
from noosphere.geometry import EmbeddingAnalyzer, IdeologyReflector, ConceptAxisBuilder
from noosphere.observability import get_logger

logger = get_logger(__name__)


# ── Type Definitions ─────────────────────────────────────────────────────────

@dataclass
class ReasoningStep:
    """A single step in a reasoning chain."""
    premise_ids: List[str]          # IDs of principles/claims used as premises
    inference_rule: str             # Type of inference (deduction, induction, analogy, etc.)
    conclusion_text: str            # The conclusion drawn from premises
    confidence: float = 0.8         # How confident in this step (0-1)


# ── PrincipleRetriever ───────────────────────────────────────────────────────

class PrincipleRetriever:
    """
    Retrieves the most relevant principles from the ontology graph.

    Uses semantic similarity (cosine on embeddings) combined with graph traversal
    to find both direct matches and supporting/refining principles.
    """

    def __init__(self, model: Optional[SentenceTransformer] = None, verbose: bool = False):
        """
        Initialize the retriever.

        Args:
            model: Optional SBERT model. If None, uses default "all-mpnet-base-v2".
            verbose: If True, log retrieval details.
        """
        self.model = model or SentenceTransformer("all-mpnet-base-v2")
        self.verbose = verbose
        logger.info("PrincipleRetriever initialized")

    def retrieve(
        self,
        query_embedding: np.ndarray,
        graph: nx.DiGraph,
        principles_dict: Dict[str, Principle],
        k: int = 10,
        min_conviction: float = 0.3,
    ) -> List[Tuple[Principle, float]]:
        """
        Retrieve the k most relevant principles from the graph.

        Strategy:
        1. Find top-k principles by cosine similarity to query embedding
        2. Filter by minimum conviction score
        3. Traverse graph to depth 1 to find supporting/refining principles
        4. Sort all results by (relevance × conviction_score)

        Args:
            query_embedding: Embedding of the question/query
            graph: The ontology graph (NetworkX DiGraph)
            principles_dict: Dict mapping principle ID to Principle object
            k: Number of top principles to retrieve
            min_conviction: Minimum conviction score (0-1) to include

        Returns:
            List of (Principle, relevance_score) tuples, sorted by score (descending)

        Raises:
            ValueError: If graph has no principles or embeddings are missing
        """
        principle_ids = [
            node_id for node_id in graph.nodes()
            if graph.nodes[node_id].get("node_type") == "principle"
        ]

        if not principle_ids:
            logger.warning("No principles found in graph")
            return []

        # Collect principles with embeddings
        candidates = []
        for pid in principle_ids:
            principle = principles_dict.get(pid)
            if principle is None:
                logger.warning(f"Principle {pid} not in dict")
                continue

            if principle.embedding is None:
                logger.debug(f"Principle {pid} has no embedding, skipping")
                continue

            candidates.append((pid, principle))

        if not candidates:
            logger.warning("No principles with embeddings found")
            return []

        # Compute cosine similarity
        embeddings = np.array([p.embedding for _, p in candidates])
        similarities = self._cosine_similarity_batch(query_embedding, embeddings)

        # Create scored list
        scored = [
            (pid, sim, principle)
            for (pid, principle), sim in zip(candidates, similarities)
        ]

        # Sort by similarity
        scored.sort(key=lambda x: x[1], reverse=True)

        # Take top-k and filter by conviction
        top_k = scored[:k]
        filtered = [
            (principle, sim)
            for pid, sim, principle in top_k
            if principle.conviction_score >= min_conviction
        ]

        if self.verbose:
            logger.info(
                f"Retrieved {len(filtered)} principles (from {len(top_k)} top-k, "
                f"filtered by conviction >= {min_conviction})"
            )

        # Traverse graph for connected principles
        connected = self._traverse_for_connections(
            [p.id for p, _ in filtered],
            graph,
            principles_dict,
            max_depth=1,
        )

        # Merge filtered + connected, deduplicate, sort
        result_dict = {}
        for principle, sim in filtered:
            result_dict[principle.id] = (principle, sim)

        for principle, conn_score in connected:
            if principle.id not in result_dict:
                result_dict[principle.id] = (principle, conn_score)

        # Sort by relevance × conviction
        results = list(result_dict.values())
        results.sort(
            key=lambda x: x[1] * x[0].conviction_score,
            reverse=True
        )

        if self.verbose:
            logger.info(
                f"Final result: {len(results)} principles after graph traversal"
            )

        return results

    def _cosine_similarity_batch(
        self,
        query: np.ndarray,
        embeddings: np.ndarray,
    ) -> np.ndarray:
        """
        Compute cosine similarity between query and batch of embeddings.

        Args:
            query: Query embedding vector of shape (d,)
            embeddings: Batch of embeddings of shape (n, d)

        Returns:
            Array of similarity scores of shape (n,)
        """
        query = np.asarray(query)
        embeddings = np.asarray(embeddings)

        # Normalize
        query_norm = np.linalg.norm(query)
        embedding_norms = np.linalg.norm(embeddings, axis=1)

        if query_norm < 1e-10:
            logger.warning("Query embedding has near-zero norm")
            return np.zeros(len(embeddings))

        query_normalized = query / query_norm
        embeddings_normalized = embeddings / np.maximum(embedding_norms[:, np.newaxis], 1e-10)

        # Compute dot product (cosine on normalized vectors)
        similarities = np.dot(embeddings_normalized, query_normalized)

        return similarities

    def _traverse_for_connections(
        self,
        seed_ids: List[str],
        graph: nx.DiGraph,
        principles_dict: Dict[str, Principle],
        max_depth: int = 1,
    ) -> List[Tuple[Principle, float]]:
        """
        Traverse graph from seed principles to find connected principles.

        Returns principles connected via supporting/refining relationships,
        scored by connection strength.

        Args:
            seed_ids: Starting principle IDs
            graph: The ontology graph
            principles_dict: Dict mapping ID to Principle
            max_depth: Maximum traversal depth

        Returns:
            List of (Principle, connection_score) tuples
        """
        connected = []
        visited = set(seed_ids)

        for seed_id in seed_ids:
            # Outgoing edges (principles this one supports/refines/etc.)
            for neighbor in graph.successors(seed_id):
                if neighbor in visited:
                    continue

                principle = principles_dict.get(neighbor)
                if principle is None or graph.nodes[neighbor].get("node_type") != "principle":
                    continue

                visited.add(neighbor)

                # Get edge weight as connection score
                edge_data = graph.get_edge_data(seed_id, neighbor)
                strength = edge_data.get("strength", 0.5) if edge_data else 0.5

                connected.append((principle, strength * 0.7))  # Discount connected principles

            # Incoming edges (principles that support this one)
            for neighbor in graph.predecessors(seed_id):
                if neighbor in visited:
                    continue

                principle = principles_dict.get(neighbor)
                if principle is None or graph.nodes[neighbor].get("node_type") != "principle":
                    continue

                visited.add(neighbor)
                edge_data = graph.get_edge_data(neighbor, seed_id)
                strength = edge_data.get("strength", 0.5) if edge_data else 0.5

                connected.append((principle, strength * 0.7))

        return connected


# ── ReasoningChain ──────────────────────────────────────────────────────────

class ReasoningChain:
    """
    Represents a step-by-step reasoning path from principles to conclusion.

    Each step is a triple of (premise_ids, inference_rule, conclusion_text).
    Provides validation, serialization, and analysis methods.
    """

    def __init__(self):
        """Initialize an empty reasoning chain."""
        self.steps: List[ReasoningStep] = []
        logger.debug("Created new ReasoningChain")

    def add_step(
        self,
        premise_ids: List[str],
        rule: str,
        conclusion_text: str,
        confidence: float = 0.8,
    ) -> None:
        """
        Add a step to the reasoning chain.

        Args:
            premise_ids: IDs of principles/claims used as premises
            rule: Type of inference rule (e.g., "deduction", "analogy", "induction")
            conclusion_text: The conclusion drawn
            confidence: Confidence in this step (0-1)
        """
        step = ReasoningStep(
            premise_ids=premise_ids,
            inference_rule=rule,
            conclusion_text=conclusion_text,
            confidence=confidence,
        )
        self.steps.append(step)
        logger.debug(f"Added step {len(self.steps)}: {rule}")

    def validate(self, coherence_engine: Optional[CoherenceEngine] = None) -> bool:
        """
        Validate coherence of the reasoning chain.

        If coherence_engine is provided, check that the conclusions don't
        contradict each other or the underlying principles.

        Args:
            coherence_engine: Optional CoherenceEngine instance

        Returns:
            True if valid, False otherwise
        """
        if len(self.steps) == 0:
            logger.warning("Empty reasoning chain")
            return False

        if coherence_engine is None:
            logger.debug("No coherence engine provided, basic validation only")
            return True

        # Build propositions from conclusions
        conclusions = [step.conclusion_text for step in self.steps]
        propositions = [
            Proposition(
                id=f"conclusion_{i}",
                text=conclusion,
                conviction_score=step.confidence,
            )
            for i, (conclusion, step) in enumerate(zip(conclusions, self.steps))
        ]

        try:
            report = coherence_engine.compute()
            is_coherent = report.composite_score > 0.3  # Threshold
            logger.info(f"Chain validation: coherence={report.composite_score:.4f}, valid={is_coherent}")
            return is_coherent
        except Exception as e:
            logger.error(f"Error validating chain: {e}")
            return False

    def to_text(self) -> str:
        """
        Convert reasoning chain to human-readable text.

        Returns:
            Formatted reasoning chain as string
        """
        if not self.steps:
            return "(empty reasoning chain)"

        lines = []
        for i, step in enumerate(self.steps, 1):
            premises = ", ".join(step.premise_ids)
            lines.append(
                f"{i}. [{step.inference_rule}] From {premises}:\n"
                f"   {step.conclusion_text}\n"
                f"   (confidence: {step.confidence:.2f})"
            )

        return "\n".join(lines)

    def get_principle_ids(self) -> List[str]:
        """
        Get all unique principle IDs used in the chain.

        Returns:
            List of principle IDs
        """
        all_ids = set()
        for step in self.steps:
            all_ids.update(step.premise_ids)
        return list(all_ids)


# ── InferenceEngine ──────────────────────────────────────────────────────────

class InferenceEngine:
    """
    Main inference engine for the Noosphere system.

    Takes a question and reasons from firm principles to produce a grounded answer.
    Uses Claude API for reasoning, semantic embeddings for retrieval, and
    coherence checking for validation.
    """

    def __init__(
        self,
        graph: nx.DiGraph,
        principles_dict: Dict[str, Principle],
        claims_dict: Optional[Dict[str, Claim]] = None,
        coherence_engine: Optional[CoherenceEngine] = None,
        model_name: str = "all-mpnet-base-v2",
        verbose: bool = False,
    ):
        """
        Initialize the inference engine.

        Args:
            graph: The ontology graph (NetworkX DiGraph)
            principles_dict: Dict mapping principle ID to Principle
            claims_dict: Optional dict mapping claim ID to Claim
            coherence_engine: Optional pre-initialized CoherenceEngine
            model_name: SBERT model name for embeddings
            verbose: If True, log details
        """
        self.graph = graph
        self.principles_dict = principles_dict
        self.claims_dict = claims_dict or {}
        self.coherence_engine = coherence_engine
        self.model = SentenceTransformer(model_name)
        self.verbose = verbose
        self.client = Anthropic()
        self.retriever = PrincipleRetriever(model=self.model, verbose=verbose)
        self.embedding_analyzer = EmbeddingAnalyzer(verbose=verbose)

        logger.info(
            f"InferenceEngine initialized with {len(principles_dict)} principles, "
            f"model={model_name}"
        )

    def ask(
        self,
        question: str,
        context: str = "",
        disciplines: Optional[List[Discipline]] = None,
        require_coherence: bool = True,
    ) -> InferenceResult:
        """
        Ask a question and get a grounded inference result.

        High-level flow:
        1. Embed the question
        2. Retrieve relevant principles
        3. Retrieve supporting claims for those principles
        4. Construct a system prompt instructing Claude to reason from these
        5. Parse Claude's structured response
        6. Optionally validate coherence
        7. Return InferenceResult

        Args:
            question: The question to answer
            context: Optional additional context
            disciplines: Optional list of relevant disciplines to scope the search
            require_coherence: If True, validate answer against principles

        Returns:
            InferenceResult containing the answer and reasoning
        """
        logger.info(f"Processing question: {question[:100]}")

        # Step 1: Embed the question
        query_text = f"{question} {context}".strip()
        try:
            query_embedding = self.model.encode(query_text)
        except Exception as e:
            logger.error(f"Failed to embed query: {e}")
            return self._error_result(question, "Embedding failed")

        # Step 2: Retrieve relevant principles
        try:
            relevant_principles = self.retriever.retrieve(
                query_embedding,
                self.graph,
                self.principles_dict,
                k=10,
                min_conviction=0.3,
            )
        except Exception as e:
            logger.error(f"Failed to retrieve principles: {e}")
            return self._error_result(question, "Principle retrieval failed")

        if not relevant_principles:
            logger.warning("No relevant principles found")
            return self._error_result(question, "No relevant principles found")

        # Step 3: Get supporting claims
        supporting_claims = self._get_supporting_claims(
            [p.id for p, _ in relevant_principles]
        )

        # Step 4: Construct system prompt and ask Claude
        try:
            reasoning_chain, answer = self._reason_with_claude(
                question,
                context,
                relevant_principles,
                supporting_claims,
            )
        except Exception as e:
            logger.error(f"Failed to reason with Claude: {e}")
            return self._error_result(question, f"Reasoning failed: {str(e)}")

        # Step 5: Validate coherence if required
        if require_coherence and self.coherence_engine is not None:
            try:
                is_coherent = self._validate_answer_coherence(answer, relevant_principles)
                if not is_coherent:
                    logger.warning("Answer failed coherence check")
            except Exception as e:
                logger.warning(f"Coherence check failed: {e}")

        # Step 6: Build result
        result = InferenceResult(
            query=InferenceQuery(
                question=question,
                context=context,
                disciplines=disciplines or [],
                require_coherence=require_coherence,
            ),
            answer=answer,
            reasoning_chain=reasoning_chain.to_text().split("\n"),
            principles_used=[p.id for p, _ in relevant_principles],
            confidence=self._estimate_confidence(answer, reasoning_chain),
            coherence_with_corpus=self._estimate_coherence(answer, relevant_principles),
            caveats=self._extract_caveats(answer),
        )

        logger.info(f"Inference complete: confidence={result.confidence:.3f}")
        return result

    def _get_supporting_claims(self, principle_ids: List[str]) -> Dict[str, List[Claim]]:
        """
        Get supporting claims for a list of principle IDs.

        Args:
            principle_ids: List of principle IDs

        Returns:
            Dict mapping principle ID to list of supporting Claim objects
        """
        result = {}

        for pid in principle_ids:
            principle = self.principles_dict.get(pid)
            if principle is None:
                continue

            claims = []
            for claim_id in principle.supporting_claims:
                claim = self.claims_dict.get(claim_id)
                if claim is not None:
                    claims.append(claim)

            result[pid] = claims

        return result

    def _reason_with_claude(
        self,
        question: str,
        context: str,
        principles: List[Tuple[Principle, float]],
        supporting_claims: Dict[str, List[Claim]],
    ) -> Tuple[ReasoningChain, str]:
        """
        Use Claude to reason from principles to answer.

        Constructs a system prompt that:
        - Lists principles as AXIOMS
        - Includes supporting evidence (claims)
        - Instructs Claude to cite which principles ground each part
        - Asks Claude to identify caveats/ambiguities
        - Requests structured JSON output

        Args:
            question: The question to answer
            context: Additional context
            principles: List of (Principle, relevance_score) tuples
            supporting_claims: Dict mapping principle ID to supporting claims

        Returns:
            Tuple of (ReasoningChain, answer_text)

        Raises:
            Exception: If Claude API call fails
        """
        # Build system prompt
        axioms_text = self._format_axioms(principles)
        evidence_text = self._format_evidence(supporting_claims)

        system_prompt = f"""You are the reasoning engine for the Noosphere system — the Brain of the Firm.

Your task is to answer questions by reasoning rigorously from the firm's foundational principles (AXIOMS).

AXIOMS (Foundational Principles):
{axioms_text}

SUPPORTING EVIDENCE (Claims from transcripts):
{evidence_text}

INSTRUCTIONS:
1. Answer the question by reasoning from these axioms using first-principles analysis.
2. For each key part of your answer, explicitly cite which principle(s) ground it.
3. Be precise: if multiple principles apply, explain how they combine or constrain the answer.
4. Identify where principles are silent or ambiguous—these are important caveats.
5. Estimate your confidence (0-1) based on how directly principles address the question.

RESPONSE FORMAT:
You MUST respond with ONLY a valid JSON object (no markdown, no extra text) matching this schema:
{{
  "answer": "Your comprehensive answer to the question, citing principles where they apply",
  "reasoning_steps": [
    {{"step": 1, "inference_rule": "deduction|induction|analogy", "conclusion": "...", "principles_cited": ["id1", "id2"]}},
    ...
  ],
  "confidence": 0.0-1.0,
  "caveats": ["Where principle X is ambiguous...", "Principle Y doesn't address..."]
}}"""

        user_message = f"""Question: {question}

Context: {context if context else "(none)"}"""

        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": user_message}],
                system=system_prompt,
            )

            response_text = response.content[0].text.strip()

            # Parse JSON response
            try:
                result_json = json.loads(response_text)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Claude response as JSON: {e}")
                logger.debug(f"Response text: {response_text[:200]}")
                raise ValueError("Claude response was not valid JSON")

            # Build reasoning chain
            chain = ReasoningChain()
            for step_data in result_json.get("reasoning_steps", []):
                chain.add_step(
                    premise_ids=step_data.get("principles_cited", []),
                    rule=step_data.get("inference_rule", "unknown"),
                    conclusion_text=step_data.get("conclusion", ""),
                    confidence=result_json.get("confidence", 0.8),
                )

            answer = result_json.get("answer", "")

            return chain, answer

        except Exception as e:
            logger.error(f"Claude reasoning failed: {e}")
            raise

    def _format_axioms(self, principles: List[Tuple[Principle, float]]) -> str:
        """Format principles as axioms for the system prompt."""
        lines = []
        for principle, relevance in principles:
            conviction = principle.conviction_score
            lines.append(
                f"- [{principle.id}] (conviction: {conviction:.2f}, relevance: {relevance:.2f}) "
                f"{principle.text}"
            )
            if principle.description:
                lines.append(f"  Description: {principle.description}")

        return "\n".join(lines)

    def _format_evidence(self, supporting_claims: Dict[str, List[Claim]]) -> str:
        """Format supporting claims as evidence."""
        lines = []
        for pid, claims in supporting_claims.items():
            if claims:
                lines.append(f"For principle [{pid}]:")
                for claim in claims[:3]:  # Limit to 3 per principle
                    lines.append(f"  - {claim.text} ({claim.speaker.name})")

        return "\n".join(lines) if lines else "(no supporting claims available)"

    def _validate_answer_coherence(
        self,
        answer: str,
        principles: List[Tuple[Principle, float]],
    ) -> bool:
        """
        Check that answer is coherent with firm principles.

        Uses the ConsistencyChecker to embed the answer and check for
        contradiction with principles.

        Args:
            answer: The answer text
            principles: List of (Principle, relevance) tuples

        Returns:
            True if coherent, False if contradictory
        """
        checker = ConsistencyChecker(model=self.model)
        is_consistent, flags = checker.check_answer_consistency(
            answer,
            [p for p, _ in principles],
        )

        if not is_consistent:
            logger.warning(f"Consistency issues: {flags}")

        return is_consistent

    def _estimate_confidence(
        self,
        answer: str,
        chain: ReasoningChain,
    ) -> float:
        """
        Estimate confidence in the answer.

        Based on:
        - Number of reasoning steps
        - Average confidence of steps
        - Answer length (more detailed = more confident)

        Args:
            answer: The answer text
            chain: The reasoning chain

        Returns:
            Confidence score in [0, 1]
        """
        if not chain.steps:
            return 0.3

        avg_step_confidence = np.mean([s.confidence for s in chain.steps])
        step_count_factor = min(len(chain.steps) / 5, 1.0)  # Normalize to ~5 steps
        answer_length_factor = min(len(answer.split()) / 100, 1.0)  # Normalize to ~100 words

        confidence = (
            0.4 * avg_step_confidence +
            0.3 * step_count_factor +
            0.3 * answer_length_factor
        )

        return float(np.clip(confidence, 0.0, 1.0))

    def _estimate_coherence(
        self,
        answer: str,
        principles: List[Tuple[Principle, float]],
    ) -> float:
        """
        Estimate coherence of answer with principles.

        Based on semantic similarity between answer and principles.

        Args:
            answer: The answer text
            principles: List of (Principle, relevance) tuples

        Returns:
            Coherence score in [0, 1]
        """
        try:
            answer_emb = self.model.encode(answer)
            principle_embs = np.array([p.embedding for p, _ in principles if p.embedding is not None])

            if len(principle_embs) == 0:
                return 0.5

            similarities = self.retriever._cosine_similarity_batch(answer_emb, principle_embs)
            coherence = float(np.mean(similarities))
            return np.clip(coherence, 0.0, 1.0)

        except Exception as e:
            logger.error(f"Error estimating coherence: {e}")
            return 0.5

    def _extract_caveats(self, answer: str) -> List[str]:
        """
        Extract caveats/ambiguities from answer text.

        Looks for phrases like "where silent", "ambiguous", "unclear", etc.

        Args:
            answer: The answer text

        Returns:
            List of caveat strings
        """
        caveats = []

        # Look for explicit caveat phrases
        caveat_patterns = [
            r"(?:where|when) .+?(?:is silent|is ambiguous|unclear)",
            r"(?:principle|axiom) [^.]*?doesn't address",
            r"caveat[s]?[^.]*",
        ]

        for pattern in caveat_patterns:
            matches = re.findall(pattern, answer, re.IGNORECASE)
            caveats.extend(matches)

        return caveats[:5]  # Limit to 5 caveats

    def _error_result(self, question: str, error_msg: str) -> InferenceResult:
        """Create an error InferenceResult."""
        return InferenceResult(
            query=InferenceQuery(question=question),
            answer=f"Error: {error_msg}",
            reasoning_chain=[],
            principles_used=[],
            confidence=0.0,
            coherence_with_corpus=0.0,
            caveats=[error_msg],
        )


# ── AdversarialGenerator ─────────────────────────────────────────────────────

class AdversarialGenerator:
    """
    Generates counter-positions via embedding geometry reflection.

    Implements the Reverse Marxism insight: the strongest case for X is the
    reflection of the strongest case against X. This works by reflecting
    embeddings across ideological concept axes and finding nearest real-world
    counter-arguments.
    """

    def __init__(
        self,
        model: Optional[SentenceTransformer] = None,
        verbose: bool = False,
    ):
        """
        Initialize the generator.

        Args:
            model: Optional SBERT model
            verbose: If True, log details
        """
        self.model = model or SentenceTransformer("all-mpnet-base-v2")
        self.verbose = verbose
        self.reflector = IdeologyReflector(verbose=verbose)
        self.axis_builder = ConceptAxisBuilder(model=self.model, verbose=verbose)
        self.client = Anthropic()

        logger.info("AdversarialGenerator initialized")

    def generate_counter_position(
        self,
        principle: Principle,
        graph: nx.DiGraph,
        principles_dict: Dict[str, Principle],
        axis_name: str = "class",
    ) -> str:
        """
        Generate the strongest counter-argument to a principle.

        Flow:
        1. Get the principle's embedding
        2. Build the concept axis (e.g., class axis)
        3. Reflect the embedding across the axis
        4. Find nearest principles/claims to the reflected embedding
        5. Use Claude to synthesize the strongest counter-position

        Args:
            principle: The Principle to counter
            graph: The ontology graph
            principles_dict: Dict of principles
            axis_name: Which axis to use for reflection ("class", "ideology", etc.)

        Returns:
            Synthesized counter-position text

        Raises:
            ValueError: If principle has no embedding
        """
        if principle.embedding is None:
            raise ValueError(f"Principle {principle.id} has no embedding")

        logger.info(f"Generating counter-position for principle {principle.id}")

        # Build axis
        try:
            if axis_name == "class":
                axis = self.axis_builder.build_class_axis(model=self.model)
            else:
                logger.warning(f"Unknown axis {axis_name}, using class axis")
                axis = self.axis_builder.build_class_axis(model=self.model)
        except Exception as e:
            logger.error(f"Failed to build axis: {e}")
            raise

        # Reflect embedding
        principle_emb = np.array(principle.embedding)
        reflected_emb = self.reflector.reflect(principle_emb, axis)

        # Find nearest principles to reflected embedding
        nearest = self._find_nearest_principles(
            reflected_emb,
            graph,
            principles_dict,
            k=5,
        )

        if not nearest:
            logger.warning("No nearby principles found for reflected embedding")
            return "(no counter-position found)"

        # Synthesize with Claude
        try:
            counter = self._synthesize_counter(principle, nearest)
            return counter
        except Exception as e:
            logger.error(f"Failed to synthesize counter-position: {e}")
            raise

    def _find_nearest_principles(
        self,
        embedding: np.ndarray,
        graph: nx.DiGraph,
        principles_dict: Dict[str, Principle],
        k: int = 5,
    ) -> List[Principle]:
        """
        Find k principles nearest to an embedding in the graph.

        Args:
            embedding: Query embedding
            graph: The ontology graph
            principles_dict: Dict of principles
            k: Number to retrieve

        Returns:
            List of Principle objects
        """
        nearest = []
        distances = {}

        for pid in principles_dict:
            principle = principles_dict[pid]
            if principle.embedding is None:
                continue

            dist = float(np.linalg.norm(np.array(principle.embedding) - embedding))
            distances[pid] = dist

        # Sort by distance
        sorted_pids = sorted(distances.items(), key=lambda x: x[1])

        for pid, dist in sorted_pids[:k]:
            nearest.append(principles_dict[pid])

        return nearest

    def _synthesize_counter(
        self,
        original: Principle,
        counter_principles: List[Principle],
    ) -> str:
        """
        Use Claude to synthesize a counter-position.

        Args:
            original: The original principle
            counter_principles: List of principles that form the counter-argument

        Returns:
            Synthesized counter-position text
        """
        counter_text = "\n".join(
            [f"- {p.text}" for p in counter_principles[:3]]
        )

        prompt = f"""You are synthesizing the strongest intellectual counter-argument to the following principle:

ORIGINAL PRINCIPLE:
{original.text}

RELATED COUNTER-ARGUMENTS (found via geometric reflection):
{counter_text}

Based on these counter-arguments, write a single coherent statement that articulates the strongest
intellectual case AGAINST the original principle. Be precise and avoid strawmanning.

Respond with only the counter-position statement, nothing else."""

        response = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text.strip()


# ── ConsistencyChecker ──────────────────────────────────────────────────────

class ConsistencyChecker:
    """
    Checks whether an answer is consistent with firm principles.

    Uses embedding analysis (Hoyer sparsity of difference vectors) to detect
    contradictions between the answer and principles.
    """

    def __init__(self, model: Optional[SentenceTransformer] = None, verbose: bool = False):
        """
        Initialize the checker.

        Args:
            model: Optional SBERT model
            verbose: If True, log details
        """
        self.model = model or SentenceTransformer("all-mpnet-base-v2")
        self.verbose = verbose
        self.analyzer = EmbeddingAnalyzer(verbose=verbose)

        logger.info("ConsistencyChecker initialized")

    def check_answer_consistency(
        self,
        answer_text: str,
        principles: List[Principle],
        sparsity_threshold: float = 0.35,
    ) -> Tuple[bool, List[str]]:
        """
        Check whether an answer is consistent with a set of principles.

        Uses Hoyer sparsity of difference vectors to detect contradictions.

        Args:
            answer_text: The answer to check
            principles: List of Principle objects
            sparsity_threshold: Sparsity threshold for contradiction detection

        Returns:
            Tuple of (is_consistent: bool, flagged_contradictions: list of strings)
        """
        logger.info(f"Checking consistency of {len(answer_text)} chars against {len(principles)} principles")

        # Embed the answer
        try:
            answer_emb = self.model.encode(answer_text)
        except Exception as e:
            logger.error(f"Failed to embed answer: {e}")
            return True, []  # Assume consistent on embedding error

        # Check against each principle
        contradictions = []

        for principle in principles:
            if principle.embedding is None:
                continue

            principle_emb = np.array(principle.embedding)

            # Compute sparsity of difference
            is_contradiction, sparsity = self.analyzer.detect_contradiction(
                answer_emb,
                principle_emb,
                threshold=sparsity_threshold,
            )

            if is_contradiction:
                flag = (
                    f"Answer contradicts principle '{principle.id}': "
                    f"'{principle.text}' (sparsity: {sparsity:.3f})"
                )
                contradictions.append(flag)

                if self.verbose:
                    logger.warning(flag)

        is_consistent = len(contradictions) == 0

        if not is_consistent:
            logger.warning(f"Found {len(contradictions)} contradictions")

        return is_consistent, contradictions

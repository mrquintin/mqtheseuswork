"""
Temporal evolution tracking for the Noosphere system — the Brain of the Firm.

This module tracks how the firm's principles evolve across weekly podcast episodes.
It detects emergence, strengthening, drift, refinement, and abandonment of principles.

Key classes:
- TemporalTracker: Records and retrieves principle states across time
- EvolutionAnalyzer: Generates reports on ideological trajectory and convergence
- ConvictionEstimator: Computes conviction scores from multiple signals
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from collections import defaultdict

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics.pairwise import cosine_similarity

from noosphere.models import (
    TemporalSnapshot,
    Principle,
    Episode,
    Claim,
    DriftEvent,
    RelationType,
)
from noosphere.ontology import OntologyGraph


from noosphere.observability import get_logger

logger = get_logger(__name__)


# ── TemporalTracker ──────────────────────────────────────────────────────────


class TemporalTracker:
    """
    Records and retrieves the temporal evolution of principles.

    Maintains a history of principle states (conviction, embedding, mentions)
    across episodes, enabling the detection of emergence, drift, abandonment,
    convergence, and splits.
    """

    def __init__(self, graph: OntologyGraph):
        """
        Initialize the temporal tracker.

        Args:
            graph: The OntologyGraph to track over time.
        """
        self.graph = graph
        # principle_id -> list[TemporalSnapshot]
        self.snapshots: Dict[str, List[TemporalSnapshot]] = defaultdict(list)
        self.episode_count = 0
        logger.info("Initialized TemporalTracker")

    def record_snapshot(
        self,
        principle_id: str,
        episode_id: str,
        date_: date,
        embedding: Optional[list[float]] = None,
    ) -> TemporalSnapshot:
        """
        Record the state of a principle at a point in time.

        Computes conviction_score from current mention_count and evidence.
        Computes drift_from_origin (cosine distance between current embedding
        and the embedding when the principle first appeared).

        Args:
            principle_id: The principle ID.
            episode_id: The episode ID in which this state was recorded.
            date_: The date of the episode.
            embedding: Optional embedding vector for the principle at this time.
                      If None, uses the principle's current embedding.

        Returns:
            The created TemporalSnapshot.

        Raises:
            ValueError: If principle not found in graph.
        """
        principle = self.graph.get_principle(principle_id)
        if principle is None:
            raise ValueError(f"Principle {principle_id} not found in graph")

        # Use provided embedding or fall back to principle's current embedding
        snapshot_embedding = embedding or principle.embedding

        # Compute drift from origin (if we have both embeddings)
        drift_from_origin = None
        if snapshot_embedding is not None and principle.embedding is not None:
            # Find the original embedding from first snapshot, if available
            if self.snapshots[principle_id]:
                original_embedding = self.snapshots[principle_id][0].embedding
                if original_embedding is not None:
                    drift_from_origin = self._cosine_distance(
                        snapshot_embedding, original_embedding
                    )
            else:
                # First snapshot: drift is 0
                drift_from_origin = 0.0

        snapshot = TemporalSnapshot(
            principle_id=principle_id,
            episode_id=episode_id,
            date=date_,
            conviction_score=principle.conviction_score,
            mention_count_cumulative=principle.mention_count,
            embedding=snapshot_embedding,
            drift_from_origin=drift_from_origin,
        )

        self.snapshots[principle_id].append(snapshot)
        logger.debug(
            f"Recorded snapshot for principle {principle_id} "
            f"on {date_} (conviction={snapshot.conviction_score:.2f})"
        )
        return snapshot

    def get_history(self, principle_id: str) -> List[TemporalSnapshot]:
        """
        Get all snapshots for a principle, sorted chronologically.

        Args:
            principle_id: The principle ID.

        Returns:
            List of TemporalSnapshot objects, sorted by date ascending.
        """
        snapshots = self.snapshots.get(principle_id, [])
        return sorted(snapshots, key=lambda s: s.date)

    def compute_conviction_trajectory(
        self, principle_id: str
    ) -> List[Tuple[date, float]]:
        """
        Compute the conviction score over time.

        A rising trajectory means the principle is being reinforced.
        A falling trajectory means it's being questioned or abandoned.

        Args:
            principle_id: The principle ID.

        Returns:
            List of (date, conviction_score) tuples, sorted chronologically.
        """
        history = self.get_history(principle_id)
        trajectory = [(snap.date, snap.conviction_score) for snap in history]
        return trajectory

    def compute_embedding_drift(
        self, principle_id: str
    ) -> List[Tuple[date, float]]:
        """
        Compute the cosine distance from the principle's original embedding over time.

        Drift > 0.1 means the principle's MEANING is shifting even if
        the label hasn't changed.

        Args:
            principle_id: The principle ID.

        Returns:
            List of (date, drift_distance) tuples, sorted chronologically.
            Drift is the cosine distance from the first snapshot's embedding.
        """
        history = self.get_history(principle_id)
        if not history:
            return []

        original_embedding = history[0].embedding
        if original_embedding is None:
            logger.warning(
                f"No embedding for principle {principle_id} at origin"
            )
            return []

        drift_trajectory = []
        for snap in history:
            if snap.embedding is not None:
                distance = self._cosine_distance(snap.embedding, original_embedding)
                drift_trajectory.append((snap.date, distance))

        return drift_trajectory

    def detect_emergence(self, episode_id: str) -> List[Principle]:
        """
        Identify principles that first appeared in this episode.

        Args:
            episode_id: The episode ID.

        Returns:
            List of Principle objects that have their first_appeared date
            matching this episode.
        """
        emerged = []
        for principle in self.graph.principles.values():
            # Get snapshots for this principle in this episode
            episode_snapshots = [
                s for s in self.snapshots.get(principle.id, [])
                if s.episode_id == episode_id
            ]
            # If this is the first mention (mention count jumped from 0),
            # it emerged in this episode
            if episode_snapshots and principle.mention_count >= 1:
                # Check if this is truly first appearance
                history = self.get_history(principle.id)
                if len(history) == 1:  # Only one snapshot = first appearance
                    emerged.append(principle)

        return emerged

    def detect_abandonment(
        self, lookback_episodes: int = 10, threshold: int = 0
    ) -> List[Principle]:
        """
        Identify principles that haven't been mentioned in the last N episodes.

        Args:
            lookback_episodes: Number of recent episodes to consider.
            threshold: Conviction threshold (only flag principles below this).

        Returns:
            List of Principle objects that appear abandoned.
        """
        abandoned = []

        for principle in self.graph.principles.values():
            history = self.get_history(principle.id)
            if not history:
                continue

            # Get the last N snapshots
            recent = history[-lookback_episodes:]

            # Check if conviction is declining
            if len(recent) > 1:
                conviction_trend = [s.conviction_score for s in recent]
                # If the last conviction is at or below threshold, flag it
                if conviction_trend[-1] <= threshold:
                    abandoned.append(principle)

        return abandoned

    def detect_convergence(
        self, principle_id_a: str, principle_id_b: str
    ) -> Optional[float]:
        """
        Check if two principles are becoming more similar over time.

        Returns the rate of convergence (negative = diverging).

        Algorithm:
        1. Get embedding history for both principles
        2. Compute similarity between them at each timestep
        3. Fit a line to the similarity trend
        4. Return the slope (positive = converging, negative = diverging)

        Args:
            principle_id_a: First principle ID.
            principle_id_b: Second principle ID.

        Returns:
            The rate of convergence (slope). Positive means converging,
            negative means diverging. None if insufficient data.
        """
        history_a = self.get_history(principle_id_a)
        history_b = self.get_history(principle_id_b)

        if len(history_a) < 2 or len(history_b) < 2:
            return None

        # Find overlapping time period
        start_date = max(history_a[0].date, history_b[0].date)
        end_date = min(history_a[-1].date, history_b[-1].date)

        if start_date >= end_date:
            return None

        # Compute similarity at each overlapping snapshot
        similarities = []
        for snap_a, snap_b in zip(history_a, history_b):
            if snap_a.date < start_date or snap_a.date > end_date:
                continue
            if snap_b.date < start_date or snap_b.date > end_date:
                continue

            if snap_a.embedding is not None and snap_b.embedding is not None:
                sim = 1.0 - self._cosine_distance(snap_a.embedding, snap_b.embedding)
                similarities.append((snap_a.date, sim))

        if len(similarities) < 2:
            return None

        # Fit a line: compute trend
        dates_numeric = np.array(
            [(s[0] - similarities[0][0]).days for s, _ in enumerate(similarities)]
        )
        sims = np.array([s[1] for s in similarities])

        if len(dates_numeric) == 1:
            return None

        # Linear regression: y = mx + b
        # We want the slope m
        coefficients = np.polyfit(dates_numeric, sims, 1)
        slope = coefficients[0]

        logger.debug(
            f"Convergence rate between {principle_id_a} and {principle_id_b}: {slope:.4f}"
        )
        return float(slope)

    def detect_splits(
        self, principle_id: str, threshold: float = 0.15
    ) -> List[Principle]:
        """
        Detect if a principle has "split" into two or more sub-principles.

        Algorithm:
        1. Get all supporting claims for the principle
        2. Cluster them into sub-groups
        3. If clusters are distinct and stable over recent episodes,
           treat them as splits
        4. Return list of detected sub-principles

        Args:
            principle_id: The principle ID to analyze.
            threshold: Distance threshold for detecting distinct clusters.

        Returns:
            List of detected sub-principles (principles with embedding distance
            > threshold from the parent).
        """
        principle = self.graph.get_principle(principle_id)
        if principle is None or principle.embedding is None:
            return []

        # Get all principles that reference this one
        potential_splits = []
        for other_principle in self.graph.principles.values():
            if other_principle.id == principle_id:
                continue
            if other_principle.embedding is None:
                continue

            # Check if this principle's embedding has diverged significantly
            distance = self._cosine_distance(
                principle.embedding, other_principle.embedding
            )

            # If distance > threshold, it's a potential split
            if distance > threshold:
                # Check if this principle mentions the parent
                related = self.graph.get_related(principle_id, depth=2)
                if other_principle.id in [r.id for r in related]:
                    potential_splits.append(other_principle)

        return potential_splits

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _cosine_distance(
        embedding_a: list[float], embedding_b: list[float]
    ) -> float:
        """
        Compute cosine distance between two embeddings.

        Distance = 1 - cosine_similarity

        Args:
            embedding_a: First embedding vector.
            embedding_b: Second embedding vector.

        Returns:
            Cosine distance (0 = identical, 1 = orthogonal, 2 = opposite).
        """
        a = np.array(embedding_a).reshape(1, -1)
        b = np.array(embedding_b).reshape(1, -1)
        similarity = cosine_similarity(a, b)[0, 0]
        return float(1.0 - similarity)


# ── EvolutionAnalyzer ────────────────────────────────────────────────────────


class EvolutionAnalyzer:
    """
    Analyzes the evolution of principles over time using temporal snapshots.

    Generates reports on ideological trajectory, principle lifecycle,
    coherence changes, and stability metrics.
    """

    def __init__(self, tracker: TemporalTracker):
        """
        Initialize the evolution analyzer.

        Args:
            tracker: The TemporalTracker to analyze.
        """
        self.tracker = tracker
        self.estimator = ConvictionEstimator()
        logger.info("Initialized EvolutionAnalyzer")

    def generate_episode_report(self, episode_id: str) -> Dict[str, Any]:
        """
        Generate a report for a given episode.

        Reports:
        - New principles emerged
        - Existing principles reinforced
        - Principles that show drift
        - Contradictions introduced
        - Overall coherence change

        Args:
            episode_id: The episode ID.

        Returns:
            Dictionary containing:
            {
                "episode_id": str,
                "emerged_principles": [Principle, ...],
                "reinforced_principles": [Principle, ...],
                "drifting_principles": [{"principle": Principle, "drift": float}, ...],
                "new_contradictions": [{"a": Principle, "b": Principle, "strength": float}, ...],
                "coherence_delta": float,  # Change from previous episode
            }
        """
        graph = self.tracker.graph

        # Find principles in this episode
        principles_in_episode = []
        for principle in graph.principles.values():
            snapshots = [
                s for s in self.tracker.snapshots.get(principle.id, [])
                if s.episode_id == episode_id
            ]
            if snapshots:
                principles_in_episode.append(principle)

        # Detect emergence
        emerged = self.tracker.detect_emergence(episode_id)

        # Detect reinforcement (mentioned again, conviction increased)
        reinforced = []
        for principle in principles_in_episode:
            history = self.tracker.get_history(principle.id)
            if len(history) > 1:
                prev_conviction = history[-2].conviction_score
                curr_conviction = history[-1].conviction_score
                if curr_conviction > prev_conviction:
                    reinforced.append(principle)

        # Detect drift
        drifting = []
        for principle in principles_in_episode:
            drift_history = self.tracker.compute_embedding_drift(principle.id)
            if drift_history:
                latest_drift = drift_history[-1][1]
                if latest_drift > 0.1:  # Significant drift
                    drifting.append({
                        "principle": principle,
                        "drift": latest_drift,
                    })

        # Detect new contradictions (principles that now contradict)
        contradictions = graph.get_contradictions()
        new_contradictions = [
            {
                "a": c[0],
                "b": c[1],
                "strength": c[2],
            }
            for c in contradictions
            if c[0] in principles_in_episode or c[1] in principles_in_episode
        ]

        # Estimate coherence change
        coherence_delta = 0.0  # Placeholder; would compute from coherence scores
        if principles_in_episode and len(principles_in_episode) > 1:
            coherence_scores = [p.coherence_score for p in principles_in_episode
                              if p.coherence_score is not None]
            if coherence_scores:
                coherence_delta = sum(coherence_scores) / len(coherence_scores)

        report = {
            "episode_id": episode_id,
            "emerged_principles": emerged,
            "reinforced_principles": reinforced,
            "drifting_principles": drifting,
            "new_contradictions": new_contradictions,
            "coherence_delta": coherence_delta,
        }

        logger.info(
            f"Generated episode report for {episode_id}: "
            f"+{len(emerged)} emerged, +{len(reinforced)} reinforced"
        )
        return report

    def generate_evolution_report(
        self, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive report for a date range.

        Reports:
        - Principles that strengthened
        - Principles that weakened
        - Principles that drifted in meaning
        - New contradictions that emerged
        - Principles that converged (two becoming one)
        - Principles that split (one becoming two)
        - Overall ideological trajectory (summary)

        Args:
            start_date: Start date of the period.
            end_date: End date of the period.

        Returns:
            Dictionary containing evolution metrics.
        """
        graph = self.tracker.graph

        # Filter snapshots by date range
        strengthened = []
        weakened = []
        drifted = []

        for principle in graph.principles.values():
            history = self.tracker.get_history(principle.id)
            period_history = [
                s for s in history
                if start_date <= s.date <= end_date
            ]

            if len(period_history) < 2:
                continue

            # Check conviction trend
            first_conviction = period_history[0].conviction_score
            last_conviction = period_history[-1].conviction_score
            delta = last_conviction - first_conviction

            if delta > 0.1:
                strengthened.append({
                    "principle": principle,
                    "delta": delta,
                })
            elif delta < -0.1:
                weakened.append({
                    "principle": principle,
                    "delta": delta,
                })

            # Check embedding drift
            drift_history = self.tracker.compute_embedding_drift(principle.id)
            period_drift = [
                (d, s) for d, s in drift_history
                if start_date <= d <= end_date
            ]
            if period_drift and period_drift[-1][1] > 0.1:
                drifted.append({
                    "principle": principle,
                    "final_drift": period_drift[-1][1],
                })

        # Detect convergences
        convergences = []
        principle_ids = list(graph.principles.keys())
        for i, pid_a in enumerate(principle_ids):
            for pid_b in principle_ids[i + 1:]:
                rate = self.tracker.detect_convergence(pid_a, pid_b)
                if rate and rate > 0.01:  # Positive rate = converging
                    p_a = graph.get_principle(pid_a)
                    p_b = graph.get_principle(pid_b)
                    if p_a and p_b:
                        convergences.append({
                            "principle_a": p_a,
                            "principle_b": p_b,
                            "convergence_rate": rate,
                        })

        # Detect splits
        splits = []
        for principle in graph.principles.values():
            detected_splits = self.tracker.detect_splits(principle.id)
            if detected_splits:
                splits.append({
                    "parent": principle,
                    "sub_principles": detected_splits,
                })

        report = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "strengthened": strengthened,
            "weakened": weakened,
            "drifted": drifted,
            "convergences": convergences,
            "splits": splits,
            "ideological_velocity": self.ideological_velocity(),
        }

        logger.info(
            f"Generated evolution report ({start_date} to {end_date}): "
            f"+{len(strengthened)} strengthened, +{len(weakened)} weakened"
        )
        return report

    def principle_lifecycle(self, principle_id: str) -> Dict[str, Any]:
        """
        Complete lifecycle analysis of a principle.

        Includes:
        - When it emerged
        - How it evolved (conviction, drift, relationships)
        - Current state
        - Prediction for future trajectory (linear extrapolation)

        Args:
            principle_id: The principle ID.

        Returns:
            Dictionary containing lifecycle information.
        """
        principle = self.tracker.graph.get_principle(principle_id)
        if principle is None:
            raise ValueError(f"Principle {principle_id} not found")

        history = self.tracker.get_history(principle_id)
        if not history:
            return {
                "principle_id": principle_id,
                "principle_text": principle.text,
                "error": "No temporal data available",
            }

        # Emergence date
        emergence_date = history[0].date

        # Conviction trajectory
        conviction_trajectory = self.tracker.compute_conviction_trajectory(
            principle_id
        )

        # Embedding drift
        drift_trajectory = self.tracker.compute_embedding_drift(principle_id)

        # Current state
        current_snapshot = history[-1]

        # Predict future trajectory (linear extrapolation)
        future_conviction = None
        if len(conviction_trajectory) > 1:
            dates_numeric = np.array(
                [(d - conviction_trajectory[0][0]).days
                 for d, _ in conviction_trajectory]
            )
            convictions = np.array([c for _, c in conviction_trajectory])

            if len(dates_numeric) > 1:
                coefficients = np.polyfit(dates_numeric, convictions, 1)
                slope = coefficients[0]
                # Predict 30 days ahead
                future_conviction = convictions[-1] + slope * 30
                future_conviction = max(0.0, min(1.0, future_conviction))

        lifecycle = {
            "principle_id": principle_id,
            "principle_text": principle.text,
            "emergence_date": emergence_date.isoformat(),
            "current_conviction": current_snapshot.conviction_score,
            "total_mentions": current_snapshot.mention_count_cumulative,
            "conviction_trajectory": [
                (d.isoformat(), c) for d, c in conviction_trajectory
            ],
            "drift_trajectory": [
                (d.isoformat(), drift) for d, drift in drift_trajectory
            ],
            "current_drift": drift_trajectory[-1][1] if drift_trajectory else 0.0,
            "predicted_conviction_30_days": future_conviction,
        }

        logger.debug(f"Generated lifecycle report for {principle_id}")
        return lifecycle

    def ideological_velocity(self, window_episodes: int = 5) -> float:
        """
        Measure how fast the firm's ideology is changing.

        Computed as the average embedding drift across all active principles
        over the last N episodes. High velocity = intellectual flux.

        Args:
            window_episodes: Number of recent episodes to consider.

        Returns:
            Average drift across all principles (0-1 scale).
        """
        graph = self.tracker.graph

        drifts = []
        for principle in graph.principles.values():
            drift_history = self.tracker.compute_embedding_drift(principle.id)
            if drift_history:
                # Get the most recent N entries
                recent_drift = drift_history[-window_episodes:]
                if recent_drift:
                    avg_drift = np.mean([d for _, d in recent_drift])
                    drifts.append(avg_drift)

        if drifts:
            velocity = float(np.mean(drifts))
        else:
            velocity = 0.0

        logger.debug(f"Ideological velocity (window={window_episodes}): {velocity:.4f}")
        return velocity

    def stability_report(self) -> Dict[str, Any]:
        """
        Identify the most stable and volatile principles.

        Returns:
            Dictionary with:
            {
                "most_stable": [Principle, ...],
                "most_volatile": [Principle, ...],
                "stability_score": float (0-1),
            }
        """
        graph = self.tracker.graph

        stability_scores = {}
        for principle in graph.principles.values():
            drift_history = self.tracker.compute_embedding_drift(principle.id)
            conviction_history = self.tracker.compute_conviction_trajectory(
                principle.id
            )

            if drift_history and conviction_history:
                # Stability = inverse of avg drift + inverse of conviction variance
                avg_drift = np.mean([d for _, d in drift_history])
                convictions = np.array([c for _, c in conviction_history])
                conviction_variance = float(np.var(convictions))

                # Combine: stable principles have low drift and low variance
                stability = 1.0 / (1.0 + avg_drift + conviction_variance)
                stability_scores[principle.id] = {
                    "principle": principle,
                    "stability": stability,
                    "avg_drift": avg_drift,
                    "conviction_variance": conviction_variance,
                }

        if not stability_scores:
            return {
                "most_stable": [],
                "most_volatile": [],
                "stability_score": 0.0,
            }

        # Sort by stability
        sorted_stability = sorted(
            stability_scores.items(),
            key=lambda x: x[1]["stability"],
            reverse=True,
        )

        most_stable = [p[1]["principle"] for p in sorted_stability[:5]]
        most_volatile = [p[1]["principle"] for p in sorted_stability[-5:]]

        overall_stability = float(np.mean(
            [s[1]["stability"] for s in sorted_stability]
        ))

        report = {
            "most_stable": most_stable,
            "most_volatile": most_volatile,
            "stability_score": overall_stability,
            "detailed_scores": {
                pid: {
                    "principle_text": score["principle"].text,
                    "stability": score["stability"],
                    "avg_drift": score["avg_drift"],
                    "conviction_variance": score["conviction_variance"],
                }
                for pid, score in sorted_stability
            },
        }

        logger.info(
            f"Generated stability report: "
            f"overall stability={overall_stability:.4f}"
        )
        return report


# ── ConvictionEstimator ──────────────────────────────────────────────────────


class ConvictionEstimator:
    """
    Estimates conviction scores from multiple signals.

    Formula combines mention frequency, recency, cross-speaker agreement,
    and graph centrality into a single 0-1 conviction score.
    """

    def estimate(
        self, principle: Principle, episode_count: int
    ) -> float:
        """
        Estimate conviction score from multiple signals.

        Formula:
        score = 0.3 * norm(mention_freq) + 0.2 * recency
              + 0.2 * norm(cross_speaker) + 0.3 * norm(centrality)

        Where norm() maps to [0,1] using sigmoid.

        Args:
            principle: The Principle to estimate.
            episode_count: Total number of episodes so far.

        Returns:
            Conviction score in [0, 1].
        """
        # 1. Mention frequency
        mention_freq = principle.mention_count / max(episode_count, 1)
        mention_norm = self._sigmoid(mention_freq)

        # 2. Recency weight (exponential decay from last_reinforced)
        recency = self._compute_recency_weight(principle)

        # 3. Cross-speaker (approximated: supporting claims / mention count)
        cross_speaker = len(principle.supporting_claims) / max(
            principle.mention_count, 1
        )
        cross_speaker_norm = self._sigmoid(cross_speaker)

        # 4. Centrality in graph
        centrality = self._compute_centrality_weight(principle)

        # Combine with weights
        conviction = (
            0.3 * mention_norm
            + 0.2 * recency
            + 0.2 * cross_speaker_norm
            + 0.3 * centrality
        )

        conviction = max(0.0, min(1.0, conviction))
        logger.debug(
            f"Estimated conviction for {principle.id}: {conviction:.3f} "
            f"(mention={mention_norm:.2f}, recency={recency:.2f}, "
            f"cross_speaker={cross_speaker_norm:.2f}, centrality={centrality:.2f})"
        )
        return conviction

    @staticmethod
    def _sigmoid(x: float) -> float:
        """
        Sigmoid function to map values to [0, 1].

        Args:
            x: Input value.

        Returns:
            Sigmoid(x) in [0, 1].
        """
        return float(1.0 / (1.0 + math.exp(-x)))

    @staticmethod
    def _compute_recency_weight(principle: Principle) -> float:
        """
        Compute recency weight (exponential decay from last_reinforced).

        Args:
            principle: The Principle.

        Returns:
            Recency weight in [0, 1].
        """
        if principle.last_reinforced is None:
            return 0.5  # Neutral if no reinforcement data

        days_since = (date.today() - principle.last_reinforced).days
        # Exponential decay with half-life of 30 days
        weight = math.exp(-days_since / 30.0)
        return float(max(0.0, min(1.0, weight)))

    def _compute_centrality_weight(self, principle: Principle) -> float:
        """
        Compute centrality weight based on relationships in graph.

        Args:
            principle: The Principle.

        Returns:
            Centrality weight in [0, 1].
        """
        # Count supporting and supported principles
        supporting = len(principle.supporting_claims)  # Approximation
        # Would normally get from graph
        centrality_score = self._sigmoid(supporting / 10.0)
        return float(centrality_score)


# ── Serialization Helpers ────────────────────────────────────────────────────


def save_temporal_snapshots(
    tracker: TemporalTracker, path: str
) -> None:
    """
    Serialize temporal snapshots to JSON.

    Args:
        tracker: The TemporalTracker.
        path: File path to save to.
    """
    data = {
        "snapshots": {
            principle_id: [s.model_dump() for s in snapshots]
            for principle_id, snapshots in tracker.snapshots.items()
        },
        "metadata": {
            "saved_at": datetime.now().isoformat(),
            "num_principles": len(tracker.snapshots),
        },
    }

    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    with open(path_obj, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info(f"Saved temporal snapshots to {path}")


def load_temporal_snapshots(
    tracker: TemporalTracker, path: str
) -> None:
    """
    Deserialize temporal snapshots from JSON.

    Args:
        tracker: The TemporalTracker.
        path: File path to load from.

    Raises:
        FileNotFoundError: If path doesn't exist.
    """
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Snapshots file not found: {path}")

    with open(path_obj, "r") as f:
        data = json.load(f)

    tracker.snapshots.clear()
    for principle_id, snapshot_list in data.get("snapshots", {}).items():
        for snap_data in snapshot_list:
            snapshot = TemporalSnapshot(**snap_data)
            tracker.snapshots[principle_id].append(snapshot)

    logger.info(
        f"Loaded temporal snapshots from {path}: "
        f"{len(tracker.snapshots)} principles"
    )


# ── Stance embedding series (author × topic) & drift surfacing ───────────────


@dataclass
class StanceSeriesPoint:
    """One time window: centroid of stance embeddings for (author, topic)."""

    window_start: date
    window_end: date
    centroid: list[float]
    claim_ids: list[str] = field(default_factory=list)


def author_key_from_claim(claim: Claim) -> str:
    return (claim.speaker.name or "unknown").strip().lower()


def _unit(v: NDArray[np.float64]) -> NDArray[np.float64]:
    n = float(np.linalg.norm(v))
    if n < 1e-12:
        return v * 0.0
    return v / n


def _centroid(vectors: list[NDArray[np.float64]]) -> NDArray[np.float64]:
    if not vectors:
        return np.zeros(1, dtype=float)
    m = np.mean(np.stack(vectors, axis=0), axis=0)
    return _unit(m)


def _cosine_distance(a: list[float], b: list[float]) -> float:
    va = _unit(np.asarray(a, dtype=float))
    vb = _unit(np.asarray(b, dtype=float))
    if va.size != vb.size:
        return 1.0
    sim = float(np.clip(np.dot(va, vb), -1.0, 1.0))
    return float(1.0 - sim)


def build_stance_embedding_series(
    claims: Sequence[Claim],
    *,
    author_key: str,
    topic_id: str,
    topic_for_claim: Callable[[Claim], Optional[str]],
    window_days: int = 30,
) -> list[StanceSeriesPoint]:
    """
    Time-ordered series of stance centroids for claims matching ``author_key`` and ``topic_id``.

    Claims are bucketed into ``window_days`` rolling windows by ``episode_date``.
    """
    rows: list[Claim] = []
    for c in claims:
        if author_key_from_claim(c) != author_key:
            continue
        tid = topic_for_claim(c)
        if tid != topic_id:
            continue
        if not c.embedding:
            continue
        rows.append(c)
    if not rows:
        return []
    rows.sort(key=lambda c: c.episode_date)

    series: list[StanceSeriesPoint] = []
    i0 = 0
    while i0 < len(rows):
        start_d = rows[i0].episode_date
        end_limit = start_d + timedelta(days=window_days)
        bucket: list[Claim] = []
        j = i0
        while j < len(rows) and rows[j].episode_date < end_limit:
            bucket.append(rows[j])
            j += 1
        vecs = [np.asarray(c.embedding, dtype=float) for c in bucket if c.embedding]
        if vecs:
            cvec = _centroid(vecs).tolist()
            series.append(
                StanceSeriesPoint(
                    window_start=start_d,
                    window_end=bucket[-1].episode_date,
                    centroid=cvec,
                    claim_ids=[c.id for c in bucket],
                )
            )
        i0 = max(i0 + 1, j)
    return series


def compute_drift_velocity_acceleration(
    series: list[StanceSeriesPoint],
) -> tuple[list[float], list[float]]:
    """
    Velocity = cosine distance per day between consecutive centroids.
    Acceleration = first difference of velocity (per step).
    """
    if len(series) < 2:
        return [], []
    vel: list[float] = []
    for i in range(1, len(series)):
        dt = max(
            1.0,
            float((series[i].window_end - series[i - 1].window_end).days) or 1.0,
        )
        d = _cosine_distance(series[i - 1].centroid, series[i].centroid)
        vel.append(d / dt)
    acc: list[float] = []
    for i in range(1, len(vel)):
        acc.append(vel[i] - vel[i - 1])
    return vel, acc


def detect_drift_events_zscore(
    series: list[StanceSeriesPoint],
    *,
    z_threshold: float = 2.5,
) -> list[tuple[int, float, float]]:
    """
    Return list of ``(series_index, velocity, z_score)`` where velocity exceeds threshold.
    ``series_index`` refers to the *later* window endpoint of the velocity segment.
    """
    vel, _ = compute_drift_velocity_acceleration(series)
    if len(vel) < 3:
        return []
    arr = np.asarray(vel, dtype=float)
    mu = float(arr.mean())
    sigma = float(arr.std() + 1e-9)
    out: list[tuple[int, float, float]] = []
    for i, v in enumerate(vel):
        z = (v - mu) / sigma
        if z >= z_threshold:
            out.append((i + 1, float(v), float(z)))
    return out


def _earliest_inconsistent_claim(
    sequence_claims: list[Claim], latest_centroid: list[float]
) -> str:
    if not sequence_claims or not latest_centroid:
        return ""
    best_id = sequence_claims[0].id
    worst_sim = 1.0
    lc = np.asarray(latest_centroid, dtype=float)
    lc = _unit(lc)
    for c in sequence_claims:
        if not c.embedding:
            continue
        v = _unit(np.asarray(c.embedding, dtype=float))
        if v.size != lc.size:
            continue
        sim = float(np.dot(v, lc))
        if sim < worst_sim:
            worst_sim = sim
            best_id = c.id
    return best_id


def surface_drift_events(
    *,
    series: list[StanceSeriesPoint],
    raw_claims: Sequence[Claim],
    author_topic_key: str,
    topic_id: str,
    z_threshold: float = 2.5,
    llm_complete: Optional[Callable[..., str]] = None,
    episode_id: str = "",
) -> list[DriftEvent]:
    """
    Build ``DriftEvent`` rows with claim sequence, LLM summary, earliest inconsistent claim pointer.
    ``llm_complete`` should behave like ``LLMClient.complete`` (system=, user=, max_tokens=).
    """
    events_idx = detect_drift_events_zscore(series, z_threshold=z_threshold)
    claim_by_id = {c.id: c for c in raw_claims}
    out: list[DriftEvent] = []
    for idx, vel, z in events_idx:
        if idx <= 0 or idx >= len(series):
            continue
        seq_ids: list[str] = []
        for k in range(max(0, idx - 2), idx + 1):
            seq_ids.extend(series[k].claim_ids)
        # de-dupe preserving order
        seen: set[str] = set()
        ordered: list[str] = []
        for cid in seq_ids:
            if cid not in seen:
                seen.add(cid)
                ordered.append(cid)
        seq_claims = [claim_by_id[cid] for cid in ordered if cid in claim_by_id]
        latest_c = series[idx].centroid
        earliest = _earliest_inconsistent_claim(seq_claims, latest_c)
        summary = ""
        if llm_complete is not None and seq_claims:
            texts = "\n".join(f"- {c.text}" for c in seq_claims[:12])
            user = (
                f"Author/topic key: {author_topic_key}\n"
                f"Drift velocity={vel:.4f}, z={z:.2f}.\nClaims:\n{texts}\n"
                "Summarize the stance shift in 2–3 sentences for founders."
            )
            try:
                summary = llm_complete(
                    system="You summarize ideological drift tersely.",
                    user=user,
                    max_tokens=220,
                ).strip()
            except Exception as e:  # pragma: no cover
                logger.warning("drift_summary_llm_failed", error=str(e))
                summary = f"Elevated drift (z={z:.2f}) across {len(ordered)} related claims."
        elif seq_claims:
            summary = f"Elevated drift (z={z:.2f}) across {len(ordered)} related claims."
        de = DriftEvent(
            target_id=author_topic_key,
            target_kind="stance_series",
            episode_id=episode_id,
            observed_at=series[idx].window_end,
            drift_score=float(min(1.0, z / 4.0)),
            notes=f"velocity={vel:.5f}, z={z:.3f}",
            claim_sequence_ids=ordered,
            natural_language_summary=summary,
            earliest_inconsistent_claim_id=earliest,
            author_topic_key=author_topic_key,
            topic_id=topic_id,
        )
        out.append(de)
    return out

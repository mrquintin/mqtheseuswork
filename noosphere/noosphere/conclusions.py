"""
Conclusions Registry for the Noosphere System.

This module provides a separate store for SUBSTANTIVE claims (conclusions about
the world) that the firm's founders make. Conclusions are tracked with method
attribution so they can feed back into calibration of the Noosphere's
methodological brain.

The firm's core brain stores only METHODOLOGICAL knowledge — how to think.
But substantive conclusions are valuable as calibration data: if the firm
predicts "AI will transform healthcare by 2028" using analogical reasoning,
and that prediction turns out wrong, that's evidence about the reliability
of analogical reasoning in that domain.

This creates a closed-loop system where substantive track records improve
methodological decision-making over time.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from enum import Enum
import uuid

from pydantic import BaseModel, ConfigDict, Field

from noosphere.llm import LLMClient, llm_client_from_settings
from noosphere.models import Claim, Principle
from noosphere.observability import get_logger

logger = get_logger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────────

class ReasoningMethod(str, Enum):
    """Fundamental reasoning methods used in substantive reasoning."""
    DEDUCTION = "deduction"                  # From general principles to specific
    INDUCTION = "induction"                  # From specific observations to general
    ANALOGY = "analogy"                      # Reasoning by structural similarity
    EMPIRICAL = "empirical"                  # Based on direct observation/data
    BASE_RATE = "base_rate"                  # Using statistical/historical frequencies
    FIRST_PRINCIPLES = "first_principles"    # From axioms and fundamental truths
    AUTHORITY = "authority"                  # Citing expert sources
    PATTERN_MATCHING = "pattern_matching"    # Recognizing recurring structures
    THOUGHT_EXPERIMENT = "thought_experiment" # Hypothetical reasoning
    ABDUCTION = "abduction"                  # Inference to best explanation
    UNKNOWN = "unknown"                      # Method not classified


class ResolutionStatus(str, Enum):
    """Status of a prediction or falsifiable claim."""
    UNRESOLVED = "unresolved"
    RESOLVED_CORRECT = "resolved_correct"
    RESOLVED_INCORRECT = "resolved_incorrect"
    PARTIALLY_CORRECT = "partially_correct"
    UNRESOLVABLE = "unresolvable"


# ── Core Models ──────────────────────────────────────────────────────────────

class SubstantiveConclusion(BaseModel):
    """
    A substantive claim about the world made by the firm's founders.

    Conclusions are atomic propositions that can be true or false, attributed
    to a speaker, produced by a specific reasoning method, and (optionally)
    falsifiable. The system tracks resolution outcomes to calibrate method
    reliability over time.

    Attributes:
        id: Unique identifier (UUID)
        text: The substantive claim itself
        speaker_id: ID of the founder who made it
        speaker_name: Name of the founder
        episode_id: Which episode it appeared in
        episode_date: When the episode aired
        domain: Topic domain (e.g., "technology", "macro_economics")
        method_used: Which reasoning method produced this
        confidence_expressed: How confident the speaker seemed (0-1)
        is_prediction: Whether this is falsifiable about the future
        falsification_condition: What would prove it wrong
        resolution_date: When we can check if it's right
        resolved: Whether outcome has been determined
        resolution_evidence: What evidence resolved it
        created_at: When this conclusion was recorded
        methodological_context: Surrounding discourse about HOW it was reached
        linked_methodology_ids: IDs of methodological principles that produced it
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    speaker_id: str
    speaker_name: str
    episode_id: str
    episode_date: date
    domain: str  # e.g., "macro_economics", "technology", "investing", "geopolitics", "science"
    method_used: ReasoningMethod = ReasoningMethod.UNKNOWN
    confidence_expressed: float = Field(ge=0.0, le=1.0)
    is_prediction: bool = False
    falsification_condition: Optional[str] = None
    resolution_date: Optional[date] = None
    resolved: Optional[bool] = None
    resolution_evidence: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    methodological_context: str = ""  # Surrounding discourse
    linked_methodology_ids: List[str] = []  # Principle IDs

    class Config:
        use_enum_values = True

    def status(self) -> ResolutionStatus:
        """Determine resolution status."""
        if self.resolved is None:
            return ResolutionStatus.UNRESOLVED
        elif self.resolved is True:
            return ResolutionStatus.RESOLVED_CORRECT
        else:
            return ResolutionStatus.RESOLVED_INCORRECT


class MethodAccuracyRecord(BaseModel):
    """
    Accuracy statistics for a reasoning method in a specific domain.

    Tracks how well a particular reasoning method performs, enabling
    the calibration feedback loop.
    """
    method_name: ReasoningMethod
    domain: str
    total_conclusions: int = 0
    resolved_conclusions: int = 0
    correct_count: int = 0
    incorrect_count: int = 0
    accuracy_rate: Optional[float] = None
    brier_score: Optional[float] = None
    average_confidence: float = 0.0
    calibration_error: Optional[float] = None  # abs(confidence - accuracy)

    class Config:
        use_enum_values = True


class ConclusionSummary(BaseModel):
    """Lightweight summary of a conclusion for display."""
    id: str
    text: str
    speaker_name: str
    domain: str
    method_used: str
    confidence_expressed: float
    is_prediction: bool
    resolved: Optional[bool] = None
    created_at: datetime


class OpenQuestionCandidate(BaseModel):
    """
    Epistemic tension surfaced when coherence stays unresolved across layers.

    Fed from the coherence pipeline into the conclusions registry for founder review.
    """

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    summary: str
    claim_a_id: str
    claim_b_id: str
    unresolved_reason: str = ""
    layer_disagreement_summary: str = ""
    created_at: datetime = Field(default_factory=datetime.now)


# ── ConclusionsRegistry ──────────────────────────────────────────────────────

class ConclusionsRegistry:
    """
    Persistent store for substantive conclusions with resolution tracking.

    Provides methods to:
    - Register new conclusions
    - Record resolution outcomes
    - Query conclusions by method, domain, or status
    - Calculate accuracy metrics for methods
    - Generate calibration feedback
    """

    def __init__(self, data_path: str = "conclusions_registry.json"):
        """
        Initialize the registry.

        Args:
            data_path: Path to persistent JSON store
        """
        self.data_path = Path(data_path)
        self.conclusions: Dict[str, SubstantiveConclusion] = {}
        self.open_questions: Dict[str, OpenQuestionCandidate] = {}
        self.load()

    def register_open_question(self, oq: OpenQuestionCandidate) -> str:
        """Persist an unresolved-coherence open question for founder review."""
        self.open_questions[oq.id] = oq
        self.save()
        logger.info("Registered open question candidate %s", oq.id)
        return oq.id

    def register(self, conclusion: SubstantiveConclusion) -> str:
        """
        Register a new substantive conclusion.

        Args:
            conclusion: SubstantiveConclusion object to register

        Returns:
            The conclusion's ID
        """
        if not conclusion.id:
            conclusion.id = str(uuid.uuid4())

        self.conclusions[conclusion.id] = conclusion
        logger.info(
            f"Registered conclusion {conclusion.id} "
            f"({conclusion.method_used}:{conclusion.domain}): "
            f"{conclusion.text[:60]}..."
        )
        self.save()
        return conclusion.id

    def resolve(
        self,
        conclusion_id: str,
        outcome: bool,
        evidence: str = ""
    ) -> SubstantiveConclusion:
        """
        Record whether a conclusion turned out to be correct.

        Args:
            conclusion_id: ID of the conclusion
            outcome: True if correct, False if incorrect
            evidence: Supporting evidence for the resolution

        Returns:
            Updated SubstantiveConclusion object

        Raises:
            ValueError: If conclusion_id not found
        """
        if conclusion_id not in self.conclusions:
            raise ValueError(f"Conclusion {conclusion_id} not found")

        conclusion = self.conclusions[conclusion_id]
        conclusion.resolved = outcome
        conclusion.resolution_evidence = evidence

        logger.info(
            f"Resolved conclusion {conclusion_id}: "
            f"{'CORRECT' if outcome else 'INCORRECT'}"
        )
        self.save()
        return conclusion

    def get_by_method(self, method: str) -> List[SubstantiveConclusion]:
        """
        Get all conclusions produced by a given reasoning method.

        Args:
            method: ReasoningMethod enum value (as string)

        Returns:
            List of conclusions using that method
        """
        return [
            c for c in self.conclusions.values()
            if str(c.method_used) == method
        ]

    def get_by_domain(self, domain: str) -> List[SubstantiveConclusion]:
        """
        Get all conclusions in a specific domain.

        Args:
            domain: Domain name (e.g., "technology", "economics")

        Returns:
            List of conclusions in that domain
        """
        return [c for c in self.conclusions.values() if c.domain == domain]

    def get_unresolved(self) -> List[SubstantiveConclusion]:
        """
        Get all conclusions awaiting resolution.

        Returns:
            List of unresolved conclusions
        """
        return [c for c in self.conclusions.values() if c.resolved is None]

    def get_predictions_due(
        self,
        as_of: Optional[date] = None
    ) -> List[SubstantiveConclusion]:
        """
        Get predictions whose resolution date has passed but aren't resolved yet.

        Args:
            as_of: Date to check against (default: today)

        Returns:
            List of overdue predictions
        """
        if as_of is None:
            as_of = date.today()

        return [
            c for c in self.conclusions.values()
            if (
                c.is_prediction
                and c.resolution_date
                and c.resolution_date <= as_of
                and c.resolved is None
            )
        ]

    def method_accuracy(
        self,
        method: str,
        domain: Optional[str] = None
    ) -> MethodAccuracyRecord:
        """
        Calculate accuracy statistics for a reasoning method.

        Args:
            method: ReasoningMethod value
            domain: Optional domain to filter by

        Returns:
            MethodAccuracyRecord with accuracy metrics
        """
        conclusions = self.get_by_method(method)
        if domain:
            conclusions = [c for c in conclusions if c.domain == domain]

        resolved = [c for c in conclusions if c.resolved is not None]
        correct = [c for c in resolved if c.resolved is True]
        incorrect = [c for c in resolved if c.resolved is False]

        accuracy_rate = None
        brier_score = None
        calibration_error = None

        if resolved:
            accuracy_rate = len(correct) / len(resolved)

            # Brier score: mean squared error of confidence vs outcome
            brier_score = sum(
                (c.confidence_expressed - (1.0 if c.resolved else 0.0)) ** 2
                for c in resolved
            ) / len(resolved)

            avg_confidence = (
                sum(c.confidence_expressed for c in conclusions) / len(conclusions)
                if conclusions else 0.0
            )
            calibration_error = abs(avg_confidence - accuracy_rate)
        else:
            avg_confidence = (
                sum(c.confidence_expressed for c in conclusions) / len(conclusions)
                if conclusions else 0.0
            )

        return MethodAccuracyRecord(
            method_name=method,
            domain=domain or "all",
            total_conclusions=len(conclusions),
            resolved_conclusions=len(resolved),
            correct_count=len(correct),
            incorrect_count=len(incorrect),
            accuracy_rate=accuracy_rate,
            brier_score=brier_score,
            average_confidence=avg_confidence,
            calibration_error=calibration_error,
        )

    def all_method_accuracies(self) -> List[MethodAccuracyRecord]:
        """
        Calculate accuracy breakdown by method × domain.

        Returns:
            List of MethodAccuracyRecords for all combinations
        """
        records = []
        methods = set(str(c.method_used) for c in self.conclusions.values())
        domains = set(c.domain for c in self.conclusions.values())

        # Calculate by method × domain
        for method in methods:
            for domain in domains:
                record = self.method_accuracy(method, domain)
                if record.total_conclusions > 0:
                    records.append(record)

            # Also include overall by method
            record = self.method_accuracy(method)
            if record.total_conclusions > 0:
                records.append(record)

        return records

    def save(self) -> None:
        """Persist conclusions to JSON."""
        try:
            data = {
                "conclusions": [
                    json.loads(c.model_dump_json())
                    for c in self.conclusions.values()
                ],
                "open_questions": [
                    json.loads(o.model_dump_json())
                    for o in self.open_questions.values()
                ],
            }
            # Convert datetime objects to ISO format strings
            for item in data["conclusions"]:
                item["created_at"] = item["created_at"]
                if item.get("resolution_evidence"):
                    pass  # Already a string

            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"Registry saved to {self.data_path}")
        except Exception as e:
            logger.error(f"Failed to save registry: {e}")
            raise

    def load(self) -> None:
        """Load conclusions from JSON."""
        if not self.data_path.exists():
            logger.info(f"Registry file {self.data_path} not found, starting fresh")
            return

        try:
            with open(self.data_path, 'r') as f:
                data = json.load(f)

            self.conclusions = {}
            for item in data.get("conclusions", []):
                # Convert ISO datetime strings back to datetime
                if isinstance(item.get("created_at"), str):
                    item["created_at"] = datetime.fromisoformat(item["created_at"])

                conclusion = SubstantiveConclusion(**item)
                self.conclusions[conclusion.id] = conclusion

            self.open_questions = {}
            for item in data.get("open_questions", []):
                if isinstance(item.get("created_at"), str):
                    item["created_at"] = datetime.fromisoformat(item["created_at"])
                oq = OpenQuestionCandidate(**item)
                self.open_questions[oq.id] = oq

            logger.info(
                f"Loaded {len(self.conclusions)} conclusions and "
                f"{len(self.open_questions)} open questions from {self.data_path}"
            )
        except Exception as e:
            logger.error(f"Failed to load registry: {e}")
            raise

    def search(self, query: str, k: int = 10) -> List[ConclusionSummary]:
        """
        Simple text search over conclusions.

        Args:
            query: Search query string
            k: Number of results to return

        Returns:
            List of matching conclusions (up to k)
        """
        query_lower = query.lower()
        matches = []

        for conclusion in self.conclusions.values():
            if (
                query_lower in conclusion.text.lower()
                or query_lower in conclusion.speaker_name.lower()
                or query_lower in conclusion.domain.lower()
            ):
                matches.append(
                    ConclusionSummary(
                        id=conclusion.id,
                        text=conclusion.text,
                        speaker_name=conclusion.speaker_name,
                        domain=conclusion.domain,
                        method_used=str(conclusion.method_used),
                        confidence_expressed=conclusion.confidence_expressed,
                        is_prediction=conclusion.is_prediction,
                        resolved=conclusion.resolved,
                        created_at=conclusion.created_at,
                    )
                )

        # Return top k matches
        return matches[:k]


# ── CalibrationAnalyzer ──────────────────────────────────────────────────────

class CalibrationAnalyzer:
    """
    Analyzes the firm's reasoning method performance to generate
    calibration feedback for the methodological brain.

    This is the KEY integration point: it transforms substantive accuracy
    data into methodological observations that the main brain CAN store.
    """

    def __init__(self, registry: ConclusionsRegistry):
        """
        Initialize the analyzer.

        Args:
            registry: ConclusionsRegistry to analyze
        """
        self.registry = registry

    def method_reliability_report(self) -> Dict:
        """
        Generate comprehensive reliability assessment for each reasoning method.

        For each method the firm uses, provides:
        - Number of conclusions produced
        - Accuracy rate (where resolvable)
        - Average confidence vs. actual accuracy (calibration)
        - Domains where the method works best/worst
        - Actionable recommendations

        Returns:
            Dictionary with reliability data for each method
        """
        accuracy_records = self.registry.all_method_accuracies()

        # Group by method
        by_method: Dict[str, List[MethodAccuracyRecord]] = {}
        for record in accuracy_records:
            if record.method_name not in by_method:
                by_method[record.method_name] = []
            by_method[record.method_name].append(record)

        report = {}
        for method, records in by_method.items():
            # Find overall record (domain="all")
            overall = next(
                (r for r in records if r.domain == "all"),
                None
            )

            if not overall:
                continue

            domain_records = [r for r in records if r.domain != "all"]
            domain_records.sort(
                key=lambda r: r.accuracy_rate if r.accuracy_rate else 0.0,
                reverse=True
            )

            best_domains = [r.domain for r in domain_records[:3] if r.accuracy_rate]
            worst_domains = [r.domain for r in domain_records[-3:] if r.accuracy_rate]

            # Determine if well-calibrated
            is_calibrated = False
            if overall.calibration_error is not None:
                # Well-calibrated if confidence-accuracy gap < 0.1
                is_calibrated = overall.calibration_error < 0.10

            confidence_assessment = "well-calibrated"
            if overall.calibration_error and overall.calibration_error > 0.2:
                if overall.average_confidence > (overall.accuracy_rate or 0.0):
                    confidence_assessment = "overconfident"
                else:
                    confidence_assessment = "underconfident"

            recommendations = self._generate_recommendations(
                method, overall, best_domains, worst_domains, is_calibrated
            )

            report[method] = {
                "total_conclusions": overall.total_conclusions,
                "resolved_conclusions": overall.resolved_conclusions,
                "accuracy_rate": overall.accuracy_rate,
                "average_confidence": overall.average_confidence,
                "calibration_error": overall.calibration_error,
                "brier_score": overall.brier_score,
                "confidence_assessment": confidence_assessment,
                "best_domains": best_domains,
                "worst_domains": worst_domains,
                "recommendations": recommendations,
            }

        return report

    def domain_report(self, domain: str) -> Dict:
        """
        Generate performance analysis for conclusions in a specific domain.

        For a given domain, shows:
        - Which methods are most/least accurate
        - Overall calibration
        - Trends over time (if available)

        Args:
            domain: Domain name to analyze

        Returns:
            Dictionary with domain analysis
        """
        conclusions_in_domain = self.registry.get_by_domain(domain)
        if not conclusions_in_domain:
            return {"error": f"No conclusions found in domain '{domain}'"}

        # Group by method
        by_method: Dict[str, List[SubstantiveConclusion]] = {}
        for c in conclusions_in_domain:
            method = str(c.method_used)
            if method not in by_method:
                by_method[method] = []
            by_method[method].append(c)

        method_analysis = {}
        for method, conclusions in by_method.items():
            resolved = [c for c in conclusions if c.resolved is not None]
            if resolved:
                correct = sum(1 for c in resolved if c.resolved)
                accuracy = correct / len(resolved)
                avg_confidence = sum(c.confidence_expressed for c in conclusions) / len(conclusions)
            else:
                accuracy = None
                avg_confidence = sum(c.confidence_expressed for c in conclusions) / len(conclusions)

            method_analysis[method] = {
                "count": len(conclusions),
                "resolved": len(resolved),
                "accuracy": accuracy,
                "average_confidence": avg_confidence,
            }

        # Sort by accuracy
        sorted_methods = sorted(
            method_analysis.items(),
            key=lambda x: x[1]["accuracy"] if x[1]["accuracy"] is not None else -1,
            reverse=True
        )

        return {
            "domain": domain,
            "total_conclusions": len(conclusions_in_domain),
            "resolved_conclusions": sum(1 for c in conclusions_in_domain if c.resolved is not None),
            "method_breakdown": dict(sorted_methods),
            "best_method": sorted_methods[0][0] if sorted_methods else None,
            "worst_method": sorted_methods[-1][0] if sorted_methods else None,
        }

    def feedback_for_methodology(self) -> List[Dict]:
        """
        Generate specific feedback for the methodological brain.

        This is the CRITICAL integration point. It transforms substantive
        accuracy data into METHODOLOGICAL observations that the main brain
        can store and learn from.

        Produces observations like:
        - "Analogical reasoning has 0.35 accuracy in tech predictions.
           Consider supplementing with base-rate analysis."
        - "First-principles reasoning has 0.78 accuracy in competitive analysis.
           This is a methodological strength."
        - "The firm is systematically overconfident (avg 0.72, accuracy 0.55).
           Recommend calibration training."

        These are formatted as METHODOLOGICAL claims about which methods work,
        not claims about the world.

        Returns:
            List of feedback dictionaries with:
            - feedback_type: "strength" | "weakness" | "calibration" | "combination"
            - method_involved: str (method name or list of methods)
            - observation: str (the methodological claim)
            - domain: str (where applicable)
            - confidence: float (how confident in this feedback)
            - evidence: dict (supporting statistics)
            - recommendation: str (what to do about it)
        """
        feedback = []
        report = self.method_reliability_report()

        if not report:
            return feedback

        # 1. Method strength/weakness feedback
        for method, stats in report.items():
            if stats["resolved_conclusions"] < 3:
                # Not enough data
                continue

            accuracy = stats["accuracy_rate"]
            if accuracy is None:
                continue

            # Strength if accuracy > 0.65
            if accuracy > 0.65:
                feedback.append({
                    "feedback_type": "strength",
                    "method_involved": method,
                    "observation": (
                        f"{method.replace('_', ' ').title()} reasoning demonstrates "
                        f"strong reliability with {accuracy:.1%} accuracy "
                        f"({stats['resolved_conclusions']} predictions resolved)."
                    ),
                    "domain": "all",
                    "confidence": min(stats["resolved_conclusions"] / 10.0, 1.0),
                    "evidence": {
                        "accuracy_rate": accuracy,
                        "resolved_count": stats["resolved_conclusions"],
                        "total_count": stats["total_conclusions"],
                    },
                    "recommendation": (
                        f"Increase reliance on {method.replace('_', ' ')} reasoning. "
                        f"Consider using it as primary method where applicable."
                    ),
                })

            # Weakness if accuracy < 0.45
            elif accuracy < 0.45:
                feedback.append({
                    "feedback_type": "weakness",
                    "method_involved": method,
                    "observation": (
                        f"{method.replace('_', ' ').title()} reasoning shows weak reliability "
                        f"with only {accuracy:.1%} accuracy "
                        f"({stats['resolved_conclusions']} predictions resolved)."
                    ),
                    "domain": "all",
                    "confidence": min(stats["resolved_conclusions"] / 10.0, 1.0),
                    "evidence": {
                        "accuracy_rate": accuracy,
                        "resolved_count": stats["resolved_conclusions"],
                        "total_count": stats["total_conclusions"],
                    },
                    "recommendation": (
                        f"Reduce reliance on {method.replace('_', ' ')} reasoning alone. "
                        f"Consider combining with other methods for validation."
                    ),
                })

        # 2. Calibration feedback
        overconfident_methods = [
            (m, s) for m, s in report.items()
            if s["calibration_error"] and s["calibration_error"] > 0.15
            and s["average_confidence"] > (s["accuracy_rate"] or 0.0)
        ]

        if overconfident_methods:
            feedback.append({
                "feedback_type": "calibration",
                "method_involved": [m for m, s in overconfident_methods],
                "observation": (
                    f"The firm shows systematic overconfidence across "
                    f"{len(overconfident_methods)} reasoning methods. "
                    f"Average confidence exceeds actual accuracy."
                ),
                "domain": "all",
                "confidence": 0.8,
                "evidence": {
                    "overconfident_methods": [
                        {
                            "method": m,
                            "avg_confidence": s["average_confidence"],
                            "accuracy": s["accuracy_rate"],
                            "gap": s["calibration_error"],
                        }
                        for m, s in overconfident_methods
                    ]
                },
                "recommendation": (
                    "Implement confidence calibration training. "
                    "When expressing confidence, systematically reduce by 10-15% "
                    "to account for overconfidence bias."
                ),
            })

        # 3. Domain-specific strength/weakness
        all_conclusions = self.registry.conclusions.values()
        domains = set(c.domain for c in all_conclusions)

        for domain in domains:
            domain_analysis = self.domain_report(domain)
            if "error" in domain_analysis:
                continue

            best_method = domain_analysis.get("best_method")
            worst_method = domain_analysis.get("worst_method")

            if best_method:
                method_stats = domain_analysis["method_breakdown"][best_method]
                if method_stats["accuracy"] and method_stats["accuracy"] > 0.60:
                    feedback.append({
                        "feedback_type": "domain_strength",
                        "method_involved": best_method,
                        "observation": (
                            f"{best_method.replace('_', ' ').title()} reasoning is particularly "
                            f"effective in {domain} domain with {method_stats['accuracy']:.1%} accuracy."
                        ),
                        "domain": domain,
                        "confidence": min(method_stats["resolved"] / 10.0, 1.0),
                        "evidence": {
                            "accuracy": method_stats["accuracy"],
                            "resolved_count": method_stats["resolved"],
                        },
                        "recommendation": (
                            f"Prioritize {best_method.replace('_', ' ')} reasoning "
                            f"for future {domain} analysis."
                        ),
                    })

        # 4. Method combination feedback
        # Look for cases where combining methods might help
        if len(report) > 1:
            high_variance = [
                (m, s) for m, s in report.items()
                if s["resolved_conclusions"] > 2
                and 0.45 <= (s["accuracy_rate"] or 0.5) <= 0.65
            ]

            if high_variance:
                feedback.append({
                    "feedback_type": "combination",
                    "method_involved": [m for m, s in high_variance],
                    "observation": (
                        f"Several methods show moderate performance "
                        f"({[m for m, s in high_variance]}). "
                        f"Combining complementary methods may improve reliability."
                    ),
                    "domain": "all",
                    "confidence": 0.6,
                    "evidence": {
                        "moderate_methods": [
                            {"method": m, "accuracy": s["accuracy_rate"]}
                            for m, s in high_variance
                        ]
                    },
                    "recommendation": (
                        f"When using {', '.join([m for m, s in high_variance])}, "
                        f"implement cross-validation with a second complementary method."
                    ),
                })

        return feedback

    def _generate_recommendations(
        self,
        method: str,
        overall: MethodAccuracyRecord,
        best_domains: List[str],
        worst_domains: List[str],
        is_calibrated: bool,
    ) -> List[str]:
        """Helper to generate specific recommendations for a method."""
        recommendations = []

        if not overall.resolved_conclusions:
            recommendations.append(f"Gather more resolved predictions ({overall.resolved_conclusions} so far).")
            return recommendations

        accuracy = overall.accuracy_rate or 0.0

        if accuracy > 0.7:
            recommendations.append(f"Excellent track record. Increase reliance in all domains.")
            if best_domains:
                recommendations.append(f"Particularly strong in: {', '.join(best_domains)}")
        elif accuracy < 0.4:
            recommendations.append(f"Weak performance. Use only as secondary validation method.")
            if worst_domains:
                recommendations.append(f"Avoid using in: {', '.join(worst_domains)}")
        else:
            recommendations.append(f"Moderate performance. Use with caution, validate with other methods.")

        if not is_calibrated:
            if overall.calibration_error and overall.calibration_error > 0.2:
                recommendations.append("Confidence is poorly calibrated. Recalibrate confidence thresholds.")

        if best_domains and worst_domains:
            recommendations.append(
                f"Strong in {best_domains[0]}, weak in {worst_domains[0]}. "
                f"Investigate domain-specific factors."
            )

        return recommendations


# ── AutoResolver ────────────────────────────────────────────────────────────

class AutoResolver:
    """
    Semi-automatic resolution of predictions using Claude with web search.

    Given a conclusion and the current date, attempts to determine:
    - Is this resolvable yet?
    - If yes, was it correct?
    - What evidence supports the resolution?
    """

    def __init__(self, llm: LLMClient | None = None):
        """
        Initialize the resolver.

        Args:
            llm: Optional LLM client (uses configured default if not provided)
        """
        self._llm = llm or llm_client_from_settings()

    def check_resolvable(
        self,
        conclusion: SubstantiveConclusion
    ) -> Tuple[bool, Optional[bool], str]:
        """
        Check if a prediction is resolvable and, if so, determine its accuracy.

        Uses Claude to reason about whether:
        1. The prediction can be checked yet (based on resolution_date)
        2. If resolvable, whether it turned out to be correct
        3. What evidence supports the determination

        Args:
            conclusion: The conclusion to check

        Returns:
            Tuple of (is_resolvable, was_correct, reasoning)
            - is_resolvable: True if we can check the prediction now
            - was_correct: True/False if resolvable, None if not
            - reasoning: Explanation of how it was determined
        """
        # Check if it's time to resolve
        if not conclusion.is_prediction:
            return False, None, "Not marked as a prediction"

        if conclusion.resolved is not None:
            return False, None, "Already resolved"

        if conclusion.resolution_date is None:
            return False, None, "No resolution date specified"

        today = date.today()
        if today < conclusion.resolution_date:
            days_until = (conclusion.resolution_date - today).days
            return False, None, f"Too early to resolve (in {days_until} days)"

        # Try to resolve using Claude
        try:
            prompt = f"""
Given this prediction made on {conclusion.episode_date}:

"{conclusion.text}"

Reasoning method: {conclusion.method_used}
Domain: {conclusion.domain}
Stated resolution condition: {conclusion.falsification_condition or "Not specified"}
Intended resolution date: {conclusion.resolution_date}
Today's date: {today}

Determine:
1. Can this prediction be evaluated now? (Yes/No)
2. If yes, was it correct? (True/False/Partially True)
3. What evidence or information supports this determination?

Format your response as:
RESOLVABLE: [Yes/No]
CORRECT: [True/False/Partially True/N/A]
EVIDENCE: [Brief explanation with sources where applicable]
"""

            response_text = self._llm.complete(
                system="Follow the user's output format exactly.",
                user=prompt,
                max_tokens=500,
                temperature=0.0,
            )

            # Parse response
            lines = response_text.strip().split('\n')
            resolvable = False
            correct = None
            evidence = ""

            for line in lines:
                if line.startswith("RESOLVABLE:"):
                    resolvable = "yes" in line.lower()
                elif line.startswith("CORRECT:"):
                    if "true" in line.lower() and "partially" not in line.lower():
                        correct = True
                    elif "false" in line.lower():
                        correct = False
                    # Partially True or N/A → return None
                elif line.startswith("EVIDENCE:"):
                    evidence = line.replace("EVIDENCE:", "").strip()

            if not evidence:
                evidence = response_text

            return resolvable, correct, evidence

        except Exception as e:
            logger.error(f"Error checking resolvable conclusion {conclusion.id}: {e}")
            return False, None, f"Error during resolution check: {str(e)}"

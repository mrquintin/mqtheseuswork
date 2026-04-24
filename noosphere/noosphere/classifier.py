"""
Discourse Classifier for Noosphere.

This module separates methodological claims from substantive claims at the
point of ingestion. In natural conversation, methodological knowledge
(how to think, how to reason, how to evaluate) is constantly interleaved
with substantive conclusions (what they think is true about the world).

This classifier decomposes mixed claims, identifies the reasoning methods
behind substantive claims, and categorizes each discourse fragment into:
- METHODOLOGICAL: How to think, reason, evaluate, investigate
- SUBSTANTIVE: What is true in the world (conclusions, predictions)
- META_METHODOLOGICAL: How to evaluate methods themselves
- MIXED: Interleaved methodological and substantive content
- NON_PROPOSITIONAL: Not a truth claim (questions, social talk)

The classifier uses Claude for primary classification and falls back to
heuristic rules if the API is unavailable.
"""

import re
import json
from enum import Enum
from typing import Optional, Tuple
from dataclasses import dataclass

from noosphere.llm import LLMClient, llm_client_from_settings
from noosphere.models import Claim, ClaimType
from noosphere.observability import get_logger

logger = get_logger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────────

class DiscourseType(str, Enum):
    """Category of discourse: how it contributes to the firm's knowledge base."""

    METHODOLOGICAL = "METHODOLOGICAL"
    """Claims about HOW to think, reason, evaluate, investigate, or decide.
    These describe intellectual processes, not conclusions.
    Examples: "Always check the base rate", "Steelman the counter-argument",
    "The way to evaluate a moat is to ask what would destroy it"."""

    SUBSTANTIVE = "SUBSTANTIVE"
    """Claims about WHAT is true in the world. Conclusions, predictions, assessments.
    Examples: "AI will transform healthcare", "Network effects create durable moats",
    "This company has no competitive advantage"."""

    META_METHODOLOGICAL = "META_METHODOLOGICAL"
    """Claims about how to EVALUATE methods. Third-order: not what to think or how,
    but how to judge whether a way of thinking is good.
    Examples: "A method is only as good as its falsification conditions",
    "We should track prediction accuracy across domains"."""

    MIXED = "MIXED"
    """Claims that interleave methodological and substantive content.
    Examples: "I arrived at the network effects thesis by analyzing 50 companies",
    "Using first-principles reasoning, the moat here is switching costs"."""

    NON_PROPOSITIONAL = "NON_PROPOSITIONAL"
    """Not a truth claim. Questions, social talk, meta-discourse about conversation.
    Examples: "What do you think about that?", "Let's move on", "That's interesting"."""


class MethodAttributionType(str, Enum):
    """The reasoning method used to arrive at a substantive claim."""

    DEDUCTION = "deduction"
    """Logical reasoning from premises to conclusion."""

    INDUCTION = "induction"
    """Pattern recognition from multiple observations."""

    ABDUCTION = "abduction"
    """Inference to the best explanation."""

    ANALOGY = "analogy"
    """Structural parallel drawn from another domain."""

    EMPIRICAL_OBSERVATION = "empirical_observation"
    """Direct observation or evidence."""

    BASE_RATE_ANALYSIS = "base_rate_analysis"
    """Analysis of reference class frequencies."""

    FIRST_PRINCIPLES = "first_principles"
    """Reasoning from foundational axioms."""

    AUTHORITY = "authority"
    """Appeal to expert or authoritative source."""

    PATTERN_MATCHING = "pattern_matching"
    """Recognition of recurring patterns."""

    THOUGHT_EXPERIMENT = "thought_experiment"
    """Hypothetical reasoning."""

    UNKNOWN = "unknown"
    """Method not identifiable or not specified."""


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class ClassifiedClaim:
    """
    Result of classifying a single claim.

    Attributes:
        claim_id: Unique identifier from the original Claim
        text: The claim text
        discourse_type: One of the DiscourseType categories
        confidence: 0-1, how confident the classification is
        methodological_content: If MIXED or SUBSTANTIVE, the extracted
            methodological component. For SUBSTANTIVE, this is the METHOD
            that produced the claim ("arrived via analogy", "based on
            empirical base rates", etc.)
        substantive_content: If MIXED or METHODOLOGICAL, the substantive
            component. For METHODOLOGICAL claims that reference specific
            domains, this captures that context.
        method_attribution: For SUBSTANTIVE/MIXED claims, which reasoning
            method was used (deduction, induction, analogy, empirical, etc.)
        decomposition_notes: Explanation of why this classification was made
    """
    claim_id: str
    text: str
    discourse_type: DiscourseType
    confidence: float
    methodological_content: Optional[str] = None
    substantive_content: Optional[str] = None
    method_attribution: Optional[MethodAttributionType] = None
    decomposition_notes: str = ""


# ── Prompts ──────────────────────────────────────────────────────────────────

CLASSIFICATION_PROMPT = """You are a discourse classifier for an epistemological research system. Your task is to classify claims extracted from conversation into exactly one of five categories:

METHODOLOGICAL: Claims about HOW to think, reason, evaluate, or decide. These describe processes, not conclusions. They answer "how should we investigate?" not "what did we find?"
Examples:
- "We should always steelman the counter-argument before committing"
- "The right way to evaluate a moat is to ask what would destroy it"
- "Base rate analysis should precede any specific prediction"
- "Always specify what would change your mind"

SUBSTANTIVE: Claims about WHAT is true in the world. These are conclusions, predictions, assessments, or factual claims. They answer "what is the case?" not "how do we determine what is the case?"
Examples:
- "Network effects create durable moats in platform businesses"
- "The Fed will cut rates by Q3"
- "This company's competitive advantage is its data flywheel"
- "AI will transform drug discovery within 5 years"

META_METHODOLOGICAL: Claims about how to evaluate METHODS themselves. These are third-order: they don't say what to think or how to think, but how to judge whether a way of thinking is good.
Examples:
- "A method is only as good as its falsification conditions"
- "We should track our prediction accuracy across domains"
- "The test of a methodology is whether it generates novel predictions"
- "Our confidence should be calibrated to our track record"

MIXED: Claims that interleave methodological and substantive content.
Examples:
- "I arrived at the network effects thesis by analyzing 50 platform companies" (substantive conclusion + empirical method)
- "Using first-principles analysis, the moat here is switching costs" (method + conclusion)

NON_PROPOSITIONAL: Not a truth claim. Questions, social talk, meta-discourse about the conversation.
Examples:
- "What do you think about that?"
- "Let's move on to the next topic"
- "That's an interesting point"

For the given claim and its conversational context, classify it and output valid JSON:
{
  "discourse_type": "METHODOLOGICAL" | "SUBSTANTIVE" | "META_METHODOLOGICAL" | "MIXED" | "NON_PROPOSITIONAL",
  "confidence": 0.0-1.0,
  "methodological_content": "the methodological component if MIXED or SUBSTANTIVE (the method used), or null",
  "substantive_content": "the substantive component if MIXED or METHODOLOGICAL, or null",
  "method_attribution": "for SUBSTANTIVE/MIXED: one of [deduction, induction, abduction, analogy, empirical_observation, base_rate_analysis, first_principles, authority, pattern_matching, thought_experiment, unknown], or null",
  "reasoning": "brief explanation of classification (1-2 sentences)"
}

Respond ONLY with valid JSON, no other text."""

DECOMPOSITION_PROMPT = """You are decomposing a MIXED claim into its methodological and substantive parts.

MIXED claims contain both:
1. A methodological element (HOW the person thinks, reasons, or investigates)
2. A substantive element (WHAT they concluded or claim)

Example decomposition:
"I arrived at the network effects thesis by analyzing 50 platform companies"
- Methodological: "arrived at by analyzing multiple platform companies" (empirical method)
- Substantive: "network effects thesis" (the conclusion)

Given the claim and its conversational context, extract both parts and output valid JSON:
{
  "methodological_part": "the method or process, or null if not clearly present",
  "substantive_part": "the conclusion or claim, or null if not clearly present"
}

Respond ONLY with valid JSON, no other text."""

METHOD_ATTRIBUTION_PROMPT = """You are identifying the reasoning method used to arrive at a substantive claim.

Given a substantive claim and its conversational context, determine which reasoning method most likely produced it. Choose exactly one:

- deduction: logical reasoning from premises to conclusion
- induction: pattern recognition from multiple observations
- abduction: inference to the best explanation
- analogy: structural parallel from another domain
- empirical_observation: direct observation or evidence
- base_rate_analysis: analysis of reference class frequencies
- first_principles: reasoning from foundational axioms
- authority: appeal to expert or authoritative source
- pattern_matching: recognition of recurring patterns
- thought_experiment: hypothetical reasoning
- unknown: method not identifiable or not specified

Output valid JSON:
{
  "method": "one of the above",
  "reasoning": "brief explanation of why (1-2 sentences)"
}

Respond ONLY with valid JSON, no other text."""


# ── Heuristic Classifier (Fallback) ──────────────────────────────────────────

class HeuristicClassifier:
    """
    Rule-based fallback classifier using keyword patterns.

    Used when the Claude API is unavailable. Returns lower confidence
    scores (0.4-0.7) to reflect the heuristic's inherent uncertainty.
    """

    # Methodological indicators
    METHODOLOGICAL_PATTERNS = [
        r'\b(we\s+should|always|never|the\s+way\s+to|the\s+right\s+way)',
        r'\b(method|approach|framework|process|strategy)',
        r'\b(by\s+looking\s+at|how\s+to|to\s+evaluate)',
        r'\b(first\s+principles|check\s+for|make\s+sure\s+to)',
        r'\b(a\s+better\s+way|reasoning|analysis\s+should)',
        r'\b(the\s+process\s+for|investigate|think\s+about)',
        r'\b(criteria\s+for|how\s+we|our\s+way\s+of)',
    ]

    # Substantive indicators
    SUBSTANTIVE_PATTERNS = [
        r'\b(is|will|has|are|were|was)\b',
        r'\b(the\s+market|the\s+company|the\s+industry)',
        r'\b(think|believe|found|shows|evidence)',
        r'\b(prediction|forecast|expect|anticipate)',
        r'\b(advantage|moat|competitive|durable)',
        r'^[A-Z].*\b(is|will|has)\b.*\.$',  # Looks like a conclusion
    ]

    # Meta-methodological indicators
    META_METHODOLOGICAL_PATTERNS = [
        r'\b(our\s+method|calibration|track\s+record)',
        r'\b(whether\s+our|evaluate\s+our|test\s+the)',
        r'\b(the\s+methodology|how\s+reliable|accuracy)',
        r'\b(confidence\s+calibrated|falsif)',
    ]

    # Non-propositional indicators
    NON_PROPOSITIONAL_PATTERNS = [
        r'^\s*\?',  # Starts with question mark
        r'\b(what\s+do\s+you|do\s+you\s+think|what\s+about)',
        r'\b(let\'s|let\s+us|moving\s+on|next)',
        r'\b(interesting|fascinating|good\s+point)',
        r'^\s*[a-z]',  # Lowercase start (often social)
    ]

    @staticmethod
    def _count_pattern_matches(text: str, patterns: list[str]) -> int:
        """Count how many patterns match in text (case-insensitive)."""
        text_lower = text.lower()
        count = 0
        for pattern in patterns:
            if re.search(pattern, text_lower):
                count += 1
        return count

    def classify(self, claim_text: str, context: str = "") -> ClassifiedClaim:
        """
        Heuristically classify a claim using keyword patterns.

        Args:
            claim_text: The claim to classify
            context: Optional surrounding context

        Returns:
            ClassifiedClaim with heuristic classification (lower confidence)
        """
        combined_text = f"{claim_text} {context}".strip()

        # Count pattern matches for each category
        methodological_score = self._count_pattern_matches(
            combined_text, self.METHODOLOGICAL_PATTERNS
        )
        substantive_score = self._count_pattern_matches(
            combined_text, self.SUBSTANTIVE_PATTERNS
        )
        meta_score = self._count_pattern_matches(
            combined_text, self.META_METHODOLOGICAL_PATTERNS
        )
        non_prop_score = self._count_pattern_matches(
            combined_text, self.NON_PROPOSITIONAL_PATTERNS
        )

        # Determine primary classification
        scores = {
            DiscourseType.METHODOLOGICAL: methodological_score,
            DiscourseType.SUBSTANTIVE: substantive_score,
            DiscourseType.META_METHODOLOGICAL: meta_score,
            DiscourseType.NON_PROPOSITIONAL: non_prop_score,
        }

        # Check for MIXED (both methodological and substantive signals)
        if methodological_score > 0 and substantive_score > 0:
            discourse_type = DiscourseType.MIXED
            confidence = 0.45  # Low confidence for heuristic MIXED
        else:
            discourse_type = max(scores, key=scores.get)
            # Confidence based on dominance (range 0.4-0.7)
            max_score = scores[discourse_type]
            if max_score == 0:
                confidence = 0.4  # Uncertain
            else:
                total = sum(scores.values())
                confidence = 0.4 + (0.3 * max_score / max(total, 1))

        return ClassifiedClaim(
            claim_id="",  # Will be set by caller
            text=claim_text,
            discourse_type=discourse_type,
            confidence=confidence,
            decomposition_notes=f"Heuristic classification: {discourse_type.value}"
        )


# ── Claim Decomposer ─────────────────────────────────────────────────────────

class ClaimDecomposer:
    """
    Decomposes MIXED claims and extracts method attributions.

    Uses Claude to:
    1. Split MIXED claims into methodological and substantive parts
    2. Identify the reasoning method behind substantive claims
    """

    def __init__(self, llm: LLMClient | None = None):
        """
        Initialize the decomposer.

        Args:
            llm: Optional LLM client. If None, uses configured default client.
        """
        self._llm = llm or llm_client_from_settings()
        self.heuristic_fallback = HeuristicClassifier()

    def decompose_mixed(
        self,
        claim_text: str,
        context: str = ""
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Decompose a MIXED claim into methodological and substantive parts.

        Args:
            claim_text: The mixed claim to decompose
            context: Optional surrounding conversational context

        Returns:
            Tuple of (methodological_part, substantive_part)
            Either part may be None if not present.
        """
        try:
            prompt = f"""{DECOMPOSITION_PROMPT}

Claim: {claim_text}
Context: {context or "(no context)"}"""

            result_text = self._llm.complete(
                system="Reply with JSON only.",
                user=prompt,
                max_tokens=500,
            ).strip()
            result = json.loads(result_text)

            return (result.get("methodological_part"), result.get("substantive_part"))

        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            logger.warning(
                f"Error decomposing claim '{claim_text[:50]}...': {e}. "
                "Using fallback heuristic."
            )
            # Heuristic fallback: simple heuristic split
            if " by " in claim_text.lower():
                parts = claim_text.split(" by ", 1)
                return (f"by {parts[1]}", parts[0])
            return (None, claim_text)

    def extract_method_attribution(
        self,
        substantive_claim: str,
        context: str = ""
    ) -> MethodAttributionType:
        """
        Identify the reasoning method used to arrive at a claim.

        Args:
            substantive_claim: The substantive claim
            context: Optional conversational context

        Returns:
            One of the MethodAttributionType values
        """
        try:
            prompt = f"""{METHOD_ATTRIBUTION_PROMPT}

Claim: {substantive_claim}
Context: {context or "(no context)"}"""

            result_text = self._llm.complete(
                system="Reply with JSON only.",
                user=prompt,
                max_tokens=200,
            ).strip()
            result = json.loads(result_text)

            method_str = result.get("method", "unknown").lower()
            return MethodAttributionType(method_str)

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(
                f"Error attributing method for '{substantive_claim[:50]}...': {e}. "
                "Defaulting to UNKNOWN."
            )
            return MethodAttributionType.UNKNOWN


# ── Main Classifier ──────────────────────────────────────────────────────────

class DiscourseClassifier:
    """
    Classifies claims into discourse categories: METHODOLOGICAL, SUBSTANTIVE,
    META_METHODOLOGICAL, MIXED, and NON_PROPOSITIONAL.

    Uses Claude for primary classification with heuristic fallback if the
    API is unavailable. For MIXED claims, decomposes into components and
    identifies the reasoning method behind substantive parts.
    """

    def __init__(self, llm: LLMClient | None = None):
        """
        Initialize the classifier.

        Args:
            llm: Optional LLM client. If None, uses configured default client.
        """
        self._llm = llm or llm_client_from_settings()
        self.heuristic_fallback = HeuristicClassifier()
        self.decomposer = ClaimDecomposer(self._llm)

    def classify(
        self,
        claim_text: str,
        context: str = "",
        claim_id: str = ""
    ) -> ClassifiedClaim:
        """
        Classify a single claim.

        Args:
            claim_text: The claim to classify
            context: Optional surrounding conversational context
            claim_id: Optional ID for tracking. Generated if not provided.

        Returns:
            ClassifiedClaim with discourse type, confidence, and decomposition
        """
        if not claim_id:
            claim_id = f"claim_{hash(claim_text) % 2**32:08x}"

        # Attempt API-based classification
        try:
            return self._classify_with_claude(claim_text, context, claim_id)
        except Exception as e:
            logger.warning(
                "LLM classification unavailable; falling back to heuristics",
                error=str(e),
            )
            result = self.heuristic_fallback.classify(claim_text, context)
            result.claim_id = claim_id
            return result

    def _classify_with_claude(
        self,
        claim_text: str,
        context: str,
        claim_id: str
    ) -> ClassifiedClaim:
        """
        Classify using Claude API.

        Args:
            claim_text: The claim text
            context: Conversational context
            claim_id: ID for the claim

        Returns:
            ClassifiedClaim
        """
        prompt = f"""{CLASSIFICATION_PROMPT}

Claim: {claim_text}
Context: {context or "(no context)"}"""

        result_text = self._llm.complete(
            system="Reply with JSON only.",
            user=prompt,
            max_tokens=500,
        ).strip()
        result = json.loads(result_text)

        discourse_type = DiscourseType(result["discourse_type"])
        confidence = result.get("confidence", 0.5)
        methodological = result.get("methodological_content")
        substantive = result.get("substantive_content")
        method_str = result.get("method_attribution")
        reasoning = result.get("reasoning", "")

        # Parse method attribution
        method_attr = None
        if method_str:
            try:
                method_attr = MethodAttributionType(method_str.lower())
            except ValueError:
                method_attr = MethodAttributionType.UNKNOWN

        # If MIXED, optionally decompose further
        if discourse_type == DiscourseType.MIXED:
            decomposed = self.decomposer.decompose_mixed(claim_text, context)
            methodological = methodological or decomposed[0]
            substantive = substantive or decomposed[1]

        # If SUBSTANTIVE, extract method attribution if not present
        if discourse_type == DiscourseType.SUBSTANTIVE and not method_attr:
            method_attr = self.decomposer.extract_method_attribution(
                claim_text, context
            )

        return ClassifiedClaim(
            claim_id=claim_id,
            text=claim_text,
            discourse_type=discourse_type,
            confidence=confidence,
            methodological_content=methodological,
            substantive_content=substantive,
            method_attribution=method_attr,
            decomposition_notes=reasoning
        )

    def classify_with_fallback(
        self,
        claim_text: str,
        context: str = ""
    ) -> ClassifiedClaim:
        """
        Classify with explicit fallback handling.

        This is an alias for classify() but makes the fallback behavior explicit.

        Args:
            claim_text: The claim to classify
            context: Optional surrounding context

        Returns:
            ClassifiedClaim
        """
        return self.classify(claim_text, context)

    def classify_batch(
        self,
        claims: list[str] | list[Claim],
        batch_size: int = 10,
        context: str = ""
    ) -> list[ClassifiedClaim]:
        """
        Classify a batch of claims efficiently.

        Groups claims into larger API calls for efficiency. Each claim in
        the batch is classified independently.

        Accepts either raw strings or Claim objects. When Claim objects
        are passed, their .id is preserved in ClassifiedClaim.claim_id
        so the orchestrator can match results back to originals.

        Args:
            claims: List of claim texts (str) or Claim objects to classify
            batch_size: Number of claims to group per API call
            context: Optional shared context for all claims

        Returns:
            List of ClassifiedClaim objects in the same order as input
        """
        # Normalise: extract texts and IDs from Claim objects if needed
        texts: list[str] = []
        ids: list[str] = []
        for c in claims:
            if isinstance(c, Claim):
                texts.append(c.text)
                ids.append(c.id)
            else:
                texts.append(c)
                ids.append("")

        results = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            batch_ids = ids[i:i+batch_size]
            batch_results = self._classify_batch_group(batch_texts, context)
            # Patch in the original Claim IDs when available
            for cc, cid in zip(batch_results, batch_ids):
                if cid:
                    cc.claim_id = cid
            results.extend(batch_results)

        return results

    def _classify_batch_group(
        self,
        claims: list[str],
        context: str
    ) -> list[ClassifiedClaim]:
        """
        Classify a single batch group.

        Args:
            claims: List of claims in this group
            context: Shared context

        Returns:
            List of ClassifiedClaim objects
        """
        try:
            # Build batch prompt
            claims_text = "\n".join(
                f"{i+1}. {claim}" for i, claim in enumerate(claims)
            )

            prompt = f"""{CLASSIFICATION_PROMPT}

Classify each of the following claims:

{claims_text}

Context: {context or "(no context)"}

Respond with a JSON array of objects, one per claim, in order."""

            result_text = self._llm.complete(
                system="Reply with JSON only.",
                user=prompt,
                max_tokens=2000,
            ).strip()

            # Try to parse as array
            try:
                results_data = json.loads(result_text)
            except json.JSONDecodeError:
                # Fallback: if not valid JSON array, try extracting JSON objects
                import re as re_module
                json_objects = re_module.findall(r'\{[^}]+\}', result_text)
                results_data = [json.loads(obj) for obj in json_objects]

            # Convert to ClassifiedClaim objects
            results = []
            for i, (claim, data) in enumerate(zip(claims, results_data)):
                try:
                    discourse_type = DiscourseType(data["discourse_type"])
                    confidence = data.get("confidence", 0.5)
                    methodological = data.get("methodological_content")
                    substantive = data.get("substantive_content")
                    method_str = data.get("method_attribution")
                    reasoning = data.get("reasoning", "")

                    method_attr = None
                    if method_str:
                        try:
                            method_attr = MethodAttributionType(method_str.lower())
                        except ValueError:
                            method_attr = MethodAttributionType.UNKNOWN

                    results.append(ClassifiedClaim(
                        claim_id=f"claim_{hash(claim) % 2**32:08x}",
                        text=claim,
                        discourse_type=discourse_type,
                        confidence=confidence,
                        methodological_content=methodological,
                        substantive_content=substantive,
                        method_attribution=method_attr,
                        decomposition_notes=reasoning
                    ))
                except (KeyError, ValueError) as e:
                    logger.warning(
                        f"Error parsing classification for claim {i+1}: {e}. "
                        "Using heuristic fallback."
                    )
                    results.append(self.heuristic_fallback.classify(claim, context))

            return results

        except Exception as e:
            logger.warning(
                "LLM unavailable during batch classification; using heuristics",
                error=str(e),
                num_claims=len(claims),
            )
            return [
                self.heuristic_fallback.classify(claim, context)
                for claim in claims
            ]


class ClaimTypeVerifier:
    """
    Zero-shot verification of `ClaimType` (starter: BART-MNLI).
    Sets `claim_type_verified` and `claim_type_disagreement` on the claim.
    """

    def __init__(self, model_name: str = "facebook/bart-large-mnli") -> None:
        self._model_name = model_name
        self._pipe = None

    def _pipeline(self):
        if self._pipe is None:
            from transformers import pipeline

            self._pipe = pipeline(
                "zero-shot-classification",
                model=self._model_name,
            )
        return self._pipe

    def verify(self, claim: Claim) -> Claim:
        labels = [e.value for e in ClaimType]
        try:
            res = self._pipeline()(
                claim.text,
                candidate_labels=labels,
                hypothesis_template="This statement is {}.",
            )
            top = ClaimType(res["labels"][0])
        except Exception as e:  # pragma: no cover
            logger.warning("claim_type_verify_failed", error=str(e))
            return claim
        claim.claim_type_verified = top
        claim.claim_type_disagreement = top != claim.claim_type
        return claim

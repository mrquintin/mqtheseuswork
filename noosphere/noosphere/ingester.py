"""
Transcript ingestion pipeline for Noosphere.

This module orchestrates the extraction of atomic claims from raw podcast
transcripts, handling multiple formats, and enriching them with embeddings
and discipline classifications.

The pipeline consists of three main stages:
1. TranscriptParser: Normalize various transcript formats into segments
2. ClaimExtractor: Extract atomic propositions from segments using Claude
3. TranscriptIngester: Full orchestration with embeddings and tagging
"""

import re
import os
from datetime import date
from typing import Any, Optional, List, Dict, Tuple
from dataclasses import dataclass
from pathlib import Path

import spacy
from sentence_transformers import SentenceTransformer

from noosphere.llm import LLMClient, llm_client_from_settings
from noosphere.models import (
    Speaker, TranscriptSegment, Claim, Episode, Discipline
)
from noosphere.observability import get_logger

logger = get_logger(__name__)


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class ExtractionConfig:
    """Configuration for claim extraction."""
    batch_size: int = 7  # Process 5-10 segments per API call
    use_fallback: bool = False  # Use spaCy if API unavailable
    api_timeout_seconds: int = 60
    min_claim_length: int = 10  # Minimum characters for a claim
    max_claims_per_segment: int = 5


# ── TranscriptParser ─────────────────────────────────────────────────────────

class TranscriptParser:
    """
    Parses raw transcripts in multiple formats and segments by speaker.

    Supported formats:
    1. Plain text with speaker labels: "SPEAKER_NAME: text here"
    2. Timestamped: "[HH:MM:SS] SPEAKER: text here"
    3. Raw unstructured text (treated as single speaker)
    """

    # Pattern for "[HH:MM:SS]" timestamps
    TIMESTAMP_PATTERN = re.compile(
        r'^\[(\d{1,2}):(\d{2}):(\d{2})\]\s+'
    )

    # Pattern for "SPEAKER_NAME: text" or "[time] SPEAKER_NAME: text"
    SPEAKER_LABEL_PATTERN = re.compile(
        r'^(?:\[[\d:]+\]\s+)?([A-Z][A-Z0-9_\s]*?):\s+(.+)$',
        re.MULTILINE
    )

    def __init__(self, logger_instance: Any = None):
        """
        Initialize the parser.

        Args:
            logger_instance: Optional logger instance for this parser
        """
        self.logger = logger_instance or logger

    def parse(
        self,
        transcript_text: str,
        episode_id: str,
        default_speaker: Optional[Speaker] = None
    ) -> List[TranscriptSegment]:
        """
        Parse a transcript into speaker segments.

        Args:
            transcript_text: Raw transcript content
            episode_id: ID for the episode
            default_speaker: Speaker to use if transcript is unstructured

        Returns:
            List of TranscriptSegment objects
        """
        if not transcript_text or not transcript_text.strip():
            self.logger.warning("Empty transcript provided")
            return []

        # Try to detect format and parse accordingly
        if self._has_timestamped_format(transcript_text):
            segments = self._parse_timestamped(transcript_text, episode_id)
        elif self._has_speaker_labels(transcript_text):
            segments = self._parse_labeled(transcript_text, episode_id)
        else:
            # Treat as unstructured text
            segments = self._parse_unstructured(
                transcript_text, episode_id, default_speaker
            )

        self.logger.info(
            f"Parsed transcript into {len(segments)} segments"
        )
        return segments

    def _has_timestamped_format(self, text: str) -> bool:
        """Check if transcript has timestamps."""
        lines = text.split('\n')[:20]  # Check first 20 lines
        return sum(1 for line in lines if self.TIMESTAMP_PATTERN.match(line)) >= 1

    def _has_speaker_labels(self, text: str) -> bool:
        """Check if transcript has speaker labels."""
        lines = text.split('\n')[:20]
        return sum(
            1 for line in lines
            if re.match(r'^[A-Z][A-Z0-9_\s]*:\s+', line)
        ) > 2

    def _parse_timestamped(
        self, text: str, episode_id: str
    ) -> List[TranscriptSegment]:
        """Parse transcripts with [HH:MM:SS] timestamps."""
        segments = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = self.TIMESTAMP_PATTERN.match(line)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2))
                seconds = int(match.group(3))
                timestamp = hours * 3600 + minutes * 60 + seconds

                # Extract speaker and text after timestamp
                remainder = line[match.end():]
                speaker_match = re.match(r'^([A-Z][A-Z0-9_\s]*?):\s+(.+)$',
                                       remainder)

                if speaker_match:
                    speaker_name = speaker_match.group(1).strip()
                    text_content = speaker_match.group(2).strip()

                    if text_content:
                        speaker = Speaker(name=speaker_name, role="participant")
                        segment = TranscriptSegment(
                            speaker=speaker,
                            text=text_content,
                            start_time=float(timestamp),
                            end_time=float(timestamp),
                            episode_id=episode_id
                        )
                        segments.append(segment)

        return segments

    def _parse_labeled(
        self, text: str, episode_id: str
    ) -> List[TranscriptSegment]:
        """Parse transcripts with speaker labels but no timestamps."""
        segments = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = re.match(r'^([A-Z][A-Z0-9_\s]*?):\s+(.+)$', line)
            if match:
                speaker_name = match.group(1).strip()
                text_content = match.group(2).strip()

                if text_content:
                    speaker = Speaker(name=speaker_name, role="participant")
                    segment = TranscriptSegment(
                        speaker=speaker,
                        text=text_content,
                        start_time=None,
                        end_time=None,
                        episode_id=episode_id
                    )
                    segments.append(segment)

        return segments

    def _parse_unstructured(
        self,
        text: str,
        episode_id: str,
        default_speaker: Optional[Speaker] = None
    ) -> List[TranscriptSegment]:
        """Parse unstructured text as a single speaker."""
        if default_speaker is None:
            default_speaker = Speaker(name="Unknown Speaker", role="participant")

        # Split into sentences and create segments
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        segments = []

        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and len(sentence) > 5:
                segment = TranscriptSegment(
                    speaker=default_speaker,
                    text=sentence,
                    start_time=None,
                    end_time=None,
                    episode_id=episode_id
                )
                segments.append(segment)

        return segments


# ── ClaimExtractor ──────────────────────────────────────────────────────────

class ClaimExtractor:
    """
    Extracts atomic claims from transcript segments using Claude API or spaCy fallback.

    A claim is a single assertoric sentence that can be true or false,
    filtered to remove meta-discourse and social niceties.
    """

    # Patterns indicating meta-discourse or non-propositional content
    NON_PROPOSITIONAL_PATTERNS = [
        r'^\s*(i think|i believe|i feel|i guess|it seems|maybe|perhaps)',
        r'(let me|let\'s|we should|we could|can we|could we)\s+(move on|continue|wrap up|finish)',
        r'^\s*(thanks|thank you|great|thanks for|appreciate)',
        r'^\s*(so|anyway|alright|okay|you know|um|uh|uh|hmm)',
        r'^\s*(what|how|why|when|where|who)\s+(do|did|does)',  # Questions only
    ]

    FALLBACK_ASSERTORIC_PATTERNS = [
        r'\b(is|are|was|were|be)\b',
        r'\b(have|has|had)\b',
        r'\b(can|could|will|would|shall|should|may|might|must)\b',
        r'\b(exist|occur|happen|cause|require|depend)\b',
    ]

    def __init__(
        self,
        config: ExtractionConfig = None,
        logger_instance: Any = None,
        llm: LLMClient | None = None,
    ):
        """
        Initialize the claim extractor.

        Args:
            config: ExtractionConfig for tuning behavior
            logger_instance: Optional logger instance
        """
        self.config = config or ExtractionConfig()
        self.logger = logger_instance or logger
        self._llm: LLMClient | None = llm
        self.nlp = None

        from noosphere.config import get_settings

        try:
            if self._llm is None and get_settings().effective_llm_api_key():
                self._llm = llm_client_from_settings()
                self.logger.info("Initialized LLM client for extraction")
            elif self._llm is None:
                self.logger.warning("No LLM API key; will use fallback extraction mode")
        except Exception as e:
            self.logger.error("Failed to initialize LLM client", error=str(e))

        # Load spaCy for fallback
        try:
            self.nlp = spacy.load("en_core_web_sm")
            self.logger.info("Loaded spaCy English model")
        except OSError:
            self.logger.warning(
                "spaCy model not found; install with: "
                "python -m spacy download en_core_web_sm"
            )

    def extract(self, segments: List[TranscriptSegment]) -> List[Claim]:
        """
        Extract claims from a list of segments.

        Uses batch processing for API efficiency (5-10 segments per call).

        Args:
            segments: List of TranscriptSegment objects

        Returns:
            List of Claim objects
        """
        if not segments:
            return []

        self.logger.info(f"Extracting claims from {len(segments)} segments")

        claims = []
        if self._llm is not None:
            claims = self._extract_via_api(segments)
        else:
            self.logger.info(
                "No API client available; using spaCy fallback mode"
            )
            claims = self._extract_via_fallback(segments)

        self.logger.info(f"Extracted {len(claims)} claims")
        return claims

    def _extract_via_api(self, segments: List[TranscriptSegment]) -> List[Claim]:
        """Extract claims using Claude API with batching."""
        claims = []

        # Process in batches
        for batch_start in range(0, len(segments), self.config.batch_size):
            batch = segments[batch_start:batch_start + self.config.batch_size]

            try:
                batch_claims = self._call_claude_for_batch(batch)
                claims.extend(batch_claims)
            except Exception as e:
                self.logger.error(f"Error extracting batch: {e}")
                # Fall back to extracting individual segments
                for segment in batch:
                    try:
                        segment_claims = self._extract_single_segment(segment)
                        claims.extend(segment_claims)
                    except Exception as seg_error:
                        self.logger.error(
                            f"Error extracting segment from "
                            f"{segment.speaker.name}: {seg_error}"
                        )

        return claims

    def _call_claude_for_batch(
        self, segments: List[TranscriptSegment]
    ) -> List[Claim]:
        """Call Claude API to extract claims from a batch of segments."""
        segment_strs = []
        for i, seg in enumerate(segments):
            segment_strs.append(
                f"[Segment {i+1}] {seg.speaker.name}: {seg.text}"
            )

        prompt = f"""Extract atomic claims from these transcript segments.

Each claim should be:
- A single assertoric sentence (can be true or false)
- Attributed to the speaker
- Free of meta-discourse, social niceties, and questions
- Substantive and propositional

For each segment, output claims in JSON format:
{{"segment_index": N, "claims": ["claim 1", "claim 2", ...]}}

Output a JSON array of these objects. If a segment has no valid claims, use empty array.

Transcript segments:
{chr(10).join(segment_strs)}"""

        try:
            response_text = self._llm.complete(
                system="Extract claims as instructed. Output JSON only.",
                user=prompt,
                max_tokens=2048,
            )
            return self._parse_claude_response(response_text, segments)

        except Exception as e:
            self.logger.error(f"Claude API error: {e}")
            raise

    def _parse_claude_response(
        self,
        response_text: str,
        segments: List[TranscriptSegment]
    ) -> List[Claim]:
        """Parse Claude's JSON response into Claim objects."""
        import json

        claims = []

        # Extract JSON from response
        try:
            # Try to find JSON array in response
            start_idx = response_text.find('[')
            end_idx = response_text.rfind(']') + 1

            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                results = json.loads(json_str)

                for result in results:
                    segment_idx = result.get('segment_index', 0)
                    if 0 <= segment_idx < len(segments):
                        segment = segments[segment_idx]
                        for claim_text in result.get('claims', []):
                            if self._is_valid_claim(claim_text):
                                claim = Claim(
                                    text=claim_text.strip(),
                                    speaker=segment.speaker,
                                    episode_id=segment.episode_id,
                                    episode_date=date.today(),  # Will be set by ingester
                                    segment_context=segment.text,
                                    timestamp_seconds=segment.start_time,
                                    confidence=0.9
                                )
                                claims.append(claim)

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse Claude response JSON: {e}")

        return claims

    def _extract_single_segment(
        self, segment: TranscriptSegment
    ) -> List[Claim]:
        """Extract claims from a single segment via API."""
        return self._extract_via_api([segment])

    def _extract_via_fallback(
        self, segments: List[TranscriptSegment]
    ) -> List[Claim]:
        """
        Fallback extraction using spaCy sentence segmentation.

        Extracts sentences containing assertoric patterns.
        """
        if not self.nlp:
            self.logger.warning("spaCy not available; returning empty claims")
            return []

        claims = []

        for segment in segments:
            doc = self.nlp(segment.text)

            for sent in doc.sents:
                sent_text = sent.text.strip()

                # Check for assertoric patterns
                if self._has_assertoric_pattern(sent_text):
                    if self._is_valid_claim(sent_text):
                        claim = Claim(
                            text=sent_text,
                            speaker=segment.speaker,
                            episode_id=segment.episode_id,
                            episode_date=date.today(),
                            segment_context=segment.text,
                            timestamp_seconds=segment.start_time,
                            confidence=0.6  # Lower confidence for fallback
                        )
                        claims.append(claim)

        return claims

    def _is_valid_claim(self, text: str) -> bool:
        """Check if text is a valid claim (filters meta-discourse)."""
        text_lower = text.lower().strip()

        # Minimum length
        if len(text_lower) < self.config.min_claim_length:
            return False

        # Check for non-propositional patterns
        for pattern in self.NON_PROPOSITIONAL_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return False

        return True

    def _has_assertoric_pattern(self, text: str) -> bool:
        """Check if text contains assertoric verb patterns."""
        text_lower = text.lower()
        return any(
            re.search(pattern, text_lower)
            for pattern in self.FALLBACK_ASSERTORIC_PATTERNS
        )


# ── DisciplineClassifier ────────────────────────────────────────────────────

class DisciplineClassifier:
    """
    Classifies claims into relevant knowledge disciplines.

    Uses keyword-based matching with fallback to embedding similarity
    against discipline prototype sentences.
    """

    # Keywords for each discipline
    DISCIPLINE_KEYWORDS: Dict[Discipline, List[str]] = {
        Discipline.PHILOSOPHY: [
            'philosophy', 'ontology', 'metaphysics', 'epistemology',
            'consciousness', 'meaning', 'truth', 'reality', 'existence',
            'fundamental', 'principle', 'nature of'
        ],
        Discipline.PHYSICS: [
            'physics', 'quantum', 'relativity', 'entropy', 'energy',
            'momentum', 'force', 'particle', 'wave', 'thermodynamic',
            'space', 'time', 'dimension', 'molecule', 'atom'
        ],
        Discipline.AI: [
            'ai', 'artificial intelligence', 'machine learning', 'neural',
            'algorithm', 'training', 'model', 'deep learning', 'llm',
            'language model', 'gpt', 'transformer', 'embedding'
        ],
        Discipline.ENTREPRENEURSHIP: [
            'startup', 'founding', 'entrepreneur', 'venture', 'build',
            'product', 'market', 'growth', 'scale', 'customer',
            'business model', 'iterate', 'launch'
        ],
        Discipline.VC: [
            'venture capital', 'fundraising', 'investment', 'funding',
            'valuation', 'equity', 'term sheet', 'dilution', 'round',
            'cap table', 'investor', 'vc', 'seed', 'series'
        ],
        Discipline.ART: [
            'art', 'film', 'cinema', 'visual', 'aesthetic', 'creation',
            'design', 'beauty', 'composition', 'artistic', 'sculpture',
            'painting', 'director', 'cinematography'
        ],
        Discipline.LITERATURE: [
            'literature', 'writing', 'narrative', 'story', 'prose',
            'poetry', 'author', 'novel', 'text', 'meaning making',
            'language', 'metaphor', 'symbolism'
        ],
        Discipline.MATHEMATICS: [
            'mathematics', 'proof', 'theorem', 'equation', 'algebra',
            'geometry', 'calculus', 'logic', 'set theory', 'topology',
            'number', 'mathematical', 'compute'
        ],
        Discipline.ECONOMICS: [
            'economics', 'market', 'price', 'supply', 'demand',
            'monetary', 'inflation', 'gdp', 'economic', 'trade',
            'profit', 'revenue', 'capitalism', 'inefficiency'
        ],
        Discipline.HISTORY: [
            'history', 'historical', 'century', 'era', 'civilization',
            'revolution', 'empire', 'war', 'movement', 'past',
            'historical period', 'tradition', 'legacy'
        ],
        Discipline.EPISTEMOLOGY: [
            'epistemology', 'knowledge', 'knowing', 'justified',
            'belief', 'certainty', 'doubt', 'skepticism', 'evidence',
            'reason', 'empirical', 'induction'
        ],
        Discipline.ETHICS: [
            'ethics', 'moral', 'good', 'evil', 'virtue', 'responsibility',
            'ought', 'right', 'wrong', 'ethical', 'integrity',
            'character', 'consequence', 'duty'
        ],
        Discipline.POLITICAL_PHILOSOPHY: [
            'political', 'government', 'power', 'state', 'law',
            'society', 'rights', 'justice', 'social contract',
            'liberty', 'freedom', 'regulation', 'authority'
        ],
        Discipline.STRATEGY: [
            'strategy', 'strategic', 'competitive', 'advantage',
            'game theory', 'positioning', 'tactics', 'plan',
            'objective', 'execution', 'risk', 'decision making'
        ],
    }

    # Prototype sentences for embedding-based fallback
    DISCIPLINE_PROTOTYPES: Dict[Discipline, str] = {
        Discipline.PHILOSOPHY: "What is the fundamental nature of reality and existence?",
        Discipline.PHYSICS: "How do matter, energy, and forces interact in the universe?",
        Discipline.AI: "How can machines learn from data and make intelligent decisions?",
        Discipline.ENTREPRENEURSHIP: "How do you build a successful business from scratch?",
        Discipline.VC: "How should capital be allocated to maximize venture returns?",
        Discipline.ART: "What makes a work of art meaningful and beautiful?",
        Discipline.LITERATURE: "How does narrative language convey meaning and emotion?",
        Discipline.MATHEMATICS: "What are the abstract structures and logical proofs?",
        Discipline.ECONOMICS: "How do markets allocate resources and determine prices?",
        Discipline.HISTORY: "What patterns emerge in human civilization over time?",
        Discipline.EPISTEMOLOGY: "How do we know what we claim to know?",
        Discipline.ETHICS: "What principles should guide human action and conduct?",
        Discipline.POLITICAL_PHILOSOPHY: "How should societies organize power and distribute rights?",
        Discipline.STRATEGY: "How should one plan and execute to achieve objectives?",
    }

    def __init__(
        self,
        embedding_model: Optional[SentenceTransformer] = None,
        logger_instance: Any = None
    ):
        """
        Initialize the discipline classifier.

        Args:
            embedding_model: Optional SentenceTransformer for similarity matching
            logger_instance: Optional logger instance
        """
        self.logger = logger_instance or logger
        self.embedding_model = embedding_model
        self._prototype_embeddings = None

    def classify(self, claim: Claim) -> List[Discipline]:
        """
        Classify a claim into one or more disciplines.

        Uses keyword matching first, then embedding similarity for borderline cases.

        Args:
            claim: Claim object to classify

        Returns:
            List of relevant Discipline enums
        """
        disciplines = []
        text_lower = claim.text.lower()

        # Keyword-based matching
        for discipline, keywords in self.DISCIPLINE_KEYWORDS.items():
            if any(keyword in text_lower for keyword in keywords):
                disciplines.append(discipline)

        # If embedding model is available and we have matches, refine with embeddings
        if self.embedding_model and disciplines:
            disciplines = self._refine_with_embeddings(claim, disciplines)

        return disciplines

    def _refine_with_embeddings(
        self,
        claim: Claim,
        candidate_disciplines: List[Discipline]
    ) -> List[Discipline]:
        """Refine discipline selection using embedding similarity."""
        try:
            claim_embedding = self.embedding_model.encode(
                claim.text, convert_to_tensor=False
            )

            # Compute similarity to prototypes
            similarities = {}
            for discipline in candidate_disciplines:
                prototype = self.DISCIPLINE_PROTOTYPES[discipline]
                prototype_embedding = self.embedding_model.encode(
                    prototype, convert_to_tensor=False
                )

                # Cosine similarity
                from sklearn.metrics.pairwise import cosine_similarity
                sim = cosine_similarity(
                    [claim_embedding],
                    [prototype_embedding]
                )[0][0]
                similarities[discipline] = sim

            # Keep only high-similarity disciplines
            return [
                d for d, sim in similarities.items()
                if sim > 0.5
            ]

        except Exception as e:
            self.logger.warning(
                f"Embedding refinement failed: {e}; keeping keyword matches"
            )
            return candidate_disciplines


# ── TranscriptIngester ──────────────────────────────────────────────────────

class TranscriptIngester:
    """
    Main orchestrator for the transcript ingestion pipeline.

    Parses transcripts, extracts claims, generates embeddings, and tags
    disciplines to produce enriched Claim objects and Episode metadata.
    """

    def __init__(
        self,
        extraction_config: ExtractionConfig = None,
        logger_instance: Any = None
    ):
        """
        Initialize the ingester.

        Args:
            extraction_config: Optional ExtractionConfig
            logger_instance: Optional logger instance
        """
        self.logger = logger_instance or logger
        self.extraction_config = extraction_config or ExtractionConfig()

        # Initialize components
        self.parser = TranscriptParser(logger_instance=self.logger)
        self.claim_extractor = ClaimExtractor(
            config=self.extraction_config,
            logger_instance=self.logger
        )

        # Load embedding model
        try:
            from noosphere.config import get_settings

            emb_name = get_settings().embedding_model_name
            device = get_settings().embedding_device or None
            kwargs: dict[str, Any] = {}
            if device:
                kwargs["device"] = device
            self.embedding_model = SentenceTransformer(emb_name, **kwargs)
            self.logger.info("Loaded SBERT embedding model", model=emb_name)
        except Exception as e:
            self.logger.error(f"Failed to load embedding model: {e}")
            self.embedding_model = None

        # Initialize discipline classifier
        self.discipline_classifier = DisciplineClassifier(
            embedding_model=self.embedding_model,
            logger_instance=self.logger
        )

    def ingest(
        self,
        transcript_path: str,
        episode_number: int,
        episode_date: date,
        episode_title: str = "",
        speaker_list: Optional[List[Speaker]] = None
    ) -> Tuple[List[Claim], Episode]:
        """
        Full ingestion pipeline: parse, extract, embed, classify.

        Args:
            transcript_path: Path to transcript file
            episode_number: Episode number
            episode_date: Date of episode
            episode_title: Optional episode title
            speaker_list: Optional list of known speakers

        Returns:
            Tuple of (List[Claim], Episode metadata)
        """
        self.logger.info(
            f"Starting ingestion of episode {episode_number} "
            f"from {transcript_path}"
        )

        episode_id = f"ep-{episode_number}"

        # 1. Read transcript
        try:
            transcript_text = self._read_transcript(transcript_path)
        except Exception as e:
            self.logger.error(f"Failed to read transcript: {e}")
            raise

        # 2. Parse into segments
        default_speaker = speaker_list[0] if speaker_list else None
        segments = self.parser.parse(
            transcript_text,
            episode_id,
            default_speaker
        )

        if not segments:
            self.logger.warning("No segments parsed from transcript")
            return [], Episode(
                number=episode_number,
                date=episode_date,
                title=episode_title,
                transcript_path=transcript_path,
                speakers=speaker_list or [],
                claim_count=0
            )

        # 3. Extract claims
        claims = self.claim_extractor.extract(segments)

        # 4. Enrich claims: embeddings and disciplines
        claims = self._enrich_claims(
            claims, episode_date, episode_number
        )

        # 5. Build episode metadata
        episode = Episode(
            id=episode_id,
            number=episode_number,
            date=episode_date,
            title=episode_title,
            transcript_path=transcript_path,
            speakers=speaker_list or [],
            claim_count=len(claims)
        )

        self.logger.info(
            f"Ingestion complete: {len(claims)} claims extracted"
        )
        return claims, episode

    def _read_transcript(self, transcript_path: str) -> str:
        """Read transcript from file."""
        path = Path(transcript_path)

        if not path.exists():
            raise FileNotFoundError(f"Transcript not found: {transcript_path}")

        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def _enrich_claims(
        self,
        claims: List[Claim],
        episode_date: date,
        episode_number: int
    ) -> List[Claim]:
        """
        Enrich claims with embeddings and discipline tags.

        Args:
            claims: List of extracted claims
            episode_date: Date to assign to claims
            episode_number: Episode number for logging

        Returns:
            Enriched claims
        """
        self.logger.info(f"Enriching {len(claims)} claims")

        from noosphere.mitigations.embedding_text import normalize_for_embedding
        from noosphere.mitigations.ingestion_guard import apply_ingestion_flags_to_claim

        for claim in claims:
            # Set episode date
            claim.episode_date = episode_date

            apply_ingestion_flags_to_claim(claim)
            embed_text = normalize_for_embedding(claim.text)

            # Generate embedding
            if self.embedding_model:
                try:
                    embedding = self.embedding_model.encode(
                        embed_text,
                        convert_to_tensor=False
                    ).tolist()
                    claim.embedding = embedding
                except Exception as e:
                    self.logger.warning(
                        f"Failed to generate embedding for claim: {e}"
                    )

            # Classify disciplines
            try:
                disciplines = self.discipline_classifier.classify(claim)
                claim.disciplines = disciplines
            except Exception as e:
                self.logger.warning(
                    f"Failed to classify discipline for claim: {e}"
                )

        return claims


# Markdown / plain-text / structured transcript artifacts (see ingest_artifacts).
from noosphere.ingest_artifacts import (  # noqa: E402
    ingest_dialectic_session_jsonl,
    ingest_markdown,
    ingest_text,
    ingest_transcript,
)

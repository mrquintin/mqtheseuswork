"""
Founder Attribution and Analysis for Noosphere.

The communal brain is composed of individual minds. This module tracks
each founder's intellectual identity, their distinctive contributions
to the methodological graph, and the dynamics of convergence and
divergence among them.

Key architectural principle: every claim in the system is attributed
to a specific founder. Principles (the distilled, stable nodes in the
graph) carry weighted contribution records showing which founders
shaped them and how much. This enables:

  1. Per-founder intellectual profiles and evolution tracking
  2. Convergence/divergence analysis (are founders aligning or splitting?)
  3. Weighted principle formation (a principle is stronger when multiple
     founders independently converge on it)
  4. Written input ingestion with proper author labeling
  5. Individual methodological orientation scores

The FounderRegistry is the central store. It persists alongside the
Ontology Graph and Conclusions Registry.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple

import numpy as np

from noosphere.models import (
    FounderProfile,
    FounderIntellectualView,
    Speaker,
    Claim,
    Principle,
    Discipline,
    InputSource,
    InputSourceType,
    TemporalSnapshot,
)

from noosphere.observability import get_logger

logger = get_logger(__name__)


# ── Founder Registry ────────────────────────────────────────────────────────

class FounderRegistry:
    """
    Persistent registry of all Theseus founders.

    Maps Speaker objects (transient, per-episode) to stable FounderProfiles.
    Handles name normalisation, profile creation, and persistence.
    """

    def __init__(self, data_path: str = "founders_registry.json"):
        self.data_path = Path(data_path)
        self.founders: Dict[str, FounderProfile] = {}
        self._name_index: Dict[str, str] = {}  # normalised_name → founder_id
        self.load()

    # ── Registration ────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        role: str = "founder",
        primary_domains: Optional[List[Discipline]] = None,
        speaker_id: str = "",
    ) -> FounderProfile:
        """
        Register a founder or return existing profile if already known.

        Name matching is case-insensitive and whitespace-normalised.
        """
        norm = self._normalise_name(name)
        if norm in self._name_index:
            existing = self.founders[self._name_index[norm]]
            # Update speaker_id if newly provided
            if speaker_id and not existing.speaker_id:
                existing.speaker_id = speaker_id
                existing.updated_at = datetime.now()
            return existing

        profile = FounderProfile(
            name=name,
            speaker_id=speaker_id,
            role=role,
            primary_domains=primary_domains or [],
        )
        self.founders[profile.id] = profile
        self._name_index[norm] = profile.id
        logger.info(f"Registered founder: {name} ({profile.id[:8]}...)")
        return profile

    def resolve_speaker(self, speaker: Speaker) -> Optional[FounderProfile]:
        """
        Find the FounderProfile matching a Speaker object.

        Tries speaker_id first, then name matching.
        """
        # Try direct ID match
        for fp in self.founders.values():
            if fp.speaker_id == speaker.id:
                return fp

        # Try name match
        norm = self._normalise_name(speaker.name)
        if norm in self._name_index:
            fp = self.founders[self._name_index[norm]]
            # Bind the speaker_id for future lookups
            if not fp.speaker_id:
                fp.speaker_id = speaker.id
            return fp

        # Auto-register if role is founder
        if speaker.role == "founder":
            return self.register(
                name=speaker.name,
                role=speaker.role,
                speaker_id=speaker.id,
            )

        return None

    def get_founder(self, founder_id: str) -> Optional[FounderProfile]:
        return self.founders.get(founder_id)

    def get_by_name(self, name: str) -> Optional[FounderProfile]:
        norm = self._normalise_name(name)
        fid = self._name_index.get(norm)
        return self.founders.get(fid) if fid else None

    def all_founders(self) -> List[FounderProfile]:
        return list(self.founders.values())

    # ── Profile Updates ─────────────────────────────────────────────────

    def record_claims(
        self,
        founder_id: str,
        claims: List[Claim],
        source_type: InputSourceType = InputSourceType.TRANSCRIPT,
        episode_date: Optional[date] = None,
    ) -> None:
        """
        Update a founder's profile after new claims are ingested.

        Increments counts, updates activity dates, recalculates
        methodological orientation.
        """
        fp = self.founders.get(founder_id)
        if not fp:
            logger.warning(f"Founder {founder_id} not found")
            return

        fp.claim_count += len(claims)

        if source_type == InputSourceType.WRITTEN:
            fp.written_input_count += 1

        # Update activity dates
        if episode_date:
            if fp.first_appearance is None or episode_date < fp.first_appearance:
                fp.first_appearance = episode_date
            if fp.last_active is None or episode_date > fp.last_active:
                fp.last_active = episode_date

        # Recalculate embedding centroid
        embeddings = [c.embedding for c in claims if c.embedding]
        if embeddings:
            new_centroid = np.mean(embeddings, axis=0).tolist()
            if fp.embedding_centroid:
                # Running average weighted by claim count
                old_weight = (fp.claim_count - len(claims)) / fp.claim_count
                new_weight = len(claims) / fp.claim_count
                fp.embedding_centroid = (
                    np.array(fp.embedding_centroid) * old_weight
                    + np.array(new_centroid) * new_weight
                ).tolist()
            else:
                fp.embedding_centroid = new_centroid

        fp.updated_at = datetime.now()

    def record_methodology_counts(
        self,
        founder_id: str,
        methodological: int,
        substantive: int,
    ) -> None:
        """
        Update per-founder methodology/substance split after classification.
        """
        fp = self.founders.get(founder_id)
        if not fp:
            return

        fp.methodological_claim_count += methodological
        fp.substantive_claim_count += substantive

        total = fp.methodological_claim_count + fp.substantive_claim_count
        if total > 0:
            fp.methodological_orientation = fp.methodological_claim_count / total

        fp.updated_at = datetime.now()

    def record_principle_contribution(
        self, founder_id: str, principle_id: str
    ) -> None:
        """Record that a founder contributed to a principle."""
        fp = self.founders.get(founder_id)
        if fp and principle_id not in fp.principle_ids:
            fp.principle_ids.append(principle_id)
            fp.updated_at = datetime.now()

    # ── Persistence ─────────────────────────────────────────────────────

    def save(self) -> None:
        data = {
            "founders": {
                fid: fp.model_dump(mode="json")
                for fid, fp in self.founders.items()
            },
            "name_index": self._name_index,
            "saved_at": datetime.now().isoformat(),
        }
        with open(self.data_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def load(self) -> None:
        if not self.data_path.exists():
            return
        try:
            with open(self.data_path, "r") as f:
                data = json.load(f)
            for fid, fdata in data.get("founders", {}).items():
                self.founders[fid] = FounderProfile(**fdata)
            self._name_index = data.get("name_index", {})
            logger.info(f"Loaded {len(self.founders)} founder profiles")
        except Exception as e:
            logger.error(f"Failed to load founder registry: {e}")

    # ── Internal ────────────────────────────────────────────────────────

    @staticmethod
    def _normalise_name(name: str) -> str:
        return " ".join(name.strip().lower().split())


# ── Input Source Registry ───────────────────────────────────────────────────

class InputSourceRegistry:
    """
    Tracks all material that has entered the system.

    Each transcript episode and each written document gets an InputSource
    record. This enables full provenance tracing: for any claim in the
    graph, you can determine where it came from and who authored it.
    """

    def __init__(self, data_path: str = "input_sources.json"):
        self.data_path = Path(data_path)
        self.sources: Dict[str, InputSource] = {}
        self.load()

    def register_transcript(
        self,
        episode_id: str,
        title: str,
        episode_date: date,
        file_path: str = "",
    ) -> InputSource:
        """Register a transcript episode as an input source."""
        source = InputSource(
            source_type=InputSourceType.TRANSCRIPT,
            title=title,
            episode_id=episode_id,
            date=episode_date,
            file_path=file_path,
        )
        self.sources[source.id] = source
        return source

    def register_written_input(
        self,
        title: str,
        author_id: str,
        author_name: str,
        file_path: str = "",
        input_date: Optional[date] = None,
        description: str = "",
        source_type: InputSourceType = InputSourceType.WRITTEN,
    ) -> InputSource:
        """Register a written document (essay, memo, notes) as an input source."""
        source = InputSource(
            source_type=source_type,
            title=title,
            author_id=author_id,
            author_name=author_name,
            file_path=file_path,
            date=input_date or date.today(),
            description=description,
        )
        self.sources[source.id] = source
        return source

    def get_source(self, source_id: str) -> Optional[InputSource]:
        return self.sources.get(source_id)

    def get_by_episode(self, episode_id: str) -> Optional[InputSource]:
        for s in self.sources.values():
            if s.episode_id == episode_id:
                return s
        return None

    def get_by_author(self, author_id: str) -> List[InputSource]:
        return [
            s for s in self.sources.values()
            if s.author_id == author_id
        ]

    def save(self) -> None:
        data = {
            "sources": {
                sid: s.model_dump(mode="json")
                for sid, s in self.sources.items()
            },
            "saved_at": datetime.now().isoformat(),
        }
        with open(self.data_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def load(self) -> None:
        if not self.data_path.exists():
            return
        try:
            with open(self.data_path, "r") as f:
                data = json.load(f)
            for sid, sdata in data.get("sources", {}).items():
                self.sources[sid] = InputSource(**sdata)
            logger.info(f"Loaded {len(self.sources)} input sources")
        except Exception as e:
            logger.error(f"Failed to load input sources: {e}")


# ── Founder Analyser ────────────────────────────────────────────────────────

class FounderAnalyser:
    """
    Analytical engine for inter-founder dynamics.

    Computes convergence, divergence, influence asymmetries, and
    per-founder intellectual evolution. Operates over the FounderRegistry,
    the OntologyGraph, and claim-level data.
    """

    def __init__(
        self,
        registry: FounderRegistry,
        embedding_model=None,
    ):
        self.registry = registry
        self.model = embedding_model

    # ── Convergence / Divergence ────────────────────────────────────────

    def pairwise_similarity(self) -> Dict[Tuple[str, str], float]:
        """
        Compute pairwise cosine similarity between all founder centroids.

        Returns:
            Dict mapping (founder_id_a, founder_id_b) → cosine similarity.
            Only founders with computed centroids are included.
        """
        founders = [
            f for f in self.registry.all_founders()
            if f.embedding_centroid is not None
        ]
        if len(founders) < 2:
            return {}

        results = {}
        for i, a in enumerate(founders):
            for b in founders[i + 1:]:
                vec_a = np.array(a.embedding_centroid)
                vec_b = np.array(b.embedding_centroid)
                cos_sim = float(
                    np.dot(vec_a, vec_b)
                    / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b) + 1e-9)
                )
                results[(a.id, b.id)] = cos_sim

        return results

    def convergence_report(self) -> Dict[str, Any]:
        """
        Comprehensive convergence/divergence analysis across all founders.

        Returns a report with:
          - Overall convergence score (mean pairwise similarity)
          - Most aligned pair
          - Most divergent pair
          - Per-founder isolation score (how far from the group centroid)
        """
        sims = self.pairwise_similarity()
        if not sims:
            return {"status": "insufficient_data", "founders": len(self.registry.all_founders())}

        similarities = list(sims.values())
        overall = float(np.mean(similarities))

        most_aligned = max(sims.items(), key=lambda x: x[1])
        most_divergent = min(sims.items(), key=lambda x: x[1])

        # Group centroid
        centroids = [
            np.array(f.embedding_centroid)
            for f in self.registry.all_founders()
            if f.embedding_centroid is not None
        ]
        if centroids:
            group_centroid = np.mean(centroids, axis=0)
        else:
            group_centroid = None

        # Per-founder isolation
        isolation = {}
        if group_centroid is not None:
            for f in self.registry.all_founders():
                if f.embedding_centroid is not None:
                    vec = np.array(f.embedding_centroid)
                    cos_sim = float(
                        np.dot(vec, group_centroid)
                        / (np.linalg.norm(vec) * np.linalg.norm(group_centroid) + 1e-9)
                    )
                    isolation[f.name] = round(1.0 - cos_sim, 4)

        return {
            "overall_convergence": round(overall, 4),
            "most_aligned": {
                "pair": (
                    self.registry.get_founder(most_aligned[0][0]).name,
                    self.registry.get_founder(most_aligned[0][1]).name,
                ),
                "similarity": round(most_aligned[1], 4),
            },
            "most_divergent": {
                "pair": (
                    self.registry.get_founder(most_divergent[0][0]).name,
                    self.registry.get_founder(most_divergent[0][1]).name,
                ),
                "similarity": round(most_divergent[1], 4),
            },
            "per_founder_isolation": isolation,
            "num_founders": len(self.registry.all_founders()),
        }

    # ── Principle Contribution Analysis ─────────────────────────────────

    def principle_authorship_report(
        self,
        principles: Dict[str, Principle],
    ) -> Dict[str, Any]:
        """
        Analyse how principles are distributed across founders.

        Reports:
          - Per-founder: which principles they shaped, total influence weight
          - Per-principle: which founders contributed, concentration (Herfindahl)
          - Collaborative vs. individual principles
        """
        founder_influence: Dict[str, float] = defaultdict(float)
        founder_principles: Dict[str, List[str]] = defaultdict(list)
        principle_concentration: Dict[str, float] = {}
        collaborative = []
        individual = []

        for pid, p in principles.items():
            contribs = p.founder_contributions
            if not contribs:
                continue

            # Per-founder aggregation
            for fid, weight in contribs.items():
                founder_influence[fid] += weight
                founder_principles[fid].append(pid)

            # Herfindahl index: sum of squared shares
            # HHI = 1.0 means one founder dominates; 1/N means equal split
            shares = list(contribs.values())
            total = sum(shares)
            if total > 0:
                normalised = [s / total for s in shares]
                hhi = sum(s ** 2 for s in normalised)
                principle_concentration[pid] = round(hhi, 4)

                if len(contribs) > 1 and hhi < 0.5:
                    collaborative.append(pid)
                else:
                    individual.append(pid)

        # Build per-founder report
        per_founder = {}
        for fid in founder_influence:
            fp = self.registry.get_founder(fid)
            name = fp.name if fp else fid[:8]
            per_founder[name] = {
                "total_influence": round(founder_influence[fid], 3),
                "principle_count": len(founder_principles[fid]),
                "methodological_orientation": round(
                    fp.methodological_orientation, 3
                ) if fp else None,
            }

        return {
            "per_founder": per_founder,
            "principle_concentration": principle_concentration,
            "collaborative_principles": len(collaborative),
            "individual_principles": len(individual),
            "total_principles": len(principles),
        }

    # ── Per-Founder Profile Summaries ───────────────────────────────────

    def founder_profile_summary(self, founder_id: str) -> Dict[str, Any]:
        """Detailed summary of a single founder's intellectual profile."""
        fp = self.registry.get_founder(founder_id)
        if not fp:
            return {"error": f"Founder {founder_id} not found"}

        total_claims = fp.methodological_claim_count + fp.substantive_claim_count

        return {
            "name": fp.name,
            "id": fp.id,
            "role": fp.role,
            "primary_domains": [d.value for d in fp.primary_domains],
            "claim_count": fp.claim_count,
            "written_inputs": fp.written_input_count,
            "methodological_claims": fp.methodological_claim_count,
            "substantive_claims": fp.substantive_claim_count,
            "methodological_orientation": round(fp.methodological_orientation, 3),
            "principles_shaped": len(fp.principle_ids),
            "avg_conviction": round(fp.avg_conviction_score, 3),
            "first_appearance": fp.first_appearance.isoformat() if fp.first_appearance else None,
            "last_active": fp.last_active.isoformat() if fp.last_active else None,
            "has_centroid": fp.embedding_centroid is not None,
        }

    def all_profiles_summary(self) -> List[Dict[str, Any]]:
        """Summary of all registered founders."""
        return [
            self.founder_profile_summary(fid)
            for fid in self.registry.founders
        ]

    # ── Method Preference Analysis ──────────────────────────────────────

    def method_preferences(
        self, claims_by_founder: Dict[str, List[Claim]]
    ) -> Dict[str, Dict[str, int]]:
        """
        For each founder, compute domain distribution of their claims.

        Returns:
            Dict[founder_name, Dict[discipline_name, count]]
        """
        result = {}
        for fid, claims in claims_by_founder.items():
            fp = self.registry.get_founder(fid)
            name = fp.name if fp else fid[:8]
            domain_counts: Dict[str, int] = defaultdict(int)
            for c in claims:
                for d in c.disciplines:
                    domain_counts[d.value] += 1
            result[name] = dict(
                sorted(domain_counts.items(), key=lambda x: -x[1])
            )
        return result


# ── Written Input Processor ─────────────────────────────────────────────────

class WrittenInputProcessor:
    """
    Handles ingestion of written documents (essays, memos, research notes).

    Unlike transcripts, written inputs have a single unambiguous author.
    The processor reads the document, extracts claims using the same
    ClaimExtractor pipeline, labels every claim with the author's
    FounderProfile, and returns enriched claims ready for the orchestrator.
    """

    def __init__(
        self,
        founder_registry: FounderRegistry,
        source_registry: InputSourceRegistry,
        claim_extractor=None,
        embedding_model=None,
        logger_instance=None,
    ):
        self.founder_registry = founder_registry
        self.source_registry = source_registry
        self._claim_extractor = claim_extractor
        self._embedding_model = embedding_model
        self.logger = logger_instance or logger

    @property
    def claim_extractor(self):
        if self._claim_extractor is None:
            from noosphere.ingester import ClaimExtractor, ExtractionConfig
            self._claim_extractor = ClaimExtractor(
                config=ExtractionConfig(),
                logger_instance=self.logger,
            )
        return self._claim_extractor

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            from sentence_transformers import SentenceTransformer

            from noosphere.config import get_settings

            s = get_settings()
            kwargs: dict[str, Any] = {}
            if s.embedding_device:
                kwargs["device"] = s.embedding_device
            self._embedding_model = SentenceTransformer(
                s.embedding_model_name, **kwargs
            )
        return self._embedding_model

    def ingest_written_input(
        self,
        file_path: str,
        author_name: str,
        title: str = "",
        input_date: Optional[date] = None,
        description: str = "",
        source_type: InputSourceType = InputSourceType.WRITTEN,
    ) -> Tuple[List[Claim], InputSource]:
        """
        Ingest a written document from a specific founder.

        The document is read, claims are extracted with Claude, and every
        claim is labeled with the author's FounderProfile and InputSource.

        Args:
            file_path: Path to the document (.txt, .md, .pdf, etc.)
            author_name: Name of the founder who wrote it
            title: Document title
            input_date: When it was written (defaults to today)
            description: Brief description of the document
            source_type: WRITTEN, ANNOTATION, or EXTERNAL

        Returns:
            Tuple of (List[Claim], InputSource)
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {path}")

        self.logger.info(f"Ingesting written input: {title or path.name} by {author_name}")

        # Resolve or register the founder
        founder = self.founder_registry.register(name=author_name)

        # Register the input source
        source = self.source_registry.register_written_input(
            title=title or path.stem,
            author_id=founder.id,
            author_name=author_name,
            file_path=str(path),
            input_date=input_date,
            description=description,
            source_type=source_type,
        )

        # Read the document
        text = self._read_document(path)

        # Convert to transcript segments for the claim extractor
        # Written inputs are treated as a single long segment from one speaker
        from noosphere.models import TranscriptSegment
        speaker = Speaker(name=author_name, role="founder", id=founder.speaker_id or str(founder.id))
        segments = self._split_into_segments(text, speaker, source.id)

        # Extract claims
        claims = self.claim_extractor.extract(segments)

        # Enrich claims with author attribution and embeddings
        actual_date = input_date or date.today()
        enriched = []
        for claim in claims:
            claim.founder_id = founder.id
            claim.source_type = source_type
            claim.source_id = source.id
            claim.episode_id = f"written_{source.id[:8]}"
            claim.episode_date = actual_date

            # Generate embedding
            if self._embedding_model or self.embedding_model:
                try:
                    claim.embedding = self.embedding_model.encode(claim.text).tolist()
                except Exception as e:
                    self.logger.warning(f"Embedding failed for claim: {e}")

            enriched.append(claim)

        # Update founder profile
        self.founder_registry.record_claims(
            founder_id=founder.id,
            claims=enriched,
            source_type=source_type,
            episode_date=actual_date,
        )

        self.logger.info(
            f"Extracted {len(enriched)} claims from {title or path.name} by {author_name}"
        )

        return enriched, source

    def _read_document(self, path: Path) -> str:
        """Read a document file. Supports .txt, .md, and plain text."""
        suffix = path.suffix.lower()

        if suffix in (".txt", ".md", ".text", ".markdown"):
            return path.read_text(encoding="utf-8")

        elif suffix == ".pdf":
            # Attempt PDF extraction
            try:
                import subprocess
                result = subprocess.run(
                    ["pdftotext", str(path), "-"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    return result.stdout
            except Exception:
                pass

            # Fallback: try pypdf
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                return "\n".join(page.extract_text() or "" for page in reader.pages)
            except ImportError:
                raise ImportError(
                    "PDF reading requires 'pypdf'. Install with: pip install pypdf"
                )

        elif suffix in (".docx",):
            try:
                from docx import Document
                doc = Document(str(path))
                return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except ImportError:
                raise ImportError(
                    "DOCX reading requires 'python-docx'. Install with: pip install python-docx"
                )

        else:
            # Try reading as plain text
            return path.read_text(encoding="utf-8")

    def _split_into_segments(
        self,
        text: str,
        speaker: Speaker,
        source_id: str,
    ) -> List[TranscriptSegment]:
        """
        Split written text into manageable segments for claim extraction.

        Written text is split on paragraph boundaries. Segments shorter
        than 50 characters are merged with the next one.
        """
        from noosphere.models import TranscriptSegment

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        # Merge short paragraphs
        merged = []
        buffer = ""
        for para in paragraphs:
            if buffer:
                buffer += "\n\n" + para
            else:
                buffer = para

            if len(buffer) >= 200:  # Minimum segment length
                merged.append(buffer)
                buffer = ""

        if buffer:
            if merged:
                merged[-1] += "\n\n" + buffer
            else:
                merged.append(buffer)

        return [
            TranscriptSegment(
                speaker=speaker,
                text=seg,
                episode_id=f"written_{source_id[:8]}",
            )
            for seg in merged
        ]


# ── Per-founder intellectual view (Phase 4) ─────────────────────────────────


def _normalise_speaker(n: str) -> str:
    return " ".join(n.lower().split())


def compute_founder_intellectual_view(
    *,
    founder: FounderProfile,
    claims: List[Claim],
    topic_for_claim: Any,
    drift_events: Optional[List[Any]] = None,
) -> FounderIntellectualView:
    """
    Aggregate positions by topic, drift hits, cross-founder tension, sole-dissenter topics.

    ``topic_for_claim`` is ``Callable[[Claim], Optional[str]]`` (e.g. store.get_topic_id_for_claim).
    ``drift_events`` is a list of ``DriftEvent``-like objects with ``author_topic_key`` / ``notes``.
    """
    drift_events = drift_events or []
    name_key = _normalise_speaker(founder.name)
    positions: Dict[str, str] = {}
    topic_claims: Dict[str, List[Claim]] = defaultdict(list)
    for c in claims:
        if _normalise_speaker(c.speaker.name) != name_key:
            continue
        tid = topic_for_claim(c) if callable(topic_for_claim) else None
        if not tid:
            tid = "_untagged"
        topic_claims[tid].append(c)
    for tid, lst in topic_claims.items():
        snippet = lst[-1].text[:240].replace("\n", " ")
        positions[tid] = snippet

    drift_ids: List[str] = []
    for ev in drift_events:
        key = getattr(ev, "author_topic_key", "") or getattr(ev, "notes", "")
        if name_key in _normalise_speaker(str(key)):
            drift_ids.append(getattr(ev, "id", ""))

    edges: List[str] = []
    my_claims = [c for c in claims if _normalise_speaker(c.speaker.name) == name_key]
    others = [c for c in claims if _normalise_speaker(c.speaker.name) != name_key]
    import numpy as np

    for a in my_claims[:40]:
        if not a.embedding:
            continue
        va = np.asarray(a.embedding, dtype=float)
        va = va / (np.linalg.norm(va) + 1e-9)
        for b in others[:80]:
            if not b.embedding:
                continue
            vb = np.asarray(b.embedding, dtype=float)
            vb = vb / (np.linalg.norm(vb) + 1e-9)
            if va.shape != vb.shape:
                continue
            if float(np.dot(va, vb)) < -0.15:
                edges.append(f"{a.id}|{b.id}")

    sole_topics: List[str] = []
    for tid, lst in topic_claims.items():
        if tid == "_untagged":
            continue
        authors = { _normalise_speaker(c.speaker.name) for c in claims if (topic_for_claim(c) if callable(topic_for_claim) else None) == tid }
        if len(authors) > 1 and _normalise_speaker(founder.name) in authors:
            others_t = authors - { _normalise_speaker(founder.name) }
            if not others_t:
                continue
            my_cent = np.mean([np.asarray(c.embedding, dtype=float) for c in lst if c.embedding], axis=0)
            o_vecs = [
                np.asarray(c.embedding, dtype=float)
                for c in claims
                if (topic_for_claim(c) if callable(topic_for_claim) else None) == tid
                and _normalise_speaker(c.speaker.name) in others_t
                and c.embedding
            ]
            if not len(o_vecs):
                continue
            oc = np.mean(o_vecs, axis=0)
            my_cent = my_cent / (np.linalg.norm(my_cent) + 1e-9)
            oc = oc / (np.linalg.norm(oc) + 1e-9)
            if float(np.dot(my_cent, oc)) < 0.2:
                sole_topics.append(tid)

    return FounderIntellectualView(
        founder_id=founder.id,
        founder_name=founder.name,
        positions_by_topic=positions,
        drift_event_ids=[x for x in drift_ids if x],
        cross_founder_contradiction_edges=edges[:50],
        sole_dissenter_topics=sole_topics,
    )

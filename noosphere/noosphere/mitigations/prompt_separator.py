"""
Pre-processing module that identifies and separates prompt/question
sections from founder response sections in uploaded text.

Defense-in-depth complement to the LLM-side author-attribution filtering
in `claim_extractor.py`: even with the extractor's per-claim
is_author_assertion flag, ambiguous rhetorical questions or embedded
quotes can sneak through. This module runs BEFORE extraction and either
strips prompt-shaped paragraphs or tags them so the extractor gets fewer
opportunities to misattribute.

Heuristics first (cheap, deterministic); a short LLM call is used only
when the heuristic confidence is low. The confidence score is returned
so upstream callers can log it and, if desired, bail out to "treat
everything as founder content" in the very-low-confidence case.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from noosphere.observability import get_logger

logger = get_logger(__name__)


# Q&A prefix markers. Matched case-insensitively at the start of a line.
# The "author" side is captured by the presence of "A:" / "Answer:" /
# "Response:" OR by the absence of any prompt prefix in a block that
# follows a prompt-prefixed block.
_PROMPT_PREFIX = re.compile(
    r"^\s*(?:\*\*)?\s*(?:Q|Question|Prompt|Interviewer|Host)\s*[:.\-]",
    flags=re.IGNORECASE,
)
_RESPONSE_PREFIX = re.compile(
    r"^\s*(?:\*\*)?\s*(?:A|Answer|Response|Founder)\s*[:.\-]",
    flags=re.IGNORECASE,
)
_SPEAKER_LINE = re.compile(r"^\s*([A-Z][A-Za-z .\-]{1,40})\s*:\s", flags=re.MULTILINE)

# Interrogative openers (used as a weak signal that a paragraph is a
# question). Paragraphs that are a single short sentence ending with ?
# are high-signal; long paragraphs that happen to contain a question
# mark are low-signal (they're likely the author posing a rhetorical
# question they then answer).
_INTERROGATIVE_OPENER = re.compile(
    r"^\s*(?:why|what|when|where|who|whom|which|how|is|are|does|do|did|can|could|"
    r"should|would|will|have|has|had|isn'?t|aren'?t|don'?t|doesn'?t|shouldn'?t|"
    r"wouldn'?t)\b",
    flags=re.IGNORECASE,
)


@dataclass
class SeparatedContent:
    """Result of prompt separation."""
    founder_sections: list[str] = field(default_factory=list)
    prompt_sections: list[str] = field(default_factory=list)
    confidence: float = 0.0  # Heuristic/LLM agreement 0..1

    @property
    def founder_text(self) -> str:
        return "\n\n".join(self.founder_sections)

    @property
    def prompt_text(self) -> str:
        return "\n\n".join(self.prompt_sections)


class PromptSeparator:
    """Identifies prompt/question sections and separates them from
    founder-authored content.

    Parameters
    ----------
    founder_names:
        Names that identify the founder in speaker-labelled transcripts.
        Case-insensitive substring matches. Typical usage: pass the
        founder's name + common aliases ("Jane", "Jane Smith"). If left
        empty the separator falls back to "first speaker wins" for
        transcripts, which is correct most of the time but flips if the
        interviewer speaks first.
    llm:
        Optional LLM client for the ambiguous-case fallback. When None
        (default), the separator skips the LLM step and returns the
        heuristic result verbatim.
    llm_confidence_threshold:
        Heuristic confidences at or above this value short-circuit the
        LLM call. Lower values mean more LLM calls; higher values mean
        more heuristic-only results.
    """

    def __init__(
        self,
        *,
        founder_names: Optional[list[str]] = None,
        llm: Any = None,
        llm_confidence_threshold: float = 0.7,
    ) -> None:
        self._founder_names = [n.strip().lower() for n in (founder_names or []) if n.strip()]
        self._llm = llm
        self._threshold = llm_confidence_threshold

    # ── Public API ──────────────────────────────────────────────────

    def separate(self, text: str, source_type: str = "written") -> SeparatedContent:
        """Separate founder content from prompts/questions.

        Args:
            text: Full uploaded text content
            source_type: "written", "transcript", "annotation", "external"
        """
        if not text or not text.strip():
            return SeparatedContent(founder_sections=[], prompt_sections=[], confidence=1.0)

        # Transcripts have a higher-signal speaker structure; branch there.
        if source_type == "transcript" and self._looks_like_speaker_transcript(text):
            return self._separate_speaker_transcript(text)

        # Written / annotation / external: paragraph-level classification.
        result = self._separate_paragraphs(text)

        # Optional LLM fallback for ambiguous splits.
        if self._llm is not None and result.confidence < self._threshold:
            refined = self._llm_refine(text, result)
            if refined is not None:
                return refined
        return result

    # ── Heuristic paths ─────────────────────────────────────────────

    def _looks_like_speaker_transcript(self, text: str) -> bool:
        lines = text.splitlines()
        speaker_lines = sum(1 for ln in lines if _SPEAKER_LINE.match(ln))
        # Need at least 3 speaker-labelled lines AND they should be a
        # non-trivial fraction of the non-empty lines.
        non_empty = sum(1 for ln in lines if ln.strip())
        return speaker_lines >= 3 and speaker_lines / max(non_empty, 1) >= 0.15

    def _separate_speaker_transcript(self, text: str) -> SeparatedContent:
        """Speaker-labelled transcripts: segments whose speaker matches
        any founder_name go to founder_sections; everyone else's
        segments are prompts. When founder_names is empty we assume the
        first speaker we see is the founder."""
        founder_sections: list[str] = []
        prompt_sections: list[str] = []
        current_speaker: Optional[str] = None
        current_buffer: list[str] = []
        first_speaker: Optional[str] = None

        def flush() -> None:
            if not current_buffer:
                return
            body = "\n".join(current_buffer).strip()
            if not body:
                return
            if self._is_founder_speaker(current_speaker, first_speaker):
                founder_sections.append(body)
            else:
                prompt_sections.append(body)

        for line in text.splitlines():
            m = _SPEAKER_LINE.match(line)
            if m:
                # Boundary: flush the previous speaker's buffer.
                flush()
                current_buffer = []
                current_speaker = m.group(1).strip()
                if first_speaker is None:
                    first_speaker = current_speaker
                # Keep the post-colon remainder of the line as buffer
                # content (the speaker's first sentence after the label).
                remainder = line[m.end():].strip()
                if remainder:
                    current_buffer.append(remainder)
            else:
                current_buffer.append(line)
        flush()

        # Confidence: transcripts with clear speaker labels are high
        # confidence. Slightly discount when we had to fall back to
        # "first speaker = founder" because founder_names was empty.
        confidence = 0.95 if self._founder_names else 0.8
        return SeparatedContent(
            founder_sections=founder_sections,
            prompt_sections=prompt_sections,
            confidence=confidence,
        )

    def _is_founder_speaker(
        self,
        speaker: Optional[str],
        first_speaker: Optional[str],
    ) -> bool:
        if not speaker:
            return True  # Pre-label content — attribute to the author.
        s = speaker.lower()
        if self._founder_names:
            return any(name in s for name in self._founder_names)
        # No configured name — first speaker is treated as the founder.
        if first_speaker is not None:
            return s == first_speaker.lower()
        return True

    def _separate_paragraphs(self, text: str) -> SeparatedContent:
        """Paragraph-level classification for written / annotation / external sources."""
        # Blank-line separated paragraphs. Collapse triple-newlines first.
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        founder_sections: list[str] = []
        prompt_sections: list[str] = []
        confident_classifications = 0

        prior_was_prompt = False
        for p in paragraphs:
            classification, strong = self._classify_paragraph(p, prior_was_prompt=prior_was_prompt)
            if strong:
                confident_classifications += 1
            if classification == "prompt":
                prompt_sections.append(p)
                prior_was_prompt = True
            else:
                founder_sections.append(p)
                prior_was_prompt = False

        # Confidence = share of paragraphs classified with a strong signal.
        confidence = (
            confident_classifications / len(paragraphs) if paragraphs else 1.0
        )
        return SeparatedContent(
            founder_sections=founder_sections,
            prompt_sections=prompt_sections,
            confidence=confidence,
        )

    def _classify_paragraph(self, p: str, *, prior_was_prompt: bool) -> tuple[str, bool]:
        """Return (label, strong) where label ∈ {"prompt", "founder"}
        and `strong` flags whether the heuristic was high-signal."""
        first_line = p.splitlines()[0] if p else ""
        stripped = p.strip()

        if _PROMPT_PREFIX.match(first_line):
            return ("prompt", True)
        if _RESPONSE_PREFIX.match(first_line):
            return ("founder", True)

        # Short paragraph ending with '?' → prompt (strong signal).
        if len(stripped) <= 280 and stripped.endswith("?"):
            if _INTERROGATIVE_OPENER.match(stripped) or stripped.count("?") >= 1:
                return ("prompt", True)

        # Blockquote-only paragraph ("> ...") → prompt (an external quote).
        if all(ln.lstrip().startswith(">") for ln in p.splitlines() if ln.strip()):
            return ("prompt", True)

        # Paragraph immediately following a prompt — treat as the founder's response.
        if prior_was_prompt:
            return ("founder", True)

        # Default: assume founder content, but mark as weak signal so the
        # caller's confidence score reflects the guess.
        return ("founder", False)

    # ── LLM fallback ────────────────────────────────────────────────

    def _llm_refine(
        self,
        text: str,
        heuristic: SeparatedContent,
    ) -> Optional[SeparatedContent]:
        """Ask the LLM to classify each paragraph; merge with the
        heuristic result. Returns None on any parsing / call failure so
        the caller falls back to the heuristic."""
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
            return heuristic

        numbered = "\n\n".join(f"[{i}] {p}" for i, p in enumerate(paragraphs))
        system = (
            "You are given a text that may contain both questions/prompts directed "
            "at an author and the author's own responses. Identify which paragraphs "
            "are the author's own assertions and which are external prompts, "
            "questions, or challenges. "
            'Return JSON: {"founder_paragraphs":[0,2,4],"prompt_paragraphs":[1,3]}'
        )
        try:
            raw = self._llm.complete(system=system, user=numbered, max_tokens=512)
        except Exception:
            return None
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            payload = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None

        founder_idx = set(int(i) for i in payload.get("founder_paragraphs", []) if isinstance(i, int))
        prompt_idx = set(int(i) for i in payload.get("prompt_paragraphs", []) if isinstance(i, int))
        founder_sections: list[str] = []
        prompt_sections: list[str] = []
        for i, p in enumerate(paragraphs):
            if i in prompt_idx and i not in founder_idx:
                prompt_sections.append(p)
            else:
                founder_sections.append(p)
        return SeparatedContent(
            founder_sections=founder_sections,
            prompt_sections=prompt_sections,
            confidence=max(heuristic.confidence, 0.85),
        )

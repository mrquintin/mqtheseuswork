"""Configuration for the Dialectic live-analysis engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os

from .resources import data_dir


@dataclass
class AudioConfig:
    sample_rate: int = 16_000
    channels: int = 1
    block_size: int = 1024          # ~64 ms per chunk at 16 kHz
    dtype: str = "int16"
    device_index: int | None = None  # None = system default


@dataclass
class TranscriptionConfig:
    # Local whisper settings (default — no API key required)
    backend: str = "whisper"        # "whisper" | "assemblyai"
    whisper_model: str = "base.en"  # tiny.en, base.en, small.en, medium.en
    whisper_device: str = "cpu"     # "cpu" | "cuda" | "auto"
    whisper_compute_type: str = "int8"

    # AssemblyAI (optional, faster + speaker diarisation)
    assemblyai_key: str = field(
        default_factory=lambda: os.environ.get("ASSEMBLYAI_API_KEY", "")
    )

    # Chunking
    silence_threshold: float = 0.02   # RMS below which audio is "silence"
    min_chunk_seconds: float = 1.5    # accumulate at least this much before transcribing
    max_chunk_seconds: float = 8.0    # force transcription after this long


@dataclass
class InterlocutorConfig:
    """SP09 — thresholds and budgets (bias toward silence)."""

    T_contradict: float = 0.85
    min_topic_touch_seconds: float = 30.0
    open_question_stale_days: int = 31
    prediction_unclear_min_length: int = 12
    min_pause_seconds_tts: float = 1.5
    tts_max_seconds: float = 12.0
    visual_latency_drop_seconds: float = 4.0
    audible_latency_drop_seconds: float = 8.0
    budget_conversational_seconds: float = 420.0
    budget_tutor_seconds: float = 180.0
    use_llm_appropriateness_gate: bool = False


# NOTE: the @dataclass decorator is required. Without it, `field(default_factory=...)`
# below evaluates to a `dataclasses.Field` sentinel object at class-level (truthy!),
# so `cfg.anthropic_key` would be a Field, not a string, and every
# `if cfg.anthropic_key:` branch would silently do the wrong thing.
@dataclass
class AnalysisConfig:
    # Contradiction detection
    nli_model: str = "cross-encoder/nli-deberta-v3-small"
    contradiction_threshold: float = 0.60

    # Topic tracking
    embedding_model: str = "all-MiniLM-L6-v2"
    topic_window_size: int = 40           # sentences in sliding window
    topic_recluster_every: int = 4        # recluster every N sentences
    topic_eps: float = 0.35               # DBSCAN eps
    topic_min_samples: int = 2

    # Open-loop detection
    loop_staleness_seconds: float = 120.0  # flag a loop as abandoned after 2 min
    loop_similarity_threshold: float = 0.55

    # Question generation
    question_backend: str = "claude"      # "claude" | "ollama"
    question_model_claude: str = "claude-sonnet-4-20250514"
    question_model_ollama: str = "mistral-small"
    question_interval_seconds: float = 45.0  # generate questions at most every N sec

    # Claude API
    anthropic_key: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", "")
    )


@dataclass
class UIConfig:
    window_title: str = "Dialectic"
    window_width: int = 1100
    window_height: int = 780
    accent_color: str = "#2E4057"
    bg_color: str = "#F7F8FA"
    panel_bg: str = "#FFFFFF"
    text_color: str = "#1A1A2E"
    muted_color: str = "#8B8B9E"
    red_accent: str = "#C0392B"
    green_accent: str = "#27AE60"
    amber_accent: str = "#D4A017"
    blue_accent: str = "#2980B9"


@dataclass
class DialecticConfig:
    audio: AudioConfig = field(default_factory=AudioConfig)
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    interlocutor: InterlocutorConfig = field(default_factory=InterlocutorConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    recordings_dir: Path = field(
        default_factory=lambda: data_dir() / "recordings"
    )

    def __post_init__(self):
        self.recordings_dir.mkdir(parents=True, exist_ok=True)

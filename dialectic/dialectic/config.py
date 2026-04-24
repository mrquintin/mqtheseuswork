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
class BatchTranscriptionConfig:
    """Post-recording (batch) transcription settings.

    Distinct from :class:`TranscriptionConfig` (live streaming): batch has
    no latency pressure, so we default to a larger model (``medium.en``
    vs. live's ``base.en``) and a wider beam. The ``initial_prompt``
    biases Whisper toward Theseus-relevant vocabulary (methodology,
    epistemic, discount, coherence) and is worth re-auditing if the
    domain ever shifts.
    """

    model: str = "medium.en"
    compute_type: str = "int8"         # override via env DIALECTIC_WHISPER_COMPUTE_TYPE
    beam_size: int = 5                 # larger beam than live; batch has no latency pressure
    language: str | None = "en"
    vad_filter: bool = True            # drop silence segments from Whisper's own output
    initial_prompt: str | None = (
        "This is a Theseus dialectic recording — a spoken discussion among "
        "founders about methodology, truth-tracking, and epistemic practice."
    )


@dataclass
class AutoTrimConfig:
    """Post-recording auto-trim (silence removal) via Silero VAD.

    Hysteresis thresholds: a frame enters the "speech" state only when
    probability exceeds ``open_threshold`` and exits only when it drops
    below ``close_threshold``. The gap between the two prevents a single
    flickering frame from toggling the state mid-word.

    ``min_speech_ms`` drops ultra-short detections (clicks, breath
    artifacts misread as phonemes). ``max_gap_ms`` bridges the thinking
    pauses inside a sentence — silence-on-thinking is content, not dead
    air. ``pad_ms`` and ``crossfade_ms`` smooth segment boundaries so
    the concatenated output has no audible clicks.
    """

    frame_duration_ms: int = 30       # Silero supports 10/20/30 ms; 30 is the robust default
    open_threshold: float = 0.6        # speech prob to START a speech segment
    close_threshold: float = 0.3       # speech prob to END a speech segment
    min_speech_ms: int = 400           # runs shorter than this are dropped as noise
    max_gap_ms: int = 800              # silences shorter than this are bridged (kept)
    pad_ms: int = 150                  # include this many ms before/after each boundary
    crossfade_ms: int = 150            # linear crossfade at concatenation points
    target_sample_rate: int = 16000    # Silero's native rate


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

    # Minimum spacing between successive interventions. Previously the
    # code reused `budget_conversational_seconds` / `budget_tutor_seconds`
    # as the per-intervention cooldown, which effectively meant "at most
    # one intervention every 7 minutes" in conversational mode — a
    # silent muzzle. These two fields are the *total* session budgets
    # (eventually used for cumulative-time enforcement); the cooldown
    # below is the gate that actually throttles emission cadence.
    min_intervention_spacing_seconds: float = 45.0
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
class AutoTitleConfig:
    """Post-recording auto-title via Claude Haiku.

    A title is a mild LLM use; the deterministic fallback (see
    ``auto_title._deterministic_fallback``) is the correct answer when
    Anthropic is unreachable, not another cloud dependency.
    """

    model: str = "claude-haiku-4-5"
    max_tokens: int = 60
    max_transcript_chars_for_title: int = 6000
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0
    temperature: float = 0.2
    anthropic_key: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", "")
    )


@dataclass
class AutoUploadConfig:
    """Post-recording upload to the Theseus Codex.

    Uses the signed-URL three-step dance (prepare → PUT → finalize). Chunk
    size governs how often the progress callback fires during the PUT;
    smaller chunks mean smoother progress at a tiny throughput cost.
    Timeouts are per-stage — the PUT timeout applies to the full upload
    so must be generous enough for a 2-hour WAV on a flaky connection.
    """

    chunk_bytes: int = 256 * 1024        # 256 KB → ~4 callbacks/MB
    prepare_timeout_seconds: float = 30.0
    put_timeout_seconds: float = 30 * 60  # 30 min for large trimmed .wav
    finalize_timeout_seconds: float = 60.0


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
    batch_transcription: BatchTranscriptionConfig = field(
        default_factory=BatchTranscriptionConfig
    )
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    interlocutor: InterlocutorConfig = field(default_factory=InterlocutorConfig)
    auto_trim: AutoTrimConfig = field(default_factory=AutoTrimConfig)
    auto_title: AutoTitleConfig = field(default_factory=AutoTitleConfig)
    auto_upload: AutoUploadConfig = field(default_factory=AutoUploadConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    recordings_dir: Path = field(
        default_factory=lambda: data_dir() / "recordings"
    )

    def __post_init__(self):
        self.recordings_dir.mkdir(parents=True, exist_ok=True)

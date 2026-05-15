"""Central, typed configuration for the Theseus Python tree.

This module is the *one* place env vars are read inside the Python codebase.
Everything that used to live as a scattered ``os.getenv("THESEUS_*")`` /
``os.getenv("NOOSPHERE_*")`` lookup, or as an inline magic-number threshold,
is exposed here as a typed attribute on the :class:`Settings` model.

Loading order (highest precedence last)::

    config/defaults.yaml
        ↓
    config/<THESEUS_ENV>.yaml          (e.g. development.yaml, production.yaml)
        ↓
    process environment variables      (highest precedence)

Secrets never live in YAML — they remain env-only. Overlays carry tunables
(thresholds, retention windows, scheduler intervals, model defaults) that
benefit from being committed and reviewable.

Read-only at runtime: the returned :class:`Settings` instance is frozen.
For tests, use :meth:`Settings.with_overrides` to obtain a transient copy
with selective fields replaced.

See :doc:`/architecture/Configuration` for the migration plan and the full
threshold rationale.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ConfigDict, Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Repo / overlay discovery
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    """Return the monorepo root.

    ``noosphere/noosphere/core/config.py`` → ``parents[3]`` is the repo root.
    """

    return Path(__file__).resolve().parents[3]


def _overlay_dir() -> Path:
    return _repo_root() / "config"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigError(
            f"Overlay file {path} must be a YAML mapping at the top level "
            f"(got {type(loaded).__name__})."
        )
    return loaded


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ConfigError(RuntimeError):
    """Raised on invalid config (bad YAML, immutability violation, missing required env)."""


# ---------------------------------------------------------------------------
# Magic-number registry — Round 17 thresholds.
#
# Every entry in this section is intentionally documented with the domain
# rationale Round 17 surfaced. **Do not change values here without an
# accompanying tuning prompt and a calibration record** — centralizing was a
# refactor; tuning is a separate workflow.
# ---------------------------------------------------------------------------


class CurrentsThresholds(BaseSettings):
    """Currents (X / news ingest) signal floors.

    These values used to live inline in ``noosphere.currents.config`` and
    related ingestors. They guard against low-signal posts polluting the
    public surface; see ``noosphere.currents`` docstrings for the
    log-weighted score derivation.
    """

    model_config = SettingsConfigDict(frozen=True, extra="forbid")

    # 1.35 ≈ one default viral-search signal cleared (1k likes OR 100 RTs);
    # raises the floor above keyword-only matches.
    min_significance_score: float = 1.35
    # Engagement raw-count fallback floors (used when impressions are
    # withheld by the API tier).
    min_likes: int = 1_000
    min_retweets: int = 100
    min_impressions: int = 25_000
    # Per-cycle ceiling so a viral spike cannot exhaust quota in one tick.
    max_events_per_cycle: int = 40
    # Discovery query candidate ceiling per cycle.
    discovery_max_candidates: int = 100
    # Outbound HTTP timeout for the X v2 API.
    request_timeout_s: float = 15.0
    # Default lookback window for each ingest pass (minutes).
    lookback_minutes: int = 15


class ForecastsThresholds(BaseSettings):
    """Forecasts trading & budget guardrails.

    Mirrors the ceilings declared in ``.env.live.template``. Values here are
    *defaults*; live deploys override via env. Anything that touches real
    money MUST come from env (see :class:`Settings.forecasts_live_*`).
    """

    model_config = SettingsConfigDict(frozen=True, extra="forbid")

    # Per-bet stake ceiling (USD). Start small; scale only after 30 resolved
    # live bets show mean Brier < 0.20.
    max_stake_usd_default: float = 5.0
    # Daily loss ceiling (USD). Hitting this auto-engages the kill switch.
    max_daily_loss_usd_default: float = 20.0
    # Auto kill-switch threshold; should fire before max_daily_loss_usd.
    kill_switch_auto_threshold_usd_default: float = 15.0
    # Paper-bankroll seed for the simulator.
    paper_initial_balance_usd_default: float = 10_000.0
    # Hourly LLM token-budget guards.
    budget_hourly_prompt_tokens: int = 1_500_000
    budget_hourly_completion_tokens: int = 400_000
    # Scheduler cadences (seconds).
    ingest_interval_s: int = 900
    generate_interval_s: int = 600
    resolution_poll_interval_s: int = 300
    paper_bet_drain_interval_s: int = 60
    # Polymarket / Kalshi per-cycle market caps.
    max_markets_per_cycle: int = 200
    request_timeout_s: float = 15.0


class CalibrationThresholds(BaseSettings):
    """Calibration & confidence-discount thresholds (STRATEGIC 05 / Round 17).

    Round 17 introduced calibration-aware confidence — see prompt
    ``14_calibration_aware_confidence``. These are the published floors.
    """

    model_config = SettingsConfigDict(frozen=True, extra="forbid")

    # Minimum number of resolved predictions before track-record discounting
    # is applied (below this, the historical sample is too small to trust).
    min_sample_size: int = 30
    # Severity multiplier applied to the discount when calibration drift
    # exceeds the warning band (see calibration scoreboard derivation).
    drift_severity_multiplier: float = 1.5
    # Drift sigma value above which calibration is flagged degraded
    # (gaussian band on Brier residuals).
    drift_sigma_warning: float = 2.0
    # Drift sigma at which the kill-switch auto-engagement detector trips.
    drift_sigma_critical: float = 3.0


class CoherenceThresholds(BaseSettings):
    """Coherence layer — similarity cutoffs and freshness windows."""

    model_config = SettingsConfigDict(frozen=True, extra="forbid")

    # Cosine similarity cutoff above which two claims are considered
    # near-duplicate for the coherence judge (Hoyer-cosine baseline).
    similarity_dedup_cutoff: float = 0.92
    # Minimum cosine similarity to surface as a contradicting neighbour.
    similarity_contradiction_floor: float = 0.55
    # Adversarial coherence (STRATEGIC 01) — neighbourhood size.
    adversarial_k_default: int = 3
    # Days after which an adversarial coherence rating is considered stale.
    adversarial_stale_days_default: int = 30


class DialecticThresholds(BaseSettings):
    """Currents dialectic engine — counter-claim retrieval & strawman gates.

    Round 17 prompt 27 tightened counter-claim retrieval from a single
    embedding-similarity signal to a three-signal hybrid gate (embedding
    similarity AND NLI "actually contradicts" AND cascade-graph backing).
    These floors were calibrated against the sample audit in
    ``docs/research/internal/Currents_Dialectic_Audit_*.md`` — the audit is
    repeatable (``noosphere/scripts/audit_currents_dialectic.py``) and any
    change to a value here MUST be accompanied by a fresh audit run, per the
    Round 17 magic-number-registry discipline. The bar is deliberately set
    high: a false-positive counter-claim erodes trust faster than a missed
    one, so every floor fails closed.
    """

    model_config = SettingsConfigDict(frozen=True, extra="forbid")

    # Cosine similarity between the predicted contradiction location and a
    # candidate. 0.55 mirrors ``coherence.similarity_contradiction_floor``;
    # the audit showed it is necessary but, on its own, not sufficient — it
    # admits "opposing in tone" claims that do not actually contradict.
    counter_similarity_floor: float = 0.55
    # NLI contradiction probability for (opinion headline -> candidate text).
    # Audit: genuine contradictions scored >0.65; opposing-tone false
    # positives clustered <0.50. 0.60 separates the two with margin.
    counter_nli_contradiction_floor: float = 0.60
    # The candidate's NLI contradiction must beat its entailment by at least
    # this margin, so a near-tie verdict cannot promote a non-contradiction.
    counter_nli_entailment_margin: float = 0.10
    # Minimum incident cascade weight. The counter-claim must be backed by at
    # least one source the firm has previously taken seriously; floating
    # claims (incident weight <0.25) had the highest strawman rate in the
    # audit. A candidate with no cascade backing at all is rejected.
    counter_cascade_weight_floor: float = 0.25
    # Candidate pool size scored on cosine before the hybrid gates run.
    counter_top_k: int = 32
    # Strawman detector: fraction of the counter-claim's content tokens the
    # reconciliation's strongest-form restatement must preserve. Raised from
    # the pre-audit implicit 0.35 — paraphrases in the 0.35–0.50 coverage
    # band reliably softened the counter.
    strawman_content_coverage_floor: float = 0.50
    # Restatement / counter content-token-count ratio floor. A materially
    # shorter "strongest form" is a softening signal even when coverage is OK.
    strawman_length_ratio_floor: float = 0.60
    # Max reconciliation attempts before falling back to the honest
    # no-counter note when the model keeps strawmanning the counter-claim.
    reconciliation_max_attempts: int = 2


class RetentionThresholds(BaseSettings):
    """Retention TTLs for ephemeral data caches."""

    model_config = SettingsConfigDict(frozen=True, extra="forbid")

    # Embedding cache TTL (seconds).
    embedding_cache_ttl_s: int = 7 * 24 * 3600
    # Audit-log retention (days). Independent of ledger immutability.
    audit_log_retention_days: int = 90
    # Public-API rate-limit window (seconds).
    rate_limit_window_s: int = 60


class LatencyBudgets(BaseSettings):
    """End-to-end latency budgets in milliseconds.

    These are *budgets*, not SLOs — exceeding one is a smell, not a page.
    """

    model_config = SettingsConfigDict(frozen=True, extra="forbid")

    public_ask_p95_ms: int = 2_500
    public_calibration_manifest_p95_ms: int = 800
    methodology_manifest_p95_ms: int = 800
    embed_pass_per_chunk_p95_ms: int = 350


class Thresholds(BaseSettings):
    """Aggregate magic-number registry."""

    model_config = SettingsConfigDict(frozen=True, extra="forbid")

    currents: CurrentsThresholds = Field(default_factory=CurrentsThresholds)
    forecasts: ForecastsThresholds = Field(default_factory=ForecastsThresholds)
    calibration: CalibrationThresholds = Field(default_factory=CalibrationThresholds)
    coherence: CoherenceThresholds = Field(default_factory=CoherenceThresholds)
    dialectic: DialecticThresholds = Field(default_factory=DialecticThresholds)
    retention: RetentionThresholds = Field(default_factory=RetentionThresholds)
    latency_budget_ms: LatencyBudgets = Field(default_factory=LatencyBudgets)


# ---------------------------------------------------------------------------
# Documented required-env list — used to make the missing-env error helpful.
# ---------------------------------------------------------------------------


REQUIRED_ENV_DOCS: dict[str, str] = {
    "DATABASE_URL": (
        "Production Postgres connection string. "
        "See docs/architecture/Configuration.md#database"
    ),
    "ANTHROPIC_API_KEY": (
        "Anthropic API key for LLM inference. "
        "See docs/architecture/Configuration.md#llm-providers"
    ),
}


# ---------------------------------------------------------------------------
# Settings model
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Process-wide typed configuration.

    Attributes here used to live as scattered ``os.getenv`` calls in
    ``noosphere``, ``current_events_api``, ``dialectic`` and module-level
    constants under ``noosphere/{currents,forecasts}/config.py``.
    """

    model_config = SettingsConfigDict(
        env_prefix="THESEUS_",
        env_file_encoding="utf-8",
        extra="ignore",
        # Frozen at runtime — overrides go through with_overrides().
        frozen=True,
    )

    # --- Environment selection ------------------------------------------------
    env: Literal["development", "staging", "production", "test"] = "development"

    # --- LLM ------------------------------------------------------------------
    embedding_model_name: str = "all-mpnet-base-v2"
    embedding_device: str = "cpu"
    nli_model_name: str = "roberta-large-mnli"
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    llm_model: str = "claude-sonnet-4-20250514"
    llm_api_key: str = ""

    # --- Storage --------------------------------------------------------------
    database_url: str = "sqlite:///./noosphere_data/noosphere.db"
    data_dir: Path = Field(default_factory=lambda: _repo_root() / "noosphere_data")
    log_level: str = "INFO"
    log_file: str = ""  # Migrated from THESEUS_LOG_FILE.

    # --- Coherence layer version tokens (cache invalidation) -----------------
    coherence_ver_nli: str = "cross-encoder/nli-deberta-v3-base:v1"
    coherence_ver_argumentation: str = "dung-neighbors:v1"
    coherence_ver_probabilistic: str = "llm-commitments:v1"
    coherence_ver_geometry: str = "hoyer-cosine:v1"
    coherence_ver_information: str = "zstd-ratio:v1"
    coherence_ver_judge: str = "llm-judge:v1"

    # --- Strategic toggles (enforcement off until human-review pass) ---------
    adversarial_enforce: bool = False
    adversarial_shadow: bool = False
    adversarial_k: int = 3
    adversarial_stale_days: int = 30
    voice_citation_shadow: bool = True
    calibration_confidence_enabled: bool = False
    ingestion_guard_enabled: bool = True

    # --- Currents (X / news) -------------------------------------------------
    x_bearer_token: str = ""
    currents_curated_accounts_path: str = ""
    currents_topic_keywords_path: str = ""
    currents_lookback_minutes: int = 15
    currents_api_host: str = "0.0.0.0"
    currents_api_port: int = 8088
    currents_cors_origins: str = "http://localhost:3001"
    currents_llm_model: str = "claude-haiku-4-5"
    currents_llm_max_prompt_tokens_per_hour: int = 1_500_000
    currents_llm_max_completion_tokens_per_hour: int = 400_000
    currents_ingest_org_id: str = ""

    # --- Noosphere data -----------------------------------------------------
    noosphere_data_dir: str = ""

    # --- Forecasts (live trading; secrets stay env-only) --------------------
    forecasts_live_trading_enabled: bool = False
    forecasts_max_stake_usd: float = 5.0
    forecasts_max_daily_loss_usd: float = 20.0
    forecasts_kill_switch_auto_threshold_usd: float = 15.0
    forecasts_paper_initial_balance_usd: float = 10_000.0
    forecasts_ingest_org_id: str = ""
    forecasts_operator_secret: str = ""
    forecasts_polymarket_categories: str = ""
    forecasts_kalshi_categories: str = ""

    # --- Public-site / theseus-public --------------------------------------
    currents_api_url: str = "http://currents-api:8088"
    public_site_origin: str = "http://localhost:3001"

    # --- Notifications -----------------------------------------------------
    theseus_notify_from: str = "notify@theseus.local"
    founder_alpha_email: str = "founder-alpha@example.invalid"

    # --- Magic-number registry --------------------------------------------
    thresholds: Thresholds = Field(default_factory=Thresholds)

    # ------------------------------------------------------------------
    # Pre-validation: layer in YAML overlays.
    # ------------------------------------------------------------------

    @model_validator(mode="before")
    @classmethod
    def _layer_overlays(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            data = {}

        # Highest precedence is what the caller already passed; lowest is the
        # defaults overlay. Build bottom-up and let later layers win.
        overlay_dir = _overlay_dir()
        merged: dict[str, Any] = {}

        defaults_path = overlay_dir / "defaults.yaml"
        merged = _deep_merge(merged, _load_yaml(defaults_path))

        env_name = (
            data.get("env")
            or os.environ.get("THESEUS_ENV")
            or "development"
        )
        env_overlay = overlay_dir / f"{env_name}.yaml"
        merged = _deep_merge(merged, _load_yaml(env_overlay))

        # Caller-provided values (env vars / explicit kwargs) win.
        merged = _deep_merge(merged, {k: v for k, v in data.items() if v is not None})
        return merged

    # ------------------------------------------------------------------
    # Helpers — provider auto-fallback (preserved from legacy config).
    # ------------------------------------------------------------------

    def effective_llm_provider(self) -> Literal["anthropic", "openai"]:
        if self.llm_api_key:
            return self.llm_provider
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if self.llm_provider == "anthropic":
            if anthropic_key:
                return "anthropic"
            if openai_key:
                return "openai"
            return "anthropic"
        if openai_key:
            return "openai"
        if anthropic_key:
            return "anthropic"
        return "openai"

    def effective_llm_api_key(self) -> str:
        if self.llm_api_key:
            return self.llm_api_key
        provider = self.effective_llm_provider()
        if provider == "anthropic":
            return os.environ.get("ANTHROPIC_API_KEY", "")
        return os.environ.get("OPENAI_API_KEY", "")

    def effective_llm_model(self) -> str:
        provider = self.effective_llm_provider()
        model = self.llm_model or ""
        lower = model.lower()
        if provider == "anthropic" and "claude" in lower:
            return model
        if provider == "openai" and ("gpt" in lower or lower.startswith("o1")):
            return model
        return (
            "claude-sonnet-4-20250514"
            if provider == "anthropic"
            else "gpt-4o-mini"
        )

    # ------------------------------------------------------------------
    # Test helper — selective overrides.
    # ------------------------------------------------------------------

    def with_overrides(self, **overrides: Any) -> "Settings":
        """Return a *new* Settings instance with selected fields replaced.

        Use this in tests to avoid mutating the singleton. The returned
        instance is itself frozen.
        """

        return self.model_copy(update=overrides)

    @classmethod
    @contextmanager
    def patch(cls, **overrides: Any) -> Iterator["Settings"]:
        """Context manager: temporarily replace the cached singleton.

        Usage::

            with Settings.patch(currents_lookback_minutes=5) as s:
                run_thing(s)
        """

        with _SETTINGS_LOCK:
            previous = _settings_singleton.get()
            patched = (previous or get_settings()).with_overrides(**overrides)
            _settings_singleton.set(patched)
        try:
            yield patched
        finally:
            with _SETTINGS_LOCK:
                _settings_singleton.set(previous)


# ---------------------------------------------------------------------------
# Deep merge utility (overlay layering).
# ---------------------------------------------------------------------------


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge ``overlay`` into ``base`` and return a new dict.

    Mappings are merged key-wise; scalars and lists are replaced.
    """

    out: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if (
            key in out
            and isinstance(out[key], Mapping)
            and isinstance(value, Mapping)
        ):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


# ---------------------------------------------------------------------------
# Module-level singleton + helpful errors.
# ---------------------------------------------------------------------------


class _SingletonHolder:
    """Tiny holder used by Settings.patch context-manager."""

    def __init__(self) -> None:
        self._value: Settings | None = None

    def get(self) -> Settings | None:
        return self._value

    def set(self, value: Settings | None) -> None:
        self._value = value


_settings_singleton = _SingletonHolder()
_SETTINGS_LOCK = threading.Lock()


def _format_validation_error(exc: ValidationError) -> str:
    lines = ["Configuration is invalid. Fix the following:"]
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "<root>"
        msg = err["msg"]
        env_var = _field_to_env_var(loc)
        # Look up docs under both the prefixed and the bare form — some
        # required env vars (e.g. ``DATABASE_URL``) are read by external
        # tooling without the ``THESEUS_`` prefix.
        bare = loc.upper() if "." not in loc else ""
        doc = REQUIRED_ENV_DOCS.get(env_var.upper()) or REQUIRED_ENV_DOCS.get(bare)
        suffix = f" — env var: {env_var}" if env_var else ""
        if doc:
            suffix += f"\n      ({doc})"
        lines.append(f"  - {loc}: {msg}{suffix}")
    return "\n".join(lines)


def _field_to_env_var(field_path: str) -> str:
    if not field_path or field_path == "<root>":
        return ""
    # Top-level fields use the THESEUS_ prefix; nested fields don't have
    # direct env-var bindings.
    if "." in field_path:
        return ""
    return f"THESEUS_{field_path.upper()}"


@lru_cache
def _build_settings_cached() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc)) from exc


def get_settings() -> Settings:
    """Process-wide settings.

    A patched override (set by :meth:`Settings.patch`) takes precedence
    over the cached singleton so tests can replace the active config
    transactionally without flushing the cache.
    """

    patched = _settings_singleton.get()
    if patched is not None:
        return patched
    return _build_settings_cached()


# Expose the standard ``cache_clear()`` shape so existing tests that call
# ``get_settings.cache_clear()`` keep working.
get_settings.cache_clear = _build_settings_cached.cache_clear  # type: ignore[attr-defined]


__all__ = [
    "CalibrationThresholds",
    "CoherenceThresholds",
    "ConfigError",
    "CurrentsThresholds",
    "DialecticThresholds",
    "ForecastsThresholds",
    "LatencyBudgets",
    "REQUIRED_ENV_DOCS",
    "RetentionThresholds",
    "Settings",
    "Thresholds",
    "get_settings",
]

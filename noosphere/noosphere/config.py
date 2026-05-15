"""Legacy configuration module — kept for backward compatibility.

The canonical configuration module is now :mod:`noosphere.core.config`,
which adds YAML overlay layering, the :class:`Thresholds` magic-number
registry, and a richer set of fields. New code MUST import from there::

    from noosphere.core.config import Settings, get_settings

This module preserves the prior, self-contained implementation so that
existing callers (``noosphere.orchestrator``, ``noosphere.store``,
``noosphere.coherence``, …) keep importing without triggering a
circular dependency on the ``noosphere.core`` package's eager
re-exports. It is on the CI gate allowlist (see
``scripts/check_no_inline_env_reads.py``) only as the legacy shim
entry point; once callers are migrated to the new path, this file can
be removed.
"""

from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    # noosphere/noosphere/config.py -> parents[2] == monorepo root (Theseus/)
    return Path(__file__).resolve().parents[2]


def _theseus_toml_flat() -> dict[str, Any]:
    path = _repo_root() / "theseus.toml"
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        raw = tomllib.load(f)
    block = raw.get("theseus", raw)
    if not isinstance(block, dict):
        return {}
    return {str(k): v for k, v in block.items()}


class NoosphereSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="THESEUS_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    embedding_model_name: str = "all-mpnet-base-v2"
    embedding_device: str = "cpu"
    nli_model_name: str = "roberta-large-mnli"
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    llm_model: str = "claude-sonnet-4-20250514"
    llm_api_key: str = ""
    database_url: str = "sqlite:///./noosphere_data/noosphere.db"
    data_dir: Path = Field(default_factory=lambda: _repo_root() / "noosphere_data")
    log_level: str = "INFO"
    # Coherence layer version tokens (bump any to invalidate caches / force re-eval).
    coherence_ver_nli: str = "cross-encoder/nli-deberta-v3-base:v1"
    coherence_ver_argumentation: str = "dung-neighbors:v1"
    coherence_ver_probabilistic: str = "llm-commitments:v1"
    coherence_ver_geometry: str = "hoyer-cosine:v1"
    coherence_ver_information: str = "zstd-ratio:v1"
    coherence_ver_judge: str = "llm-judge:v1"
    # Adversarial coherence (STRATEGIC 01) — enforcement off until human review pass.
    adversarial_enforce: bool = False
    adversarial_shadow: bool = False
    adversarial_k: int = 3
    adversarial_stale_days: int = 30
    # Voice decomposition (STRATEGIC 02): citation writes are shadow until review.
    voice_citation_shadow: bool = True
    # Calibration scoreboard (STRATEGIC 05): discount synthesis confidence using track record.
    calibration_confidence_enabled: bool = False
    # Red-team / robustness (STRATEGIC 08): first-line ingestion scanner + embedding hygiene.
    ingestion_guard_enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def _apply_toml_defaults(cls, data: Any) -> Any:
        base = _theseus_toml_flat()
        if isinstance(data, dict):
            merged = {**base, **{k: v for k, v in data.items() if v is not None}}
            return merged
        return {**base}

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


@lru_cache
def get_settings() -> NoosphereSettings:
    """Process-wide settings (call ``get_settings.cache_clear()`` in tests).

    For new code, prefer :func:`noosphere.core.config.get_settings`,
    which loads YAML overlays and exposes the :class:`Thresholds`
    magic-number registry.
    """

    return NoosphereSettings()

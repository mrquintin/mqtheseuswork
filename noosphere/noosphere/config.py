"""
Central configuration: environment variables and optional `theseus.toml` at repo root.
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
    llm_model: str = "claude-3-5-sonnet-20241022"
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

    def effective_llm_api_key(self) -> str:
        """API key from explicit setting or provider-default env var."""
        if self.llm_api_key:
            return self.llm_api_key
        if self.llm_provider == "anthropic":
            return os.environ.get("ANTHROPIC_API_KEY", "")
        return os.environ.get("OPENAI_API_KEY", "")


@lru_cache
def get_settings() -> NoosphereSettings:
    """Process-wide settings (call `get_settings.cache_clear()` in tests)."""
    return NoosphereSettings()

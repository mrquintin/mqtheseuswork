"""Multi-provider adapters for the peer-review swarm.

A single LLM provider is a single failure mode. This package exposes a
uniform :class:`ProviderAdapter` protocol so the swarm can rotate
across architecturally distinct providers (Claude, GPT, Gemini, an
open-weights Mistral). Each adapter records its own cost and latency
so the orchestrator can enforce a per-run budget.

Provider keys are read from the environment only — never embedded in
code or config files committed to git. Models are configurable
defaults so we can move with provider releases without touching the
swarm.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ── Per-provider defaults ────────────────────────────────────────────
#
# Model names live here, not in code that talks to the SDKs, so a model
# bump is a one-line change. Pricing is approximate USD per 1K tokens
# and is used only for the budget governor — operators can override
# both via environment variables when calling the registry.

@dataclass(frozen=True)
class ProviderDefaults:
    name: str
    env_key: str
    default_model_env: str
    default_model: str
    cost_per_1k_in: float
    cost_per_1k_out: float


PROVIDER_DEFAULTS: dict[str, ProviderDefaults] = {
    "anthropic": ProviderDefaults(
        name="anthropic",
        env_key="ANTHROPIC_API_KEY",
        default_model_env="THESEUS_PEER_REVIEW_ANTHROPIC_MODEL",
        default_model="claude-3-5-sonnet-20241022",
        cost_per_1k_in=0.003,
        cost_per_1k_out=0.015,
    ),
    "openai": ProviderDefaults(
        name="openai",
        env_key="OPENAI_API_KEY",
        default_model_env="THESEUS_PEER_REVIEW_OPENAI_MODEL",
        default_model="gpt-4o-2024-08-06",
        cost_per_1k_in=0.0025,
        cost_per_1k_out=0.01,
    ),
    "gemini": ProviderDefaults(
        name="gemini",
        env_key="GOOGLE_API_KEY",
        default_model_env="THESEUS_PEER_REVIEW_GEMINI_MODEL",
        default_model="gemini-1.5-pro-002",
        cost_per_1k_in=0.00125,
        cost_per_1k_out=0.005,
    ),
    "mistral_oss": ProviderDefaults(
        # The "oss" framing is deliberate: this slot is for a
        # self-hosted or third-party-hosted open-weights model so the
        # swarm has at least one non-frontier-vendor voice. Default
        # endpoint is a local vLLM/OpenAI-compatible server; pricing is
        # zero because the operator pays for compute, not tokens.
        name="mistral_oss",
        env_key="MISTRAL_OSS_API_KEY",
        default_model_env="THESEUS_PEER_REVIEW_MISTRAL_MODEL",
        default_model="mistralai/Mixtral-8x7B-Instruct-v0.1",
        cost_per_1k_in=0.0,
        cost_per_1k_out=0.0,
    ),
}


# ── Public types ─────────────────────────────────────────────────────


@dataclass
class ObjectionResult:
    """Single provider's adversarial objection on a claim."""

    provider: str
    model: str
    text: str
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    error: Optional[str] = None
    seed: Optional[int] = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text)


@runtime_checkable
class ProviderAdapter(Protocol):
    """Uniform interface every adapter implements."""

    name: str
    model: str

    def is_available(self) -> bool: ...

    def produce_objection(
        self,
        *,
        claim: str,
        methodology: str,
        context: dict[str, Any],
        max_tokens: int = 512,
        temperature: float = 0.2,
        seed: Optional[int] = None,
    ) -> ObjectionResult: ...


# ── Prompt assembly ──────────────────────────────────────────────────
#
# Same instruction surface for every provider so disagreement signal
# reflects model architecture, not prompt drift.

SYSTEM_PROMPT = (
    "You are an adversarial peer reviewer for a knowledge firm. Your job "
    "is to identify the single most damaging objection to the claim "
    "below given the methodology used to produce it. State the objection "
    "directly in 2-4 sentences. Begin with whether the central "
    "assumption is HIDDEN or EXPLICIT. Do not hedge."
)


def build_user_prompt(
    claim: str, methodology: str, context: dict[str, Any]
) -> str:
    parts = [f"CLAIM:\n{claim.strip()}", f"METHODOLOGY:\n{methodology.strip()}"]
    if context:
        ctx_lines = [f"- {k}: {v}" for k, v in context.items() if v is not None]
        if ctx_lines:
            parts.append("CONTEXT:\n" + "\n".join(ctx_lines))
    parts.append(
        "Produce one objection. Lead with the literal token HIDDEN or "
        "EXPLICIT to declare your read on the assumption."
    )
    return "\n\n".join(parts)


# ── Registry ─────────────────────────────────────────────────────────

_ADAPTERS: dict[str, ProviderAdapter] = {}


def register_adapter(adapter: ProviderAdapter) -> ProviderAdapter:
    _ADAPTERS[adapter.name] = adapter
    return adapter


def get_adapter(name: str) -> ProviderAdapter:
    if name not in _ADAPTERS:
        _ensure_default_adapters()
    if name not in _ADAPTERS:
        raise KeyError(f"unknown provider {name!r}")
    return _ADAPTERS[name]


def all_adapters() -> list[ProviderAdapter]:
    _ensure_default_adapters()
    return list(_ADAPTERS.values())


def available_providers() -> list[ProviderAdapter]:
    """Adapters whose API key is present in the environment."""
    return [a for a in all_adapters() if a.is_available()]


def reset_registry() -> None:
    """Test hook: forget every registered adapter."""
    _ADAPTERS.clear()


def _ensure_default_adapters() -> None:
    if _ADAPTERS:
        return
    # Lazy import keeps SDK dependencies optional at module-import time
    # — operators who only run one provider should not pay for the
    # other three's import surface.
    from noosphere.peer_review.providers.anthropic import AnthropicAdapter
    from noosphere.peer_review.providers.openai import OpenAIAdapter
    from noosphere.peer_review.providers.gemini import GeminiAdapter
    from noosphere.peer_review.providers.mistral_oss import MistralOSSAdapter

    for cls in (AnthropicAdapter, OpenAIAdapter, GeminiAdapter, MistralOSSAdapter):
        register_adapter(cls())


# ── Cost / availability helpers ──────────────────────────────────────


def env_key_present(env_key: str) -> bool:
    val = os.environ.get(env_key, "").strip()
    return bool(val)


def estimate_cost(
    *, defaults: ProviderDefaults, tokens_in: int, tokens_out: int
) -> float:
    return (
        (tokens_in / 1000.0) * defaults.cost_per_1k_in
        + (tokens_out / 1000.0) * defaults.cost_per_1k_out
    )


# ── Disagreement detection ───────────────────────────────────────────


@dataclass(frozen=True)
class ProviderDisagreement:
    """Two providers' objections were judged contradictory by NLI."""

    provider_a: str
    provider_b: str
    objection_a: str
    objection_b: str
    contradiction_score: float


# Type alias for a pluggable NLI scorer. The default uses the
# registered `nli_scorer` method; tests inject a stub.
NLIScoreFn = Callable[[str, str], dict[str, float]]


def _default_nli_scorer(premise: str, hypothesis: str) -> dict[str, float]:
    from noosphere.methods import get_method
    from noosphere.methods import nli_scorer as _registered_nli_scorer  # noqa: F401
    from noosphere.methods.nli_scorer import NLIInput

    _, nli_scorer_method = get_method("nli_scorer")
    score = nli_scorer_method(NLIInput(premise=premise, hypothesis=hypothesis))
    return {
        "entailment": score.entailment,
        "neutral": score.neutral,
        "contradiction": score.contradiction,
        "verdict": score.verdict,
    }


def detect_disagreements(
    objections: Iterable[ObjectionResult],
    *,
    threshold: float = 0.55,
    nli_score: Optional[NLIScoreFn] = None,
) -> list[ProviderDisagreement]:
    """Pairwise contradiction check across provider objections.

    Uses NLI on the objection text rather than string comparison —
    "the assumption is hidden" and "the assumption is explicit" share
    no surface tokens but are semantically opposed, and that is
    precisely what we want to surface to a human reviewer.
    """
    score = nli_score or _default_nli_scorer
    items = [o for o in objections if o.ok]
    out: list[ProviderDisagreement] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            scored = score(a.text, b.text)
            contradiction = float(scored.get("contradiction", 0.0))
            if contradiction >= threshold:
                out.append(
                    ProviderDisagreement(
                        provider_a=a.provider,
                        provider_b=b.provider,
                        objection_a=a.text,
                        objection_b=b.text,
                        contradiction_score=contradiction,
                    )
                )
    return out


__all__ = [
    "ObjectionResult",
    "ProviderAdapter",
    "ProviderDefaults",
    "ProviderDisagreement",
    "PROVIDER_DEFAULTS",
    "SYSTEM_PROMPT",
    "all_adapters",
    "available_providers",
    "build_user_prompt",
    "detect_disagreements",
    "env_key_present",
    "estimate_cost",
    "get_adapter",
    "register_adapter",
    "reset_registry",
]

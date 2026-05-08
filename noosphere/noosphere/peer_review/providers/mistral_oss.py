"""Open-source Mistral adapter (OpenAI-compatible HTTP API).

The point of this adapter is architectural diversity: by default the
swarm leans on three frontier vendors, all with similar safety
post-training, similar instruction-tuning data sources, and partly
overlapping pre-training corpora. An open-weights model served via a
local vLLM, TGI, or third-party endpoint gives the swarm a voice that
fails differently. The adapter speaks the OpenAI-compatible Chat
Completions schema since that is the de-facto interface for OSS model
servers (vLLM, TGI, llama.cpp, Ollama via openai-compat, etc.).
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from noosphere.peer_review.providers import (
    PROVIDER_DEFAULTS,
    SYSTEM_PROMPT,
    ObjectionResult,
    build_user_prompt,
    env_key_present,
    estimate_cost,
)


class MistralOSSAdapter:
    name = "mistral_oss"

    # Endpoint env vars are public knobs (URL, not a secret) but we
    # honour a default that points at localhost so the operator does
    # not have to set them when running a local vLLM server.
    _BASE_URL_ENV = "THESEUS_PEER_REVIEW_MISTRAL_BASE_URL"
    _DEFAULT_BASE_URL = "http://localhost:8000/v1"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        defaults = PROVIDER_DEFAULTS["mistral_oss"]
        self._defaults = defaults
        self._api_key = api_key if api_key is not None else os.environ.get(defaults.env_key, "")
        self.model = (
            model
            or os.environ.get(defaults.default_model_env, "")
            or defaults.default_model
        )
        self._base_url = (
            base_url
            or os.environ.get(self._BASE_URL_ENV, "")
            or self._DEFAULT_BASE_URL
        )

    def is_available(self) -> bool:
        # The OSS slot is "available" if either the operator set its
        # API key (third-party host like Together/Fireworks/Anyscale),
        # or they pointed it at a non-localhost base URL (self-host
        # gateway), which is the explicit opt-in signal.
        if self._api_key:
            return True
        if env_key_present(self._defaults.env_key):
            return True
        if os.environ.get(self._BASE_URL_ENV, "").strip():
            return True
        return False

    def produce_objection(
        self,
        *,
        claim: str,
        methodology: str,
        context: dict[str, Any],
        max_tokens: int = 512,
        temperature: float = 0.2,
        seed: Optional[int] = None,
    ) -> ObjectionResult:
        user_prompt = build_user_prompt(claim, methodology, context)
        api_key = self._api_key or os.environ.get(self._defaults.env_key, "") or "EMPTY"
        start = time.perf_counter()
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=self._base_url)
            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            }
            if seed is not None:
                kwargs["seed"] = seed
            resp = client.chat.completions.create(**kwargs)
            text = (resp.choices[0].message.content or "").strip()
            usage = getattr(resp, "usage", None)
            tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
            tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
            latency_ms = (time.perf_counter() - start) * 1000.0
            return ObjectionResult(
                provider=self.name,
                model=self.model,
                text=text,
                cost_usd=estimate_cost(
                    defaults=self._defaults,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                ),
                latency_ms=latency_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                seed=seed,
                extra={"base_url": self._base_url},
            )
        except Exception as exc:  # pragma: no cover
            latency_ms = (time.perf_counter() - start) * 1000.0
            return ObjectionResult(
                provider=self.name,
                model=self.model,
                text="",
                latency_ms=latency_ms,
                error=f"{type(exc).__name__}: {exc}",
                seed=seed,
            )

"""OpenAI GPT adapter for the multi-provider peer-review swarm."""

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


class OpenAIAdapter:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        defaults = PROVIDER_DEFAULTS["openai"]
        self._defaults = defaults
        self._api_key = api_key if api_key is not None else os.environ.get(defaults.env_key, "")
        self.model = (
            model
            or os.environ.get(defaults.default_model_env, "")
            or defaults.default_model
        )

    def is_available(self) -> bool:
        if self._api_key:
            return True
        return env_key_present(self._defaults.env_key)

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
        api_key = self._api_key or os.environ.get(self._defaults.env_key, "")
        start = time.perf_counter()
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key or "")
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

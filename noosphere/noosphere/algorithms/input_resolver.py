"""Adapter-fronted resolver for algorithm input slots.

The runtime walks an algorithm's declared inputs through this resolver
once per fire. Each :class:`AlgorithmInput` carries an
``observability_source`` string (e.g. ``currents.x.escalation_index``);
the resolver dispatches it to the longest-prefix
:class:`InputAdapter` registered in the
:class:`AdapterRegistry`.

Returning ``None`` means *no observation available right now* — the
caller (the runtime) treats this as a skip with reason
``INPUT_UNAVAILABLE``. Returning an observation whose ``value is None``
means *the source resolved but the value is missing*; rarely useful in
practice, but the distinction is preserved so future adapters can keep
it.
"""

from __future__ import annotations

from typing import Optional

from noosphere.algorithms.adapters import (
    AdapterRegistry,
    InputObservation,
)
from noosphere.algorithms.schemas import AlgorithmInput
from noosphere.observability import get_logger


logger = get_logger(__name__)


class InputResolver:
    """Resolve algorithm input slots through a shared adapter registry."""

    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry

    @property
    def registry(self) -> AdapterRegistry:
        return self._registry

    async def resolve(
        self, input_spec: AlgorithmInput
    ) -> Optional[InputObservation]:
        source = (input_spec.observability_source or "").strip()
        if not source:
            return None
        adapter = self._registry.adapter_for(source)
        if adapter is None:
            logger.warning(
                "algorithms.resolver.unknown_source",
                input_name=input_spec.name,
                source=source,
            )
            return None
        try:
            return await adapter.resolve(source)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "algorithms.resolver.adapter_error",
                input_name=input_spec.name,
                source=source,
                error=f"{type(exc).__name__}: {exc}",
            )
            return None


__all__ = ["InputResolver"]

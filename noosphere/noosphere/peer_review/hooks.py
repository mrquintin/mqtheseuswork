from __future__ import annotations

import logging
from typing import Any

from noosphere.models import Conclusion, ConfidenceTier

logger = logging.getLogger(__name__)

_swarm_queue: list[str] = []


def enqueue_swarm_review(conclusion_id: str) -> None:
    _swarm_queue.append(conclusion_id)
    logger.info("Enqueued swarm review for conclusion %s", conclusion_id)


def _on_firm_tier_conclusion(
    spec: Any, inv: Any, input_data: Any, result: Any
) -> None:
    if isinstance(result, Conclusion) and result.confidence_tier == ConfidenceTier.HIGH:
        enqueue_swarm_review(result.id)


def register_peer_review_hooks() -> None:
    from noosphere.methods import register_post_hook

    register_post_hook("peer_review.auto_queue", _on_firm_tier_conclusion)

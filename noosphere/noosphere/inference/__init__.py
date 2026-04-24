"""
Inference package: forward inference engine and inverse (back-propagation)
inference with blindspot detection.
"""

from noosphere.inference.inverse import InverseInferenceEngine, run_inverse
from noosphere.inference.blindspot import compute_blindspot, suggest_research


def __getattr__(name: str):
    """Lazy import for legacy forward-inference classes whose dependencies
    may not be fully available in all environments."""
    _LEGACY = {
        "AdversarialGenerator",
        "ConsistencyChecker",
        "InferenceEngine",
        "PrincipleRetriever",
        "ReasoningChain",
        "ReasoningStep",
    }
    if name in _LEGACY:
        from noosphere.inference import _engine  # noqa: F811

        return getattr(_engine, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Legacy forward inference (lazy)
    "AdversarialGenerator",
    "ConsistencyChecker",
    "InferenceEngine",
    "PrincipleRetriever",
    "ReasoningChain",
    "ReasoningStep",
    # Inverse inference
    "InverseInferenceEngine",
    "run_inverse",
    # Blindspot
    "compute_blindspot",
    "suggest_research",
]

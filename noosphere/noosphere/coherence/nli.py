"""
Coherence layer 1 — NLI-style scoring for claim pairs (DeBERTa cross-encoder).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from noosphere.models import Claim, CoherenceVerdict, SixLayerScore
from noosphere.observability import get_logger

logger = get_logger(__name__)


@dataclass
class NLIProbabilities:
    entailment: float
    neutral: float
    contradiction: float


def _softmax(logits: np.ndarray) -> np.ndarray:
    x = logits - np.max(logits)
    e = np.exp(x)
    return e / e.sum()


class NLIScorer:
    """
    Pair classifier using a cross-encoder (DeBERTa-v3 NLI head family).
    """

    def __init__(self, model_name: str = "cross-encoder/nli-deberta-v3-base") -> None:
        self.model_name = model_name
        self._model: Any = None
        self._nli_idx: Optional[tuple[int, int, int]] = None  # entailment, neutral, contradiction

    def _model_obj(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
            cfg = self._model.model.config
            id2label = getattr(cfg, "id2label", None) or {}
            ent = neu = con = None
            for k, v in id2label.items():
                i = int(k)
                name = str(v).lower()
                if "entail" in name:
                    ent = i
                elif "neutral" in name:
                    neu = i
                elif "contradict" in name:
                    con = i
            if ent is not None and neu is not None and con is not None:
                self._nli_idx = (ent, neu, con)
            else:
                # cross-encoder/nli-deberta-v3-base: 0=c, 1=e, 2=n
                self._nli_idx = (1, 2, 0)
        return self._model

    def _map_nli_probs(self, logits3: np.ndarray) -> tuple[float, float, float]:
        probs = _softmax(np.asarray(logits3, dtype=float).reshape(-1)[:3])
        ei, ni, ci = self._nli_idx or (1, 2, 0)
        return float(probs[ei]), float(probs[ni]), float(probs[ci])

    def score_pair(self, premise: str, hypothesis: str) -> tuple[NLIProbabilities, SixLayerScore, CoherenceVerdict]:
        logits = self._model_obj().predict([(premise, hypothesis)], show_progress_bar=False)
        arr = np.asarray(logits, dtype=float).reshape(-1)
        if arr.size >= 3:
            ent, neu, con = self._map_nli_probs(arr[:3])
        else:
            ent, neu, con = 0.33, 0.34, 0.33
        nli = NLIProbabilities(entailment=ent, neutral=neu, contradiction=con)
        s1 = float(1.0 - nli.contradiction)
        partial = SixLayerScore(s1_consistency=s1)
        if nli.contradiction >= 0.55 and nli.contradiction > nli.entailment:
            verdict = CoherenceVerdict.CONTRADICT
        elif nli.entailment >= 0.55:
            verdict = CoherenceVerdict.COHERE
        else:
            verdict = CoherenceVerdict.UNRESOLVED
        return nli, partial, verdict

    def score_claim_pair(self, a: Claim, b: Claim) -> tuple[NLIProbabilities, SixLayerScore, CoherenceVerdict]:
        return self.score_pair(a.text, b.text)

    def score_pairs_batch(
        self, pairs: list[tuple[str, str]]
    ) -> list[tuple[NLIProbabilities, SixLayerScore, CoherenceVerdict]]:
        logits = self._model_obj().predict(pairs, show_progress_bar=False)
        out: list[tuple[NLIProbabilities, SixLayerScore, CoherenceVerdict]] = []
        mat = np.asarray(logits, dtype=float)
        if mat.ndim == 1:
            mat = mat.reshape(1, -1)
        for row in mat:
            if row.size >= 3:
                ent, neu, con = self._map_nli_probs(row[:3])
            else:
                ent, neu, con = 0.33, 0.34, 0.33
            nli = NLIProbabilities(entailment=ent, neutral=neu, contradiction=con)
            s1 = float(1.0 - nli.contradiction)
            partial = SixLayerScore(s1_consistency=s1)
            if nli.contradiction >= 0.55 and nli.contradiction > nli.entailment:
                v = CoherenceVerdict.CONTRADICT
            elif nli.entailment >= 0.55:
                v = CoherenceVerdict.COHERE
            else:
                v = CoherenceVerdict.UNRESOLVED
            out.append((nli, partial, v))
        return out


class StubNLIScorer:
    """Test double with no transformer load."""

    def __init__(
        self,
        *,
        verdict: CoherenceVerdict = CoherenceVerdict.UNRESOLVED,
        partial: Optional[SixLayerScore] = None,
    ) -> None:
        self._verdict = verdict
        self._partial = partial or SixLayerScore(s1_consistency=0.5)

    def score_pair(
        self, premise: str, hypothesis: str
    ) -> tuple[NLIProbabilities, SixLayerScore, CoherenceVerdict]:
        return (
            NLIProbabilities(0.34, 0.33, 0.33),
            self._partial,
            self._verdict,
        )

    def score_claim_pair(self, a: Claim, b: Claim) -> tuple[NLIProbabilities, SixLayerScore, CoherenceVerdict]:
        return self.score_pair(a.text, b.text)

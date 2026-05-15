"""Dialectic engine for Currents opinions.

Each Currents opinion is paired with at least one canonical counter-claim
drawn from the firm's own graph plus a worked-out reconciliation (or an
explicit "we cannot reconcile" note).

Retrieval is a three-signal hybrid gate (Round 17 prompt 27). The first
version of this engine surfaced a counter-claim on embedding similarity to
the predicted contradiction location alone, and that admitted a steady
stream of false positives: claims that *sound* opposed but, on inspection,
do not actually contradict the firm's opinion. A candidate now has to
clear all three of:

  1. embedding similarity to the predicted contradiction location, above
     the calibrated floor (necessary, but the audit showed not sufficient);
  2. an NLI judgment that the candidate *actually contradicts* the firm's
     opinion — "opposes in tone" is not enough; and
  3. cascade-graph evidence — the candidate must be backed by at least one
     source the firm has previously taken seriously, not a floating claim.

All three must hold. The bar is intentionally high: a false-positive
counter-claim erodes trust faster than a missed one, so every gate fails
closed. The thresholds live in the unified config
(``noosphere.core.config`` -> ``Thresholds.dialectic``), calibrated against
the sample audit in ``docs/research/internal/Currents_Dialectic_Audit_*``.

The reconciliation pass is severity-weighted, not diplomatic. The prompt
forbids strawmanning the counter-claim, requires the strongest available
form of it, and accepts an explicit unresolved tension over a forced
reconciliation. After generation, the strawman detector
(``noosphere.currents.strawman_detector``) verifies the reconciliation's
restatement faithfully carries the retrieved counter-claim's actual text;
a softening paraphrase forces regeneration, and a repeated strawman
collapses to the honest no-counter note rather than persisting a soft
reconciliation.

Counter-claims must resolve to existing firm Conclusions or Claims. The
generator never fabricates a counter-claim out of thin air; if no candidate
clears all three gates, the opinion is published with an honest "no
canonical counter-claim found in firm history" marker rather than a
strawman.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    import numpy as np
except ImportError:  # pragma: no cover - fallback for broken local wheels.
    np = None  # type: ignore[assignment]

from noosphere.currents import strawman_detector
from noosphere.currents._llm_client import LLMResponse, make_client
from noosphere.currents.budget import BudgetExhausted

NO_COUNTER_FOUND_NOTE = "no canonical counter-claim found in firm history"
NO_COUNTER_UNCERTAINTY_TAG = "no_canonical_counter_claim_found"
RECONCILIATION_ROLE = "counter_claim"
RECONCILIATION_MAX_TOKENS = 700
# Documented fallbacks, used only when the unified config layer is
# unavailable. They MUST mirror ``DialecticThresholds`` in
# ``noosphere.core.config`` — the live values are read from there.
DEFAULT_COUNTER_SIMILARITY_FLOOR = 0.55
DEFAULT_COUNTER_NLI_CONTRADICTION_FLOOR = 0.60
DEFAULT_COUNTER_NLI_ENTAILMENT_MARGIN = 0.10
DEFAULT_COUNTER_CASCADE_WEIGHT_FLOOR = 0.25
DEFAULT_COUNTER_K = 32
DEFAULT_RECONCILIATION_MAX_ATTEMPTS = 2
COUNTER_QUOTED_SPAN_CHARS = 160


@dataclass(frozen=True)
class _DialecticThresholdsView:
    """Resolved threshold snapshot for one retrieval / reconciliation pass.

    Built from ``noosphere.core.config`` when available; falls back to the
    documented module constants above so the engine still runs (fail-closed)
    if the config layer cannot be loaded.
    """

    counter_similarity_floor: float = DEFAULT_COUNTER_SIMILARITY_FLOOR
    counter_nli_contradiction_floor: float = DEFAULT_COUNTER_NLI_CONTRADICTION_FLOOR
    counter_nli_entailment_margin: float = DEFAULT_COUNTER_NLI_ENTAILMENT_MARGIN
    counter_cascade_weight_floor: float = DEFAULT_COUNTER_CASCADE_WEIGHT_FLOOR
    counter_top_k: int = DEFAULT_COUNTER_K
    strawman_content_coverage_floor: float = (
        strawman_detector.FALLBACK_CONTENT_COVERAGE_FLOOR
    )
    strawman_length_ratio_floor: float = (
        strawman_detector.FALLBACK_LENGTH_RATIO_FLOOR
    )
    reconciliation_max_attempts: int = DEFAULT_RECONCILIATION_MAX_ATTEMPTS


def _dialectic_thresholds() -> _DialecticThresholdsView:
    """Read the dialectic thresholds from the unified config.

    Centralizing the magic numbers in ``noosphere.core.config`` is the
    Round 17 discipline; this helper is the one place the dialectic engine
    reads them. A config-layer failure degrades to the documented fallback
    constants rather than crashing the opinion pipeline.
    """

    try:
        from noosphere.core.config import get_settings

        cfg = get_settings().thresholds.dialectic
        return _DialecticThresholdsView(
            counter_similarity_floor=float(cfg.counter_similarity_floor),
            counter_nli_contradiction_floor=float(
                cfg.counter_nli_contradiction_floor
            ),
            counter_nli_entailment_margin=float(cfg.counter_nli_entailment_margin),
            counter_cascade_weight_floor=float(cfg.counter_cascade_weight_floor),
            counter_top_k=int(cfg.counter_top_k),
            strawman_content_coverage_floor=float(
                cfg.strawman_content_coverage_floor
            ),
            strawman_length_ratio_floor=float(cfg.strawman_length_ratio_floor),
            reconciliation_max_attempts=int(cfg.reconciliation_max_attempts),
        )
    except Exception:  # pragma: no cover - exercised only on a broken config.
        return _DialecticThresholdsView()


@dataclass(frozen=True)
class CounterClaim:
    """A canonical opposing claim drawn from the firm's own graph.

    Both `source_kind` and `source_id` resolve to an existing firm Conclusion
    or Claim — never a fabrication. A `CounterClaim` only exists if it cleared
    all three hybrid-retrieval gates:

    - `similarity` is the cosine similarity between the predicted
      contradiction location and the candidate's embedding (gate 1).
    - `nli_contradiction` / `nli_entailment` are the NLI probabilities for
      "(opinion headline) -> (this claim)"; the candidate cleared the gate by
      scoring contradiction above the floor *and* above entailment by the
      configured margin (gate 2 — "actually contradicts", not just opposes
      in tone).
    - `cascade_weight` snapshots the firm's load-bearing weight on the
      counter-claim; the candidate cleared gate 3 by having at least this
      much cascade backing, so later revisions can propagate and the
      counter-claim is provably one the firm has taken seriously.
    """

    source_kind: str
    source_id: str
    text: str
    similarity: float
    cascade_weight: float | None = None
    direction_method: str = "unknown"
    direction_low_confidence: bool = True
    exemplar_count: int = 0
    nli_contradiction: float = 0.0
    nli_entailment: float = 0.0


@dataclass(frozen=True)
class Reconciliation:
    """The 'where this could be wrong' pass result attached to an opinion."""

    counter_claim: CounterClaim | None
    reconciliation_markdown: str
    unresolved_tension: bool
    what_we_would_need_to_know: str
    strongest_form_of_counter_claim: str
    no_counter_found: bool
    model_name: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    audit: dict[str, Any] = field(default_factory=dict)


def _prompt_path(name: str) -> Path:
    return Path(__file__).resolve().parent / "_prompts" / name


def read_reconciliation_prompt() -> str:
    return _prompt_path("reconciliation.txt").read_text(encoding="utf-8").strip()


def _to_vector(value: Any) -> Any:
    if np is None:
        if hasattr(value, "tolist"):
            value = value.tolist()
        return [float(item) for item in value]
    return np.asarray(value, dtype=float).reshape(-1)


def _cosine(a: Any, b: Any) -> float:
    if np is not None:
        left = np.asarray(a, dtype=float).ravel()
        right = np.asarray(b, dtype=float).ravel()
        if left.size == 0 or right.size == 0 or left.shape != right.shape:
            return 0.0
        ln = float(np.linalg.norm(left))
        rn = float(np.linalg.norm(right))
        if ln <= 1e-12 or rn <= 1e-12:
            return 0.0
        return float(np.dot(left, right) / (ln * rn))
    left = list(map(float, a))
    right = list(map(float, b))
    if not left or len(left) != len(right):
        return 0.0
    ln = sum(x * x for x in left) ** 0.5
    rn = sum(x * x for x in right) ** 0.5
    if ln <= 1e-12 or rn <= 1e-12:
        return 0.0
    return sum(x * y for x, y in zip(left, right)) / (ln * rn)


def _is_revoked(item: Any) -> bool:
    if getattr(item, "revoked_at", None) is not None:
        return True
    status = getattr(item, "status", None)
    if status is not None:
        name = getattr(status, "name", None) or str(status)
        if name.upper() == "REVOKED":
            return True
    return False


def _is_private(item: Any) -> bool:
    visibility = getattr(item, "visibility", None)
    if visibility is None:
        return False
    name = getattr(visibility, "name", None) or str(visibility)
    return name.lower() == "private"


def _firm_endorsed(item: Any) -> bool:
    """Public, non-revoked firm-authored sources are endorsed by default.

    A counter-claim must resolve to something the firm has stood behind. A
    Conclusion on the firm's graph already implies the firm authored it; the
    revoked / private gates are the only filters needed. For Claims, we
    additionally require an internal origin (FOUNDER / INTERNAL / VOICE /
    LITERATURE) so that user-uploaded external claims do not count as the
    firm's own counter-arguments.
    """

    if _is_revoked(item) or _is_private(item):
        return False
    origin = getattr(item, "claim_origin", None)
    if origin is None:
        return True
    name = getattr(origin, "name", None) or str(origin)
    return name.upper() in {"FOUNDER", "INTERNAL", "VOICE", "LITERATURE"}


def _opinion_query_text(opinion_payload: dict[str, Any]) -> str:
    parts = [
        str(opinion_payload.get("headline", "") or ""),
        str(opinion_payload.get("body_markdown", "") or ""),
    ]
    return "\n".join(part for part in parts if part).strip()


def _opinion_assertion_text(opinion_payload: dict[str, Any]) -> str:
    """The firm's assertion, as an NLI premise.

    The embedding query uses headline + body so the geometric probe sees
    the whole opinion, but the NLI gate wants the firm's *claim* in a form
    a cross-encoder can hold in one pass. We use the headline (the firm's
    one-sentence position) and prepend the stance so a counter-claim is
    judged against what the firm actually asserts, not against neutral
    topic text.
    """

    headline = str(opinion_payload.get("headline", "") or "").strip()
    stance = str(opinion_payload.get("stance", "") or "").strip()
    body = str(opinion_payload.get("body_markdown", "") or "").strip()
    assertion = headline or body[:280]
    if stance and assertion:
        return f"The firm's position ({stance}): {assertion}"
    return assertion


def _embed(text: str) -> Any:
    from noosphere.currents import enrich

    return enrich.embed_text(text)


# Cross-encoder NLI scorer is loaded lazily and cached: the model load is
# expensive, but the same scorer serves every counter-claim candidate in a
# process. Tests monkeypatch `_nli_scores` directly rather than load it.
_NLI_SCORER: Any | None = None


def _get_nli_scorer() -> Any:
    global _NLI_SCORER
    if _NLI_SCORER is None:
        from noosphere.coherence.nli import NLIScorer

        _NLI_SCORER = NLIScorer()
    return _NLI_SCORER


def _nli_scores(premise: str, hypothesis: str) -> tuple[float, float]:
    """Return ``(contradiction_prob, entailment_prob)`` for premise -> hypothesis.

    This is the gate-2 seam: it answers "does this candidate *actually
    contradict* the firm's opinion" rather than the geometry probe's "does
    it live where an opposing claim would live". Raises on scorer failure;
    `find_counter_claim` treats a raise as fail-closed (the candidate is
    skipped), because surfacing a counter-claim we could not verify is
    exactly the false positive this engine exists to suppress.
    """

    scorer = _get_nli_scorer()
    nli, _partial, _verdict = scorer.score_pair(premise, hypothesis)
    return float(nli.contradiction), float(nli.entailment)


def _conclusion_iter(store: Any) -> Iterable[Any]:
    lister = getattr(store, "list_conclusions", None)
    if not callable(lister):
        return []
    return lister()


def _claim_iter(store: Any) -> Iterable[Any]:
    for name in ("list_claims", "iter_claims", "all_claims"):
        fn = getattr(store, name, None)
        if callable(fn):
            try:
                return fn()
            except TypeError:
                continue
    return []


def _candidate_embedding(item: Any) -> Any | None:
    existing = getattr(item, "embedding", None)
    if existing is not None and (
        (np is not None and getattr(existing, "size", 1) > 0)
        or (np is None and existing)
    ):
        try:
            return _to_vector(existing)
        except Exception:
            pass
    text = getattr(item, "text", "") or ""
    if not text.strip():
        return None
    try:
        return _to_vector(_embed(text))
    except Exception:
        return None


def _predicted_contradiction_location(
    query_embedding: Any,
) -> tuple[Any, str, bool, int]:
    """Return (predicted_vector, method, low_confidence, exemplar_count).

    Falls back to the symbolic-flip estimator when no calibrated exemplar
    pairs are available. The probe is required to be deterministic so the
    test fixture can plant an opposing claim and assert it is surfaced.
    """

    from noosphere.coherence.contradiction_direction import (
        predict_contradiction_location,
    )

    if np is None:  # pragma: no cover - numpy is a hard dependency at runtime.
        raise RuntimeError(
            "contradiction probe requires NumPy; install the currents extras"
        )
    arr = np.asarray(query_embedding, dtype=float).reshape(-1)
    predicted, direction = predict_contradiction_location(arr)
    if float(np.linalg.norm(direction)) <= 1e-12 or float(direction.alpha) <= 1e-12:
        from noosphere.coherence.contradiction_direction import (
            symbolic_antonym_direction,
        )

        flip = symbolic_antonym_direction(arr)
        norm = float(np.linalg.norm(flip))
        if norm > 1e-12:
            predicted = arr + flip
            return (
                predicted,
                "symbolic_antonym_flip_v1",
                True,
                int(direction.exemplar_count),
            )
    return (
        predicted,
        str(direction.method),
        bool(direction.low_confidence),
        int(direction.exemplar_count),
    )


def _cascade_weight_for(store: Any, source_kind: str, source_id: str) -> float | None:
    """Best-effort lookup of the firm's current cascade weight on a node.

    The cascade graph stores load-bearing weights on edges, not nodes; we
    surface the maximum incident weight as a proxy. Stores that do not
    expose a cascade graph return None and the audit field stays empty.
    """

    fetch = getattr(store, "cascade_weight_for", None)
    if callable(fetch):
        try:
            value = fetch(source_kind=source_kind, source_id=source_id)
            return None if value is None else float(value)
        except Exception:
            return None
    edges_fn = getattr(store, "iter_cascade_edges", None)
    if not callable(edges_fn):
        return None
    try:
        edges = list(edges_fn())
    except Exception:
        return None
    weight: float | None = None
    for edge in edges:
        if getattr(edge, "dst_id", None) != source_id and getattr(
            edge, "src_id", None
        ) != source_id:
            continue
        candidate = getattr(edge, "weight", None)
        if candidate is None:
            continue
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            continue
        weight = value if weight is None else max(weight, value)
    return weight


def find_counter_claim(
    store: Any,
    *,
    opinion_payload: dict[str, Any],
    excluded_source_ids: Iterable[str] = (),
    similarity_floor: float | None = None,
    nli_contradiction_floor: float | None = None,
    nli_entailment_margin: float | None = None,
    cascade_weight_floor: float | None = None,
    top_k: int | None = None,
) -> CounterClaim | None:
    """Surface the firm's strongest *genuine* counter-claim, or None.

    Three-signal hybrid gate. We predict where, in embedding space, the
    opinion's logical negation would lie (contradiction-direction probe),
    score the firm's own non-revoked, non-private endorsed Conclusions and
    Claims by cosine to that predicted location, then walk the candidates
    from most- to least-similar and return the first that clears **all
    three** gates:

    1. **Embedding similarity** at or above ``similarity_floor`` — the
       candidate lives where an opposing claim should live.
    2. **NLI contradiction** — an NLI judgment that the candidate *actually
       contradicts* the firm's opinion (contradiction probability at or
       above ``nli_contradiction_floor`` *and* exceeding entailment by at
       least ``nli_entailment_margin``). This is the gate that rejects
       "opposes in tone but does not actually contradict" false positives.
    3. **Cascade-graph evidence** — the candidate's incident cascade weight
       is at or above ``cascade_weight_floor``, i.e. it is backed by at
       least one source the firm has previously taken seriously, not a
       floating claim.

    Any gate that cannot be evaluated (NLI scorer raises, store exposes no
    cascade graph, candidate has no embedding) fails **closed**: that
    candidate is skipped. Surfacing a counter-claim the engine could not
    verify is the false positive this design exists to suppress.

    Citations already used by the opinion are excluded so the counter-claim
    is genuinely a different node. Thresholds default to the unified config
    (``noosphere.core.config`` -> ``Thresholds.dialectic``); callers may
    override per-call, which the test fixtures and the audit script do.
    """

    cfg = _dialectic_thresholds()
    similarity_floor = (
        cfg.counter_similarity_floor if similarity_floor is None else similarity_floor
    )
    nli_contradiction_floor = (
        cfg.counter_nli_contradiction_floor
        if nli_contradiction_floor is None
        else nli_contradiction_floor
    )
    nli_entailment_margin = (
        cfg.counter_nli_entailment_margin
        if nli_entailment_margin is None
        else nli_entailment_margin
    )
    cascade_weight_floor = (
        cfg.counter_cascade_weight_floor
        if cascade_weight_floor is None
        else cascade_weight_floor
    )
    top_k = cfg.counter_top_k if top_k is None else top_k

    query_text = _opinion_query_text(opinion_payload)
    if not query_text:
        return None

    excluded = {str(sid) for sid in excluded_source_ids if sid}
    available_conclusions = [
        item
        for item in list(_conclusion_iter(store))
        if str(getattr(item, "id", "") or "") not in excluded
        and _firm_endorsed(item)
    ]
    available_claims = [
        item
        for item in list(_claim_iter(store))
        if str(getattr(item, "id", "") or "") not in excluded
        and _firm_endorsed(item)
    ]
    if not available_conclusions and not available_claims:
        return None

    try:
        query_embedding = _to_vector(_embed(query_text))
    except Exception:
        return None

    try:
        predicted, method, low_confidence, exemplar_count = (
            _predicted_contradiction_location(query_embedding)
        )
    except Exception:
        return None

    candidates: list[tuple[float, str, str, str]] = []

    for conclusion in available_conclusions:
        cid = str(getattr(conclusion, "id", "") or "")
        if not cid:
            continue
        emb = _candidate_embedding(conclusion)
        if emb is None:
            continue
        sim = _cosine(predicted, emb)
        candidates.append(
            (float(sim), "conclusion", cid, str(getattr(conclusion, "text", "") or ""))
        )

    for claim in available_claims:
        cid = str(getattr(claim, "id", "") or "")
        if not cid:
            continue
        emb = _candidate_embedding(claim)
        if emb is None:
            continue
        sim = _cosine(predicted, emb)
        candidates.append(
            (float(sim), "claim", cid, str(getattr(claim, "text", "") or ""))
        )

    if not candidates:
        return None

    candidates.sort(key=lambda row: row[0], reverse=True)
    assertion_text = _opinion_assertion_text(opinion_payload)

    for sim, kind, cid, text in candidates[: max(1, int(top_k))]:
        # Gate 1 — embedding similarity. Candidates are sorted descending,
        # so the first below the floor means every remaining one is too.
        if sim < similarity_floor:
            break
        if not text.strip():
            continue

        # Gate 3 — cascade-graph evidence. Cheaper than NLI, so check it
        # first; a candidate with no recorded backing is rejected outright.
        cascade_weight = _cascade_weight_for(store, kind, cid)
        if cascade_weight is None or cascade_weight < cascade_weight_floor:
            continue

        # Gate 2 — NLI "actually contradicts". A scorer failure fails
        # closed: we skip the candidate rather than surface it unverified.
        try:
            nli_contradiction, nli_entailment = _nli_scores(assertion_text, text)
        except Exception:
            continue
        if nli_contradiction < nli_contradiction_floor:
            continue
        if nli_contradiction < nli_entailment + nli_entailment_margin:
            continue

        return CounterClaim(
            source_kind=kind,
            source_id=cid,
            text=text,
            similarity=sim,
            cascade_weight=cascade_weight,
            direction_method=method,
            direction_low_confidence=low_confidence,
            exemplar_count=exemplar_count,
            nli_contradiction=nli_contradiction,
            nli_entailment=nli_entailment,
        )

    return None


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("reconciliation response was not parseable JSON") from None
        return json.loads(text[start : end + 1])


def _references_counter(text: str, counter_id: str) -> bool:
    if not counter_id:
        return False
    return f"[C:{counter_id}]" in text


def no_counter_reconciliation(
    *,
    audit: dict[str, Any] | None = None,
) -> Reconciliation:
    """The honest no-counter case.

    Published verbatim under the opinion. The text is fixed so the firm
    does not paper over the gap with a freshly minted strawman.
    """

    return Reconciliation(
        counter_claim=None,
        reconciliation_markdown=(
            f"The firm has searched its own prior conclusions and claims for a "
            f"canonical counter-claim to this opinion and found none above the "
            f"similarity floor: {NO_COUNTER_FOUND_NOTE}. The firm's silence on "
            f"the other side of this question is reported here rather than "
            f"hidden, and the firm treats the absence as a flag for further "
            f"work rather than as evidence the opinion is uncontested."
        ),
        unresolved_tension=False,
        what_we_would_need_to_know="",
        strongest_form_of_counter_claim="",
        no_counter_found=True,
        audit=audit or {},
    )


def _regeneration_directive(verdict: strawman_detector.StrawmanVerdict) -> str:
    """The reinforcement appended to the user prompt on a strawman retry.

    A bare retry at temperature 0 would reproduce the rejected response
    verbatim, so the retry has to *change the prompt*: it tells the model
    exactly which softening signal the strawman detector caught and demands
    the counter-claim be restated at full force.
    """

    return "\n\n".join(
        [
            "PRIOR ATTEMPT REJECTED — STRAWMAN DETECTED",
            (
                "The previous reconciliation softened the counter-claim. "
                f"Reason: {verdict.reason}."
            ),
            (
                "Regenerate. State the counter-claim in its strongest form "
                "using the counter-claim's own load-bearing terms — do not "
                "paraphrase it weaker, do not shorten it to a gesture, do "
                "not introduce hedges ('arguably', 'to some extent', 'a "
                "minor', 'on balance') the firm's prior text never used. "
                "The strongest_form_of_counter_claim field must carry the "
                "full force of the counter_claim_text below."
            ),
        ]
    )


async def generate_reconciliation(
    *,
    opinion_payload: dict[str, Any],
    counter_claim: CounterClaim,
    budget: Any | None = None,
    client: Any | None = None,
    max_attempts: int | None = None,
) -> Reconciliation:
    """Run the strongest-objection prompt against (opinion, counter-claim).

    The system prompt forbids strawmanning, requires the strongest form of
    the counter-claim, and accepts unresolved tension. After each
    generation the strawman detector
    (``noosphere.currents.strawman_detector``) verifies the response's
    ``strongest_form_of_counter_claim`` faithfully carries the retrieved
    counter-claim's actual text. A softening paraphrase forces
    regeneration — up to ``max_attempts`` total tries, the prompt reinforced
    each round with the specific signal that was caught. If every attempt
    strawmans, the pass collapses to the honest no-counter note rather than
    persisting a soft reconciliation. Malformed responses (empty,
    unparseable, missing the inline counter reference) are not retried —
    they fall straight back to the honest note.
    """

    cfg = _dialectic_thresholds()
    if max_attempts is None:
        max_attempts = cfg.reconciliation_max_attempts
    max_attempts = max(1, int(max_attempts))

    system_prompt = read_reconciliation_prompt()
    if client is None:
        client = make_client()

    prompt_tokens_charged = 0
    completion_tokens_charged = 0
    last_strawman: strawman_detector.StrawmanVerdict | None = None
    regeneration_note = ""

    for attempt in range(1, max_attempts + 1):
        user_prompt = _reconciliation_user_prompt(
            opinion_payload, counter_claim, regeneration_note=regeneration_note
        )
        if budget is not None:
            authorize = getattr(budget, "authorize", None)
            if callable(authorize):
                try:
                    authorize(
                        max(1, (len(system_prompt) + len(user_prompt)) // 4 + 1),
                        RECONCILIATION_MAX_TOKENS,
                    )
                except BudgetExhausted:
                    if last_strawman is not None:
                        return _strawman_rejected_reconciliation(
                            counter_claim, last_strawman, attempt - 1
                        )
                    return no_counter_reconciliation(
                        audit={
                            "skipped": "budget_exhausted",
                            "counter_claim_id": counter_claim.source_id,
                        }
                    )

        response: LLMResponse = await client.complete(
            system=system_prompt,
            user=user_prompt,
            max_tokens=RECONCILIATION_MAX_TOKENS,
            temperature=0.0,
        )
        if budget is not None:
            charge = getattr(budget, "charge", None)
            if callable(charge):
                charge(response.prompt_tokens, response.completion_tokens)
        prompt_tokens_charged += int(response.prompt_tokens or 0)
        completion_tokens_charged += int(response.completion_tokens or 0)

        raw_text = (response.text or "").strip()
        if not raw_text:
            return no_counter_reconciliation(
                audit={
                    "skipped": "empty_reconciliation_response",
                    "counter_claim_id": counter_claim.source_id,
                    "attempts": attempt,
                }
            )

        try:
            payload = _extract_json_object(raw_text)
        except (ValueError, json.JSONDecodeError):
            return no_counter_reconciliation(
                audit={
                    "skipped": "unparseable_reconciliation_response",
                    "counter_claim_id": counter_claim.source_id,
                    "attempts": attempt,
                }
            )

        paragraph = str(payload.get("reconciliation_markdown") or "").strip()
        strongest = str(payload.get("strongest_form_of_counter_claim") or "").strip()
        unresolved = bool(payload.get("unresolved_tension"))
        needed = str(payload.get("what_we_would_need_to_know") or "").strip()

        if not paragraph or not _references_counter(
            paragraph, counter_claim.source_id
        ):
            return no_counter_reconciliation(
                audit={
                    "skipped": "missing_counter_reference",
                    "counter_claim_id": counter_claim.source_id,
                    "attempts": attempt,
                }
            )

        verdict = strawman_detector.detect_strawman(
            counter_text=counter_claim.text,
            strongest_form=strongest,
            reconciliation_markdown=paragraph,
            content_coverage_floor=cfg.strawman_content_coverage_floor,
            length_ratio_floor=cfg.strawman_length_ratio_floor,
        )
        if verdict.is_strawman:
            last_strawman = verdict
            regeneration_note = _regeneration_directive(verdict)
            continue

        if unresolved and not needed:
            needed = (
                "Specific firm-internal evidence that would close this tension "
                "has not yet been articulated."
            )

        audit = {
            "counter_claim_kind": counter_claim.source_kind,
            "counter_claim_id": counter_claim.source_id,
            "counter_claim_similarity": counter_claim.similarity,
            "counter_claim_cascade_weight": counter_claim.cascade_weight,
            "counter_claim_nli_contradiction": counter_claim.nli_contradiction,
            "counter_claim_nli_entailment": counter_claim.nli_entailment,
            "direction_method": counter_claim.direction_method,
            "direction_low_confidence": counter_claim.direction_low_confidence,
            "exemplar_count": counter_claim.exemplar_count,
            "reconciliation_attempts": attempt,
            "strawman_check": verdict.as_audit_dict(),
        }

        return Reconciliation(
            counter_claim=counter_claim,
            reconciliation_markdown=paragraph,
            unresolved_tension=unresolved,
            what_we_would_need_to_know=needed,
            strongest_form_of_counter_claim=strongest,
            no_counter_found=False,
            model_name=response.model or "",
            prompt_tokens=prompt_tokens_charged,
            completion_tokens=completion_tokens_charged,
            audit=audit,
        )

    # Every attempt strawmanned the counter-claim. The honest no-counter
    # note is more truthful than a persisted soft reconciliation.
    return _strawman_rejected_reconciliation(
        counter_claim, last_strawman, max_attempts
    )


def _strawman_rejected_reconciliation(
    counter_claim: CounterClaim,
    verdict: strawman_detector.StrawmanVerdict | None,
    attempts: int,
) -> Reconciliation:
    """Honest no-counter note for a counter-claim the model kept softening."""

    audit: dict[str, Any] = {
        "skipped": "strawman_rejected",
        "counter_claim_id": counter_claim.source_id,
        "attempts": attempts,
    }
    if verdict is not None:
        audit["strawman_reason"] = verdict.reason
        audit["strawman_check"] = verdict.as_audit_dict()
    return no_counter_reconciliation(audit=audit)


def _reconciliation_user_prompt(
    opinion_payload: dict[str, Any],
    counter: CounterClaim,
    *,
    regeneration_note: str = "",
) -> str:
    sections = [
        "FIRM OPINION JUST PUBLISHED",
        f"headline: {opinion_payload.get('headline', '')}",
        f"stance: {opinion_payload.get('stance', '')}",
        "body_markdown:",
        str(opinion_payload.get("body_markdown", "") or ""),
        "CANONICAL COUNTER-CLAIM FROM FIRM HISTORY",
        f"counter_claim_id: {counter.source_id}",
        f"counter_claim_kind: {counter.source_kind}",
        f"counter_claim_similarity: {counter.similarity:.6f}",
        f"counter_claim_nli_contradiction: {counter.nli_contradiction:.6f}",
        "counter_claim_text:",
        counter.text,
        "TASK",
        (
            "Write the firm's strongest-objection reconciliation against "
            "this exact counter-claim. Do not invent a different "
            "counter-claim. Strawmanning is the cardinal failure mode: the "
            "strongest_form_of_counter_claim field must carry the full "
            "force of counter_claim_text — same substance, no softening "
            "paraphrase, no introduced hedges."
        ),
    ]
    if regeneration_note:
        sections.append(regeneration_note)
    sections.append("Return only the JSON object specified in the system prompt.")
    return "\n\n".join(sections)


def counter_quoted_span(counter: CounterClaim) -> str:
    """Return a verbatim slice of the counter-claim text for citation rows.

    Persistence currently piggybacks on the OpinionCitation table, which
    requires `quoted_span` to be a verbatim substring of the cited source.
    We slice the head of the counter-claim text up to a fixed character
    budget so the audit row passes the store's verbatim check while still
    being legible in the UI as 'the counter-claim's own words'.
    """

    text = (counter.text or "").strip()
    if not text:
        return ""
    if len(text) <= COUNTER_QUOTED_SPAN_CHARS:
        return text
    head = text[:COUNTER_QUOTED_SPAN_CHARS]
    last_space = head.rfind(" ")
    if last_space >= 80:
        head = head[:last_space]
    return head


def reconciliation_metadata(reconciliation: Reconciliation) -> dict[str, Any]:
    """Encode reconciliation data for storage on an OpinionCitation row.

    Used by `opinion_generator` to attach the dialectic result to a
    counter-claim citation's `justification_metadata` JSON field. The
    `role` key is the stable hook the public API uses to identify the
    reconciliation row among the opinion's citations.
    """

    counter = reconciliation.counter_claim
    return {
        "role": RECONCILIATION_ROLE,
        "reconciliation_markdown": reconciliation.reconciliation_markdown,
        "unresolved_tension": bool(reconciliation.unresolved_tension),
        "what_we_would_need_to_know": reconciliation.what_we_would_need_to_know,
        "strongest_form_of_counter_claim": (
            reconciliation.strongest_form_of_counter_claim
        ),
        "no_counter_found": bool(reconciliation.no_counter_found),
        "counter_claim_kind": counter.source_kind if counter else "",
        "counter_claim_id": counter.source_id if counter else "",
        "counter_claim_similarity": counter.similarity if counter else 0.0,
        "counter_claim_cascade_weight": (
            counter.cascade_weight if counter else None
        ),
        "counter_claim_nli_contradiction": (
            counter.nli_contradiction if counter else 0.0
        ),
        "counter_claim_nli_entailment": (
            counter.nli_entailment if counter else 0.0
        ),
        "direction_method": (
            counter.direction_method if counter else "no_counter"
        ),
        "direction_low_confidence": (
            counter.direction_low_confidence if counter else True
        ),
        "exemplar_count": counter.exemplar_count if counter else 0,
        "model_name": reconciliation.model_name,
        "prompt_tokens": reconciliation.prompt_tokens,
        "completion_tokens": reconciliation.completion_tokens,
        "audit": dict(reconciliation.audit or {}),
    }

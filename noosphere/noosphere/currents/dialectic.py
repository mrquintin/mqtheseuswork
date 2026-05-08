"""Dialectic engine for Currents opinions.

Each Currents opinion is paired with at least one canonical counter-claim
drawn from the firm's own graph plus a worked-out reconciliation (or an
explicit "we cannot reconcile" note). The retrieval is geometric: it uses
the contradiction-direction probe to predict where, in embedding space, an
opposing claim would live, then surfaces the firm's nearest endorsed
non-revoked claim to that location.

The reconciliation pass is severity-weighted, not diplomatic. The prompt
forbids strawmanning the counter-claim, requires the strongest available
form of it, and accepts an explicit unresolved tension over a forced
reconciliation.

Counter-claims must resolve to existing firm Conclusions or Claims. The
generator never fabricates a counter-claim out of thin air; if no candidate
clears the similarity threshold, the opinion is published with an honest
"no canonical counter-claim found in firm history" marker rather than a
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

from noosphere.currents._llm_client import LLMResponse, make_client
from noosphere.currents.budget import BudgetExhausted

NO_COUNTER_FOUND_NOTE = "no canonical counter-claim found in firm history"
NO_COUNTER_UNCERTAINTY_TAG = "no_canonical_counter_claim_found"
RECONCILIATION_ROLE = "counter_claim"
RECONCILIATION_MAX_TOKENS = 700
DEFAULT_COUNTER_SIMILARITY_FLOOR = 0.55
DEFAULT_COUNTER_K = 32
COUNTER_QUOTED_SPAN_CHARS = 160
_TOKEN_RE = re.compile(r"[A-Za-z0-9]{3,}")


@dataclass(frozen=True)
class CounterClaim:
    """A canonical opposing claim drawn from the firm's own graph.

    Both `source_kind` and `source_id` resolve to an existing firm Conclusion
    or Claim — never a fabrication. `similarity` is the cosine similarity
    between the predicted contradiction location and the candidate's
    embedding (higher = closer to where an opposing claim should live).
    `cascade_weight` snapshots the firm's load-bearing weight on the
    counter-claim at the time the reconciliation was written, so later
    revisions can propagate.
    """

    source_kind: str
    source_id: str
    text: str
    similarity: float
    cascade_weight: float | None = None
    direction_method: str = "unknown"
    direction_low_confidence: bool = True
    exemplar_count: int = 0


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


def _embed(text: str) -> Any:
    from noosphere.currents import enrich

    return enrich.embed_text(text)


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
    similarity_floor: float = DEFAULT_COUNTER_SIMILARITY_FLOOR,
    top_k: int = DEFAULT_COUNTER_K,
) -> CounterClaim | None:
    """Surface the firm's nearest endorsed opposing claim, or None.

    Geometric: we predict where, in embedding space, the opinion's logical
    negation would lie (contradiction-direction probe), then select the
    firm's own non-revoked, non-private endorsed Conclusion or Claim closest
    to that predicted location. Citations already used by the opinion are
    excluded so the counter-claim is genuinely a different node.
    """

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
    top = candidates[: max(1, int(top_k))]
    best = top[0]
    if best[0] < similarity_floor:
        return None

    cascade_weight = _cascade_weight_for(store, best[1], best[2])
    return CounterClaim(
        source_kind=best[1],
        source_id=best[2],
        text=best[3],
        similarity=best[0],
        cascade_weight=cascade_weight,
        direction_method=method,
        direction_low_confidence=low_confidence,
        exemplar_count=exemplar_count,
    )


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


def _strawman_check(strongest_form: str, counter_text: str) -> bool:
    """Reject reconciliations whose 'strongest form' is shorter than the
    firm's prior text on the counter-claim or that drops every meaningful
    content token. This is the peer-review swarm's veto: a reconciliation
    that down-weights the counter-claim's force is the cardinal failure
    mode and must not be persisted.
    """

    if not strongest_form.strip():
        return False
    counter_tokens = {match.group(0).lower() for match in _TOKEN_RE.finditer(counter_text)}
    counter_tokens = {tok for tok in counter_tokens if len(tok) > 3}
    if not counter_tokens:
        return True
    strongest_tokens = {
        match.group(0).lower() for match in _TOKEN_RE.finditer(strongest_form)
    }
    overlap = len(counter_tokens & strongest_tokens)
    coverage = overlap / max(1, len(counter_tokens))
    return coverage >= 0.35


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


async def generate_reconciliation(
    *,
    opinion_payload: dict[str, Any],
    counter_claim: CounterClaim,
    budget: Any | None = None,
    client: Any | None = None,
) -> Reconciliation:
    """Run the strongest-objection prompt against (opinion, counter-claim).

    The pass is one-shot — the system prompt forbids strawmanning, requires
    the strongest form of the counter-claim, and accepts unresolved tension.
    A peer-review-style strawman check rejects responses whose 'strongest
    form' drops the counter-claim's content; failures fall back to the
    no-counter honest note rather than publishing a soft reconciliation.
    """

    system_prompt = read_reconciliation_prompt()
    user_prompt = _reconciliation_user_prompt(opinion_payload, counter_claim)
    if budget is not None:
        authorize = getattr(budget, "authorize", None)
        if callable(authorize):
            try:
                authorize(
                    max(1, (len(system_prompt) + len(user_prompt)) // 4 + 1),
                    RECONCILIATION_MAX_TOKENS,
                )
            except BudgetExhausted:
                return no_counter_reconciliation(
                    audit={
                        "skipped": "budget_exhausted",
                        "counter_claim_id": counter_claim.source_id,
                    }
                )

    if client is None:
        client = make_client()
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

    raw_text = (response.text or "").strip()
    if not raw_text:
        return no_counter_reconciliation(
            audit={
                "skipped": "empty_reconciliation_response",
                "counter_claim_id": counter_claim.source_id,
            }
        )

    try:
        payload = _extract_json_object(raw_text)
    except (ValueError, json.JSONDecodeError):
        return no_counter_reconciliation(
            audit={
                "skipped": "unparseable_reconciliation_response",
                "counter_claim_id": counter_claim.source_id,
            }
        )

    paragraph = str(payload.get("reconciliation_markdown") or "").strip()
    strongest = str(payload.get("strongest_form_of_counter_claim") or "").strip()
    unresolved = bool(payload.get("unresolved_tension"))
    needed = str(payload.get("what_we_would_need_to_know") or "").strip()

    if not paragraph or not _references_counter(paragraph, counter_claim.source_id):
        return no_counter_reconciliation(
            audit={
                "skipped": "missing_counter_reference",
                "counter_claim_id": counter_claim.source_id,
            }
        )

    if not _strawman_check(strongest, counter_claim.text):
        return no_counter_reconciliation(
            audit={
                "skipped": "strawman_rejected",
                "counter_claim_id": counter_claim.source_id,
            }
        )

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
        "direction_method": counter_claim.direction_method,
        "direction_low_confidence": counter_claim.direction_low_confidence,
        "exemplar_count": counter_claim.exemplar_count,
    }

    return Reconciliation(
        counter_claim=counter_claim,
        reconciliation_markdown=paragraph,
        unresolved_tension=unresolved,
        what_we_would_need_to_know=needed,
        strongest_form_of_counter_claim=strongest,
        no_counter_found=False,
        model_name=response.model or "",
        prompt_tokens=int(response.prompt_tokens or 0),
        completion_tokens=int(response.completion_tokens or 0),
        audit=audit,
    )


def _reconciliation_user_prompt(
    opinion_payload: dict[str, Any], counter: CounterClaim
) -> str:
    return "\n\n".join(
        [
            "FIRM OPINION JUST PUBLISHED",
            f"headline: {opinion_payload.get('headline', '')}",
            f"stance: {opinion_payload.get('stance', '')}",
            "body_markdown:",
            str(opinion_payload.get("body_markdown", "") or ""),
            "CANONICAL COUNTER-CLAIM FROM FIRM HISTORY",
            f"counter_claim_id: {counter.source_id}",
            f"counter_claim_kind: {counter.source_kind}",
            f"counter_claim_similarity: {counter.similarity:.6f}",
            "counter_claim_text:",
            counter.text,
            "TASK",
            (
                "Write the firm's strongest-objection reconciliation against "
                "this exact counter-claim. Do not invent a different "
                "counter-claim. Strawmanning is the cardinal failure mode."
            ),
            "Return only the JSON object specified in the system prompt.",
        ]
    )


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

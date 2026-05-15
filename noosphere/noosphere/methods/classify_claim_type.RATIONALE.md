# Classify Claim Type — Rationale

## Purpose

`classify_claim_type` categorises a single claim into one of five discourse
types: METHODOLOGICAL (how to think), SUBSTANTIVE (what is true),
META_METHODOLOGICAL (how to evaluate methods), MIXED (interleaved), or
NON_PROPOSITIONAL (not a truth claim). This separation is architecturally
critical: Noosphere's core brain stores only methodological knowledge, while
substantive conclusions are routed to the conclusions registry for calibration.

## Inputs

`ClassifyClaimTypeInput`:

- `claim_text` (str) — the claim to classify (required).
- `context` (str, default `""`) — surrounding context passed to the LLM.
- `claim_id` (str, default `""`) — id echoed onto the output; when empty, a
  hash-derived id is generated.

## Outputs

`ClassifyClaimTypeOutput` with `claim_id`, `discourse_type`, `confidence`, and —
for MIXED claims — `methodological_content` and `substantive_content`
decompositions, plus `method_attribution` (the reasoning method credited for a
SUBSTANTIVE claim) and free-text `decomposition_notes`.

The method emits no cascade edges and declares no `depends_on` methods. It is
registered `nondeterministic=False`: the heuristic fallback is deterministic and
the LLM is called with a tightly constrained JSON schema.

## Algorithm

1. Resolve `claim_id` (caller-supplied or hash-derived).
2. **Primary path:** call the LLM with `CLASSIFICATION_PROMPT` plus the claim and
   context; parse the JSON response into the output fields.
3. **Fallback path:** on any exception, `_heuristic_classify` runs keyword
   pattern matching over `METHOD_PATTERNS` / `SUBSTANTIVE_PATTERNS` and returns a
   discourse type with a deliberately low confidence in the **0.4–0.5** range to
   signal its reduced reliability.

> **Drift correction (2026-05-14).** Earlier revisions of this rationale gave the
> heuristic fallback's confidence range as "0.4–0.7". The actual range in
> `_heuristic_classify` is **0.4–0.5** (the four return paths emit 0.45, 0.5,
> 0.5, and 0.4). Corrected to match the code.

## Domain

Built on the assumption that discourse can be separated into methodological and
substantive layers. In practice the most interesting claims blur the boundary —
"the way to evaluate a moat is to ask what would destroy it" contains both a
method and an implicit substantive claim — which is what the MIXED category and
its decomposition handle. The method-attribution taxonomy (11 types) is assumed
exhaustive with UNKNOWN as a catch-all. No machine-checkable `DomainBound` is
declared.

## Failure Modes

This method has no `FAILURES.yaml` catalog; its limits are documented inline.

- **Boundary instability** — edge cases near category boundaries may still
  classify differently on re-invocation even though the method is flagged
  deterministic, because the LLM path is not perfectly constrained.
- **English-specific heuristics** — the fallback's keyword patterns are
  English-only and misfire on domain jargon (e.g. "method" in a chemistry
  context is substantive, not methodological).
- **Unsurfaced verifier disagreement** — the `ClaimTypeVerifier` (BART-MNLI
  zero-shot) is a separate verification step not invoked through this registered
  method, so disagreements between the discourse classifier and the type
  verifier are not surfaced here.

## References

No external research dependencies. Classification is LLM-driven with a
firm-curated keyword-heuristic fallback; there is no underlying paper the
registered method depends on. (The separate, non-invoked `ClaimTypeVerifier`
uses a BART-MNLI zero-shot classifier — out of scope for this method's
contract.)

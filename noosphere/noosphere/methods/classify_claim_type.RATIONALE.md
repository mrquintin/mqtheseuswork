# Classify Claim Type — Rationale

## What the method is trying to do

The classify_claim_type method categorises a single claim into one of five
discourse types: METHODOLOGICAL (how to think), SUBSTANTIVE (what is true),
META_METHODOLOGICAL (how to evaluate methods), MIXED (interleaved), or
NON_PROPOSITIONAL (not a truth claim). For MIXED claims, it decomposes them into
their methodological and substantive components. For SUBSTANTIVE claims, it
identifies which reasoning method produced the conclusion (deduction, induction,
analogy, empirical observation, etc.). This separation is architecturally
critical because the Noosphere's core brain stores only methodological knowledge;
substantive conclusions are routed to the conclusions registry for calibration.

## Epistemic assumptions

The method assumes that discourse can be cleanly separated into methodological
and substantive layers. In practice, most interesting intellectual claims blur
this boundary — "The way to evaluate a moat is to ask what would destroy it"
contains both a method and an implicit substantive claim about moat fragility.
The MIXED category handles this, but the decomposition is itself a judgment call.
The heuristic fallback classifier uses keyword pattern matching with deliberately
lower confidence scores (0.4–0.7) to signal its reduced reliability. The method
attribution taxonomy (11 types) is assumed to be exhaustive, with UNKNOWN as a
catch-all.

## Known failure modes

The LLM classification is marked nondeterministic=False because the heuristic
fallback is deterministic and the LLM is called with structured JSON output that
is highly constrained. However, edge cases near category boundaries may still
produce different results on re-invocation. The heuristic fallback's keyword
patterns are English-specific and may misfire on domain-specific jargon (e.g.,
"method" in a chemistry context is substantive, not methodological). The
ClaimTypeVerifier (BART-MNLI zero-shot) is not invoked through this registered
method — it remains a separate verification step — so disagreements between the
discourse classifier and the type verifier are not surfaced here.

## Dependencies

- **External LLM**: Requires a configured LLM client (Claude API via
  `llm_client_from_settings`). Falls back to heuristic keyword classification
  if the LLM is unavailable.

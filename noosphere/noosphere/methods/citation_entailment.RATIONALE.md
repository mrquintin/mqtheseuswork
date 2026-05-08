# Citation Entailment — Rationale

## What the method is trying to do

Most "did this source actually support the claim?" failures in the firm's
publication path are not retraction events. They are paraphrasing drift: the
firm cites paper P for claim X, paper P is actually about Y, and a chain of
intermediate citations has slowly turned X into something the original author
would not endorse. Source-standing (prompt 18) catches the *first* failure mode
— the cited paper got retracted, corrected, or expired. Source credibility
(prompt 19) catches the second — a source's track record can be weighed and
discounted. Citation entailment is the third leg: the cited *text* must
actually support the firm's stated claim.

This method is the per-citation NLI judge. Premise = a text excerpt drawn from
the underlying source; hypothesis = the firm's stated claim. It returns a
discrete verdict label (`entails`, `contradicts`, `neutral`, `ambiguous`)
plus the raw NLI probabilities. The `excerpt_used` and `stated_claim` fields
travel with the verdict so an auditor can re-derive the call from the recorded
inputs without depending on the live source text (which may have changed by
the time the audit runs).

The thresholds (0.55, beats-its-rival) match the legacy NLI scorer used by the
S1 coherence layer. They are duplicated rather than imported so a future
re-tuning of S1 doesn't silently move citation verdicts under the firm's feet.

## Epistemic assumptions

We assume the same things the legacy NLI head assumes — entailment, neutral,
and contradiction are exhaustive; the cross-encoder is reasonably calibrated;
domain transfer from SNLI/MultiNLI to firm-style claims is not catastrophic.
On top of that:

* The cited *excerpt* fairly represents what the source says about the firm's
  claim. The validator is responsible for windowing the excerpt around the
  cited region; this method does not re-window. Garbage-in still produces
  garbage-out — but it produces it on a recorded excerpt, so the failure is
  diagnosable.
* The firm's `relation` declaration is taken at face value. A cite declared
  `mentions` is treated as non-load-bearing: even if NLI says the excerpt
  entails the claim, we clamp the verdict to `ambiguous` to refuse the silent
  promotion of a passing reference into supporting evidence. Demoting in the
  other direction (a cite declared `supports` that NLI says is `neutral`) is
  *not* clamped — that is a finding worth surfacing.
* The model only sees the excerpt and the claim, not the surrounding
  conclusion. Implicit context (the firm has prior beliefs that change how the
  cite reads) is intentionally not given to the judge: if the cite cannot
  stand on its excerpt alone, the verdict should reflect that.

## Known failure modes

* **Out-of-domain claims.** Long technical or quantitative claims —
  econometrics, climate physics, regulatory law — produce poorly calibrated
  NLI probabilities. The verdict will tend to land on `ambiguous` for these.
  That is the right behavior for the publication gate (don't auto-fail), but
  ambiguous on a load-bearing cite escalates to founder triage downstream.
* **Negation scope errors.** "X is not robust" vs. "X is robust" — the legacy
  scorer is known to flip these in long sentences. A `contradicts` verdict on
  a `supports` cite must be reviewed in triage rather than auto-failed.
* **Length asymmetry.** A 200-word excerpt against a one-sentence claim biases
  toward `neutral` because most of the excerpt is unrelated to the claim.
  Callers should prefer a tight window around the cited region; the
  recommended default in the validator is ~150 words centered on the
  reported span.
* **Quotation detection.** If the firm's stated claim is a verbatim quotation
  from the source, the NLI head will (correctly) label it `entails` even when
  the surrounding context contradicts the quote. Quotation accuracy is a
  separate check; this method does not perform it.
* **Mentions-clamp asymmetry.** We clamp `mentions` + `entails` to
  `ambiguous`, but we do not clamp `mentions` + `contradicts` — a contradicting
  excerpt for what the firm called a passing reference is itself a finding.

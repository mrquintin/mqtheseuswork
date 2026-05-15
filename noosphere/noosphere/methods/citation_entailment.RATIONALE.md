# Citation Entailment — Rationale

## Purpose

Most "did this source actually support the claim?" failures in the firm's
publication path are not retraction events. They are paraphrasing drift: the
firm cites paper P for claim X, P is actually about Y, and a chain of
intermediate citations has slowly turned X into something the original author
would not endorse. Source-standing catches the *first* failure mode (the cited
paper got retracted, corrected, or expired); source credibility catches the
second (a source's track record can be discounted). `citation_entailment` is the
third leg: the cited *text* must actually support the firm's stated claim.

This method is the per-citation NLI judge. It returns a discrete verdict label
plus the raw NLI probabilities, and travels the inputs alongside the verdict so
an auditor can re-derive the call from the recorded excerpt without depending on
the live source text.

## Inputs

`CitationEntailmentInput`:

- `excerpt` (str) — the source text excerpt; the **premise** side of NLI. The
  caller is responsible for windowing it — this method does not re-trim.
- `stated_claim` (str) — the firm's claim about the source; the **hypothesis**
  side.
- `relation` (str, default `"supports"`) — the firm-declared relation type.
  `mentions` is treated as non-load-bearing (see Algorithm).

## Outputs

`CitationEntailmentOutput` with `relation_holds`
(`entails` / `contradicts` / `neutral` / `ambiguous`), `confidence` (the chosen
class probability, bounded to `[0, 1]`), `excerpt_used` and `stated_claim`
echoed back for the verdict row, the declared `relation`, the `model_version` of
the NLI head, and the three raw probabilities.

The method emits `COHERES_WITH` and `CONTRADICTS` cascade edges and is
registered `nondeterministic=False`. It declares no `depends_on` methods: it
duplicates the `0.55` / beats-its-rival thresholds of the legacy NLI scorer
rather than importing them, so a future re-tuning of the S1 coherence layer does
not silently move citation verdicts.

## Algorithm

1. Instantiate the legacy `NLIScorer` (lazy import) and `score_pair(excerpt,
   stated_claim)`.
2. `_label_from_probs`: a class must clear `0.55` **and** beat its rival to be
   picked; `entails` requires `entailment > contradiction`, `contradicts`
   requires `contradiction > entailment`, `neutral` requires it beat both.
   Otherwise the verdict is `ambiguous`, with confidence set to the max class
   probability.
3. **Mentions clamp:** if the firm declared the cite as `mentions` and NLI says
   `entails`, the verdict is clamped to `ambiguous` — a passing reference must
   not be silently promoted to supporting evidence. Demoting in the other
   direction (a `supports` cite that NLI reads as `neutral`) is **not** clamped:
   that is a finding worth surfacing.

## Domain

A per-citation adjudication step over a source excerpt and a firm claim. We
assume the same things the legacy NLI head assumes — entailment / neutral /
contradiction are exhaustive, the cross-encoder is reasonably calibrated, and
domain transfer from SNLI/MultiNLI to firm-style claims is not catastrophic. On
top of that: the cited excerpt must fairly represent what the source says (the
validator windows it; this method does not re-window); the firm's `relation`
declaration is taken at face value; and the judge sees only the excerpt and the
claim, not the firm's surrounding conclusion — if the cite cannot stand on its
excerpt alone, the verdict should reflect that. No machine-checkable
`DomainBound` is declared.

## Failure Modes

This method has no `FAILURES.yaml` catalog; its limits are documented inline.

- **Out-of-domain claims** — long technical or quantitative claims
  (econometrics, climate physics, regulatory law) produce poorly calibrated NLI
  probabilities and tend to land on `ambiguous`. That is the right behaviour for
  the publication gate, but an `ambiguous` on a load-bearing cite escalates to
  founder triage.
- **Negation scope errors** — "X is not robust" vs. "X is robust": the legacy
  scorer is known to flip these in long sentences. A `contradicts` verdict on a
  `supports` cite must be reviewed in triage rather than auto-failed.
- **Length asymmetry** — a 200-word excerpt against a one-sentence claim biases
  toward `neutral` because most of the excerpt is unrelated; callers should pass
  a tight window (~150 words centred on the cited span).
- **Quotation detection** — if the stated claim is a verbatim quotation, the NLI
  head will (correctly) label it `entails` even when the surrounding context
  contradicts the quote. Quotation accuracy is a separate check.
- **Mentions-clamp asymmetry** — `mentions` + `entails` is clamped to
  `ambiguous`, but `mentions` + `contradicts` is **not** clamped: a contradicting
  excerpt for a declared passing reference is itself a finding.

## References

- DeBERTa / DeBERTaV3, the NLI cross-encoder behind the verdict — [@he2021deberta],
  [@he2023debertav3].
- SNLI, a training corpus for the NLI head — [@bowman2015snli].
- MultiNLI, a training corpus for the NLI head — [@williams2018multinli].

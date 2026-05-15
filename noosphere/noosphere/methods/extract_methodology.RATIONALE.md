# extract_methodology — Rationale

## Purpose

Noosphere previously extracted object-level claims and only incidentally
classified a few as methodological. That lost the reusable part of serious
dialogue: the way a conclusion was reached.

`extract_methodology` produces deterministic methodology profiles from source
text. The profiles are intentionally not final judgments. They are structured
first-pass records that make later review, publication, and cross-domain
transfer ask:

- What reasoning move is being used?
- What assumption makes the move work?
- Where else might the move transfer?
- Where would this method fail?
- Which source sentences justify the profile?

It is deterministic (`nondeterministic=False`) because it runs in reanalysis
and backfills, where the same source must yield the same profile. A future LLM
pass can improve the prose, but it must write into the same profile-shaped
contract rather than inventing a new surface.

## Inputs

- `text` (str) — the source passage to analyse.
- `source_title` (str, default `""`) — title used to keep transfer targets
  honest (see Domain).
- `max_profiles` (int, default `6`) — requested profile count; clamped to
  `[1, 12]` inside the method.

## Outputs

`ExtractMethodologyOutput.profiles`: a list of `MethodologyProfileItem`, each
with `pattern_type`, `title`, `summary`, `reasoning_moves`, `transfer_targets`,
`assumptions`, `failure_modes`, `evidence_anchors`, and a `confidence` scalar.
The method emits an `EXTRACTED_FROM` cascade edge. It declares no `depends_on`
methods — it is a leaf extractor.

## Algorithm

The method delegates to `noosphere.methodology.derive_methodology_profiles`,
which scans the text for reasoning patterns — first-principles decomposition,
adversarial revision, analogical transfer, dialogic unfolding, value-to-design
reasoning, and empirical calibration — and emits one profile per pattern it can
anchor to source sentences. `max_profiles` is clamped to `[1, 12]` before the
call. No LLM is invoked; the pipeline is rule-based so it is reproducible.

## Domain

Built for transcripts and written documents that contain explicit reasoning. It
assumes methodological knowledge surfaces as describable moves; it is weak on
sources that *demonstrate* a method without narrating it (see Failure Modes).
The transfer targets describe reusable arenas for the method, not the source
topic — an education transcript may yield "institutional design" as a transfer
target, but the education conclusion is preserved only as source evidence, not
as a portable answer.

No machine-checkable `DomainBound` (see `domain_bounds.py`) is declared on this
method; applicability is enforced only by the prose contract above and by the
per-field source-anchor mitigations in the failure catalog.

## Failure Modes

Curated, machine-readable failure modes live in
[`extract_methodology.FAILURES.yaml`](extract_methodology.FAILURES.yaml). Do not
trust a profile when:

- **`profile_inflates_method_from_thin_text`** — thin or narrative source text
  produces a full-coverage profile by confabulation. The profile *looks*
  complete, which carries it past review.
- **`transfer_targets_smuggle_source_topic`** — on heavily on-topic sources the
  extractor lists the original domain itself as a transfer target.
- **`failure_modes_field_left_empty_treated_as_safe`** — a blank `failure_modes`
  field on a profile means "not assessed", not "assessed and clean"; downstream
  transfer use must not read the blank as a green light.

## References

No external research dependencies. The methodology pattern taxonomy is
firm-internal; see `docs/methods/MQS_Specification.md` and
`docs/methods/Aim_Method_Fit_Rubric.md` for how profiles are scored and used
downstream.

# Safety Properties

This document enumerates the ten safety properties the firm guards
with the load-bearing regression suite at `tests/safety/`. CI workflow
`.github/workflows/safety.yml` runs the suite on every PR; a failure
**blocks sync** until the property is repaired or — in the rare case
where the property itself needs to change — the change is reviewed by
the operator under the procedure in [Changing a property](#changing-a-property).

| Property | Test file | What it defends against |
| --- | --- | --- |
| P1 — Sandbox is unescapable | `tests/safety/test_sandbox.py::TestP1TriggerPredicateSandbox` | Code execution via algorithm trigger predicates |
| P2 — No unmocked network in tests | `tests/safety/test_sandbox.py::TestP2NoUnmockedNetwork` | Tests silently calling live APIs |
| P3 — pdflatex cannot shell-out | `tests/safety/test_sandbox.py::TestP3PdflatexShellEscape` | Code execution via memo PDF generation |
| P4 — Eight-gate contract | `tests/safety/test_eight_gates.py` | Unauthorized live trading |
| P5 — Verbatim citation discipline | `tests/safety/test_verbatim_citations.py` | LLMs fabricating source citations |
| P6 — Provenance policy | `tests/safety/test_provenance_policy.py` | Opposing-external material leaking into synthesis |
| P7 — No secrets in logs | `tests/safety/test_no_secrets_in_logs.py` | Key material leaking via observability |
| P8 — Operator HMAC | `tests/safety/test_operator_hmac.py` | Unauthorized operator-route access |
| P9 — Kill switch | `tests/safety/test_kill_switch.py` | Live submissions continuing during halt |
| P10 — Idempotency | `tests/safety/test_idempotency.py` | Double-write of memos, dispatches, invocations |

---

## P1 — Trigger-predicate sandbox is unescapable

**Threat model.** An algorithm draft contains a `trigger_predicate`
string that is `ast.parse`-d and `eval`-d by the runtime. A
sufficiently clever attacker who can stage a draft (or persuade a
maintainer to merge one) could embed `__import__('os').system(...)`,
attribute walks (`input.x.__class__.__mro__`), comprehensions that
iterate `__globals__`, lambdas, f-strings, or subscript chains. Any of
these would let the runtime execute arbitrary code under the
algorithm worker's permissions.

**Enforcing test.** Parametric fixture
`tests/safety/fixtures/adversarial_predicates.txt` lists every known
attack with the expected refusal-reason fragment. The test asserts
each line raises `AlgorithmValidationError`. A separate case proves
the legitimate happy path still validates. The runtime's
documented pause-after-three-refusals discipline is exercised by
asserting three consecutive refusals all raise.

**Acceptable conditions for change.** Adding to the allow-list of AST
node kinds (`_ALLOWED_NODES`) is the single change that is **not**
permitted without operator review — it widens the attack surface
directly. Removing nodes is always safe. New adversarial fixtures may
be added freely (they only strengthen the suite).

## P2 — Algorithm runtime makes zero unmocked network calls in tests

**Threat model.** A future regression silently re-introduces a live
HTTP call into the algorithm runtime or one of its adapters
(synthesizer, memo builder, KG reasoner). The tests "pass" in CI
because they happen to hit a flaky endpoint that returns 2xx, but
they would fail offline and would also be billing the firm's API
budget on every CI run.

**Enforcing test.** `TestP2NoUnmockedNetwork` monkeypatches
`httpx.AsyncClient.request` and `httpx.Client.request` with a
tripwire and imports the Round-19 LLM-touching modules. Any
request triggers an `AssertionError` from inside the patch.

**Acceptable conditions for change.** New LLM-touching modules MUST
be added to the import set in this test (so the tripwire stays
comprehensive). The patch itself is never weakened. If a new
non-mockable network surface is genuinely required, the operator
reviews the change and the test is widened to allow that one
endpoint by URL prefix — never by deleting the assertion.

## P3 — Memo PDF generation cannot execute arbitrary code

**Threat model.** pdflatex under `-shell-escape` interprets
`\write18{...}` as a shell command. A memo body containing such a
directive could exfiltrate data, modify the filesystem, or run
remote commands. The canonical build script must NEVER pass
`-shell-escape`.

**Enforcing test.** `TestP3PdflatexShellEscape` reads
`docs/memos/build_memo_pdf.sh` and asserts the forbidden flags are
absent and the constrained-mode flags are present. When `pdflatex`
is on PATH locally, the test additionally runs the canonical script
against `tests/safety/fixtures/adversarial_pdflatex.tex` (which
contains `\immediate\write18{touch /tmp/theseus-shell-escape-canary}`)
and asserts the canary file was NOT created. CI runners do not have
texlive installed; the test skips with a recorded reason so an
operator can verify it ran locally somewhere recently.

**Acceptable conditions for change.** Operator review required for
any change that would add `-shell-escape` or remove
`-interaction=nonstopmode` / `-halt-on-error`. Adding additional
constrained flags is always safe.

## P4 — Eight-gate safety contract stands

**Threat model.** Live trading happens only when EVERY gate is
green: trading enabled → credentials configured → prediction
authorized → bet confirmed → stake within ceiling → daily loss
within ceiling → kill switch clear → live balance covers stake.
Bypassing any one of them puts firm capital at risk.

**Enforcing test.** `test_eight_gates.py` has one test per gate
code (`DISABLED`, `NOT_CONFIGURED`, `NOT_AUTHORIZED`,
`NOT_CONFIRMED`, `STAKE_OVER_CEILING`, `DAILY_LOSS_OVER_CEILING`,
`KILL_SWITCH_ENGAGED`, `INSUFFICIENT_BALANCE`). The polymorphic-bet
variant verifies only `MARKET_BET` runs the eight gates;
`ADVISORY_BET`, `STRATEGIC_BET`, and `SCIENTIFIC_BET` MUST NOT
pick them up by accident.

**Acceptable conditions for change.** Operator review for ANY change
to a gate code or its evaluation order. New gates can be added (the
test must be extended to cover them); existing gates cannot be
removed without an explicit security review.

## P5 — Verbatim citation discipline holds

**Threat model.** An LLM-emitted reasoning chain cites
`prn_does_not_exist_999` (pure fabrication), or
`prn_safety_p5_real_OO1` (a one-character homoglyph of a real id),
or an empty string. Each is a citation-by-fabrication — the
synthesis cannot be audited because the cited source does not
exist or is not the one the LLM claims it is.

**Enforcing test.** `test_verbatim_citations.py` covers two
citing surfaces:

* algorithm reasoning chain — `validate_reasoning_chain`
  in `noosphere/algorithms/validators.py`
* synthesizer reasoning chain —
  `SynthesisEngine._parse_chain`

Each is exercised against four fabrication shapes from
`tests/safety/fixtures/almost_verbatim_citations.json`: exact match
(accept), fabricated id (reject), homoglyph id (reject), empty id
(reject). Memo body and knowledge-graph citation surfaces inherit
their provenance from these two upstream surfaces; their own
suites carry separate citation tests.

**Acceptable conditions for change.** Any change that loosens the
governing-set membership check (e.g., "treat near-miss ids as
matches") requires operator review. Strengthening the check
(e.g., adding verbatim-substring validation) is always safe and
should be accompanied by additional fixture cases here.

## P6 — Provenance policy is honored

**Threat model.** A synthesis configured with
`include_opposing_external=false` (the default) accidentally cites
an `OPPOSING_EXTERNAL` principle — either because the filter
broke, or because the LLM cited the principle id directly,
bypassing the filtered governing set.

**Enforcing test.** `test_provenance_policy.py` exercises
`default_provenance_filter()` against every `ProvenanceKind` and
asserts `OPPOSING_EXTERNAL` is dropped. Then it exercises
`SynthesisEngine._filter_by_provenance` over a mixed-provenance
principle set and verifies the opposing source is removed.
Finally, the adversarial case: a fabricated payload that cites the
filtered principle anyway MUST be refused by `_parse_chain`
(it's not in the governing set, so it's a fabrication).

**Acceptable conditions for change.** The default filter cannot be
loosened without operator review. Operators may tighten policy
(e.g., proprietary-only mode) without review; the test demonstrates
that pattern.

## P7 — No PII / secret in any log output

**Threat model.** A logging statement (or structured-log field, or
exception message, or env-dump endpoint) echoes the value of
`POLYMARKET_PRIVATE_KEY`, `KALSHI_API_PRIVATE_KEY`,
`DATABASE_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`FORECASTS_OPERATOR_SECRET`, `ALPACA_API_SECRET_KEY`, or
`ROBINHOOD_PASSWORD`. The secret then surfaces in CI logs, in a
shared logging tier, or in a screenshot the operator pastes.

**Enforcing test.** `test_no_secrets_in_logs.py` plants distinct
marker values for each secret env var, runs the surfaces that
read those vars (gate context builders, operator HMAC compute,
trading-mode probe), captures logs via `caplog` and `capsys`, and
asserts no marker appears. A second test scans every artifact under
`docs/verification/smoke/` for the same markers — used when smoke
runs precede the test, the artifacts must be clean too.

The failure message reports the env-var NAME and the hit COUNT only —
**never** the marker value and **never** the offending line. Doing
otherwise would itself leak the secret into the CI test report.

**Acceptable conditions for change.** Adding new secret env vars to
`_SECRET_MARKERS` is always safe and required when a new secret is
introduced. Removing an entry requires operator review.

## P8 — Operator HMAC secret guards operator routes

**Threat model.** An attacker discovers an operator endpoint and
calls it without a signature, with a wrong signature, with a stale
timestamp (replay attack), or with a body modified after signing.

**Enforcing test.** `test_operator_hmac.py` exercises
`require_operator` (the FastAPI dependency) directly against every
Round-19 operator-only route URL with four hostile shapes: missing
signature, wrong-secret signature, signature with stale timestamp
(beyond the 5-minute replay window), and signature with body
tampered after signing. The healthy path (valid signature, fresh
timestamp, untampered body) MUST be accepted. The current
implementation returns HTTP 401 for HMAC failures; the test pins
the actual status code. Operators changing this mapping (e.g., to
403 as in the original spec) must update the route AND the test.

**Acceptable conditions for change.** Adding a new operator route
requires extending `PROTECTED_ROUTES` in the test. Loosening the
auth check (e.g., shortening replay window, accepting unsigned
GETs) requires operator review.

## P9 — Kill switch blocks every live path

**Threat model.** The operator engages the kill switch and a live
order still goes out because a code path didn't consult the
portfolio state.

**Enforcing test.** `test_kill_switch.py` covers all four
`MARKET_BET` subkinds (`POLYMARKET`, `KALSHI`, `ALPACA`,
`ROBINHOOD`). For each: kill switch engaged → `GateFailure(code=
"KILL_SWITCH_ENGAGED")`; kill switch clear → no gate raises that
code. Other gates may still fail in isolation — that is fine; the
property under test is the kill-switch gate specifically.

**Acceptable conditions for change.** Any change that lets a code
path skip the kill-switch check requires operator review. Adding a
new MARKET_BET subkind requires extending the parametric coverage.

## P10 — Idempotency holds end-to-end

**Threat model.** A scheduler runs the algorithm runtime twice over
the same input observation and two invocations are persisted. A
synthesizer is triggered twice for the same question and two memos
are written. A portfolio agent dispatches a memo twice and two
`MemoDispatch` rows are created. A contradiction is evaluated twice
in the same time window under the same method version and two
results are stored. Each duplicate is a measurement error that
distorts calibration or an operator confusion that could trigger
duplicate live submissions.

**Enforcing test.** `test_idempotency.py` covers four surfaces:

* `canonical_input_hash` is order-independent and discriminating.
* `AlgorithmRuntime._is_recent_replay` returns True for identical
  inputs within the window, False outside it, and False for
  different inputs.
* `Store.put_investment_memo` is idempotent by id (three puts → one
  row).
* `Store.put_memo_dispatch` is idempotent by id (three puts → one
  row).
* The contradiction-engine canonical hash is stable across key
  orderings and discriminates on method-version bumps (the same
  primitive the runtime uses for replay detection).

**Acceptable conditions for change.** Operator review for any
change that introduces a non-deterministic component into a
canonical hash. Adding new surfaces (e.g., a new dispatch type)
requires extending this test.

---

## Changing a property

A safety property is changed by **failing the corresponding test
intentionally** in a PR, then:

1. Documenting the new threat model in this file under the relevant
   section.
2. Posting the PR for operator review with a `safety-property-change`
   label.
3. Updating the test in the same PR so the new property is
   enforced.
4. The operator approves the merge only after re-reading the threat
   model and signing off.

The CI workflow `.github/workflows/safety.yml` is required on the
main branch's branch-protection rules. **A failing safety job blocks
sync.**

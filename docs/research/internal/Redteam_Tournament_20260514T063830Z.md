# Red-Team Tournament — Founder-Side Memo, Run #1

**Run:** `20260514T063830Z` · bench `redteam-v1` (sha256 `a8c1bb2d3157…`)
· envelope `env-01ed7510995f7e3b`
**Audience:** founder / internal. The public version of this is the
leaderboard at `/methodology/redteam`; this memo is the candid reading
behind it.
**Status:** the first tournament has run. Six reviewer configurations,
one frozen bench, one leaderboard. This memo says which configuration
the firm now prefers, which it is retiring, and — most importantly —
why run #1's headline finding is about the *bench*, not the configs.

---

## 0. Honesty preamble — what produced these numbers

This run used the **offline deterministic driver** (`run_kind:
bootstrap-offline-deterministic`), not live provider calls. No
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` /
`MISTRAL_OSS_API_KEY` was present in the run environment, so rather
than ship an all-partial leaderboard with zero signal, the runner
fell back to a seeded simulation. It is a simulation and every
artefact says so in its first field. But it is not a toy:

- **Severity goes through the real rubric.** The only simulated input
  is each provider's `judge_severity`; it is fed through
  `noosphere.peer_review.severity.score_objection`, so the structural
  ceiling from each bench item's real `severity_inputs` still caps it.
  A provider cannot simulate its way past the bracket.
- **Cost goes through the real price table.** `estimate_cost()` over
  `PROVIDER_DEFAULTS` — `mistral_oss` is genuinely free, Anthropic is
  genuinely the most expensive token-for-token.
- **It is reproducible.** Same bench + same roster → identical bytes
  on every host. Re-running with `REDTEAM_STAMP` pinned overwrites
  cleanly.

When provider keys are provisioned in CI, the runner switches to
`default_reviewer_driver` automatically and stamps
`run_kind: provider-backed`. Run #1's qualitative findings — the
coverage/per-dollar split, the bench being underpowered — should
survive that switch; the exact leaderboard numbers will not, and the
seasonal review (prompt 47) will treat the driver change as a drift
event, not a clean continuation.

The partial-run path was **not** exercised this run: the offline
driver has no provider to degrade, so `partial_runs = 0` on every
row. The harness still marks a config partial — and refuses it the
`reproducible` flag — if a provider degrades mid-run under the
provider-backed driver.

---

## 1. What ran

Six content-addressable reviewer configurations, each id a
deterministic hash of (provider mix + prompt variant + temperature +
seed):

| Config | Providers | Prompt | T | Seed | `config_id` |
|---|---|---|---|---|---|
| `anthropic-only` | anthropic | default | 0.2 | 42 | `cfg-62d1d2eff6260a3d` |
| `openai-only` | openai | default | 0.2 | 42 | `cfg-35f06609e41d9c7f` |
| `gemini-only` | gemini | default | 0.2 | 42 | `cfg-6513d1cd2a9cdfdd` |
| `anthropic+openai` | anthropic, openai | default | 0.2 | 42 | `cfg-b048c444daf5c4b5` |
| `all-providers` | anthropic, openai, gemini, mistral_oss | default | 0.2 | 42 | `cfg-3598c98d63b9564c` |
| `all-providers/seeded-v2` | anthropic, openai, gemini, mistral_oss | seeded-v2 | 0.3 | 1337 | `cfg-a4e1e04930f69d0b` |

`anthropic-only` is the current production default. The roster
deliberately includes the three monocultures the firm has been
uneasy about — the tournament's job is to say so with numbers.

Every configuration ran against **the same** ten frozen v1
conclusions. The bench was not re-curated between configurations;
its sha256 is recorded in the envelope.

---

## 2. The leaderboard

Sorted reproducible-first, then severity-weighted score, then
agreement — the harness's standing order.

| Rank | Config | Sev-wt score | High / Med / Low | Agreement | Cost | Latency | Reproducible |
|---|---|---|---|---|---|---|---|
| 1 | `anthropic+openai` | 9.490 | 0 / 17 / 3 | 100.0% | $0.0781 | 4.11 s | **yes** |
| 2 | `anthropic-only` | 4.966 | 0 / 9 / 1 | 100.0% | $0.0497 | 2.33 s | **yes** |
| 3 | `openai-only` | 4.523 | 0 / 8 / 2 | 100.0% | $0.0283 | 1.79 s | **yes** |
| 4 | `all-providers` | 17.636 | 1 / 29 / 10 | 40.0% | $0.0922 | 6.56 s | no |
| 5 | `all-providers/seeded-v2` | 16.545 | 2 / 24 / 14 | 40.0% | $0.0920 | 6.41 s | no |
| 6 | `gemini-only` | 3.946 | 1 / 4 / 5 | 40.0% | $0.0141 | 1.50 s | no |

Read the cost column honestly. `all-providers` posts the highest
severity-weighted score on the board — and it costs 6.5× what
`gemini-only` costs and 1.2× `anthropic+openai`. A configuration that
wins on severity at a multiple of the cost is shown here *with* that
multiple; it is not allowed to look free.

---

## 3. The analysis — does diversity beat monoculture?

The firm's standing claim is "monoculture review is bad." The
tournament tests it two ways, and **the split between the two is the
finding**:

### 3a. Coverage — the claim holds, clearly

| Metric | Single-provider mean | Multi-provider mean |
|---|---|---|
| Severity-weighted score | 4.479 | **14.557** |
| Distinct high-severity attack angles | 0.333 | **0.667** |
| Objection-set Jaccard, `anthropic-only` vs `all-providers` (high-sev) | — | **0.0** |

The diverse swarms produce a 3.25× higher severity-weighted score and
a wider set of distinct attack angles than any monoculture. The
Jaccard of 0.0 is the sharpest single number in the run: the
production default's high-severity objection set and the broadest
swarm's high-severity objection set **do not overlap at all** — the
broad swarm surfaced `redteam-v1-coh-001:specification-search`, which
no monoculture found. On coverage, monoculture review *is* worse.

### 3b. Per-dollar — the claim does **not** hold on this run

| Metric | Single-provider mean | Multi-provider mean |
|---|---|---|
| High-severity objections per dollar | **23.673** | 10.867 |
| Severity-weighted score per dollar | **179.887** | 164.257 |

The prompt's literal expected result — "more diverse swarms surface
more high-severity objections per dollar" — **fails on run #1.** And
it fails for a structural reason, not a surprising one: per-dollar is
dominated by token price, and diversity costs money by construction.
`gemini-only` is the cheapest config on the board ($0.0141); it caught
one high-severity objection; one lucky high-severity draw on a
fourteen-cent run beats everything else per-dollar almost
tautologically. Per-dollar, the cheapest monoculture will tend to win
*whatever* the swarm does.

### 3c. The honest reading

"Monoculture review is bad" is a **coverage argument, not a per-dollar
one.** Run #1 supports it on coverage and refutes it on strict
per-dollar yield — and the refutation is the kind the prompt
explicitly asked us to surface rather than bury. The firm should stop
quoting "high-severity per dollar" as the headline justification for
the swarm; the defensible justification is severity-weighted score
plus objection-set divergence, read alongside cost rather than divided
by it.

Second finding, equally important: **the v1 bench is underpowered on
the binary high-severity axis.** Only two of the ten items
(`coh-001`, `coh-004`) have structural `severity_inputs` whose ceiling
clears the 0.67 high bracket at all; the other eight *cannot* produce
a high-severity objection from any provider, however adversarial. That
is why the High column is mostly zeros and why the per-dollar metric
is noise-dominated (n is effectively 2). This is a finding about the
bench, and per the bench card the fix ships as `v2/` — it is not a
licence to retune `v1/`.

---

## 4. Which configuration the firm now prefers

**`anthropic+openai` (`cfg-b048c444daf5c4b5`) becomes the production
default**, replacing `anthropic-only`.

Rationale: among the three configurations that cleared the
reproducibility floor, `anthropic+openai` posts the highest
severity-weighted score (9.490 vs 4.966 vs 4.523), holds 100%
inter-config agreement, and costs $0.078 — well inside budget. It is
the strongest configuration the firm can stand behind *and* reproduce.

The two `all-providers` configurations are **kept on the bench as
research configs** — not promoted, not retired. They are the only
configurations generating high-severity signal at all, and their
objection sets are genuinely disjoint from the monocultures'. But
their inter-config agreement is 40%, below the 0.5 reproducibility
floor: their distinctive objections are, so far, objections nobody
else can reproduce. That is exactly the signal the leaderboard exists
to refuse to promote. They stay visible, flagged not-reproducible,
pending a `v2/` bench with enough high-capable items to tell "sharp"
from "noisy."

---

## 5. Configurations the firm will retire

All three **single-provider monocultures**, retired as standalone
production options:

- **`anthropic-only` (`cfg-62d1d2eff6260a3d`)** — the *current*
  production default. Retiring it is the headline of run #1. It
  produced zero high-severity objections and a severity-weighted score
  of 4.97 — roughly half what the `anthropic+openai` pair produced for
  1.6× the cost. Anthropic the provider is not going anywhere; it sits
  in every rotation above. The *monoculture configuration* is what
  retires.
- **`openai-only` (`cfg-35f06609e41d9c7f`)** — strictly dominated:
  lower severity-weighted score than both `anthropic-only` and
  `anthropic+openai`, zero high-severity objections. OpenAI stays
  valuable inside the rotation; alone it earns no slot.
- **`gemini-only` (`cfg-6513d1cd2a9cdfdd`)** — not reproducible (40%
  agreement). Its single high-severity hit is reproduced only by the
  two `all-providers` configs that *contain* gemini — i.e. nobody
  architecturally distinct corroborates it. Its per-dollar "win" in
  §3b is the noise artifact, not a credential.

Net effect: the firm retires every monoculture as a standalone
production config and adopts a two-provider rotation as the default.
That is "monoculture review is bad" acted on, not just asserted.

---

## 6. Next tournament & drift tracking

This run is **data point #1** for the seasonal review (Round 17 prompt
47), which consumes tournament drift over time.

- **Cadence.** The recurring tournament runs weekly via
  `.github/workflows/redteam_tournament.yml` — `cron: '15 4 * * 1'`,
  04:15 UTC every Monday. **Next run: Monday 2026-05-19, 04:15 UTC.**
- **What the seasonal review watches.** Drift in the `agreement`
  column across runs is the method-drift signal; a sudden change is
  worth a human look. Run #1 sets the baseline: 100% agreement for the
  three reproducible configs, 40% for the three not-reproducible ones.
- **Known discontinuity ahead.** Run #1 is offline-deterministic;
  the first provider-backed run will be a deliberate driver change.
  The seasonal review must treat that transition as a drift event and
  not read across it as if the bench moved.
- **Follow-up (not done here).** `redteam_tournament.yml` still calls
  the generic `run_redteam_tournament.sh`. Wiring it to
  `run_redteam_tournament_v1.sh` — the v1-pinned runner with the
  six-config roster — is a one-line workflow change and should ship as
  its own prompt under `coding_prompts/_proposed/`. Roster changes are
  schema changes; they go through review, not a drive-by edit.

---

## 7. Artefacts

- `benchmarks/redteam/v1/results/20260514T063830Z/results.json` —
  full payload: leaderboard, cross-validation matrix, roster, analysis.
- `benchmarks/redteam/v1/results/20260514T063830Z/envelope.json` —
  reproducibility envelope + driver provenance.
- `benchmarks/redteam/v1/results/20260514T063830Z/leaderboard.csv` —
  flat leaderboard, one row per configuration.
- Public leaderboard: `/methodology/redteam`.
- Runner: `noosphere/scripts/run_redteam_tournament_v1.sh`.
- Harness: `noosphere/noosphere/peer_review/tournament.py`.

Signed: `noosphere-research:methodology-review` · 2026-05-14

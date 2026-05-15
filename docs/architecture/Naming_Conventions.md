# Naming Conventions

Round 17's parallel authorship produced naming drift across the codebase
(`methodology_quality_score` vs `mqs` vs `MQS`; `source_credibility` vs
`sourceCredibility`; `/methodology/[method]` vs `/methodology/[name]`).
This document is the single source of truth for how identifiers and URLs
are spelled. New code that violates it fails CI; existing violations are
catalogued by `scripts/survey_naming_violations.py` and resolved either by
codemod or with explicit founder approval.

## Scope

Style only. No behavioural change is justified by this document. Field
renames that cross any of these surfaces require an out-of-band review
*before* the rename lands:

- **Public-API envelope fields** (the `data` payload in versioned
  responses — see `docs/architecture/API_Envelope_Contract.md`).
  Renaming any field requires a schema-version bump.
- **Signed publication input** (the canonicalization rules from Round
  17). Renaming a field that participates in the canonical preimage
  invalidates every historical signature.
- **Public URL paths** that may have been linked-to or indexed
  externally. Renames are allowed but must leave a 308 alias in
  `theseus-codex/src/lib/urlAliases.ts`.
- **Database columns**. A column rename is a data-migration step, not a
  schema-only operation. Schema-only renames are permitted here; data
  renames are flagged in the survey for a follow-up migration that
  drops the alias view after a deprecation window.

## Conventions

### Python

| Construct | Convention | Example |
|---|---|---|
| Modules / files | `snake_case` | `methodology_quality_score.py` |
| Functions, methods | `snake_case` | `compute_source_credibility()` |
| Local variables, parameters | `snake_case` | `methodology_quality_score` |
| Classes | `PascalCase` | `class MethodologyQualityScore:` |
| Module-level constants | `UPPER_CASE` | `DEFAULT_WEIGHTS = {...}` |
| Type aliases | `PascalCase` | `MQSWeights = dict[str, float]` |
| Private helpers | leading underscore | `_normalise_weights()` |

Acronyms are treated as single words in PascalCase / lowercased in
snake_case. `MQS` becomes `Mqs` in `class MqsResult` and `mqs` in
`compute_mqs()` — never `methodology_quality_score` *and* `mqs` in the
same file for the same concept. Pick the canonical spelling once per
concept and use it consistently.

The canonical spelling for the four recurring offenders is:

| Concept | Canonical (Python) | Canonical (TS) | Canonical (URL slug) |
|---|---|---|---|
| Methodology Quality Score | `methodology_quality_score` (full); `mqs` *only* inside `noosphere.evaluation.mqs` and its callers | `methodologyQualityScore`; `mqs` only in tight scope | n/a |
| Source credibility | `source_credibility` | `sourceCredibility` | n/a |
| Methodology slug (URL param) | `method` | `method` | `[method]` |

### TypeScript

| Construct | Convention | Example |
|---|---|---|
| Functions, methods, vars | `camelCase` | `methodologyQualityScore` |
| Types, interfaces | `PascalCase` | `type MethodologyQualityScore = ...` |
| React components | `PascalCase` | `function MethodTabs() { ... }` |
| Module-level constants | `SCREAMING_SNAKE` | `const DEFAULT_WEIGHTS = ...` |
| Enum members | `PascalCase` | `enum Tier { High, Medium, Low }` |

`I`-prefixed interfaces (`IThing`) are not used. Hungarian prefixes are
not used.

### URLs

- Path segments are `kebab-case`. `/open-questions`, not
  `/open_questions` or `/openQuestions`.
- Path parameter names use the conceptual noun, not the storage type.
  `/methodology/[method]`, not `/methodology/[name]` or
  `/methodology/[methodId]` (unless the value is the integer id rather
  than the slug — then the *suffix* `Id` is intentional and
  load-bearing).
- Query parameters are `kebab-case` when used as filter keys, and
  `camelCase` only when they map 1:1 onto a TypeScript field name in a
  signed canonical request.
- A renamed public route MUST leave a 308 alias in
  `theseus-codex/src/lib/urlAliases.ts`. The middleware reads that
  table and issues the redirect before auth runs, so aliased paths
  resolve cleanly from any unauthenticated link.

### Database

- Columns and tables are `snake_case`. `source_credibility`,
  `methodology_quality_score`.
- Prisma models are `PascalCase`. `model SourceCredibility { ... }`
  with `@@map("source_credibility")` when the model name does not
  collapse to the table name automatically.
- Foreign-key columns end in `_id` (`methodology_id`), never `Id` or
  `_ref`.
- A column rename is a *data* migration:
  1. `ALTER TABLE ... RENAME COLUMN old TO new`,
  2. create a generated `old`-named column or compatibility view,
  3. update all callers,
  4. drop the alias after one release window.
  Schema-only renames (where the column has no rows or only rows
  written by this rename's branch) are permitted in style PRs;
  populated tables are flagged by the survey for a follow-up data
  migration.

### Files on disk

- Python: `snake_case.py`.
- TypeScript non-component modules: `camelCase.ts` (matches the
  exported symbol). React components: `PascalCase.tsx` (Next.js
  convention; the component name matches the file).
- Next.js route segments under `src/app/`: `kebab-case` directory
  names (`open-questions/`), with the special `page.tsx`,
  `layout.tsx`, `route.ts` filenames as Next.js defines them.
- Dynamic segment directories use the parameter convention from the
  URL section (`[method]`, not `[name]`).

## Enforcement

- `scripts/survey_naming_violations.py` walks the repo and lists every
  identifier and URL that violates the conventions above. It writes a
  machine-readable JSON report and a human-readable markdown summary.
  Manually-reviewable cases (public-API field names, signed-input
  fields, URLs with external link risk) are flagged separately for
  founder approval before any codemod runs.
- `scripts/check_naming_conventions.py` is the CI gate. It fails the
  build if new violations appear that are not on the approved
  allowlist.
- Ruff's `N` ruleset (pep8-naming) enforces the Python rules at lint
  time; configured in the root `pyproject.toml`.
- ESLint's `@typescript-eslint/naming-convention` enforces the
  TypeScript rules in `theseus-codex/.eslintrc.json`.

## Allowlist

When a violation is deliberate (third-party API field, signed-input
field that cannot be renamed without invalidating signatures, a
historical alias kept around to honour external links), add an entry
to the allowlist near the top of `scripts/check_naming_conventions.py`
with a one-line justification. The allowlist is the contract for what
CI will tolerate; everything else fails.

# Round 15 Currents and Coherence Regression

Date: 2026-05-07

## Preflight

- Repository: `/Users/michaelquintin/Desktop/Theseus`
- Prompt 01 SCOPE paths: 5/5 present
- Prompt 02 SCOPE paths: 6/6 present
- Prompt 03 SCOPE paths: 7/7 present
- Prompt 04 SCOPE paths: 3/3 present
- Prompt 05 SCOPE paths: 7/7 present
- Prompt 06 SCOPE paths: 7/7 present
- Prompt 07 SCOPE paths: 5/5 present
- Prompt 08 scripts: `scripts/migrate_production.sh` executable; `scripts/migrate_production_dry_run.sh` executable
- No production code was edited in this pass.

## A. Static Checks

### `pnpm --filter theseus-codex lint`

Exit status: 0

20-line tail:

```text
Scope: 2 of 4 projects
.../theseus-codex-starting-material lint$ eslint
theseus-codex lint$ tsc --noEmit --incremental false
.../theseus-codex-starting-material lint: /Users/michaelquintin/Desktop/Theseus/reference/theseus-codex-starting-material/src/app/contribute/ContributeForm.tsx
.../theseus-codex-starting-material lint:   38:41  warning  Image elements must have an alt prop, either with meaningful text, or an empty string for decorative images  jsx-a11y/alt-text
.../theseus-codex-starting-material lint: /Users/michaelquintin/Desktop/Theseus/reference/theseus-codex-starting-material/src/components/AttachmentPanel.tsx
.../theseus-codex-starting-material lint:    55:6  warning  React Hook useEffect has a missing dependency: 'load'. Either include it or remove the dependency array                                                                                                                                                                                  react-hooks/exhaustive-deps
.../theseus-codex-starting-material lint:   341:9  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element
.../theseus-codex-starting-material lint:   348:9  warning  Unused eslint-disable directive (no problems were reported from 'jsx-a11y/media-has-caption')
.../theseus-codex-starting-material lint:   352:9  warning  Unused eslint-disable directive (no problems were reported from 'jsx-a11y/media-has-caption')
.../theseus-codex-starting-material lint: /Users/michaelquintin/Desktop/Theseus/reference/theseus-codex-starting-material/src/lib/auth.ts
.../theseus-codex-starting-material lint:   41:36  warning  '_pw' is defined but never used      @typescript-eslint/no-unused-vars
.../theseus-codex-starting-material lint:   42:38  warning  '_pw' is defined but never used      @typescript-eslint/no-unused-vars
.../theseus-codex-starting-material lint:   42:51  warning  '_hash' is defined but never used    @typescript-eslint/no-unused-vars
.../theseus-codex-starting-material lint:   43:37  warning  '_userId' is defined but never used  @typescript-eslint/no-unused-vars
.../theseus-codex-starting-material lint:   45:37  warning  '_token' is defined but never used   @typescript-eslint/no-unused-vars
.../theseus-codex-starting-material lint: ✖ 10 problems (0 errors, 10 warnings)
.../theseus-codex-starting-material lint:   0 errors and 2 warnings potentially fixable with the `--fix` option.
.../theseus-codex-starting-material lint: Done
theseus-codex lint: Done
```

### `pnpm --filter theseus-codex tsc --noEmit`

Exit status: 0

20-line tail:

```text
Scope: 2 of 4 projects
None of the selected packages has a "tsc" script
```

### `ruff check noosphere`

Exit status: 127

20-line tail:

```text
zsh:4: command not found: ruff
```

Gap: the exact requested `ruff` executable is not available on `PATH` in this shell, so the regression pass stopped here.

### `ruff format --check noosphere`

Exit status: not run

Reason: stopped after `ruff check noosphere` failed.

## B. Unit + Integration

### `pytest noosphere/tests -q -k "currents or coherence or contradiction or methodology"`

Exit status: not run

Reason: stopped after `ruff check noosphere` failed.

### `pnpm --filter theseus-codex test -- OpinionCard XPostEmbed`

Exit status: not run

Reason: stopped after `ruff check noosphere` failed.

## C. Smoke

### `python coding_prompts/_audit_implementation.py`

Exit status: not run

Reason: stopped after `ruff check noosphere` failed.

### `bash scripts/migrate_production_dry_run.sh --allow-localhost`

Exit status: not run

Reason: stopped after `ruff check noosphere` failed.

## D. Visual

Screenshot path: `docs/regression/2026-05-07_x_post_corners.png`

Status: not created

Reason: stopped after `ruff check noosphere` failed before reaching the visual smoke step.

## Final

No-go: the regression pass cannot be treated as clean until `ruff check noosphere` can run successfully from the requested command surface.

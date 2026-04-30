# App-Building Prompts (Round 4)

8 Claude Code prompts that package the Theseus software suite into installable desktop applications and deployable web services for macOS and Windows.

## Prompt index

| # | Name | What it does | Depends on |
|---|------|-------------|------------|
| 01 | `dialectic_pyinstaller_config` | PyInstaller spec, frozen-mode resource resolver, placeholder icons, pyproject.toml | — |
| 02 | `founder_portal_electron_core` | Electron main process, Next.js server wrapper, preload, DB path resolver | — |
| 03 | `noosphere_cli_packaging` | PyInstaller spec, frozen-mode support, Alembic bundling, pyproject.toml | — |
| 04 | `deployment_configs` | Dockerfiles (Founder Portal + Public), docker-compose, Vercel/Netlify configs | — |
| 05 | `platform_builds_and_installers` | macOS DMG + Windows NSIS installer scripts for Dialectic and Noosphere | 01, 03 |
| 06 | `founder_portal_desktop_packaging` | electron-builder config, auto-updater, macOS + Windows build scripts | 02 |
| 07 | `ci_cd_build_pipelines` | GitHub Actions workflows for cross-platform builds + release publishing | 01–06 |
| 08 | `code_signing_and_notarization` | Apple notarization, Windows Authenticode, self-update checker | 01, 03, 05, 07 |

## Wave structure

Prompts within a wave touch disjoint file sets and can run in parallel. Waves must run sequentially.

- **Wave 1** (01, 02, 03, 04): Foundation — packaging configs, Electron core, deployment
- **Wave 2** (05, 06, 07, 08): Platform builds, CI/CD, signing, auto-update

## Running

Use the `run_prompts.sh` script at the repo root:

```bash
./run_prompts.sh                  # run all 8 prompts sequentially
./run_prompts.sh --from 5         # start at prompt 05
./run_prompts.sh --only 03        # run only prompt 03
./run_prompts.sh --dry-run        # show plan without executing
./run_prompts.sh --continue       # don't halt on failure
```

## Archive

The previous round-3 coding prompts (26 prompts) are in `archive_round3/`.

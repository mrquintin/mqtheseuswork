# CI secrets registry — documentation only.
#
# This file is *not* read by GitHub Actions. Secrets themselves live
# in the GitHub repo/org secret vault; this registry exists so the
# firm has one place to answer:
#
#   "Which workflow needs ${{ secrets.X }}? Under what env var name?
#    Why does CI need it at all?"
#
# Discipline:
#   - Every secret referenced by any workflow under .github/workflows/
#     must be listed below.
#   - Add or remove entries in the same PR that adds or removes the
#     `${{ secrets.X }}` reference; a stale row is a leak waiting to
#     happen.
#   - "Justification" should answer "why CI, not local-only?" — i.e.
#     what would break if we deleted this secret from the vault today.

# yaml-language-server: $schema=
#
# Schema (informal):
#
#   <SECRET_NAME>:
#     env_var: <ENV_VAR_NAME>            # how the workflow exposes it
#     workflows:                         # callers — list every consumer
#       - <workflow-filename.yml>
#     scope: org | repo | env:<name>     # where the value is stored
#     rotation: <cadence>                # how often to rotate
#     justification: <one-line reason>

ANTHROPIC_API_KEY:
  env_var: ANTHROPIC_API_KEY
  workflows:
    - redteam_tournament.yml
    - _setup_python.yml         # passthrough only — not a direct consumer
  scope: repo
  rotation: 90d
  justification: >-
    redteam_tournament rotates Claude as one of the reviewer voices in
    the adversarial peer-review swarm. Missing key is logged and that
    voice is skipped; CI does not fail.

OPENAI_API_KEY:
  env_var: OPENAI_API_KEY
  workflows:
    - redteam_tournament.yml
    - _setup_python.yml         # passthrough
  scope: repo
  rotation: 90d
  justification: >-
    Same as ANTHROPIC_API_KEY but for GPT-class reviewers.

GOOGLE_API_KEY:
  env_var: GOOGLE_API_KEY
  workflows:
    - redteam_tournament.yml
    - _setup_python.yml         # passthrough
  scope: repo
  rotation: 90d
  justification: >-
    Same as ANTHROPIC_API_KEY but for Gemini-class reviewers.

MISTRAL_OSS_API_KEY:
  env_var: MISTRAL_OSS_API_KEY
  workflows:
    - redteam_tournament.yml
    - _setup_python.yml         # passthrough
  scope: repo
  rotation: 90d
  justification: >-
    Same as ANTHROPIC_API_KEY but for Mistral-class reviewers. The
    "_OSS" suffix is historical and refers to the hosted OSS-Mistral
    endpoint, not Mistral SaaS.

# ---------------------------------------------------------------------
# Notes for reviewers
# ---------------------------------------------------------------------
#
# - The reusable `_setup_python.yml` declares the four LLM provider
#   secrets in its `workflow_call.secrets:` block as `required: false`.
#   Callers opt in by adding `secrets: inherit` at the call site.
# - No workflow under `.github/workflows/` should reference a secret
#   not present in this file. A pre-merge lint is intentionally NOT
#   implemented because the registry is small and review-by-eye is the
#   point — automating it would push the cost of adding a secret below
#   the cost of asking "do we really need this?".
# - Vars (e.g. `LOAD_TEST_STAGING_URL`) are NOT secrets and live in
#   GitHub's vars vault, documented inline in the consuming workflow.

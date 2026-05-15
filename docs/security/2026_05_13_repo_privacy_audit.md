# Theseus Repo Privacy Audit — 2026-05-13

**Auditor:** Codex dev-workflow prompt (Round 21).
**Repo:** `github.com/mrquintin/mqtheseuswork`
**Branch examined:** all refs (`git log --all`).
**Commits scanned:** 234 commits across all branches.

This document answers three questions the founder raised:

  1. Is the repo currently private?
  2. Have any credentials leaked through commits we already pushed?
  3. What is the exact procedure if a leak is found?

---

## 1. Current visibility — PUBLIC (must be flipped to PRIVATE)

`gh repo view mrquintin/mqtheseuswork --json visibility,isPrivate` reports:

```json
{ "isPrivate": false, "name": "mqtheseuswork", "visibility": "PUBLIC" }
```

**The agent CANNOT flip this bit.** GitHub deliberately requires the repo
owner to confirm the change in the browser. The founder must do it manually.

### Manual steps for the founder (≈ 60 seconds)

  1. Open `https://github.com/mrquintin/mqtheseuswork/settings`.
  2. Scroll to the very bottom — section titled **"Danger Zone"**
     (the heading is rendered in red text on the right edge of the page).
  3. Find the row labelled **"Change repository visibility"** with a button
     **"Change visibility"** on the right.
  4. Click that button. A modal appears with three options:
     `Public`, `Private`, `Internal`. Select **Private**.
  5. GitHub will prompt: *"To confirm, type `mrquintin/mqtheseuswork` below"*.
     Paste that exact string.
  6. Click **"I understand, change repository visibility"**. The red button
     greys out for a second, the modal closes, and the badge at the top of
     the repo page changes from `Public` to `Private`.
  7. Verify with `gh repo view mrquintin/mqtheseuswork --json isPrivate` —
     it should now print `{"isPrivate":true}`.

### What flipping to private does NOT do

It does **not** remove the repo from anyone's existing clone, fork, or
local copy. Any secret that was ever in a public commit must be treated as
*permanently exposed* and rotated, regardless of the current visibility
setting. See §3 below.

---

## 2. Credential-leak grep — RESULT: clean

The following greps were run across every commit on every branch:

```bash
git log --all -p -S 'sk-ant-api'           # Anthropic live keys
git log --all -p -S 'BEGIN RSA PRIVATE KEY'
git log --all -p -S 'BEGIN EC PRIVATE KEY'
git log --all -p -S 'BEGIN PRIVATE KEY'
git log --all -p -S 'sk_live_'             # Stripe live keys
git log --all -p -S 'AKIA'                 # AWS access keys
```

All six greps returned **no real-credential matches**.

The looser searches (`sk-ant-`, `private_key`, `POLYMARKET_PRIVATE_KEY=0x`)
do return hits, but every hit is one of:

  - Prompt text in `coding_prompts/NN_*.txt` that *describes* the pattern
    a credential validator should look for. No actual key value.
  - JSONL transcripts in `.claude_code_runs/*.raw.jsonl` where a previous
    Codex agent discussed credential-scanning. No actual key value.
  - The `scripts/check_no_secrets_in_code.py` regexes themselves.

No commit contains a real Anthropic, Stripe, AWS, RSA, EC, or generic
PEM-encoded private key.

### Files-of-concern scan

`git log --all --diff-filter=A --name-only` enumerates every file that has
ever been added on any branch (2,643 distinct paths). The intersection
with credential-shaped filenames is:

| File added | Verdict |
| --- | --- |
| `.env.example` | safe — template, no values |
| `.env.live.template` | safe — template, blank `KEY=` lines |
| `current_events_api/.env.example` | safe — template |
| `founder-portal/.env.example` | safe — template |
| `theseus-codex/.env.example` | safe — template |
| `theseus-public/.env.example` | safe — template |
| `scripts/check_no_secrets_in_code.py` | safe — the linter |

No `.pem`, `.key`, `.p12`, `.pfx`, `.cer`, `.keystore`, `id_rsa`, or
`id_ed25519` file has ever been added on any branch. No `.env`, `.env.live`,
or `.env.production` (the non-template variants) has ever been added.

**Conclusion: no rotation is required at this time.** The `.gitignore`
already blocks the dangerous non-template patterns (lines 34–48), and the
sync.sh hardening added by this prompt provides a redundant second line
of defence (§4).

---

## 3. What to do if a future audit DOES find a leak

If a future audit run (re-run the §2 greps quarterly, or after any incident)
turns up a real key in commit `<sha>` at path `<file>`, the recovery is:

### Step 1 — Rotate immediately (before touching git)

Assume the secret is compromised the moment it was pushed to a public
remote, even if the repo is now private. The order matters:

  1. **Rotate at the provider** (Stripe dashboard, Anthropic console,
     AWS IAM, Polymarket wallet rebind, etc.). The old value is dead from
     this moment on.
  2. **Record the rotation** in this audit doc: append a "Rotation log"
     section with `(timestamp, provider, old-key-fingerprint, who-rotated)`.
     Do NOT record the old key value itself.
  3. **Update `.env.live`** on every operator machine. Restart any service
     that read the old value.

Only after rotation is complete is it safe to do the history rewrite below.

### Step 2 — Purge the value from git history

The standard tool is `git-filter-repo` (preferred over the deprecated
`git filter-branch`). Install with `brew install git-filter-repo`.

```bash
# From a fresh, clean clone — NOT your working repo.
git clone --mirror https://github.com/mrquintin/mqtheseuswork.git
cd mqtheseuswork.git

# Build a replacements file. Each line replaces a literal string with
# the placeholder `REDACTED-2026-05-13`. ONE line per leaked value.
cat > /tmp/leaked-values.txt <<'EOF'
literal:sk-ant-api03-EXAMPLE-the-real-leaked-value==>REDACTED-2026-05-13
literal:0xfeedfacedeadbeef==>REDACTED-2026-05-13
EOF

git filter-repo --replace-text /tmp/leaked-values.txt

# Force-push the rewritten history. This is destructive — anyone who has
# cloned the public repo still has the original values locally. They are
# already burned by Step 1, which is why rotation comes first.
git push --force --all
git push --force --tags
```

### Step 3 — Notify and re-clone

  1. Tell every collaborator: *"history was rewritten on 2026-05-13.
     Delete your local clone and re-clone fresh."* Pulling on top of a
     rewritten history produces confusing merge conflicts.
  2. Re-issue any auto-sync cron entries (the local working tree is now
     desynced from the remote).
  3. Open a GitHub Support request asking them to expire cached views of
     the old commits (`https://support.github.com/contact?form%5Bsubject%5D=Repository+content+removal`).

### Step 4 — Audit dependent systems

A leaked Stripe/AWS/Anthropic key is presumed used. Check the provider's
usage logs for the 30 days preceding the leak discovery for charges,
inferences, or API calls not initiated by the operator. If unexplained
activity is found, treat the affected accounts as compromised and follow
the provider's incident-response playbook.

---

## 4. Defences added by this prompt

The previous protections were:

  - `.gitignore` rules covering `.env*` (with explicit `!template` and
    `!example` exclusions).
  - Manual review by the founder before committing.

This prompt adds three more:

  1. **`scripts/hooks/pre-commit.sh`** — runs the fast unit-test suites
     and `prisma format`/`prisma validate` before a commit is allowed.
     Installed via `scripts/hooks/install.sh`.
  2. **`run_prompts.sh --branch-mode`** — opt-in flag that runs each
     prompt on its own `auto/<round>/<NN>-<slug>` branch and opens a
     draft PR (when `gh` is available) instead of committing to main.
     Lets the founder review every prompt's output as a discrete unit.
  3. **`sync.sh` credential guard** — final-defence regex scan over the
     staged diff. If anything looks like an Anthropic / Stripe / AWS /
     PEM-shaped secret it refuses to push and prints the offending file.

These do not replace `.gitignore` — they catch the case where someone
deletes a `.gitignore` line or adds a new credential-bearing file in a
location the rules don't cover.

---

## 5. Recommended cadence

  - Re-run the §2 greps after every Round (≈ once a week given current
    cadence). Append the date and the result (clean / dirty) to a running
    log in this file.
  - Re-run the audit unconditionally before any future visibility flip
    (e.g. if the repo is ever made public again to share with a
    collaborator) — what's safe under "private" can leak under "public".
  - The pre-commit hook (§4.1) is the day-to-day defence; this audit is
    the periodic verification that the defence is holding.

---

## Audit log

| Date | Auditor | Result | Action taken |
| --- | --- | --- | --- |
| 2026-05-13 | Codex Round 21 prompt | Clean — no real credentials found in 234 commits. Repo confirmed PUBLIC; founder asked to flip to PRIVATE manually. | Added pre-commit hook, sync.sh credential guard, optional branch-per-prompt runner mode. |

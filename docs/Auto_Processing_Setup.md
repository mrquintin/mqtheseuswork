# Auto-processing: Codex upload → Noosphere pipeline

**What this gets you:** every upload on
`https://mqtheseuswork-qiw6.vercel.app/upload` is automatically
analyzed by Noosphere within ~60 seconds — claims extracted,
contradictions detected, open questions generated, all visible at
`/conclusions`, `/contradictions`, `/open-questions`, and `/ask`. No
local command to run, no waiting for you to notice.

Three trigger paths, so nothing falls through the cracks:

| Trigger | When | Latency |
|---|---|---|
| **`repository_dispatch`** | Codex fires a webhook the moment the Upload row is created | ~30 s to job start |
| **`schedule: '*/10 * * * *'`** | Cron sweep picks up anything stuck in `queued_offline` | up to 10 min |
| **`workflow_dispatch` + `/api/trigger-processing`** | Manual retry from the dashboard or `gh workflow run` | immediate |

All three run the same workflow — `.github/workflows/noosphere-process-uploads.yml` — calling the same `noosphere ingest-from-codex` CLI command.

---

## Setup — 4 secrets, ~5 minutes

### 1. Add secrets on GitHub (repo → Settings → Secrets and variables → Actions)

| Secret name | Value | Required? |
|---|---|---|
| `CODEX_DATABASE_URL` | Your Supabase **DIRECT** connection URL — port **5432**, not the 6543 pooler | **yes** |
| `OPENAI_API_KEY` | `sk-proj-…` from OpenAI | optional but recommended (enables LLM mode) |
| `ANTHROPIC_API_KEY` | `sk-ant-…` from Anthropic | optional (alternative to OpenAI) |

> **Where to find the DIRECT URL:** Supabase dashboard → Project Settings → Database → Connection string → **Direct connection** (not Session/Transaction). Format:
> `postgresql://postgres.<ref>:<pw>@aws-1-us-west-2.pooler.supabase.com:5432/postgres`
>
> If you used 6543 before for Prisma, that's the pooler — Noosphere needs 5432 because psycopg2 does DDL-like operations that some pooler modes reject.

### 2. Add secrets on Vercel (Project → Settings → Environment Variables)

| Variable name | Value | Required? |
|---|---|---|
| `GITHUB_DISPATCH_TOKEN` | A GitHub Personal Access Token with `repo` scope. Generate at https://github.com/settings/tokens/new | **yes** (for immediate dispatch; without it the cron still runs every 10 min) |
| `GITHUB_DISPATCH_REPO` | `mrquintin/mqtheseuswork` | optional (defaults to this already) |
| `OPENAI_API_KEY` | `sk-proj-…` | optional — only needed if you want Whisper transcription of audio uploads to work on Vercel (without it, audio uploads still succeed but transcription happens later in the GH Actions run) |
| `SUPABASE_URL` | `https://<ref>.supabase.co` (your Supabase project URL) | **yes for podcast uploads** — without this, audio is accepted but won't play on the blog |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase dashboard → Project Settings → API → `service_role` key | **yes for podcast uploads** — server-only; never ship to the browser |
| `SUPABASE_AUDIO_BUCKET` | Bucket name in Supabase Storage (default: `audio`) | optional (defaults to `audio`) |
| `MAX_AUDIO_BYTES` | Integer bytes cap on audio uploads (default: 52_428_800, i.e. 50 MB) | optional |

> **Podcast audio upload + playback setup:**
> 1. **Supabase dashboard → Storage → New bucket → name `audio`**. Mark **Public** so the blog post can serve the file directly.
> 2. **Project Settings → API**: copy the `service_role` key. Set it as `SUPABASE_SERVICE_ROLE_KEY` on Vercel (Production scope).
> 3. Copy your project URL (starts with `https://...supabase.co`) and set `SUPABASE_URL`.
> 4. Redeploy Vercel.
> 5. Upload an audio file at `/upload` with "Publish as blog post" checked. The form will:
>    - measure the file's duration client-side;
>    - POST to `/api/upload/audio/prepare` for a one-shot signed upload URL;
>    - PUT the audio bytes directly to Supabase Storage (bypasses Vercel's 4.4 MB serverless body cap);
>    - POST to `/api/upload/audio/finalize/:id` to commit the row and fire Noosphere processing.
> 6. Visit the post at `/post/<slug>` — you'll see an `<audio controls>` player at the top + the transcript below + the ⚡ LISTEN badge on `/`.
>
> Audio files up to 50 MB are accepted (≈40 min at 128 kbps, or 2+ hrs at 64 kbps). If `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` aren't set, audio upload still succeeds but `audioUrl` stays null and the blog renders text-only — so the pipeline degrades gracefully.

> **Creating the dispatch token:**
> - Go to https://github.com/settings/tokens (classic) OR https://github.com/settings/personal-access-tokens/new (fine-grained).
> - **Classic:** check `repo` scope (full).
> - **Fine-grained:** limit to the `mrquintin/mqtheseuswork` repo; permissions → Contents: Read & Write (dispatch endpoint requires this).
> - Expiry: pick however long you want; you can rotate any time.
> - Copy the `ghp_…` token and paste it into Vercel.

### 3. Redeploy Vercel once to pick up the new env vars

Either push any commit (the existing sync hook will redeploy) or click "Redeploy" in the Vercel dashboard.

### 4. (Optional) Test the pipeline manually first

```bash
# From a terminal with gh authed as mrquintin:
gh workflow run noosphere-process-uploads.yml -f with_llm=true
```

Or visit
`https://github.com/mrquintin/mqtheseuswork/actions/workflows/noosphere-process-uploads.yml`
and click **Run workflow**.

---

## What happens on every upload, end-to-end

```
┌─────────────────────────────────────────────────────────────┐
│  1. User drops a file at /upload                            │
│     → Codex POST /api/upload                                │
│     → extractText() pulls text out (PDF/DOCX/audio/etc.)    │
│     → Upload row created with status=pending               │
├─────────────────────────────────────────────────────────────┤
│  2. triggerNoosphereProcessing() fires GitHub dispatch      │
│     → Upload row status → processing (UI shows "analyzing") │
│     → GH Actions workflow starts within ~30s               │
├─────────────────────────────────────────────────────────────┤
│  3. Workflow installs Noosphere + runs ingest-from-codex    │
│     → reads Upload.textContent                              │
│     → LLM extracts claims + contradictions + questions      │
│     → writes Conclusion / Contradiction / OpenQuestion rows │
│     → Upload.status → ingested                              │
├─────────────────────────────────────────────────────────────┤
│  4. User sees results live at:                              │
│     /conclusions        firm-level claims + tiers           │
│     /contradictions     tensions between claims             │
│     /open-questions     questions to revisit                │
│     /research           suggested topics/readings            │
│     /ask                LLM-grounded Q&A over the corpus    │
└─────────────────────────────────────────────────────────────┘
```

Every failure mode has a fallback:

* **Dispatch token missing** → UI message: "Auto-processing skipped: 10-minute cron will pick it up." → cron runs 10 min later.
* **Dispatch returns non-2xx** (rate-limited, token revoked) → logged in `processLog`, cron retries.
* **Workflow itself fails** (dependency mismatch, transient network) → the scheduled sweep re-runs with `continue-on-error: true`; manual retry from `/dashboard` works any time.
* **Upload has no extractable text** → 422 on manual retry, with actionable error.

---

## Observability

* **Every dispatch is audited:** `AuditEvent` rows with `action=trigger_processing`.
* **Every ingest run is logged:** view at https://github.com/mrquintin/mqtheseuswork/actions/workflows/noosphere-process-uploads.yml.
* **Per-upload process log:** `Upload.processLog` is appended by both the Codex-side extraction and the GitHub-side ingest run.
* **UI status badge:** dashboard shows `pending | processing | ingested | queued_offline | failed` per row.

---

## Cost & limits

* **GitHub Actions minutes:** free tier = 2,000 min/month. Each sweep is <30 s idle / ~2–4 min with a real upload. Worst case at 6 sweeps/hour * 30s = 3 min/hour = ~2100 min/month — just over free tier; in practice idle runs exit in seconds and use much less. If you hit the cap, switch the cron to `*/30 * * * *` (every 30 min).
* **Supabase connections:** each run opens 1 Postgres connection for <60 s. Negligible.
* **OpenAI:** each `--with-llm` run is ~2–4k tokens depending on upload size. At `gpt-4o-mini` default pricing, that's well under $0.01 per upload.

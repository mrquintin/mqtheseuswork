# Deploying Theseus Codex to Vercel + Supabase (free tier)

This is a full runbook for going from `git push origin main` to a live URL at
`https://theseus-codex.vercel.app` (or whatever slug you pick), backed by a
Supabase Postgres that Noosphere also writes to, with Dialectic auto-uploading
session transcripts after every recording.

**End state:**

- Public URL — no custom domain required — `https://<your-slug>.vercel.app`
- Free Postgres at Supabase (500 MB cap; roomy for a long time)
- Dialectic sessions appear in the Codex dashboard automatically when the app
  stops a recording
- Noosphere runs locally and writes its conclusions to the same Postgres

Total setup time: roughly 30 minutes (first time; 5 minutes once you know the
dashboard clicks).

---

## 0. Prerequisites

- A GitHub account (you already have one — your repo is `mrquintin/mqtheseuswork`).
- A web browser.
- Nothing else. No Docker. No credit card for Vercel. Supabase asks for
  payment info only if you exceed the free tier (you won't, for a long time).

---

## 1. Create the Supabase project (5 min)

1. Go to [supabase.com](https://supabase.com) → **Start your project** → sign
   in with GitHub.
2. Click **New project**:
   - **Name**: `theseus-codex`
   - **Database password**: generate a strong one and save it to your password
     manager. You'll paste it into the DB URL below.
   - **Region**: pick the one closest to you. (Irrelevant for latency with
     Vercel; pick any.)
   - Plan: **Free**.
3. Wait ~2 minutes for the project to provision.
4. Once the dashboard loads, click **Project Settings** (gear icon, bottom-left)
   → **Database** → scroll to **Connection string** → **URI** tab.
5. Copy the **"Transaction pooler"** URL (port 6543, has `pgbouncer=true` in
   the query string). Not the direct connection. Paste it somewhere. It
   looks like:
   ```
   postgresql://postgres.<project-ref>:<db-password>@aws-0-<region>.pooler.supabase.com:6543/postgres?pgbouncer=true
   ```
   Vercel serverless burns through connection slots on the direct port;
   pgbouncer is what makes serverless + Postgres actually work.

You now have a free Postgres. Save the URL — that's your `DATABASE_URL`.

---

## 2. Apply the schema migration (3 min)

There are two ways:

### Option A — from your laptop (recommended, first-time only)

```bash
cd theseus-codex
export DATABASE_URL="postgresql://postgres.<ref>:<pw>@…pooler.supabase.com:6543/postgres?pgbouncer=true"
npx prisma migrate deploy
```

`migrate deploy` applies any unapplied migrations without prompting. On a
fresh Supabase DB it runs the `20260417000000_init` migration and creates all
the tables. Takes ~10 seconds.

### Option B — let Vercel do it on first build

Add a `postinstall` or `build` script that runs the migration. We already
generate the Prisma client on build; adding migrate-deploy is one line. Skip
this unless you specifically want a zero-laptop-setup path.

### Seed the first founder account

```bash
cd theseus-codex
export DATABASE_URL="…"                         # same URL as above
export SEED_FOUNDER_A_EMAIL="you@example.com"
export SEED_FOUNDER_A_PASSWORD="something-strong"
export SEED_FOUNDER_B_EMAIL="second-founder@example.com"
export SEED_FOUNDER_B_PASSWORD="something-strong-too"
npx tsx prisma/seed.ts
```

This creates the `theseus-local` organization and two founder accounts. You
log in with the email + password + org slug.

---

## 3. Connect Vercel to GitHub (5 min)

1. Go to [vercel.com](https://vercel.com) → **Sign up** → **Continue with GitHub**.
2. Grant Vercel access to the `mqtheseuswork` repo (or "All repos" if you
   prefer).
3. Click **Add New…** → **Project** → find `mqtheseuswork` → **Import**.
4. Configure the build:
   - **Framework Preset**: Next.js (should auto-detect).
   - **Root Directory**: click **Edit** → set to `theseus-codex` → **Continue**.
     (Without this, Vercel tries to build from the repo root and can't find
     `package.json`.)
   - **Build Command**: leave default (`npm run build`).
   - **Install Command**: leave default (`npm install`).
   - **Output Directory**: leave default.
5. Expand **Environment Variables** and paste these in (one row per var):

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | _(the Supabase pooler URL from step 1)_ |
   | `SESSION_SECRET` | _(run `openssl rand -hex 32` and paste the output)_ |
   | `OPENAI_API_KEY` | _(your OpenAI key)_ |
   | `ANTHROPIC_API_KEY` | _(your Anthropic key, if you use Claude models)_ |
   | `DEFAULT_ORGANIZATION_SLUG` | `theseus-local` |

   Skip `REDIS_URL` and `USE_JOB_QUEUE` for the first deploy — without them,
   the Codex just runs ingest in-process (fine for low traffic).

6. Click **Deploy**. First build takes ~3 minutes (Prisma generation,
   Next.js build, function bundling).

When it's green, you have a live URL like `https://theseus-codex-<hash>.vercel.app`.
Visit it — you should see the login page. Log in with a seeded founder
credential from step 2.

### Rename the public URL (optional)

In the Vercel project dashboard: **Settings** → **Domains** → the auto-generated
slug includes a random hash. You can rename the project (top-right settings
gear → General → Project Name) to get a cleaner URL like
`theseus-codex.vercel.app`. Vercel enforces uniqueness across all their users
so you may need a variation (`theseus-codex-mq.vercel.app`).

### Link it from the GitHub repo sidebar

1. Go to your repo on GitHub → top right ⚙ (Settings gear beside **About**) on
   the repo homepage.
2. Paste the Vercel URL into the **Website** field → **Save changes**.
3. The URL now appears next to the "About" blurb on your repo homepage —
   that's your "GitHub link" to the live site.

---

## 4. Point Noosphere at the same Postgres (2 min)

On any machine running Noosphere CLI (probably your laptop):

```bash
export THESEUS_DATABASE_URL="postgresql://postgres.<ref>:<pw>@…pooler.supabase.com:6543/postgres?pgbouncer=true"
pip install -r noosphere/requirements.txt          # picks up psycopg2-binary
python -m noosphere ingest --source dialectic --path session.jsonl
python -m noosphere synthesize
```

Conclusions written by `noosphere synthesize` land in the same Postgres the
Codex reads from. They appear in the `/conclusions` page immediately.

**Noosphere's own tables** (`artifact`, `claim`, `predictive_claim`,
`adversarial_challenge`, etc.) and **the Codex's Prisma tables**
(`Organization`, `Founder`, `Upload`, `Conclusion`, …) coexist peacefully in
the same `public` schema — they don't share table names. The Codex's
`/adversarial` page, for example, reads the SQLModel-owned
`adversarial_challenge` table directly via raw SQL (no Prisma mapping needed).

---

## 5. Mint an API key and wire up Dialectic auto-sync (3 min)

Dialectic's cloud uploader is off by default. Two env vars turn it on.

### 5a. Mint a key from the Codex

The simplest path for now is a direct POST since there's no settings UI page
yet:

```bash
# Set TCX_URL and TCX_COOKIE first. Cookie value: log into the Codex in a
# browser, open DevTools → Application → Cookies → copy the `theseus_session`
# value. It's an opaque signed string.
export TCX_URL="https://theseus-codex.vercel.app"
export TCX_COOKIE="<paste theseus_session cookie value>"

curl -X POST "$TCX_URL/api/auth/api-keys" \
  -H "Content-Type: application/json" \
  -H "Cookie: theseus_session=$TCX_COOKIE" \
  -d '{"label":"Dialectic on laptop"}'
```

Response looks like:
```json
{
  "id": "ckxyz…",
  "label": "Dialectic on laptop",
  "prefix": "abcd1234efgh",
  "plaintext": "tcx_abcd1234efgh_<48-char-secret>",
  "createdAt": "2026-04-17T…"
}
```

**Copy `plaintext` now — it's never shown again.** (You can revoke + mint a
new one at any time.)

### 5b. Set the env vars in Dialectic

Add these to your shell rc, or to a `.env` file Dialectic reads:

```bash
export DIALECTIC_CLOUD_URL="https://theseus-codex.vercel.app"
export DIALECTIC_CLOUD_API_KEY="tcx_abcd1234efgh_<secret>"
```

Run Dialectic (`python run.py` or open the `.app`). When you stop a session,
the status line now reads `Saved: … | Reflection: … | Cloud upload started.`
and the transcript appears in the Codex's `/uploads` page within a couple of
seconds.

Unset either env var to turn auto-sync off again — no code changes needed.

---

## 6. What doesn't work yet (known gaps)

- **Large binary uploads on Vercel.** Vercel serverless functions cap request
  bodies at 4.5 MB. Audio (`.wav`, `.mp3`), PDFs, and docx larger than that
  are rejected with a 413 and a message pointing at Supabase Storage. The fix
  is a pre-signed-URL direct-to-storage flow — I can implement it in a
  follow-up once you say the word. Text payloads (`.jsonl`, `.txt`, `.md`,
  `.vtt`) are fine: they're stored inline in Postgres.
- **Redis / job queue** is not wired up in the Vercel deployment. Uploads
  process in-process in the API route. For low traffic this is fine; for
  heavy batch ingest you'd add Upstash Redis (free tier, 10k commands/day)
  and flip `USE_JOB_QUEUE=1`.
- **Cold starts**: Supabase free tier pauses your database after 7 days of
  inactivity. First request after a pause takes ~30 s to warm up. Subsequent
  requests are fast. Supabase Pro ($25/month) removes the pause.
- **Custom domain**: you asked for "no custom domain" and that's what you
  get (`<slug>.vercel.app`). If you later want `codex.theseus.co` or similar,
  Vercel lets you add one for free on the Hobby plan — just point DNS at
  Vercel's CNAME.

---

## 7. Local development after the switch

Since the Codex is now Postgres-only, local dev needs a Postgres somewhere.
Two easy options:

### Option A — point at Supabase for dev too

Put the same Supabase `DATABASE_URL` in `theseus-codex/.env.local`. Your
local `npm run dev` reads from and writes to the same cloud DB as production.
This is fine for a one-person project; use a separate Supabase project for
prod once you have real users.

### Option B — local Docker Postgres

```bash
docker compose -f docker-compose.dev.yml up -d
# DATABASE_URL="postgresql://theseus:theseus@localhost:5432/theseus"
cd theseus-codex
npx prisma migrate deploy
npx tsx prisma/seed.ts
npm run dev
```

The `docker-compose.dev.yml` at the repo root provisions a local Postgres 16
container. Everything else (Next.js, Prisma, Noosphere) is unchanged.

---

## 8. Troubleshooting

**Build fails on Vercel with `PrismaConfigEnvError: Cannot resolve environment variable: DATABASE_URL`.**
You forgot to add `DATABASE_URL` in the Vercel env vars. Add it under
Settings → Environment Variables → apply to Production + Preview + Development.

**Login page loads but `/dashboard` 500s with "connection refused".**
Your `DATABASE_URL` is using the direct-connection port (5432) instead of
the pgbouncer port (6543). Swap ports in the URL. Serverless + direct
Postgres connections = broken.

**Dialectic upload always returns 401.**
API key is either wrong, revoked, or the `Authorization: Bearer tcx_…` prefix
is missing. Mint a fresh key via `/api/auth/api-keys` and verify the plaintext.

**Supabase project shows "paused"** (after a week of inactivity).
Click **Resume** in the project dashboard. Takes ~30 s. Dialectic uploads
done while paused will fail — retry after resume.

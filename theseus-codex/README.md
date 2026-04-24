# Theseus Codex

The Theseus Codex is the web-facing control plane for Theseus. It is where the firm's founders authenticate, upload the raw materials that the epistemic engine reasons over (podcast transcripts, essays, memos, Dialectic session files), trigger Noosphere processing, and read back the conclusions, contradictions, and research-advisor recommendations that the engine produces.

(Originally prototyped as `founder-portal/`; renamed to reflect that it builds on and replaces the earlier `theseus-codex/` starting material. The original starting material is preserved at `reference/theseus-codex-starting-material/` for provenance.)

## Stack

Next.js 16 (App Router) · React 19 · TypeScript · Prisma 7 · SQLite · bcryptjs for password hashing · Tailwind v4 · running against a local Noosphere installation through a thin Python bridge.

## Layout

```
theseus-codex/
├── prisma/
│   ├── schema.prisma       Founder, Upload, Conclusion, Contradiction models
│   └── seed.ts             Seeds initial founder accounts
├── src/
│   ├── app/
│   │   ├── api/upload/     POST multipart upload + async processing route
│   │   ├── (authed)/       Dashboard, uploads list, conclusion browser
│   │   └── login/
│   ├── components/         UI primitives + panel components
│   └── lib/
│       ├── auth.ts         Session + bcrypt verification
│       ├── ingest.ts       Shells out to noosphere CLI, streams logs back
│       └── db.ts           Prisma client singleton
└── package.json
```

## Typical flow

A founder logs in with their credentials (seeded by `prisma/seed.ts`). They upload a transcript or session file through `POST /api/upload`, which writes the file, creates an `Upload` row, and kicks off `ingest.ts` asynchronously. `ingest.ts` spawns `python -m noosphere ingest` followed by `python -m noosphere synthesize`, streaming stdout back into the database so the UI can show live progress. When synthesis finishes, the dashboard lists the new conclusions, any contradictions the coherence engine flagged, and the research advisor's suggested topics and readings for the next discussion.

## Running locally

```
npm install
npx prisma migrate dev
npx prisma db seed
npm run dev
```

The portal assumes a working Noosphere install at `../noosphere/` and calls it via the user's Python environment — no network hop, no serverless layer.

# Deploying theseus-public on Vercel with an external currents API

Since prompt 08 dropped `output: "export"`, theseus-public now requires a runtime. Vercel is a native target.

## Required environment variables (set in Vercel project settings)

- `CURRENTS_API_URL` — publicly reachable URL of current_events_api (e.g. `https://currents-api.theseus.example`). TLS mandatory.
- `PUBLIC_SITE_ORIGIN` — `https://theseus.example` (used for OG URLs).

## Routing

The Next.js route handlers under `/api/currents/*` proxy to `CURRENTS_API_URL`, including SSE streams. Vercel's Node runtime keeps long-lived connections open under the Fluid pricing tier — confirm your plan supports it, or serve SSE directly from the API host and point `EventSource` there. That alternative is a larger change and not in scope here.

## Caching

`GET /api/currents/feed` uses `export const dynamic = "force-dynamic"` so Vercel will not cache opinion lists. Do not add `revalidate`.

## Build

No special build step. `npm run build && npm run start` as usual. Do NOT set `NEXT_BUILD_TARGET=standalone` on Vercel.

## Existing vercel.json and netlify.toml

The repo's `vercel.json` / `netlify.toml` were written for the static-export era (prior to prompt 08). Update them to remove the `outputDirectory: "out"` / `publish = "out"` assumptions before deploying. This prompt does not edit those files to avoid disrupting existing deploys that may still be live.

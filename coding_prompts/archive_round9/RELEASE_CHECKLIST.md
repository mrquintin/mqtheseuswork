# Release checklist -- merger + Currents

## Merger
- [ ] / public homepage renders cleanly on theseuscodex.com
- [ ] /dashboard auth still gated
- [ ] All migrated routes (/methodology, /methods, /interop, /c/[slug], /open-questions, /responses, RSS, Atom) return 200
- [ ] theseus-public is gone from tree (under reference/)

## Currents
- [ ] /currents shows seed opinions (or empty state)
- [ ] CurrentsNavPulse visible in nav
- [ ] /currents/[id] detail page + source drawer + follow-up chat work
- [ ] Permalink button copies URL without UTM params
- [ ] Transparency footer present at bottom of /currents*
- [ ] Homepage teaser appears when API is up; homepage still renders when API is down

## Backend
- [ ] FastAPI service /healthz returns 200
- [ ] Scheduler status file is fresh (mtime < 600s)
- [ ] /metrics endpoint scrapes
- [ ] One full ingest cycle visible in scheduler logs

## Tests
- [ ] `pytest -q` green for all noosphere/, current_events_api/ tests
- [ ] `npm test` green in theseus-codex
- [ ] `npx playwright test` green (with stack running)

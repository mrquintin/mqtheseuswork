# Archive Round 12 Implemented Prompts

Moved here during the podcast conversation geometry pass so the active
`coding_prompts/[0-9][0-9]_*.txt` batch contains only the current 8 prompts.

Classification rule: archive only prompts whose main user-facing deliverables
can be matched to current repo surfaces and tests. This is repo-surface evidence,
not a full historical proof that every old sub-bullet was implemented exactly as
written.

| Prompt | Classification evidence checked in the repo |
|---|---|
| 01 login/dashboard transition | `theseus-codex/src/components/Gate.tsx`, `theseus-codex/src/app/api/auth/login/route.ts`, `theseus-codex/e2e/login-transition.spec.ts` |
| 02 conclusion dismiss/delete UX | `theseus-codex/src/app/(authed)/dashboard/DashboardConclusionsClient.tsx`, `theseus-codex/src/app/api/dashboard-dismissals/route.ts`, `theseus-codex/src/__tests__/dashboardDismissalActions.test.ts` |
| 03 Oracle markdown formatting | `theseus-codex/src/app/(authed)/ask/AskForm.tsx`, `theseus-codex/src/lib/oracleCitations.ts`, `theseus-codex/src/__tests__/oracleCitations.test.ts` |
| 04 founder display-name settings | `theseus-codex/src/app/(authed)/account/page.tsx`, `theseus-codex/src/app/api/account/route.ts`, `theseus-codex/e2e/account-display-name.spec.ts` |
| 05 public homepage reorganization | `theseus-codex/src/app/(home)/DualPulseSection.tsx`, `theseus-codex/src/app/(home)/TransparencyFooter.tsx`, `theseus-codex/src/__tests__/homepage.test.tsx` |
| 06 about page | `theseus-codex/src/app/about/page.tsx`, `theseus-codex/src/app/about/ContactForm.tsx`, `theseus-codex/src/__tests__/aboutPage.test.tsx` |
| 07 identity copy library | `theseus-codex/src/content/theseusIdentity.ts`, `theseus-codex/src/__tests__/theseusIdentity.test.ts` |
| 08 contact channel | `theseus-codex/src/app/api/contact/route.ts`, `theseus-codex/src/app/(authed)/admin/contact/page.tsx`, `theseus-codex/e2e/contact-inbox.spec.ts` |
| 09 Currents live X/commentary | `noosphere/noosphere/currents/x_ingestor.py`, `noosphere/noosphere/currents/opinion_generator.py`, `current_events_api/current_events_api/routes/currents.py`, `theseus-codex/e2e/currents-smoke.spec.ts` |
| 10 X outbound posts | `noosphere/noosphere/social/x_formatter.py`, `noosphere/noosphere/social/x_live_client.py`, `theseus-codex/src/app/(authed)/social/page.tsx`, `theseus-codex/e2e/social-queue.spec.ts` |
| 11 Substack publish | `noosphere/noosphere/social/substack_formatter.py`, `noosphere/noosphere/social/substack_live_client.py`, `theseus-codex/e2e/substack-publish.spec.ts` |
| 12 unified publish panel | `theseus-codex/src/app/(authed)/social/page.tsx`, `theseus-codex/src/app/(authed)/social/[id]/review-blocks.tsx`, `theseus-codex/e2e/social-publish-both.spec.ts` |
| 13 citation deep-links | `theseus-codex/src/lib/oracleCitations.ts`, `theseus-codex/e2e/oracle-citations.spec.ts` |
| 14 transcript explorer | `theseus-codex/src/app/(authed)/transcripts/[uploadId]/page.tsx`, `theseus-codex/src/app/(authed)/transcripts/[uploadId]/TranscriptAnchorClient.tsx`, `theseus-codex/e2e/transcript-anchor.spec.ts` |
| 15 auto-embed pipeline | `theseus-codex/src/app/api/conclusions/embeddings/route.ts`, `noosphere/noosphere/articles/transcript_enrichment.py`, `noosphere/tests/test_transcript_enrichment.py` |
| 16 knowledge hub consolidation | `theseus-codex/src/app/(authed)/knowledge/page.tsx`, `theseus-codex/src/app/(authed)/knowledge/RetiredRouteToast.tsx`, `theseus-codex/e2e/knowledge-nav.spec.ts` |
| 17 forecast portfolio | `theseus-codex/src/app/(authed)/forecasts/portfolio/page.tsx`, `theseus-codex/src/lib/forecastPortfolioData.ts`, `theseus-codex/e2e/forecast-portfolio.spec.ts` |

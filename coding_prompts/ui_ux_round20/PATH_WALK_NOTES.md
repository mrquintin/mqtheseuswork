# UI UX Round 20 Path Walk Notes

Date: 2026-05-11

## Prompt Archive Check

Ran:

```bash
python3 coding_prompts/_audit_implementation.py
```

Result:

- 50 active top-level prompt scopes remain active and should stay at
  the top level.
- None of the active top-level prompt scopes are fully implemented.
- 191 implemented prompt scopes are already archived.
- No active prompt file was moved or archived in this pass.

## Live Path Walk

Checked:

- Public home: `https://www.theseuscodex.com/`
- Public Currents: `/currents`
- Dashboard: `/dashboard`
- Knowledge: `/knowledge`
- Transcript index: `/knowledge?tab=transcripts`
- Conclusion detail: `/conclusions/c_2276f14a65124a1898843fb3`
- Audio transcript detail: `/transcripts/c6080d00458676eb57380e57d`
- Upload: `/upload`
- Public ask: `/ask`
- Founder Currents: `/founder-currents`
- Ops: `/ops`

## Findings

1. The operational UI is still too ceremonial. Labels such as
   "Conclusiones", "Dedicatio", "Sisyphus", "Scriba praeparat",
   wide all-caps labels, and italic body copy make routine work feel
   like reading a manifesto. Public pages can keep a restrained brand
   voice; founder/operator pages need clearer product language.

2. The conclusion detail page puts too much machinery above the fold:
   hero copy, confidence, rationale, publication state, enqueue form,
   export, peer review, publication queue, decay, failure modes,
   source links, tabs, and deletion. The first viewport should answer:
   what is the claim, why does the system believe it, what source did
   it come from, and what needs attention.

3. Conclusion actions lack hierarchy. Administrative actions,
   diagnostics, exports, publication workflow, and destructive requests
   visually compete with reading the claim.

4. Dashboard is noisy. The header is large, then the page immediately
   surfaces display-name reminders, contradiction warnings, repeated
   attention actions, and decorative forum language. It should behave
   like an operational home: queue summary, processing status, recent
   uploads, recent conclusions, and clear next actions.

5. The transcript index now contains audio entries, which is good, but
   entries are dense anchor blocks with long excerpts. Users need a
   scannable list with source type, transcript availability, chunk
   count, processing status, and source title.

6. The audio transcript detail page still presents conversation
   geometry and methodology panels before the transcript itself. For
   audio/podcast uploads, the raw transcript should be the main object;
   analysis panels should be secondary.

7. The transcript page uses "Conversation Geometry / Harvest Table" as
   the identity of a source even when no speaker labels exist. That
   makes an audio transcript feel mislabeled. Speaker absence should be
   explained quietly, and geometry should be a secondary analysis view.

8. Upload is visually spacious but not operationally efficient. The
   important workflow is: choose file, set visibility, add metadata,
   submit, track extraction/transcription/analysis. Those states need
   compact and explicit feedback.

9. Ask has route inconsistency: public navigation exposes `/ask`, while
   authenticated navigation routes "Ask" to `/codex-ask`. This should
   be intentional, documented in code, and not produce broken or
   surprising transitions.

10. Public and founder Currents both showed reconnecting/empty states.
    The public view should be calm and neutral; founder/operator views
    should expose backend health, last successful generation, last
    ingest, and whether scheduled jobs are running.

11. Ops is dense and has too many peer panels competing in one row. It
    should become a triage console: processing health, scheduler health,
    failures requiring action, and drill-down sections.

12. Several links and buttons work as anchors, but the product still
    feels sluggish. Route transitions, disabled states, optimistic
    feedback, and loading/error states need a dedicated hardening pass.

## Added Product-Direction Extension

After the UI path walk, the batch was expanded with prompts 13-19 to
cover founder-alpha market infrastructure:

1. Noosphere should become an algorithmized decision engine for
   investment and prediction markets, not only a prose reasoning system.
2. Market decisions should produce inspectable logic metrics, rule
   outputs, decision traces, and investment actions.
3. Polymarket/Kalshi setup should be clear enough that a founder can add
   credentials and immediately see whether monitoring, metric scans,
   paper trading, live candidates, and live order gates are ready.
4. Scheduler/script cadence should be explicit and realistic.
5. Live capital deployment must remain behind explicit safety gates:
   credentials, live enablement, risk limits, authorization, per-bet
   confirmation, sufficient balance, and kill-switch health.

## Added Empirical/Abstract Decision Extension

The batch was then expanded with prompts 20-25 to make algorithmized
decision making work across both empirical and abstract frames:

1. Empirical case studies in sources should become structured objects
   with actors, institutions, mechanisms, outcomes, source spans, and
   abstract-principle links.
2. Abstract principles should be contradiction-testable, scoped, and
   linked to supporting, contradicting, bounding, and refining cases.
3. New real-world cases, current events, and markets should be checked
   against prior cases by structural fit, not just keyword similarity.
4. Decision traces should include multiple explicit frames: incentives,
   coordination, principal-agent dynamics, reflexivity, option value,
   contradiction pressure, and empirical transfer.
5. The system should reject superficial analogies and downgrade to
   WATCH or ABSTAIN when preconditions or transfer fit are weak.

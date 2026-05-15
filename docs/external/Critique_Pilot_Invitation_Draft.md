# Open-Critique Pilot — Invitation Draft (Round 17, prompt 44)

The agent that produced this draft did NOT contact anyone. The text
below is meant to be edited and sent by the founder, by hand, to
three-to-five named outside reviewers.

The draft assumes:

- The pilot tag is `round17_pilot_2026Q2`.
- Per-reviewer pre-shared links are issued by setting
  `THESEUS_CRITIQUE_PILOT_REVIEWERS=<slug>:<token>,...` in the
  codex environment, then sharing
  `https://theseuscodex.com/post/<slug>?pilot=<token>` with each
  named reviewer.
- The pilot window is configured via
  `THESEUS_CRITIQUE_PILOT_WINDOW=<startISO>..<endISO>`.

---

## Subject

> Invited critique of three Theseus conclusions — $500 bounty per
> severe finding

## Body

> Hi {first name},
>
> I'm writing to invite you to file a *structured critique* of one or
> more conclusions the firm has published. You're on a short list of
> three-to-five people I trust to push back hard on substance, and
> this is the first time the channel is being opened deliberately to
> outsiders.
>
> **What I'm asking for.** Read one (or more) of the three target
> articles below and file a critique through the per-reviewer link
> below. The form asks for the specific claim you challenge, your
> counter-evidence, the method you used to derive it, and citations.
> Brevity is fine; substance is what matters.
>
> **The three pilot targets** (deliberately substantive and stable —
> not fresh, not under active revision):
>
> 1. **QH Benchmark v1 Results** —
>    `https://theseuscodex.com/post/qh-benchmark-v1-results`
>    The first reported benchmark of the QH method against the
>    project's curated comparison set. Cleanest target for a critique
>    of the *measurement framing*.
> 2. **Cross-Model Geometry Study** —
>    `https://theseuscodex.com/post/cross-model-geometry-study`
>    Empirical study comparing reasoning-trace geometry across model
>    families. Targets for critique: sampling design, what the
>    differences mean, whether the conclusions generalize beyond the
>    sampled models.
> 3. **Householder Ablation** —
>    `https://theseuscodex.com/post/householder-ablation`
>    Ablation of the Householder reflection component in the
>    QH pipeline. Targets for critique: ablation completeness, the
>    role of the component the ablation *didn't* remove, whether the
>    observed effect is causal.
>
> **The bounty.** Severity is scored from structural inputs (cascade
> weight, claim centrality, curated failure-mode match, source
> credibility) and gated by an LLM judge that is *capped* by the
> structural bracket. The rubric is published at
> `https://theseuscodex.com/critiques`.
>
> - low — accepted with credit; no bounty.
> - medium — accepted with credit; no bounty. Often paired with a
>   private follow-up or an article addendum.
> - high — accepted with credit AND a $500 bounty. The critique
>   attacks a load-bearing claim and the firm has updated its
>   position. Typical marker: a revision-engine pass changes the
>   conclusion's headline confidence.
>
> Bounty payment is gated by my explicit confirmation; the codex
> queues the payout but never sends money on its own. You can take
> the bounty personally or direct it to a charity of your choice —
> the form has a `payoutMode` toggle.
>
> **Identity / consent.** Your name appears publicly on
> `/critiques` only if you check the "consent to public credit" box
> on the form. If you'd rather stay private, the critique still
> counts — you'll be credited internally and any bounty still
> applies; the public page just won't name you.
>
> **Your pre-shared link.** This is unique to you and stamps your
> submission with the pilot tag so I can route it to the top of the
> queue:
>
> > `https://theseuscodex.com/post/<article-slug>?pilot={your token}`
>
> Replace `<article-slug>` with the slug of whichever of the three
> targets you're filing against. The token in the URL is yours; please
> don't share it.
>
> **Timeline.** The pilot window opens **{startDate}** and closes
> **{endDate}**. I will respond to every submission within seven days
> of receipt: accept (publish with credit), partial (private
> discussion), or reject (with a written reason — the pilot doesn't
> cherry-pick favorable findings, so a rejection comes with the
> reasoning attached).
>
> **What I'm hoping for, and why.** The firm's methodological edge
> depends on inviting the strongest possible external critique.
> Hoping critique arrives is not enough; this pilot is the first
> attempt to make the invitation explicit, named, and paid.
>
> Thanks for considering it.
>
> — {founder name}

---

## Operator checklist before sending

- [ ] Set `THESEUS_CRITIQUE_PILOT_REVIEWERS` in the codex environment with one
      `slug:token` pair per invited reviewer.
- [ ] Set `THESEUS_CRITIQUE_PILOT_WINDOW` to the actual start..end ISO
      range you communicate in the email.
- [ ] Verify the three target article slugs render and the
      `?pilot=<token>` query is preserved through the
      `Challenge this conclusion` form.
- [ ] Confirm `/critiques` page only displays critics with
      `hallOfFameConsent=true` (i.e. nothing leaks before opt-in).
- [ ] Schedule a debrief slot in the calendar at endDate + 5 business
      days so the
      `docs/external/Critique_Pilot_Debrief_<stamp>.md` file is
      compiled while the pilot is fresh.

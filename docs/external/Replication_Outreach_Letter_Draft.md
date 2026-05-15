# Replication Outreach — Invitation Letter Draft (Round 18, prompt 45)

The agent that produced this draft did NOT contact anyone. The text
below is meant to be edited and sent by the founder, by hand, to
three-to-five named researchers from
`Replication_Outreach_Targets.md`.

The draft assumes:

- The harness is at `replication/` in the firm's public repository.
- The reader has already seen
  `https://theseuscodex.com/methodology/replicate`.
- A "replicators" page exists at
  `https://theseuscodex.com/methodology/replicators` and renders the
  certificate trail once at least one researcher consents to public
  credit.

The letter is intentionally short. A long invitation is its own
deterrent.

---

## Subject

> Invitation to replicate three Theseus empirical claims —
> one-command harness, signed certificate on completion

## Body

> Hi {first name},
>
> I'm writing to invite you to run the firm's replication harness
> against three of our headline empirical claims. The harness has
> been public for several rounds; this is the first time I'm
> deliberately pulling outside researchers to use it.
>
> **What I'm asking for.** Clone the repo, run `cd replication &&
> make install && make all`, and tell me whether your numbers
> reproduce the firm's recorded numbers within the published
> tolerance. The whole thing takes ~30 seconds for the QH benchmark
> and ~1 minute for the ablation; cross-model is a few minutes if
> you set the embedding API keys, and skips models you don't have a
> key for without erroring. No Docker, no GPU, Python 3.11.
>
> **The three claims you'd be testing:**
>
> 1. **QH benchmark v1** (`make qh-benchmark`) — the firm's
>    `contradiction_geometry` probe wins AUROC and loses accuracy
>    against the trivial cosine baseline at frozen v1 thresholds.
>    The leaderboard is one the firm itself can lose on, and does.
> 2. **Cross-model geometry study** (`make cross-model`) — does the
>    QH signal survive across embedding back-ends? The
>    deterministic adapter reproduces the QH numbers exactly; the
>    remote-API adapters either replicate the asymmetry or surface
>    a fact about the provider.
> 3. **Householder ablation** (`make ablation`) — on the
>    deterministic embedder, the five variants collapse to
>    identical accuracy. That null result is itself the finding.
>
> **Why I'm asking *you*.** {one or two sentences naming the
> specific overlap — see the per-target signal lines in
> `Replication_Outreach_Targets.md`. Examples:
>
> - *"Your work on calibration of linear probes intersects directly
>   with the QH AUROC-vs-accuracy asymmetry; if the asymmetry is an
>   artefact of our threshold choice, you would notice."*
> - *"Your published critique of the MTEB threshold conventions is
>   exactly the lens I want applied to our cross-model agreement
>   matrix."*
> - *"You've replicated nulls in adjacent settings; an outside
>   confirmation that our Householder reflection is a no-op on QH
>   v1 is worth more than another internal pass."*
>
> Tailor this paragraph to the recipient. A generic version reads
> as a mass email and will be deleted.}
>
> **What you get.** Two things, neither of which is a payment:
>
> 1. **A signed reproducibility certificate.** When the harness
>    verifies your numbers against the firm's, it emits a JSON
>    certificate signed with the firm's publication key (the same
>    key that signs the conclusions on theseuscodex.com). The
>    certificate is portable — you keep it, you can attach it to
>    your own writeup, and the firm cannot retroactively unpublish
>    it.
> 2. **A row on the firm's replicators page**
>    (`/methodology/replicators`), with your name and institution,
>    *if and only if* you check the "consent to public credit"
>    box. If you'd rather stay private, the firm still has the
>    certificate; the public page just doesn't list you.
>
> The certificate does **not** certify that the firm's numbers are
> *correct* — only that the harness reproduced them on your
> hardware. That distinction is on the replicators page in plain
> language; I don't want the certificate to look like a vouch.
>
> **What happens when the numbers don't match.** The harness emits
> one of three verdicts — `match`, `mismatch`, `incompatible`. A
> `mismatch` (numbers diverge outside tolerance, envelopes
> compatible) is the most interesting outcome the firm can hear
> about. Please file an issue with the two
> `replication_envelope.json` files attached. A failed replication
> of our own thesis is the loudest alert in the codebase, and the
> firm wants to know.
>
> **If you hit a snag.** The harness ships a
> `replication/TROUBLESHOOTING.md` — every snag I know about from
> running it on three machines is documented there. If you hit a
> *new* one, that is itself a useful contribution: the harness is
> only useful insofar as outsiders can run it without me on the
> phone.
>
> **Timeline.** The outreach window is **{startDate}–{endDate}**
> (suggest 3 weeks). I will respond to every reply within 5
> business days; replications submitted in that window are the
> ones that populate the first cut of the replicators page.
>
> **What I'm hoping for, and why.** The firm's claim that QH is an
> empirical thing rather than a story-shaped thing rests entirely
> on outside replications. Hoping replications happen is not
> enough; this letter is the first time I'm asking specific
> people, by name, to try.
>
> Thanks for considering it.
>
> — {founder name}
> {founder email / contact}

---

## Operator checklist before sending

- [ ] Replace `{first name}`, `{startDate}`, `{endDate}`,
      `{founder name}` and the per-target signal paragraph.
- [ ] Verify that `https://theseuscodex.com/methodology/replicate`
      and `https://theseuscodex.com/methodology/replicators` both
      render at the time the email is sent. If `replicators` is
      empty (no consented researchers yet), drop the link and say
      "the page goes live as soon as the first replication
      arrives".
- [ ] Confirm the harness's `replication/TROUBLESHOOTING.md` is
      current — the letter promises it covers "every snag I know
      about from running it on three machines".
- [ ] Pre-stage a Slack/inbox reminder for `{endDate} + 5 business
      days` so the
      `docs/external/Replication_Outreach_Debrief_<stamp>.md`
      file is compiled while the replies are still fresh.
- [ ] If you contacted ≥3 researchers from the same institution,
      stagger the sends by at least 24 hours so it doesn't look
      like a campaign blast.

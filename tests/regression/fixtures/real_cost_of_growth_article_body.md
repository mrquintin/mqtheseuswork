# Real cost of growth

> Fixture for B08 — sanitised body of the article whose rendering
> broke in round 18 prompt 51. PII and any operator-private details
> have been replaced with neutral placeholders.

The headline number on a growth-stage P&L is rarely the real cost.
Three line items absorb the rest:

1. **Customer acquisition** — paid acquisition, sales-led demos,
   the SDR layer that orchestrates them. None of this is visible
   in the gross margin row.
2. **Retention spend** — the support engineering hours that keep
   churn out of the top-of-funnel chart. The chart shows growth;
   the bill shows the bracing.
3. **Re-platforming debt** — every quarter spent maintaining the
   old stack to keep customers alive on it while the new one is
   built.

The principle: **growth absorbs cost faster than the income statement
reveals**. When you read a growth-stage 10-K, ask which line items are
load-bearing for the customer base and which are funded by the next
round.

---

## Renderable check

The pre-fix bug was that the article rendered with broken bullets
("•1.", "•2.", …) because the markdown extractor stripped the
newline between the bullet marker and the digit. The body above
intentionally contains three numbered bullets, three list-item
prefixes, and an em-dash. A renderer must:

- Preserve the three numbered items as a single `<ol>` (or
  equivalent).
- Render the bolded labels as `<strong>`.
- Not interpolate the principle paragraph into the previous
  list item.
- Produce a single top-level `<h1>` for the title.

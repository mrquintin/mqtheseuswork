# Currents Pipeline

Currents now discovers public events before consulting the knowledge base. The
primary X path asks for trending or high-engagement source posts, filters out
low-significance candidates, and only then asks whether Theseus has enough
relevant corpus material to justify commentary. Founder-curated accounts remain
a trusted side channel: they bypass the significance floor because the author
selection is already editorial, but they still must clear KB relevance before an
opinion is written.

The knowledge base must not seed discovery. Configured `search_queries` remain
available only as targeted augmentation for narrow operator use, and their
execution is logged so it is visible when they affect a cycle. The KB's job is
second-order: distinguish significant off-domain events from significant events
where the corpus has something concrete to say, then ground the resulting
commentary in sources.

```text
X Trends / high-engagement recent search
        |
        v
significance floor + raw engagement floors
        |
        +------ rejected: below significance
        |
        v
dedupe + persist CurrentEvent
        |
        v
embeddings + near-duplicate enrichment
        |
        v
KB relevance gate
        |
        +------ abstain: off domain
        +------ abstain: insufficient sources
        |
        v
source-grounded opinion commentary

Founder-curated accounts -> dedupe + persist -> enrichment -> KB relevance
Targeted search queries  -> dedupe + persist -> enrichment -> significance -> KB relevance
```

/**
 * Public-facing documentation content.
 *
 * Source: docs/guides/01–07 (the .tex files), paraphrased and sanitized
 * for public reading. Each entry describes Theseus Codex at the level
 * of methodology, algorithms, interfaces, and operator workflow. Nothing
 * here exposes private corpus rows, internal credentials, deployment
 * URLs, or unreleased material.
 */

export type PublicDocSafetyLevel =
  | "public-overview"
  | "public-methodology"
  | "public-architecture";

export type PublicDocSection = {
  heading: string;
  paragraphs: string[];
  bullets?: string[];
};

export type PublicDocEntry = {
  slug: string;
  order: number;
  title: string;
  subtitle: string;
  audience: string;
  sourceGuide: string;
  summary: string;
  sections: PublicDocSection[];
  relatedRoutes: ReadonlyArray<{ href: string; label: string; description: string }>;
  safetyLevel: PublicDocSafetyLevel;
};

const SAFETY_NOTE =
  "This documentation describes Theseus Codex's infrastructure and methodology. It does not expose private firm materials, uploaded source documents, or unreleased internal records.";

export const PUBLIC_DOCS_SAFETY_NOTE = SAFETY_NOTE;

/**
 * A short, public-safe sketch of how material flows through the system.
 * Source -> evidence claims / conclusions -> principles -> algorithms ->
 * public methodology, forecasts, and Currents commentary.
 */
export const PUBLIC_DOCS_SYSTEM_MAP: ReadonlyArray<{
  stage: string;
  description: string;
}> = [
  {
    stage: "Source material",
    description:
      "A written document, transcript, or recorded conversation enters the system. Source material is the raw input; nothing is published from this stage alone.",
  },
  {
    stage: "Evidence claims",
    description:
      "The source is segmented into one-sentence atomic assertions, each carrying its speaker, span pointer, type, and embedding. (Historically these rows were also called \"conclusions\" inside the workshop — a legacy term for an evidence claim, not a finished public answer.)",
  },
  {
    stage: "Principles",
    description:
      "Clusters of related claims are distilled into reusable principles. A principle is a durable, third-person statement carrying a kind (rule, mechanism, heuristic, and others), a domain of applicability, falsifiable proxies, and a verbatim source anchor.",
  },
  {
    stage: "Algorithms",
    description:
      "Repeatable reasoning functions that apply principles to inputs. An algorithm names what it observes, the condition that fires it, the principles it draws from, and the structured output it produces.",
  },
  {
    stage: "Public surfaces",
    description:
      "Reviewed methodology pages, Currents opinions, Forecasts, and articles. Each public artifact carries its citation chain back to the principles and claims it depends on.",
  },
];

const overview: PublicDocEntry = {
  slug: "overview",
  order: 1,
  title: "Overview",
  subtitle: "What Theseus Codex is, and how the parts fit together",
  audience: "Anyone reading the public site for the first time.",
  sourceGuide: "Guide 1 — Quick Start",
  safetyLevel: "public-overview",
  summary:
    "Theseus Codex is the website face of a research and investment firm whose product is its recorded reasoning. Three programs work together: a desktop recorder that turns spoken conversation into structured transcripts, a background workshop that turns recorded material into a navigable library of claims and principles, and the Codex itself — the website you are reading now, which exposes a reviewed subset of that work to the public.",
  sections: [
    {
      heading: "Three programs, one record",
      paragraphs: [
        "The platform has three pieces that share one record.",
      ],
      bullets: [
        "A desktop recorder listens during a meeting, transcribes in near real time, breaks the transcript into one-sentence claims, and flags when two claims pull against each other.",
        "A background workshop turns any recorded material — a meeting, an essay, a podcast — into atomic claims, distilled principles, a knowledge graph, coherence checks, adversarial objections, and methodology profiles.",
        "The Codex is the website. Its public face renders reviewed conclusions, methodology, Currents opinions, and Forecasts. A signed-in founder workspace lives behind it; that workspace is not what these public docs describe.",
      ],
    },
    {
      heading: "Two access levels",
      paragraphs: [
        "Sign-in is gated. Founders can upload material, browse the corpus, review what the workshop produces, and ask the firm's internal Oracle. A smaller operator role — referred to in the guides as founder-alpha — handles publication approval, kill switches, live trade authorization, and the quarterly methodology review.",
        "The split exists because some actions touch the world outside the firm. Publication and trading are accountable to a single human role; routine reasoning work is not.",
      ],
    },
    {
      heading: "The reader's path",
      paragraphs: [
        "Material enters through upload or recording. The workshop processes it into claims, then principles, then conclusions. Operator-side review either accepts a conclusion for publication or sends it back. Once published, the article shows up on the public site with its citation chain intact.",
        "Live commentary (Currents) and prediction-market opinions (Forecasts) run continuously on the same corpus. Both abstain when the corpus is too thin to back a position; both publish their audit trail next to the position itself.",
      ],
    },
  ],
  relatedRoutes: [
    { href: "/about", label: "About", description: "Why Theseus exists and what it is not." },
    { href: "/methodology", label: "Methodology", description: "The firm's methods, calibration, and failure modes." },
    { href: "/principles", label: "Principles", description: "The corpus-derived principle library." },
    { href: "/algorithms", label: "Algorithms", description: "Reasoning functions that apply principles to inputs." },
  ],
};

const knowledge: PublicDocEntry = {
  slug: "knowledge-and-principles",
  order: 2,
  title: "Knowledge, Evidence Claims, and Principles",
  subtitle: "How recorded material becomes durable, reusable belief",
  audience:
    "Readers who want to understand the corpus side of the system — how a sentence in a source becomes a principle the firm can act on.",
  sourceGuide: "Guide 2 — Knowledge and Principles",
  safetyLevel: "public-methodology",
  summary:
    "Everything the firm reads or records is broken into atomic evidence claims, embedded, clustered by meaning, distilled into principles, and — when the firm is willing to commit — promoted into vetted positions that carry a falsifiability layer. The corpus is two passes: one builds the principle library, the other builds the principle-shaped conclusions that cite them.",
  sections: [
    {
      heading: "What a claim is",
      paragraphs: [
        "A claim is one sentence, one speaker, one assertion, plus a fingerprint of its meaning. The workshop refuses to roll claims into paragraphs — the whole point is to be able to reason about them individually.",
      ],
      bullets: [
        "The text itself.",
        "Who said it (speaker label, founder identity when known).",
        "Where it came from (source upload, span start and end).",
        "Its disciplines, from a fixed vocabulary.",
        "Its fingerprint (an embedding vector).",
        "Its type — factual, methodological, normative, predictive, definitional, or interpretive.",
        "Its origin — founder (the speaker's own assertion) or external (a quoted external position, stripped before inference).",
        "Hedges and evidence pointers.",
      ],
    },
    {
      heading: "A note on the word \"conclusion\"",
      paragraphs: [
        "Inside the workshop and in the early guides, some rows are called \"conclusions.\" In current usage this is a legacy term for a principle-shaped evidence claim — a structured assertion the firm is willing to commit to internally — not the finished public answer a reader of this site might expect.",
        "The firm's finished public answers live as reviewed methodology pages, articles, and Currents opinions. A \"conclusion\" inside the corpus is a building block on the way there.",
      ],
    },
    {
      heading: "The principle-shape contract",
      paragraphs: [
        "Every principle-grade evidence claim has to declare what kind of thing it is and where it applies. The firm requires five fields before the row is allowed to graduate to the highest confidence tier.",
      ],
      bullets: [
        "principleKind — one of seven shapes: RULE (a normative \"do X\"), CRITERION (\"X is the test for Y\"), MECHANISM (\"X causes Y by Z\"), HEURISTIC (\"X usually works in case Y\"), DEFINITION, FORMULA, or ALGORITHM.",
        "domainOfApplicability — a short description of where the claim is meant to hold and where it stops working. \"Always\" is not acceptable.",
        "quantifiableProxies — up to five measurable proxies that would let an outside reviewer falsify the principle.",
        "decisionExamples — up to three concrete decisions the principle would direct.",
        "sourceSpan — a verbatim substring of a source chunk that the principle is anchored to. If the quoted span does not literally appear in the source, the workshop refuses to write the row.",
      ],
    },
    {
      heading: "The falsifiability layer",
      paragraphs: [
        "Anything being prepared for publication must also carry a quantitative formalisation: a null hypothesis, one or more metrics, one or more statistical tests, and one or more data sources. Without all four, the workshop refuses to mark the formalisation approved.",
        "This is the operational form of the working criterion that the test should be severe enough that the claim would have failed if it were wrong. If the firm cannot state what would falsify a principle, the principle does not get to be public.",
      ],
    },
    {
      heading: "Provenance, contradictions, and decay",
      paragraphs: [
        "Every uploaded source carries one of four provenance labels — proprietary, endorsed external, studied external, or opposing external — chosen at upload time. The contradiction engine uses these labels to skip cross-provenance pairs the firm expects to disagree with.",
        "A single calibrated contradiction detector replaces an earlier family of heuristics. It returns a score, a confidence band, and a human-readable explanation. Contradictions no longer resolve by operator click; they resolve when new source material weights one side decisively over the other.",
        "Knowledge ages. A conclusion can decay on a fixed schedule, on evidence change, on method version bumps, on embedding drift, on outcome observation, or on a calibration regression. Each row in the decay surface carries revalidate, retire, and update actions.",
      ],
    },
  ],
  relatedRoutes: [
    { href: "/principles", label: "Principles", description: "The corpus-derived principle library, publicly visible portion." },
    { href: "/methodology", label: "Methodology", description: "The methods that produce these claims, with calibration." },
    { href: "/algorithms", label: "Algorithms", description: "Where principles get applied to inputs." },
  ],
};

const oracle: PublicDocEntry = {
  slug: "oracle",
  order: 3,
  title: "The Oracle and Ask Interface",
  subtitle: "Citation-grounded question-answering, with deliberate abstention",
  audience: "Readers who want to understand what happens when the firm answers a question.",
  sourceGuide: "Guide 3 — The Oracle",
  safetyLevel: "public-methodology",
  summary:
    "The Oracle is the firm's question-answering surface. It does not run a free chat against a foundation model; it answers from the firm's corpus and refuses, or warns, when the corpus is too thin. Every quoted span must appear verbatim in the cited source — if it does not, the answer is rejected before it reaches the reader.",
  sections: [
    {
      heading: "How an answer is composed",
      paragraphs: [
        "The path under the hood is short and conservative.",
      ],
      bullets: [
        "Encode the question into a fingerprint.",
        "Retrieve the top-ranked principles and conclusions nearest that fingerprint, filtered by a minimum conviction threshold.",
        "Pull the supporting claims for each retrieved principle.",
        "Hand the principles (as axioms) and claims (as evidence) to a language model with a strict contract: produce an answer, cite which principle grounds each part, note caveats.",
        "Validate that the answer does not contradict the retrieved principles with a coherence check.",
        "Generate an adversarial counter-position to the leaned-on principles and include its strongest objection as a caveat.",
        "Run a final consistency check before returning the answer.",
      ],
    },
    {
      heading: "The verbatim-citation rule",
      paragraphs: [
        "The single load-bearing rule of every public-facing surface is the verbatim citation contract: any quoted span the answer leans on must appear word-for-word in the cited source. The validator checks this on every answer. When a quoted span does not match, the answer is not retried with a fix-it prompt — it is rejected, and the Oracle abstains.",
        "The same rule echoes through the stack. Currents abstains rather than publish an opinion whose quote is not in any source. Forecasts abstains rather than ship a prediction whose reasoning cites a span that is not there.",
      ],
    },
    {
      heading: "Confidence bands",
      paragraphs: [
        "Each answer carries a band based on the strength and breadth of the citation chain.",
      ],
      bullets: [
        "high — supported by multiple independent citations, including at least one principle or conclusion.",
        "medium — supported by at least one citation that directly addresses the question.",
        "low — citations exist but only weakly support the answer; treat as a starting point.",
        "abstain — the corpus is too thin or off-topic to answer. The Oracle returns no answer text and explains what material it would have needed.",
      ],
    },
    {
      heading: "Hallucination warning, and what to do with low confidence",
      paragraphs: [
        "When post-hoc verification finds the answer contains a span the cited sources do not unambiguously support, the system surfaces a hallucination badge. The badge does not mean the answer is wrong; it means the support is weaker than the prose makes it sound. The recommended response is to read the cited sources, decide whether the unsupported span is a paraphrase that survives, and narrow the question if it does not.",
        "Low confidence does not mean probably wrong. It means the corpus will not let the Oracle commit to a sharper answer. Standard responses are to add corpus on the topic, narrow the question, or accept the abstention.",
      ],
    },
    {
      heading: "Inverse inference",
      paragraphs: [
        "A specialty mode runs the inverse question: given that an event happened, what does it imply about (or refute in) the firm's existing positions? The result is a list of supporting implications, refuted implications with severity, a transparency list of irrelevant principles, and a blindspot report of entities, mechanisms, or adjacent topics the corpus is missing in light of the event.",
      ],
    },
  ],
  relatedRoutes: [
    { href: "/ask", label: "Ask", description: "The public question form, gated to the publicly safe portion of the corpus." },
    { href: "/methodology", label: "Methodology", description: "How methods are evaluated and where they fail." },
    { href: "/principles", label: "Principles", description: "What the Oracle leans on when it answers." },
  ],
};

const currents: PublicDocEntry = {
  slug: "currents",
  order: 4,
  title: "Currents",
  subtitle: "Live commentary, source-grounded or abstained",
  audience: "Readers who want to understand how the firm comments on the day's events.",
  sourceGuide: "Guide 4 — Currents",
  safetyLevel: "public-methodology",
  summary:
    "Currents is the firm's live commentary surface. A scheduler pulls recent public posts in, runs each through a significance floor and a relevance gate, and either writes a short citation-grounded opinion or abstains. Every published opinion satisfies eight structural invariants designed to prevent free-floating assertion and to keep private material out of public output.",
  sections: [
    {
      heading: "The pipeline, top to bottom",
      paragraphs: [
        "The Currents scheduler runs continuously on a short cycle. Each cycle moves a candidate event through a fixed sequence.",
      ],
      bullets: [
        "Discovery — recent high-engagement public posts are pulled in from the upstream feed.",
        "Significance floor — each candidate gets a significance score computed from impressions, retweets, likes, replies, and quote-and-bookmark counts (a weighted log-sum). Posts below the floor are dropped.",
        "Persistence and dedupe — survivors become event rows.",
        "Enrichment — the post is embedded, near-duplicate matched against recent events, and tagged with topic hints.",
        "Relevance gate — the event's fingerprint is compared against the firm's stored conclusions and claims. The gate requires at least two qualifying hits above a relevance threshold; otherwise the event becomes an abstention.",
        "Opinion generation — the retrieval bundle is wrapped in unambiguous markers and handed to a language model with a strict contract: cite each source by id and quote verbatim spans.",
        "Citation validation — every quoted span is checked against its source character by character. A fabrication anywhere causes the whole opinion to abstain.",
        "Strawman detection — a separate guard checks the opinion is not mischaracterizing the source post.",
        "Publication — the opinion row is written and the public feed picks it up immediately.",
        "Article dispatch — a separate, longer-cycle job periodically clusters related opinions and drafts a long-form article when the cluster is dense enough.",
      ],
    },
    {
      heading: "The eight structural invariants",
      paragraphs: [
        "An opinion that fails any of these is rejected before it reaches the public feed.",
      ],
      bullets: [
        "Grounded — every non-trivial claim is backed by an inline citation to a firm conclusion or principle.",
        "Source-respecting — citations resolve only to publicly-safe corpus surfaces. Private material may inform internal reasoning but must not appear as a public citation target.",
        "Quorum — at least two relevance-cleared firm conclusions back the opinion. If the corpus cannot supply two, the system abstains rather than under-cite.",
        "Voice-consistent — the opinion is written in the firm's first-person voice rather than recapping or paraphrasing the source post.",
        "Event-anchored — each opinion is bound to exactly one event. Multi-event commentary lives in the articles pipeline.",
        "Revocable — every opinion is publishable iff its revocation timestamp is null. Operator revocation is the canonical inverse of publication; there is no separate \"hide\" flag.",
        "Abstention-honest — when the relevance gate fails, the system records a reason on the event and shows a public abstention. Abstentions are a public stance.",
        "Provenance-complete — each opinion ships an audit trail: source post, relevance scores, conclusions cited, generator parameters. The audit trail is addressable from the public page.",
      ],
    },
    {
      heading: "The audit trail",
      paragraphs: [
        "Below every opinion sit the source post, the cited conclusions (linked through to public pages — private conclusions never appear here), the relevance scores at generation time, generator metadata, and, if the opinion has been revoked, a banner indicating so. The opinion is hidden from the feed when revoked, but its row and audit trail remain readable for accountability.",
      ],
    },
    {
      heading: "Reader engagement",
      paragraphs: [
        "Each opinion has a follow-up thread for short questions and a separate public-response flow for structured replies — counter-evidence, counter-argument, clarification, or extension. Submitters who want their response published by name tick a publish-consent box; otherwise the firm holds the response as internal feedback.",
        "A higher-effort form for invited expert critique exists alongside. Accepted high-severity critiques can earn a small bounty: the firm pays for being shown wrong, in public.",
      ],
    },
  ],
  relatedRoutes: [
    { href: "/currents", label: "Currents feed", description: "The live opinions themselves." },
    { href: "/critiques", label: "Critiques", description: "The expert-critique submission form." },
    { href: "/responses", label: "Public responses", description: "Structured reader responses." },
  ],
};

const forecasts: PublicDocEntry = {
  slug: "forecasts-and-portfolio",
  order: 5,
  title: "Forecasts and Portfolio",
  subtitle: "Prediction-market opinions, the decision trace, and the eight gates",
  audience:
    "Readers who want to understand how a forecast is generated, scored, and (when authorized) translated into a real-money bet.",
  sourceGuide: "Guide 5 — Forecasts and Portfolio",
  safetyLevel: "public-architecture",
  summary:
    "The Forecasts surface tracks markets on Polymarket and Kalshi, retrieves relevant firm conclusions, and builds a deterministic decision trace for each market. Live trading requires eight successive human gates; paper mode is the default. After resolution, every prediction is Brier-scored, log-loss-scored, and added to the public calibration manifest.",
  sections: [
    {
      heading: "How a forecast is generated",
      paragraphs: [
        "For each market the firm decides to score, the workshop runs a conservative sequence.",
      ],
      bullets: [
        "Retrieve the firm's most relevant conclusions and claims by embedding search. The bundle must contain at least three distinct conclusions; otherwise the workshop abstains.",
        "Check the near-duplicate window. If a forecast on a similar market was published in the last 24 hours, the workshop abstains.",
        "Check the market-close buffer. If the market closes within an hour, the workshop refuses to predict. Stale-but-open markets are the firm's most expensive losses.",
        "Call a language model with a strict JSON contract: probability, confidence band, headline, reasoning body, uncertainty notes, citations.",
        "Validate every quoted span against the cited source — verbatim, character-by-character. Fabrications cause the prediction to abstain.",
        "Build the Market Decision Trace.",
        "Persist the prediction with status PUBLISHED, with the trace and one citation row per quoted span.",
      ],
    },
    {
      heading: "The Market Decision Trace",
      paragraphs: [
        "After the language model has produced a probability and a written rationale, the workshop builds a separate object — fully deterministic — that computes a small set of metrics from the inputs, runs a fixed rule graph over them, and produces an action (HOLD, WATCH, PAPER, or LIVE) and a stake recommendation. No randomness, no further model calls.",
        "The deterministic trace is the artifact the firm is willing to defend. The model's prose explains, it never overrides. If the prose says \"buy\" but the trace says WATCH, the trace wins.",
      ],
      bullets: [
        "Edge estimate — firm probability versus market price.",
        "Confidence and locality — how on-domain the retrieval was.",
        "Liquidity, contradiction load, decay status.",
        "Each rule's firing — which threshold was crossed, which veto triggered, which combination escalated to the next tier.",
        "The final action and stake.",
        "A version string, so a later refactor that changes the trace format is detectable rather than silently mixed with old data.",
      ],
    },
    {
      heading: "The eight-gate safety architecture",
      paragraphs: [
        "Each gate is a separate human action. No gate auto-promotes the next; if any gate fails, every later gate refuses.",
      ],
      bullets: [
        "1. Exchange credentials configured.",
        "2. Scheduler ingesting and monitoring. Absence of fresh rows blocks every downstream step.",
        "3. Paper mode validated. Paper bets have been written, scored, and reconciled for long enough that the firm trusts the decision pipeline.",
        "4. Risk caps configured. Maximum per-bet stake and maximum daily loss are set to numbers the firm is willing to lose. The submitter checks both on every bet.",
        "5. Master live flag on. Without this, no other authorization counts.",
        "6. Per-prediction live authorization. The operator flags a specific forecast row as live-eligible.",
        "7. Per-bet live confirmation. For each individual bet, the operator clicks confirm. The system refuses to submit without it.",
        "8. Kill switch clear at submit time. The submitter re-evaluates the kill switch immediately before placing the order. If the kill switch flipped between confirmation and submission, the bet is dropped.",
      ],
    },
    {
      heading: "Resolution and the public calibration manifest",
      paragraphs: [
        "When a market closes, the workshop polls the venue and writes a resolution carrying the outcome (YES, NO, CANCELLED, or AMBIGUOUS), the Brier score, the log-loss, the calibration bucket, and the raw settlement payload.",
        "The firm publishes its own track record. A public calibration manifest shows, per probability bucket, the number of predictions and the realized YES rate. The horizon view shows the same broken down by time-to-resolution. The manifest is regenerated on a schedule.",
        "This is one of the most uncomfortable surfaces the firm offers: it is the firm publicly grading itself on every prediction it has staked publicly. If the firm has been consistently overconfident at a given bucket, the public page shows it.",
      ],
    },
    {
      heading: "Resolution overrides",
      paragraphs: [
        "If a founder believes the venue resolved incorrectly, the chain handles it: a resolution override records an alternative resolution with citation and reason, a mismatch row logs any later venue disagreement, and an append-only revision history preserves prior settlement for audit.",
      ],
    },
  ],
  relatedRoutes: [
    { href: "/forecasts", label: "Forecasts", description: "The public forecasts grid." },
    { href: "/calibration", label: "Calibration", description: "The public calibration manifest." },
    { href: "/methodology", label: "Methodology", description: "How methods are scored and where they fail." },
  ],
};

const operator: PublicDocEntry = {
  slug: "operator-console-and-safety-gates",
  order: 6,
  title: "Operator Console and Safety Gates",
  subtitle: "Publication review, signing, kill switches, deletion versus retraction",
  audience: "Readers who want to understand the human-accountability layer that wraps the rest of the system.",
  sourceGuide: "Guide 6 — Operator Console",
  safetyLevel: "public-architecture",
  summary:
    "A small number of actions concentrate in the operator role: publishing to the public site, signing the quarterly methodology review, flipping kill switches, authorizing real-money trades, removing material the firm has cited publicly, and managing roles. The split exists because these actions have real-world consequences, require cryptographic signing, or carry concentrated risk.",
  sections: [
    {
      heading: "Why a separate operator role",
      paragraphs: [
        "The firm runs on separation of duties. Any founder can upload material, browse the corpus, review evidence claims, ask the internal Oracle, and read everything the firm publishes. A small number of actions are concentrated in the operator role for three reasons.",
      ],
      bullets: [
        "Real-world consequences. Publishing and trading touch the world outside the firm. Each of those gates wants a single accountable actor.",
        "Cryptographic signing. The firm signs its public publications and its quarterly review with private keys. Those keys live with the operator role, not in the web app, so signing is an explicit human action.",
        "Concentration of risk. Kill switches and live-bet authorization can lose money. They live on the surface that gets reviewed most carefully.",
      ],
    },
    {
      heading: "The publication review queue",
      paragraphs: [
        "The publication queue is the gate before any conclusion or article goes public. Each queue item carries a checklist: meta-analysis OK (the methodology profile has been read), adversarial engaged OK (the strongest objection has been reviewed, not just produced), clarity OK (readable to a smart outsider), and no leakage OK (the conclusion does not expose private material). Approving the item mints a permanent public version and the workshop's ledger writes a cryptographic signature attached to the canonical hash. The Codex stores the signature; the signing keys never live inside the website.",
      ],
    },
    {
      heading: "The quarterly methodology review week",
      paragraphs: [
        "Once a quarter, the operator walks the firm's recent work and writes a structured account of what the firm learned. Each day's draft is summarized by the workshop, then edited and signed by the operator. Once a day is signed cryptographically, the row becomes immutable. To revise after signing, the operator must clear the signature first, which is itself an audited event.",
        "The history page shows every prior week's signed daily summaries. This is the firm's durable record of methodological self-assessment.",
      ],
    },
    {
      heading: "Kill switches",
      paragraphs: [
        "There is no global kill switch. There are several precise ones, and that is deliberate.",
      ],
      bullets: [
        "Currents ingestion off — the next scheduler cycle writes no new events. Existing opinions stay up.",
        "Articles dispatcher off — existing articles stay up; no new ones are clustered or written.",
        "Master live-trading off — the platform-wide live-bet flag. Setting it off refuses every downstream submit.",
        "Per-submit kill switch — re-checked immediately before each order placement; trips even bets that already passed operator confirmation.",
      ],
    },
    {
      heading: "Deletion versus retraction",
      paragraphs: [
        "Two adjacent flows. Understanding the difference matters because they leave very different audit trails.",
      ],
      bullets: [
        "Deletion is removal of source material. The upload is soft-deleted, derived bridge rows are hard-deleted, and any conclusion left with zero sources is then hard-deleted. The public surface stops resolving the affected rows. Used for legal, compliance, or subject-request reasons.",
        "Retraction is removal of a published output. The retraction is itself a published artifact: it creates a new public version that retracts the previous one, leaving an audit trail. Used for an article or conclusion the firm no longer endorses.",
      ],
    },
    {
      heading: "The reason for the ceremony",
      paragraphs: [
        "It is fair to ask why the firm builds in so many gates, queues, and signatures when most days nothing goes wrong. The answer is the one that animates the whole platform: the product is the recorded reasoning, not the opinions. That product is only worth anything if a later reviewer can inspect the record and trust what they see. Publication review, signing, source-standing triage, deletion-versus-retraction, kill switches, live-bet gates — all of it exists so the record is trustworthy when it matters most.",
      ],
    },
  ],
  relatedRoutes: [
    { href: "/methodology", label: "Methodology", description: "The reviewed methods that pass through these gates." },
    { href: "/calibration", label: "Calibration", description: "The public manifest the firm grades itself on." },
    { href: "/about", label: "About", description: "Why the firm is structured this way." },
  ],
};

const afterRound19: PublicDocEntry = {
  slug: "architecture-after-round-19",
  order: 7,
  title: "Architecture After Round 19",
  subtitle: "Principles instead of summaries, algorithms on top, one contradiction engine",
  audience: "Readers who want to know what the recent rebuild changed and why.",
  sourceGuide: "Guide 7 — What Changed",
  safetyLevel: "public-architecture",
  summary:
    "The system was rebuilt around a different idea about what it should store. Earlier, the extractor produced first-person summaries of what an author seemed to be saying. The firm cannot act on that. The pipeline was reshaped so the stored object is a third-person, generalizable principle — and a new layer of algorithms was added on top to turn principles into structured reasoning when their conditions match an observed input.",
  sections: [
    {
      heading: "The core change",
      paragraphs: [
        "The extractor no longer emits first-person summaries. If a source span is purely autobiographical and no underlying principle can be extracted from it, the extractor logs that fact and emits nothing. If a principle is present, it is stored with structure: principleKind, domainOfApplicability, quantifiableProxies, decisionExamples, and a verbatim source anchor.",
        "This is the load-bearing change. Everything else in the rebuild either follows from it or cleans up something that was getting in the way of it.",
      ],
    },
    {
      heading: "Algorithms as a new layer",
      paragraphs: [
        "A principle says what is true. An algorithm says when, given what can be observed, the principle predicts something specific. The algorithm is the bridge between abstract principle and concrete prediction.",
        "Each algorithm names the observables it watches, the condition that has to be true for it to fire, the principles it is reasoning from, and the structured output it produces. The reasoning chain inside an algorithm cites the principles it depends on, so a prediction is always traceable.",
      ],
    },
    {
      heading: "One contradiction engine",
      paragraphs: [
        "An earlier family of six contradiction heuristics — different rules that disagreed with each other and were hard to calibrate — was replaced with a single detector that returns a calibrated score, a confidence band, and a human-readable explanation. The legacy heuristics are deprecated and no longer write new rows.",
        "A related change: contradictions no longer have a manual resolve button. Operator clicks were being treated as authoritative, which was wrong — the record should reflect what the sources jointly imply, not which side an operator preferred on a given afternoon. Contradictions now resolve when new source material weights one side decisively over the other.",
      ],
    },
    {
      heading: "Provenance at upload time",
      paragraphs: [
        "Every piece of source material now carries one of four labels, chosen when it is uploaded: proprietary (the firm wrote it), endorsed external (someone else wrote it, but the firm explicitly endorses it as representative), studied external (reference material, read but not endorsed), and opposing external (material the firm disagrees with, kept for the value of testing positions against it).",
        "Why this matters: the system used to flag contradictions between the firm's principles and opposing material it was reading — which is noise, because the firm expects to disagree with that material. Provenance demarcation lets the contradiction engine skip those cross-provenance pairs and surface only the contradictions that are actually news.",
      ],
    },
    {
      heading: "Memos as the canonical output",
      paragraphs: [
        "When the system answers a question, the answer takes a fixed memo shape: a TL;DR, the question, the governing principles, the observed inputs, the reasoning chain, the implied position, what would change the firm's mind, and any caveats or abstentions. The memo is the canonical output.",
        "The system explicitly prefers to abstain over making a chain of reasoning it cannot ground. If there are no governing principles, or the principles directly contradict each other, or the confidence band is too wide, or the question itself is unformed — the memo says so, by name.",
      ],
    },
    {
      heading: "\"Bet\" was generalized",
      paragraphs: [
        "A bet used to mean a financial position on a prediction market or an equity. It now means any falsifiable commitment of firm resources: a financial position, a public statement of position with no money behind it, an internal allocation of operator time or hiring direction, or a scientific prediction that resolves against external data. All four are tracked in one place. The firm's edge is the principle layer, not any specific way of expressing a view.",
      ],
    },
    {
      heading: "A knowledge graph view",
      paragraphs: [
        "The corpus is no longer a flat list of claims. There is a cross-source graph view where principles, sources, algorithms, memos, and concepts are nodes, and the relationships between them are edges (derived from, contradicts, supports, applies to, cites). The accompanying reasoner produces a grounded explanation of why an edge exists, and refuses to fabricate connections the data does not support.",
        "This is the reading view for \"what does the corpus jointly imply about X?\" — a question that was not directly answerable before the underlying structure existed.",
      ],
    },
  ],
  relatedRoutes: [
    { href: "/algorithms", label: "Algorithms", description: "The reasoning layer that sits on top of principles." },
    { href: "/principles", label: "Principles", description: "The library this rebuild was reshaped around." },
    { href: "/knowledge-graph", label: "Knowledge graph", description: "The corpus as a graph rather than a flat list." },
  ],
};

export const PUBLIC_DOCS: ReadonlyArray<PublicDocEntry> = [
  overview,
  knowledge,
  oracle,
  currents,
  forecasts,
  operator,
  afterRound19,
];

export function getPublicDoc(slug: string): PublicDocEntry | undefined {
  return PUBLIC_DOCS.find((doc) => doc.slug === slug);
}

export function listPublicDocs(): ReadonlyArray<PublicDocEntry> {
  return [...PUBLIC_DOCS].sort((a, b) => a.order - b.order);
}

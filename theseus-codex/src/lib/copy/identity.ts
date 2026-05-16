/**
 * Canonical "Philosopher in a Box" identity copy.
 *
 * Every public surface (homepage, about page, README, pitch deck) reads
 * the same strings from this module. The lint at
 * `scripts/check_no_inline_identity_duplicates.py` refuses commits that
 * hardcode any of the four canonical strings outside this file.
 *
 * Voice: restrained, confident, not promotional. No "AI-powered". No
 * "revolutionary". No emoji.
 */

export const THESEUS_TAGLINE = "A philosopher in a box.";

export const THESEUS_ONE_PARAGRAPH =
  "Theseus is a philosopher in a box. We extract principles from a curated corpus, build logical algorithms that apply those principles to live observations of the world, and place bets when the algorithms predict outcomes the principles support. We are the Renaissance Technologies of formal logic — the same machine shape (inputs → engine → conclusions → bets), one level of abstraction higher. We do not commercialize this. The machine is our edge.";

export const THESEUS_LOGIC_VS_QUANT =
  "Quantitative firms abstract numerical patterns out of price data and arbitrage them. Theseus abstracts logical patterns out of text — principles — and arbitrages them. The stack is the same shape, one level up: a curated corpus replaces the tick archive, a synthesizer replaces the model trainer, principles replace fitted parameters, and an algorithm executing those principles against live observations replaces the alpha signal. The bet, when the algorithm predicts something the principles support, is the output of the same machine — operating on logic instead of numbers.";

export const THESEUS_NOT_COMMERCIAL =
  "Theseus is not a SaaS product. The reasoning architecture is our edge.";

export interface TheseusAxiom {
  readonly name: string;
  readonly summary: string;
  readonly elaboration: string;
}

export const THESEUS_AXIOMS: readonly TheseusAxiom[] = [
  {
    name: "Progress",
    summary: "The future is a responsibility.",
    elaboration:
      "We choose projects, questions, and investments by whether they make tomorrow more capable than today. Progress is the standard against which work is judged; nostalgia and stagnation are not neutral.",
  },
  {
    name: "Rigor",
    summary: "First-principles reasoning under pressure.",
    elaboration:
      "Assumptions are named, methods are judged, and confidence is earned only after serious objection. The machine exists because rigor at scale requires instrumentation — a record detailed enough to show what failed when we are wrong.",
  },
  {
    name: "Camaraderie",
    summary: "Disagreement as shared work.",
    elaboration:
      "Intellectual companionship — a small community that challenges assumptions, thinks in fundamental ways, and treats the dialectic as a craft rather than a social threat. The corpus is the record of that work.",
  },
] as const;

/** The named bet domains the machine is polymorphic across. */
export const THESEUS_BET_DOMAINS: readonly string[] = [
  "Equities",
  "Prediction markets",
  "Advisory",
  "Scientific",
  "Private markets (eventually)",
] as const;

/**
 * Short variants used by headers and rails on the public surface. These
 * are NOT considered duplicates of the four canonical strings above;
 * they are deliberately distinct shorter phrasings of the same idea.
 */
export const THESEUS_IDENTITY_HEADINGS = {
  homeHero: "A philosopher in a box.",
  machineRail: "The machine.",
  liveActivity: "What the machine is thinking right now.",
  readTheDeck: "Read the deck",
  axiomsHeading: "Three axioms.",
} as const;

/**
 * The pipeline ASCII diagram rendered on the homepage. Kept here so the
 * About page and the pitch deck can render the same shape without
 * duplicating the layout.
 */
export const THESEUS_PIPELINE_ASCII = `   corpus ──▶ synthesizer ──▶ principles ──▶ algorithms
                                                  │
                              live observations ──┤
                                                  ▼
                                            conclusions
                                                  │
                                                  ▼
                                               memos
                                                  │
                                                  ▼
                                         portfolio agent
                                                  │
                                                  ▼
                                                bet`;

/**
 * The set of strings the lint treats as canonical. The lint script
 * imports this list (parsed as text) and refuses any file outside this
 * module that contains them verbatim. Keep aligned with the four
 * constants above.
 */
export const CANONICAL_IDENTITY_STRINGS: readonly string[] = [
  THESEUS_TAGLINE,
  THESEUS_ONE_PARAGRAPH,
  THESEUS_LOGIC_VS_QUANT,
  THESEUS_NOT_COMMERCIAL,
] as const;

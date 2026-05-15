/**
 * Reader-guide data and the reading-tour state machine.
 *
 * Two responsibilities, kept in one pure module so the page, the tour
 * components, and the tests all read from the same source of truth:
 *
 *   1. READER_GUIDE_STEPS — the seven-stop reading map for an outside
 *      reader. Each step indexes a surface that already exists; the
 *      guide never restates the surface, it points at it and says how
 *      long the surface takes to read.
 *   2. tourReducer — the "tour me" overlay's state. A reader can start
 *      the tour, walk it next/prev, dismiss it at any point, or run it
 *      to the end. Reaching the end produces a `complete` status whose
 *      only effect is an exportable record; nothing material gates on
 *      it. No DOM, no storage, no React in here — just a reducer and a
 *      few selectors, which is what makes the navigation behaviour
 *      testable in the node test environment.
 */

export type ReaderGuideLink = {
  href: string;
  label: string;
  /** External links open in a new tab and get rel="noreferrer". */
  external?: boolean;
};

export type ReaderGuideStep = {
  /** Stable id — used for anchors, tour keys, and the export record. */
  id: string;
  /** 1-based stop number shown to the reader. */
  index: number;
  /** Short label, e.g. "Step 1". */
  eyebrow: string;
  title: string;
  /** One paragraph. The reading map's entry for this surface. */
  summary: string;
  /** Estimated minutes to read the surface(s) this step points at. */
  readingMinutes: number;
  /**
   * What the reader is looking at, in the tour overlay's voice. This is
   * the "explaining what they are looking at" copy — one or two plain
   * sentences, no marketing.
   */
  tourNote: string;
  /** The surfaces this step indexes. The first is the primary link. */
  links: ReaderGuideLink[];
};

/**
 * The canonical reading map. Order is the order an outside reader needs
 * it: what the firm is, then the commitment under it, then the rubric
 * that commitment produces, then the evidence, then the three doors a
 * reader can walk back through — challenge, replicate, subscribe.
 */
export const READER_GUIDE_STEPS: ReaderGuideStep[] = [
  {
    id: "what",
    index: 1,
    eyebrow: "Step 1",
    title: "What Theseus does",
    summary:
      "Theseus is a research firm that publishes its conclusions and, more durably, the discipline that produced them: recorded deliberation is turned into public theses, each one carrying the method that made it and the record that method has earned. Start on the firm's own description of itself.",
    readingMinutes: 1,
    tourNote:
      "This is the firm's self-description. Read it for the claim Theseus makes about its own work: it sells conclusions, but the reusable object is the method.",
    links: [
      { href: "/about", label: "About the firm" },
      { href: "/", label: "Public homepage" },
    ],
  },
  {
    id: "commitment",
    index: 2,
    eyebrow: "Step 2",
    title: "The methodological commitment",
    summary:
      "Before any single method, the firm holds a method for judging methods. The Meta-Method is the document that states it: inquiry is only worth publishing when it can be checked, and the firm commits to scoring its own work against that standard. Everything downstream in this guide is that commitment made inspectable.",
    readingMinutes: 8,
    tourNote:
      "You are looking at the prior commitment the firm made — the standard it agreed to be held to before it had results. The methodology explorer is this document turned into a working surface.",
    links: [
      {
        href: "https://github.com/mrquintin/mqtheseuswork/blob/main/THE_META_METHOD.md",
        label: "THE_META_METHOD",
        external: true,
      },
      { href: "/methodology", label: "Methodology explorer" },
    ],
  },
  {
    id: "criteria",
    index: 3,
    eyebrow: "Step 3",
    title: "The five working criteria",
    summary:
      "The Meta-Method resolves into five criteria the firm applies to every method it uses: Progressivity, Severity, Aim-Method Fit, Compressibility, and Domain Sensitivity. The criteria page carries the exact rubric and composite formula — the same one the running scorer uses, checked against code so the page cannot drift from it.",
    readingMinutes: 6,
    tourNote:
      "These five criteria are the rubric. Read them as the test the firm runs on itself: each is a question a method must answer, with the scoring thresholds shown.",
    links: [{ href: "/methodology/criteria", label: "Five-criterion rubric" }],
  },
  {
    id: "empirical",
    index: 4,
    eyebrow: "Step 4",
    title: "The empirical claims the firm has tested",
    summary:
      "The firm has put its headline claim — that logical coherence leaves a geometric signature in embedding space — on a frozen, public benchmark, replicated it across embedding back-ends, and run an ablation against its own method. The benchmark includes results the firm loses on, and the cross-model study reports a negative finding. Read these for what the claims are and how they have actually scored.",
    readingMinutes: 12,
    tourNote:
      "This is the evidence layer. Note that the leaderboard is one the firm can lose on, and that the cross-model and ablation results include negative findings the firm published anyway.",
    links: [
      { href: "/methodology/benchmark/qh", label: "Quintin Hypothesis benchmark" },
      {
        href: "/methodology/benchmark/qh/cross-model",
        label: "Cross-model study",
      },
      {
        href: "/methodology/contradiction_geometry",
        label: "Householder ablation",
      },
    ],
  },
  {
    id: "challenge",
    index: 5,
    eyebrow: "Step 5",
    title: "How to challenge the firm",
    summary:
      "A reader who thinks a conclusion is wrong has a published path to say so. The critique hall of fame carries the severity rubric and every accepted challenge; the response form — the \"Challenge this conclusion\" affordance on any published article — is how a challenge is filed. Severe critiques carry a bounty. This is the part of the firm designed to be attacked.",
    readingMinutes: 3,
    tourNote:
      "You are looking at the adversarial channel. The severity rubric is published before you file, so the bounty is grounded in something concrete rather than the mood of the firm.",
    links: [
      { href: "/critiques", label: "Critique hall of fame" },
      { href: "/post", label: "Articles — the response form lives on each" },
    ],
  },
  {
    id: "replicate",
    index: 6,
    eyebrow: "Step 6",
    title: "How to replicate",
    summary:
      "The empirical claims are either reproducible or they are not. The replication harness is a one-command path: clone the repo, run a make target, and compare your reproducibility envelope against the firm's recorded runs. The page also documents the dataset, the success rubric, and what to do when your numbers differ.",
    readingMinutes: 5,
    tourNote:
      "This is the standing offer the firm makes to be checked. The harness skips models you have no API key for rather than failing, so a researcher who has never spoken to the firm can still run it.",
    links: [{ href: "/methodology/replicate", label: "Replication harness" }],
  },
  {
    id: "subscribe",
    index: 7,
    eyebrow: "Step 7",
    title: "How to subscribe",
    summary:
      "If you want to follow the firm's output — new theses, revisions, retractions — the subscriber form below sends a digest at the cadence you choose. Double opt-in, one-click unsubscribe, no tracking pixels. This is the last stop on the map; it is optional.",
    readingMinutes: 1,
    tourNote:
      "The final stop. Subscribing is optional and changes nothing about your access — every surface in this guide is public.",
    links: [{ href: "#subscribe", label: "Subscriber form" }],
  },
];

/** Step ids on the fast path — the shortest route to "I understand the
 * claim and how I would test it." Skips the commitment essay and the
 * subscribe/replicate housekeeping. */
export const FAST_PATH_STEP_IDS = ["what", "criteria", "empirical", "challenge"] as const;

export function totalReadingMinutes(steps: ReaderGuideStep[] = READER_GUIDE_STEPS): number {
  return steps.reduce((sum, step) => sum + step.readingMinutes, 0);
}

export function fastPathReadingMinutes(
  steps: ReaderGuideStep[] = READER_GUIDE_STEPS,
): number {
  return steps
    .filter((step) => (FAST_PATH_STEP_IDS as readonly string[]).includes(step.id))
    .reduce((sum, step) => sum + step.readingMinutes, 0);
}

// ── Reading-tour state machine ─────────────────────────────────────────

export type TourStatus = "idle" | "active" | "complete" | "dismissed";

export type TourState = {
  status: TourStatus;
  /** Index into READER_GUIDE_STEPS of the current tour stop. */
  stepIndex: number;
};

export const INITIAL_TOUR_STATE: TourState = { status: "idle", stepIndex: 0 };

export type TourAction =
  | { type: "start" }
  | { type: "next" }
  | { type: "prev" }
  | { type: "dismiss" }
  | { type: "restart" };

const LAST_INDEX = READER_GUIDE_STEPS.length - 1;

/**
 * Pure transition function for the tour overlay.
 *
 *   start    — begin the tour at stop 1 (from any non-active status).
 *   next     — advance one stop; from the last stop, finish (complete).
 *   prev     — step back one stop; clamped at the first stop.
 *   dismiss  — close the overlay from anywhere. Dismissing is always
 *              allowed and is not the same as completing.
 *   restart  — re-enter the tour at stop 1 (used after complete/dismiss).
 *
 * `next`/`prev` only do anything while the tour is `active`; a reader
 * who has dismissed or completed must `start`/`restart` first.
 */
export function tourReducer(state: TourState, action: TourAction): TourState {
  switch (action.type) {
    case "start":
    case "restart":
      return { status: "active", stepIndex: 0 };
    case "next":
      if (state.status !== "active") return state;
      if (state.stepIndex >= LAST_INDEX) {
        return { status: "complete", stepIndex: LAST_INDEX };
      }
      return { status: "active", stepIndex: state.stepIndex + 1 };
    case "prev":
      if (state.status !== "active") return state;
      return { status: "active", stepIndex: Math.max(0, state.stepIndex - 1) };
    case "dismiss":
      return { status: "dismissed", stepIndex: state.stepIndex };
    default:
      return state;
  }
}

export function isTourActive(state: TourState): boolean {
  return state.status === "active";
}

export function isTourComplete(state: TourState): boolean {
  return state.status === "complete";
}

export function currentTourStep(state: TourState): ReaderGuideStep | null {
  if (state.status !== "active" && state.status !== "complete") return null;
  return READER_GUIDE_STEPS[state.stepIndex] ?? null;
}

/** "Stop 3 of 7" — the overlay's progress label. */
export function tourProgressLabel(state: TourState): string {
  const stop = Math.min(state.stepIndex + 1, READER_GUIDE_STEPS.length);
  return `Stop ${stop} of ${READER_GUIDE_STEPS.length}`;
}

export type TourRecord = {
  completedAt: string;
  stepsViewed: number;
  steps: string[];
};

/**
 * The exportable "you've completed the tour" record. Returns null unless
 * the tour is actually complete — there is nothing to export from a tour
 * that was dismissed early. The record affects nothing in the product;
 * it exists only so a reader who wants a trace can keep one.
 */
export function exportTourRecord(
  state: TourState,
  now: Date = new Date(),
): TourRecord | null {
  if (state.status !== "complete") return null;
  return {
    completedAt: now.toISOString(),
    stepsViewed: READER_GUIDE_STEPS.length,
    steps: READER_GUIDE_STEPS.map((step) => step.id),
  };
}
